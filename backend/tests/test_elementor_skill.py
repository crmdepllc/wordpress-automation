"""Eval: 5+ briefs run through the real skill pipeline (generator mocked).

Each scenario stands in for a model output (a PageSpec) and is driven through
generate → build → validate exactly as production would, asserting the result
is valid Elementor data with the requested sections. This is the offline bar
for the Sprint 5 deliverable; true in-editor rendering is the gated integration
eval (tests/integration/test_elementor_render.py).
"""

from __future__ import annotations

import pytest

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.skill import (
    ElementorValidationError,
    generate_elementor_page,
)
from app.agent.skills.elementor.validator import validate_elementor_data


class FakeGenerator:
    def __init__(self, spec: PageSpec):
        self._spec = spec

    async def generate(self, brief: str) -> PageSpec:
        return self._spec


# 5 briefs → the PageSpec a good model would produce for each.
SCENARIOS: dict[str, PageSpec] = {
    "photographer portfolio, dark minimal": PageSpec(
        title="Lens & Light",
        sections=[
            SectionSpec(type="hero", content={"heading": "Lens & Light", "subheading": "Portrait photography", "cta_text": "Book a shoot"}),
            SectionSpec(type="features", items=[{"title": "Portraits", "text": "Studio & natural light"}, {"title": "Events", "text": "Weddings & parties"}, {"title": "Editorial", "text": "Brand stories"}]),
            SectionSpec(type="contact", content={"heading": "Get in touch", "subheading": "Let's plan your session", "email": "hi@lensandlight.test"}),
        ],
    ),
    "SaaS pricing landing page": PageSpec(
        title="FlowPad",
        sections=[
            SectionSpec(type="hero", content={"heading": "Ship faster with FlowPad", "subheading": "Docs that write themselves", "cta_text": "Start free"}),
            SectionSpec(type="pricing", items=[{"plan_name": "Free", "price": "$0", "cta_text": "Start"}, {"plan_name": "Team", "price": "$12", "cta_text": "Try"}, {"plan_name": "Business", "price": "$29", "cta_text": "Buy"}]),
            SectionSpec(type="footer", content={"text": "© FlowPad"}),
        ],
    ),
    "restaurant one-pager": PageSpec(
        title="Riverside Bistro",
        sections=[
            SectionSpec(type="hero", content={"heading": "Riverside Bistro", "subheading": "Seasonal riverside dining", "cta_text": "Reserve a table"}),
            SectionSpec(type="features", items=[{"title": "Brunch", "text": "Weekends 9–2"}, {"title": "Dinner", "text": "Nightly from 5"}]),
            SectionSpec(type="contact", content={"heading": "Find us", "subheading": "On the river", "email": "eat@riverside.test"}),
        ],
    ),
    "agency site": PageSpec(
        title="North Studio",
        sections=[
            SectionSpec(type="hero", content={"heading": "We build brands", "subheading": "Design & strategy", "cta_text": "Work with us"}),
            SectionSpec(type="features", items=[{"title": "Branding", "text": "Identity systems"}, {"title": "Web", "text": "Sites that convert"}, {"title": "Content", "text": "Story-led"}]),
            SectionSpec(type="footer", content={"text": "© North Studio"}),
        ],
    ),
    "mobile app landing": PageSpec(
        title="Trailmark",
        sections=[
            SectionSpec(type="hero", content={"heading": "Never lose the trail", "subheading": "Offline hiking maps", "cta_text": "Download"}),
            SectionSpec(type="features", items=[{"title": "Offline", "text": "Works with no signal"}, {"title": "Live GPS", "text": "Track your route"}, {"title": "Share", "text": "Send routes to friends"}]),
            SectionSpec(type="pricing", items=[{"plan_name": "Free", "price": "$0", "cta_text": "Get"}, {"plan_name": "Pro", "price": "$5", "cta_text": "Upgrade"}]),
        ],
    ),
}


@pytest.mark.parametrize("brief", list(SCENARIOS))
async def test_brief_produces_valid_page(brief):
    spec = SCENARIOS[brief]
    result = await generate_elementor_page(brief, generator=FakeGenerator(spec))

    # 3–4 sections, all requested types present, and structurally valid.
    assert 3 <= len(result["sections"]) <= 4
    assert result["sections"] == [s.type for s in spec.sections]
    assert validate_elementor_data(result["elementor_data"]) == []
    assert result["title"] == spec.title


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
