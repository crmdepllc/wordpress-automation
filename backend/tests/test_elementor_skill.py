"""Elementor skill edge cases (generator mocked).

The 5-brief scored golden dataset moved to
``app/evals/scenarios/elementor.py`` as part of Sprint 8's eval suite — see
``tests/test_evals.py`` for the scored/thresholded version. This file keeps
the non-scenario edge-case tests: defensive section filtering and the
never-write-invalid-data invariant.
"""

from __future__ import annotations

import pytest

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
