"""Tests for the wp_create_elementor_page tool — gating + the write path."""

from __future__ import annotations

import pytest

import app.agent.skills.elementor as elementor_pkg
import app.agent.tools.wp_tools as wp_tools
from app.agent.skills.elementor import ElementorValidationError
from app.wp.schemas import CliResult, ContentItem, SiteCredentials


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
    created: dict | None = None

    @classmethod
    def from_credentials(cls, creds, **kwargs):
        return cls()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def create_elementor_page(self, title, data, *, status="draft"):
        FakeWp.created = {"title": title, "n": len(data), "status": status}
        return ContentItem(id=123, title=title, status=status)


class FakeCli:
    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def flush_css(self):
        return CliResult(command="elementor flush-css", exit_code=0, stdout="ok")


async def test_gated_without_approval(monkeypatch):
    async def boom(site_slug):
        raise AssertionError("credentials accessed without approval!")

    monkeypatch.setattr(wp_tools, "_credentials", boom)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "a photographer site"}
    )
    assert result["status"] == "needs_approval"
    assert result["action"] == "create Elementor page"


async def test_applies_and_flushes_when_approved(fake_creds, monkeypatch):
    async def fake_generate(brief):
        return {
            "title": "Acme",
            "elementor_data": [{"id": "s", "elType": "section", "elements": []}],
            "sections": ["hero", "features"],
        }

    monkeypatch.setattr(elementor_pkg, "generate_elementor_page", fake_generate)
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "a landing page", "approved": True}
    )
    assert result["status"] == "applied"
    assert result["page"]["id"] == 123
    assert result["sections"] == ["hero", "features"]
    assert result["css_flushed"] is True
    assert FakeWp.created["title"] == "Acme"


async def test_validation_failure_does_not_write(fake_creds, monkeypatch):
    async def bad_generate(brief):
        raise ElementorValidationError(["boom: bad nesting"])

    monkeypatch.setattr(elementor_pkg, "generate_elementor_page", bad_generate)

    # If it tried to write, this would blow up — prove it doesn't.
    class NoWrite:
        @classmethod
        def from_credentials(cls, creds, **kwargs):
            raise AssertionError("attempted to write invalid Elementor data!")

    monkeypatch.setattr(wp_tools, "WordPressRestClient", NoWrite)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "x", "approved": True}
    )
    assert result["status"] == "error"
    assert result["stage"] == "validation"
    assert result["errors"] == ["boom: bad nesting"]
