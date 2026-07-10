"""Tests for the wp_create_elementor_page tool — gating + the write path."""

from __future__ import annotations

import pytest

import app.agent.skills.elementor as elementor_pkg
import app.agent.skills.images as images_pkg
import app.agent.skills.images.resolver as images_resolver_mod
import app.agent.tools.wp_tools as wp_tools
from app.agent.skills.elementor import ElementorValidationError
from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.wp.schemas import CliResult, ContentItem, MediaItem, SiteCredentials


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
    uploaded: list[dict] | None = None

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

    async def upload_media(self, filename, content, mime_type):
        FakeWp.uploaded = (FakeWp.uploaded or []) + [{"filename": filename, "mime_type": mime_type}]
        media_id = len(FakeWp.uploaded)
        return MediaItem(id=media_id, source_url=f"http://wp.test/media/{media_id}.png", mime_type=mime_type)


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
    spec = PageSpec(
        title="Acme",
        sections=[SectionSpec(type="hero"), SectionSpec(type="features")],
    )

    async def fake_generate_page_spec(brief):
        return spec

    async def fake_resolve_images(spec, wp, **kwargs):
        return spec  # no image_prompt set on this spec — nothing to resolve

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", fake_generate_page_spec)
    monkeypatch.setattr(images_pkg, "resolve_images", fake_resolve_images)
    monkeypatch.setattr(
        elementor_pkg,
        "build_and_validate",
        lambda s: [{"id": "s", "elType": "section", "elements": []}],
    )
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
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])

    async def fake_generate_page_spec(brief):
        return spec

    async def fake_resolve_images(spec, wp, **kwargs):
        return spec

    def bad_build(spec):
        raise ElementorValidationError(["boom: bad nesting"])

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", fake_generate_page_spec)
    monkeypatch.setattr(images_pkg, "resolve_images", fake_resolve_images)
    monkeypatch.setattr(elementor_pkg, "build_and_validate", bad_build)

    # The REST client legitimately opens up front now (image resolution needs
    # it) — what must never happen is the actual page write.
    class NoWrite(FakeWp):
        async def create_elementor_page(self, title, data, *, status="draft"):
            raise AssertionError("attempted to write invalid Elementor data!")

    monkeypatch.setattr(wp_tools, "WordPressRestClient", NoWrite)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "x", "approved": True}
    )
    assert result["status"] == "error"
    assert result["stage"] == "validation"
    assert result["errors"] == ["boom: bad nesting"]


async def test_resolves_and_uploads_image_when_prompt_set(fake_creds, monkeypatch):
    """End-to-end through the real ``resolve_images`` (not mocked) — only the
    Gemini image generator and the WP client are fakes."""
    FakeWp.uploaded = None  # class-level state; isolate from other tests
    spec = PageSpec(
        title="Studio",
        sections=[
            SectionSpec(type="hero", content={"image_prompt": "a bright modern studio"}),
            SectionSpec(type="features"),
        ],
    )

    async def fake_generate_page_spec(brief):
        return spec

    class FakeImageGenerator:
        async def generate(self, prompt: str) -> bytes:
            assert prompt == "a bright modern studio"
            return b"fake-png-bytes"

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", fake_generate_page_spec)
    # resolve_images (not mocked here) resolves build_image_generator against
    # its own module's binding, not the images package re-export — patch it there.
    monkeypatch.setattr(
        images_resolver_mod, "build_image_generator", lambda: FakeImageGenerator()
    )
    monkeypatch.setattr(
        elementor_pkg,
        "build_and_validate",
        lambda s: [{"id": "s", "elType": "section", "elements": []}] * len(s.sections),
    )
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "a design studio site", "approved": True}
    )
    assert result["status"] == "applied"
    assert len(FakeWp.uploaded) == 1
    assert FakeWp.uploaded[0]["mime_type"] == "image/png"
    assert FakeWp.uploaded[0]["filename"].startswith("hero-")
