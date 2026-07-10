"""Elementor skill edge cases (generator mocked).

The 5-brief scored golden dataset moved to
``app/evals/scenarios/elementor.py`` as part of Sprint 8's eval suite — see
``tests/test_evals.py`` for the scored/thresholded version. This file keeps
the non-scenario edge-case tests: defensive section filtering and the
never-write-invalid-data invariant.
"""

from __future__ import annotations

import pytest

from app.agent.skills.elementor.icons import ALLOWED_ICONS, DEFAULT_ICON, safe_icon
from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.skill import (
    ElementorValidationError,
    generate_elementor_page,
)


class FakeGenerator:
    def __init__(self, spec: PageSpec):
        self._spec = spec

    async def generate(self, brief: str) -> PageSpec:
        return self._spec


class PassthroughCopyGenerator:
    """Stand-in for the Gemini copy pass: the fake spec already has its final
    copy, so this just returns the skeleton unchanged."""

    async def fill(self, brief: str, skeleton: PageSpec) -> PageSpec:
        return skeleton


async def test_unknown_section_is_dropped_defensively():
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(type="hero", content={"heading": "H"}),
            SectionSpec.model_construct(type="nonexistent", content={}, items=[]),
        ],
    )
    result = await generate_elementor_page(
        "x", generator=FakeGenerator(spec), copy_generator=PassthroughCopyGenerator()
    )
    assert result["sections"] == ["hero"]  # unknown type filtered out


async def test_invalid_data_is_never_returned(monkeypatch):
    # Force the builder to emit something invalid; the skill must raise, not write.
    import app.agent.skills.elementor.skill as skill_mod

    monkeypatch.setattr(
        skill_mod, "build_page", lambda spec: [{"id": "x", "elType": "widget"}]
    )
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])
    with pytest.raises(ElementorValidationError):
        await generate_elementor_page(
            "x", generator=FakeGenerator(spec), copy_generator=PassthroughCopyGenerator()
        )


# --- Optional image widget (hero/about) -------------------------------


def _find_widgets(el, widget_type: str) -> list[dict]:
    found = []
    if isinstance(el, dict):
        if el.get("widgetType") == widget_type:
            found.append(el)
        for child in el.get("elements", []):
            found.extend(_find_widgets(child, widget_type))
    return found


async def test_hero_image_widget_dropped_when_no_image_resolved():
    # generate_elementor_page never resolves image_prompt (that's images/
    # resolver.py's job, gated behind approval) — an unresolved prompt must
    # never leak an empty/broken image widget into the built page.
    spec = PageSpec(
        title="X",
        sections=[SectionSpec(type="hero", content={"heading": "H", "image_prompt": "a sunrise"})],
    )
    result = await generate_elementor_page(
        "x", generator=FakeGenerator(spec), copy_generator=PassthroughCopyGenerator()
    )
    assert _find_widgets(result["elementor_data"][0], "image") == []
    assert "a sunrise" not in str(result["elementor_data"])  # prompt never leaks as visible text


async def test_hero_image_widget_kept_with_int_id_once_resolved():
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(
                type="hero",
                content={"heading": "H", "image_url": "http://wp.test/1.png", "image_id": "42"},
            )
        ],
    )
    result = await generate_elementor_page(
        "x", generator=FakeGenerator(spec), copy_generator=PassthroughCopyGenerator()
    )
    images = _find_widgets(result["elementor_data"][0], "image")
    assert len(images) == 1
    assert images[0]["settings"]["image"]["url"] == "http://wp.test/1.png"
    assert images[0]["settings"]["image"]["id"] == 42  # token-fill produces a string; builder coerces to int


# --- Icon allowlist (found via live verification: an icon Elementor's ------
# --- bundled Font Awesome 5.15.3 dataset doesn't have breaks the page) -----


def test_safe_icon_accepts_known_icons_in_any_form():
    # Output is always fully "fas fa-<name>" prefixed — Elementor's own
    # parser regex-extracts the name from that exact form (a bare/unprefixed
    # value fails the same way an unknown icon does).
    assert safe_icon("fas fa-camera") == "fas fa-camera"
    assert safe_icon("fa-camera") == "fas fa-camera"
    assert safe_icon("camera") == "fas fa-camera"


def test_safe_icon_falls_back_for_unknown_icons():
    # "mountain-sun" is real Font Awesome 6 but not in Elementor's bundled
    # FA 5.15.3 set — this is the exact icon that broke a live page.
    assert safe_icon("fas fa-mountain-sun") == f"fas fa-{DEFAULT_ICON}"
    assert DEFAULT_ICON in ALLOWED_ICONS


async def test_generated_page_never_contains_an_unsafe_icon():
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(
                type="features",
                items=[
                    {"title": "A", "text": "a", "icon": "fas fa-mountain-sun"},
                    {"title": "B", "text": "b", "icon": "fas fa-camera"},
                ],
            )
        ],
    )
    result = await generate_elementor_page(
        "x", generator=FakeGenerator(spec), copy_generator=PassthroughCopyGenerator()
    )
    blob = str(result["elementor_data"])
    assert "mountain-sun" not in blob
    assert f"'value': 'fas fa-{DEFAULT_ICON}'" in blob
    assert "'value': 'fas fa-camera'" in blob
