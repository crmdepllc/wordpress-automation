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


async def test_unknown_section_is_dropped_defensively():
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(type="hero", content={"heading": "H"}),
            SectionSpec.model_construct(type="nonexistent", content={}, items=[]),
        ],
    )
    result = await generate_elementor_page("x", generator=FakeGenerator(spec))
    assert result["sections"] == ["hero"]  # unknown type filtered out


async def test_invalid_data_is_never_returned(monkeypatch):
    # Force the builder to emit something invalid; the skill must raise, not write.
    import app.agent.skills.elementor.skill as skill_mod

    monkeypatch.setattr(
        skill_mod, "build_page", lambda spec: [{"id": "x", "elType": "widget"}]
    )
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero")])
    with pytest.raises(ElementorValidationError):
        await generate_elementor_page("x", generator=FakeGenerator(spec))


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
    result = await generate_elementor_page("x", generator=FakeGenerator(spec))
    blob = str(result["elementor_data"])
    assert "mountain-sun" not in blob
    assert f"'value': 'fas fa-{DEFAULT_ICON}'" in blob
    assert "'value': 'fas fa-camera'" in blob
