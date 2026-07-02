"""Sprint 6 tools: approval gating + the applied paths (deps mocked)."""

from __future__ import annotations

import pytest

import app.agent.skills.content as content_pkg
import app.agent.skills.seo as seo_pkg
import app.agent.skills.theme as theme_pkg
import app.agent.tools.wp_tools as wp_tools
from app.agent.skills.content.schema import PostDraft
from app.agent.skills.seo.schema import SeoMeta
from app.wp.schemas import CliResult, ContentItem, SiteCredentials


@pytest.fixture
def fake_creds(monkeypatch):
    async def _fake(site_slug: str) -> SiteCredentials:
        return SiteCredentials(
            slug=site_slug, base_url="http://wp.test", wp_username="admin",
            wp_app_password="pw", wpcli_transport="local_docker",
        )

    monkeypatch.setattr(wp_tools, "_credentials", _fake)


@pytest.fixture
def guard_creds(monkeypatch):
    async def boom(site_slug):
        raise AssertionError("credentials accessed without approval!")

    monkeypatch.setattr(wp_tools, "_credentials", boom)


class FakeWp:
    meta_written: dict | None = None

    @classmethod
    def from_credentials(cls, creds, **kwargs):
        return cls()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def ensure_categories(self, names):
        return [100 + i for i, _ in enumerate(names)]

    async def ensure_tags(self, names):
        return [200 + i for i, _ in enumerate(names)]

    async def create_post(self, payload):
        return ContentItem(id=55, title=payload.title, status=payload.status)

    async def get_post(self, post_id):
        return ContentItem(id=post_id, title="Existing", status="publish", link="http://wp.test/p")

    async def update_content_meta(self, resource, item_id, meta):
        FakeWp.meta_written = meta
        return ContentItem(id=item_id, title="Existing", status="publish")


class FakeCli:
    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def set_option(self, name, value):
        return CliResult(command=f"opt {name}", exit_code=0)

    async def search_plugin(self, query, *, limit=10):
        return CliResult(command="search", exit_code=0, stdout='[{"slug":"contact-form-7"}]')


# --- gating -------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,args",
    [
        ("wp_publish_post", {"site_slug": "acme", "brief": "a post about hiking"}),
        ("wp_apply_seo", {"site_slug": "acme", "target_id": 1, "subject": "boots"}),
        ("wp_apply_theme", {"site_slug": "acme", "brief": "dark minimal"}),
        ("wp_configure_plugin", {"site_slug": "acme", "option_name": "x", "option_value": "y"}),
    ],
)
async def test_writes_are_gated(guard_creds, tool, args):
    fn = {t.name: t for t in wp_tools.WRITE_TOOLS}[tool]
    result = await fn.ainvoke(args)
    assert result["status"] == "needs_approval"


# --- applied paths ------------------------------------------------------


async def test_publish_post_ensures_terms_and_creates(fake_creds, monkeypatch):
    async def fake_draft(brief):
        return PostDraft(title="Hiking 101", content="<p>go</p>", categories=["Travel"], tags=["hiking"])

    monkeypatch.setattr(content_pkg, "generate_post_draft", fake_draft)
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)

    result = await wp_tools.wp_publish_post.ainvoke(
        {"site_slug": "acme", "brief": "hiking basics", "tags": ["outdoors"], "approved": True}
    )
    assert result["status"] == "applied"
    assert result["post"]["id"] == 55
    assert "Travel" in result["categories"]
    assert "outdoors" in result["tags"] and "hiking" in result["tags"]


async def test_publish_post_schedules_when_publish_at(fake_creds, monkeypatch):
    async def fake_draft(brief):
        return PostDraft(title="T", content="x")

    monkeypatch.setattr(content_pkg, "generate_post_draft", fake_draft)
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)

    result = await wp_tools.wp_publish_post.ainvoke(
        {"site_slug": "acme", "brief": "b", "publish_at": "2026-12-01T09:00:00", "approved": True}
    )
    assert result["post"]["status"] == "future"
    assert result["scheduled_for"] == "2026-12-01T09:00:00"


async def test_apply_seo_writes_provider_meta(fake_creds, monkeypatch):
    async def fake_seo(subject):
        return SeoMeta(title="Best Boots", description="Buy the best boots online")

    monkeypatch.setattr(seo_pkg, "generate_seo", fake_seo)
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)

    result = await wp_tools.wp_apply_seo.ainvoke(
        {"site_slug": "acme", "target_id": 7, "subject": "boots", "approved": True}
    )
    assert result["status"] == "applied"
    assert "_yoast_wpseo_title" in FakeWp.meta_written
    assert "_seo_schema_jsonld" in FakeWp.meta_written


async def test_apply_theme_runs_applier(fake_creds, monkeypatch):
    from app.agent.skills.theme.schema import ThemeSpec

    async def fake_theme(brief):
        return ThemeSpec(footer_text="© X")

    async def fake_apply(cli, spec):
        return [{"step": "color:primary", "ok": True}]

    monkeypatch.setattr(theme_pkg, "generate_theme", fake_theme)
    monkeypatch.setattr(theme_pkg, "apply_theme", fake_apply)
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)

    result = await wp_tools.wp_apply_theme.ainvoke(
        {"site_slug": "acme", "brief": "dark", "approved": True}
    )
    assert result["status"] == "applied"
    assert result["results"][0]["ok"] is True


async def test_search_plugins_is_read_and_recommends(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)
    result = await wp_tools.wp_search_plugins.ainvoke(
        {"site_slug": "acme", "query": "contact form"}
    )
    assert result["status"] == "ok"
    assert result["recommended"]["slug"] == "contact-form-7"


async def test_configure_plugin_sets_option(fake_creds, monkeypatch):
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)
    result = await wp_tools.wp_configure_plugin.ainvoke(
        {"site_slug": "acme", "option_name": "cache_enabled", "option_value": "1", "approved": True}
    )
    assert result["status"] == "applied"
