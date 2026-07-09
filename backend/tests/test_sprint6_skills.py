"""Unit tests for the Sprint 6 skill logic (generators mocked)."""

from __future__ import annotations

import json

from app.agent.skills.content.generator import LLMContentGenerator
from app.agent.skills.content.schema import PostDraft
from app.agent.skills.plugins import recommend_plugin
from app.agent.skills.seo.generator import LLMSeoGenerator
from app.agent.skills.seo.json_ld import build_json_ld
from app.agent.skills.seo.providers import meta_keys
from app.agent.skills.seo.schema import SeoMeta
from app.agent.skills.seo.skill import seo_to_meta
from app.agent.skills.theme.applier import apply_theme
from app.agent.skills.theme.schema import ThemeSpec
from app.wp.schemas import CliResult


class FakeStructuredLLM:
    """Stand-in for a with_structured_output model."""

    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return self._result


# --- SEO ----------------------------------------------------------------


def test_provider_meta_keys():
    assert meta_keys("yoast")["title"] == "_yoast_wpseo_title"
    assert meta_keys("rankmath")["description"] == "rank_math_description"
    assert meta_keys("unknown") == meta_keys("yoast")  # fallback


def test_json_ld_article_has_headline():
    seo = SeoMeta(title="T", description="D", schema_type="Article")
    ld = build_json_ld(seo, name="Acme", url="http://acme.test")
    assert ld["@type"] == "Article"
    assert ld["headline"] == "T"
    assert ld["@context"] == "https://schema.org"


def test_json_ld_organization_has_no_headline():
    seo = SeoMeta(title="T", description="D", schema_type="Organization")
    assert "headline" not in build_json_ld(seo, name="Acme", url="http://acme.test")


def test_seo_to_meta_shape():
    seo = SeoMeta(title="Best Boots", description="Buy boots", schema_type="Product")
    meta = seo_to_meta(seo, provider="yoast", name="Boots", url="http://x.test")
    assert meta["_yoast_wpseo_title"] == "Best Boots"
    assert json.loads(meta["_seo_schema_jsonld"])["@type"] == "Product"


async def test_seo_generator_parses_model_output():
    seo = SeoMeta(title="Gen", description="Desc")
    result = await LLMSeoGenerator(llm=FakeStructuredLLM(seo)).generate("a page")
    assert result.title == "Gen"


# --- Content ------------------------------------------------------------


async def test_content_generator_returns_draft():
    draft = PostDraft(title="Hi", content="<p>x</p>", categories=["News"], tags=["a"])
    result = await LLMContentGenerator(llm=FakeStructuredLLM(draft)).generate("brief")
    assert result.title == "Hi"
    assert result.categories == ["News"]


# --- Theme --------------------------------------------------------------


class RecordingCli:
    """Records WP-CLI calls the applier makes; simulates an active kit."""

    def __init__(self):
        self.theme_mods: dict[str, str] = {}
        self.options: dict[str, str] = {}
        self.kit_meta: str | None = None

    async def set_theme_mod(self, name, value):
        self.theme_mods[name] = value
        return CliResult(command=f"mod {name}", exit_code=0)

    async def set_option(self, name, value):
        self.options[name] = value
        return CliResult(command=f"opt {name}", exit_code=0)

    async def get_option(self, name):
        return CliResult(command="get", exit_code=0, stdout="7")  # active kit id

    async def get_post_meta(self, post_id, key):
        return CliResult(command="metaget", exit_code=0, stdout="{}")

    async def update_post_meta(self, post_id, key, value, *, as_json=False):
        self.kit_meta = value
        self.kit_meta_as_json = as_json
        return CliResult(command="metaset", exit_code=0)


async def test_apply_theme_sets_mods_and_kit():
    cli = RecordingCli()
    spec = ThemeSpec(footer_text="© Acme")
    results = await apply_theme(cli, spec)  # type: ignore[arg-type]

    # A theme mod per palette color + fonts were set.
    assert cli.theme_mods["wpa_color_primary"] == spec.palette.primary
    assert cli.theme_mods["wpa_font_heading"] == spec.fonts.heading
    assert cli.options["wpa_footer_text"] == "© Acme"
    # Elementor kit colors merged in and written back.
    assert cli.kit_meta is not None
    assert "system_colors" in json.loads(cli.kit_meta)
    assert any(r["step"] == "elementor_kit_colors" and r["ok"] for r in results)
    # Must be written as a real PHP array (WP-CLI --format=json), not a plain
    # JSON string — otherwise Elementor's Controls_Stack fatals trying to use
    # a string as an array (found via live verification against a real site).
    assert cli.kit_meta_as_json is True


# --- Plugins ------------------------------------------------------------


def test_recommend_plugin_maps_intent():
    assert recommend_plugin("we need caching")["slug"] == "w3-total-cache"
    assert recommend_plugin("add a contact form")["slug"] == "contact-form-7"
    assert recommend_plugin("something obscure") is None
