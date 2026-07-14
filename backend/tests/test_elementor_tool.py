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
    """Defaults to "everything already active" so tests that don't care about
    the stack check aren't forced to mock it — override per-test via subclass
    or monkeypatch when a test needs a different stack state."""

    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def flush_css(self):
        return CliResult(command="elementor flush-css", exit_code=0, stdout="ok")

    async def plugin_is_active(self, slug):
        return CliResult(command=f"plugin is-active {slug}", exit_code=0)

    async def plugin_is_installed(self, slug):
        return CliResult(command=f"plugin is-installed {slug}", exit_code=0)

    async def activate_plugin(self, slug):
        return CliResult(command=f"plugin activate {slug}", exit_code=0)

    async def install_plugin(self, slug, *, activate=True):
        return CliResult(command=f"plugin install {slug}", exit_code=0)

    async def theme_is_active(self, slug):
        return CliResult(command=f"theme is-active {slug}", exit_code=0)

    async def theme_is_installed(self, slug):
        return CliResult(command=f"theme is-installed {slug}", exit_code=0)

    async def activate_theme(self, slug):
        return CliResult(command=f"theme activate {slug}", exit_code=0)

    async def install_theme(self, slug, *, activate=True):
        return CliResult(command=f"theme install {slug}", exit_code=0)


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
    # Stack check ran (default FakeCli: everything already active) and is reported.
    assert {i["name"]: i["status"] for i in result["stack_check"]} == {
        "astra": "already_active",
        "elementor": "already_active",
        "royal-elementor-addons": "already_active",
        "elementskit-lite": "already_active",
    }


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
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)

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


async def test_page_still_creates_when_image_generation_fails(fake_creds, monkeypatch):
    """Real incident: a Gemini quota error must degrade to 'no image for this
    section', not abort the whole page write — see progress-tracker.md."""
    FakeWp.uploaded = None
    spec = PageSpec(
        title="Studio",
        sections=[SectionSpec(type="hero", content={"image_prompt": "a bright modern studio"})],
    )

    async def fake_generate_page_spec(brief):
        return spec

    class BrokenImageGenerator:
        async def generate(self, prompt: str) -> bytes:
            raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", fake_generate_page_spec)
    monkeypatch.setattr(
        images_resolver_mod, "build_image_generator", lambda: BrokenImageGenerator()
    )
    monkeypatch.setattr(
        elementor_pkg,
        "build_and_validate",
        lambda s: [{"id": "s", "elType": "section", "elements": []}],
    )
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    monkeypatch.setattr(wp_tools, "WpCli", FakeCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "a design studio site", "approved": True}
    )
    assert result["status"] == "applied"  # page still gets created
    assert FakeWp.uploaded is None  # upload was never reached


# --- Required theme/plugin stack check ------------------------------------


def _stack_ready(spec):
    async def fake_generate_page_spec(brief):
        return spec

    return fake_generate_page_spec


async def _passthrough_resolve_images(spec, wp, **kwargs):
    return spec


async def test_stack_check_installs_whatever_is_missing(fake_creds, monkeypatch):
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])

    class PartiallySetUpCli(FakeCli):
        """Astra installed-but-inactive; Royal Addons missing entirely; the
        rest already active."""

        async def theme_is_active(self, slug):
            return CliResult(command="x", exit_code=1)  # not active

        async def theme_is_installed(self, slug):
            return CliResult(command="x", exit_code=0)  # but installed

        async def plugin_is_active(self, slug):
            if slug == "royal-elementor-addons":
                return CliResult(command="x", exit_code=1)
            return CliResult(command="x", exit_code=0)

        async def plugin_is_installed(self, slug):
            if slug == "royal-elementor-addons":
                return CliResult(command="x", exit_code=1)  # not installed either
            return CliResult(command="x", exit_code=0)

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", _stack_ready(spec))
    monkeypatch.setattr(images_pkg, "resolve_images", _passthrough_resolve_images)
    monkeypatch.setattr(
        elementor_pkg, "build_and_validate", lambda s: [{"id": "s", "elType": "section", "elements": []}]
    )
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    monkeypatch.setattr(wp_tools, "WpCli", PartiallySetUpCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "x", "approved": True}
    )
    assert result["status"] == "applied"
    by_name = {i["name"]: i["status"] for i in result["stack_check"]}
    assert by_name["astra"] == "activated"  # installed but inactive -> just activate
    assert by_name["royal-elementor-addons"] == "installed"  # missing entirely -> install
    assert by_name["elementor"] == "already_active"
    assert by_name["elementskit-lite"] == "already_active"


async def test_elementor_missing_aborts_page_creation(fake_creds, monkeypatch):
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])

    class NoElementorCli(FakeCli):
        async def plugin_is_active(self, slug):
            if slug == "elementor":
                return CliResult(command="x", exit_code=1)
            return CliResult(command="x", exit_code=0)

        async def plugin_is_installed(self, slug):
            return CliResult(command="x", exit_code=1)  # not installed either

        async def install_plugin(self, slug, *, activate=True):
            return CliResult(command="x", exit_code=1, stderr="could not resolve host")

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", _stack_ready(spec))

    class NoWrite(FakeWp):
        async def create_elementor_page(self, title, data, *, status="draft"):
            raise AssertionError("must not write a page when Elementor is unavailable!")

    monkeypatch.setattr(wp_tools, "WordPressRestClient", NoWrite)
    monkeypatch.setattr(wp_tools, "WpCli", NoElementorCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "x", "approved": True}
    )
    assert result["status"] == "error"
    assert result["stage"] == "stack_check"
    assert "elementor" in result["errors"][0]


async def test_optional_plugin_failure_does_not_block_page_creation(fake_creds, monkeypatch):
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])

    class FlakyRoyalAddonsCli(FakeCli):
        async def plugin_is_active(self, slug):
            if slug == "royal-elementor-addons":
                return CliResult(command="x", exit_code=1)
            return CliResult(command="x", exit_code=0)

        async def plugin_is_installed(self, slug):
            if slug == "royal-elementor-addons":
                return CliResult(command="x", exit_code=1)
            return CliResult(command="x", exit_code=0)

        async def install_plugin(self, slug, *, activate=True):
            if slug == "royal-elementor-addons":
                return CliResult(command="x", exit_code=1, stderr="plugin not found")
            return CliResult(command="x", exit_code=0)

    monkeypatch.setattr(elementor_pkg, "generate_page_spec", _stack_ready(spec))
    monkeypatch.setattr(images_pkg, "resolve_images", _passthrough_resolve_images)
    monkeypatch.setattr(
        elementor_pkg, "build_and_validate", lambda s: [{"id": "s", "elType": "section", "elements": []}]
    )
    monkeypatch.setattr(wp_tools, "WordPressRestClient", FakeWp)
    monkeypatch.setattr(wp_tools, "WpCli", FlakyRoyalAddonsCli)

    result = await wp_tools.wp_create_elementor_page.ainvoke(
        {"site_slug": "acme", "brief": "x", "approved": True}
    )
    assert result["status"] == "applied"  # page still gets created
    by_name = {i["name"]: i["status"] for i in result["stack_check"]}
    assert by_name["royal-elementor-addons"] == "failed"
