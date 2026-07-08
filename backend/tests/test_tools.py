"""Unit tests for the typed WP tools — especially the approval gate."""

from __future__ import annotations

import pytest

import app.agent.tools.wp_tools as wp_tools
from app.agent.tools import wp_tools as tools_mod
from app.agent.wp_agent import run_approved
from app.wp.schemas import CliResult, ContentItem, MenuItem, MenuItemEntry, SiteCredentials


@pytest.fixture
def fake_creds(monkeypatch):
    async def _fake(site_slug: str) -> SiteCredentials:
        return SiteCredentials(
            slug=site_slug,
            base_url="http://wp.test",
            wp_username="admin",
            wp_app_password="pw",
            wpcli_transport="local_docker",
        )

    monkeypatch.setattr(wp_tools, "_credentials", _fake)


class FakeWp:
    """Stand-in REST client supporting the async-context-manager protocol."""

    last_created: dict | None = None

    @classmethod
    def from_credentials(cls, creds, **kwargs):
        return cls()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def list_pages(self, per_page=20):
        return [ContentItem(id=1, title="Home", status="publish")]

    async def create_page(self, payload):
        FakeWp.last_created = payload.model_dump()
        return ContentItem(id=99, title=payload.title, status=payload.status)


class FakeCli:
    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def install_plugin(self, slug, *, activate=True):
        return CliResult(command=f"plugin install {slug}", exit_code=0, stdout="Success")


# --- The approval gate ---------------------------------------------------


async def test_create_page_without_approval_is_gated(monkeypatch):
    # _credentials must NOT be called when a write is unapproved.
    async def boom(site_slug):
        raise AssertionError("credentials accessed without approval!")

    monkeypatch.setattr(wp_tools, "_credentials", boom)

    result = await wp_tools.wp_create_page.ainvoke(
        {"site_slug": "acme", "title": "Home"}
    )
    assert result["status"] == "needs_approval"
    assert result["action"] == "create page"
    assert result["preview"]["title"] == "Home"


async def test_install_plugin_without_approval_is_gated(monkeypatch):
    async def boom(site_slug):
        raise AssertionError("credentials accessed without approval!")

    monkeypatch.setattr(wp_tools, "_credentials", boom)

    result = await wp_tools.wp_install_plugin.ainvoke(
        {"site_slug": "acme", "plugin_slug": "elementor"}
    )
    assert result["status"] == "needs_approval"
    assert result["preview"]["plugin"] == "elementor"


# --- Approved writes apply ----------------------------------------------


async def test_create_page_applies_when_approved(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    result = await wp_tools.wp_create_page.ainvoke(
        {"site_slug": "acme", "title": "Home", "status": "publish", "approved": True}
    )
    assert result["status"] == "applied"
    assert result["page"]["id"] == 99
    assert FakeWp.last_created["title"] == "Home"


async def test_run_approved_injects_approval(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    # run_approved is the only path that flips approved on; caller omits it.
    result = await run_approved("wp_create_page", {"site_slug": "acme", "title": "X"})
    assert result["status"] == "applied"


async def test_install_plugin_applies_when_approved(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)
    result = await wp_tools.wp_install_plugin.ainvoke(
        {"site_slug": "acme", "plugin_slug": "elementor", "approved": True}
    )
    assert result["status"] == "applied"
    assert result["result"]["exit_code"] == 0


# --- Read tools are ungated ---------------------------------------------


async def test_list_pages_reads_without_approval(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    result = await wp_tools.wp_list_pages.ainvoke({"site_slug": "acme"})
    assert result["status"] == "ok"
    assert result["pages"][0]["title"] == "Home"


def test_tool_schemas_have_site_slug():
    # Every tool exposes a typed schema including site_slug.
    for tool in tools_mod.WP_TOOLS:
        assert "site_slug" in tool.args_schema.model_json_schema()["properties"]


# --- wp_assemble_menu (Sprint 7) -----------------------------------------


class FakeMenuWp:
    """Stand-in REST client for the menu-assembly tool."""

    created_items: list[dict] | None = None

    @classmethod
    def from_credentials(cls, creds, **kwargs):
        return cls()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def create_menu(self, name):
        return MenuItem(id=5, name=name, slug="main")

    async def get_page(self, page_id):
        return ContentItem(id=page_id, title=f"Page {page_id}", status="publish")

    async def create_menu_item(self, menu_id, *, page_id, title, menu_order=0):
        item = {"menu_id": menu_id, "page_id": page_id, "title": title, "order": menu_order}
        FakeMenuWp.created_items = (FakeMenuWp.created_items or []) + [item]
        return MenuItemEntry(id=100 + page_id, title=title, object_id=page_id)


async def test_assemble_menu_without_approval_is_gated(monkeypatch):
    async def boom(site_slug):
        raise AssertionError("credentials accessed without approval!")

    monkeypatch.setattr(wp_tools, "_credentials", boom)

    result = await wp_tools.wp_assemble_menu.ainvoke(
        {"site_slug": "acme", "menu_name": "Main", "page_refs": [1, 2]}
    )
    assert result["status"] == "needs_approval"
    assert result["preview"]["menu"] == "Main"


async def test_assemble_menu_applies_when_approved(fake_creds, monkeypatch):
    FakeMenuWp.created_items = None
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeMenuWp)
    result = await wp_tools.wp_assemble_menu.ainvoke(
        {
            "site_slug": "acme",
            "menu_name": "Main",
            "page_refs": [1, 2],
            "approved": True,
        }
    )
    assert result["status"] == "applied"
    assert result["menu"]["id"] == 5
    assert len(result["items"]) == 2
    assert FakeMenuWp.created_items[0]["page_id"] == 1
    assert FakeMenuWp.created_items[1]["order"] == 1


async def test_assemble_menu_accepts_resolved_ref_values(fake_creds, monkeypatch):
    # By execution time, $ref placeholders have already been resolved to real
    # ints (graph.resolve_refs) — the tool just needs to accept int-like input.
    FakeMenuWp.created_items = None
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeMenuWp)
    result = await run_approved(
        "wp_assemble_menu",
        {"site_slug": "acme", "menu_name": "Main", "page_refs": [42]},
    )
    assert result["status"] == "applied"
    assert FakeMenuWp.created_items[0]["page_id"] == 42
