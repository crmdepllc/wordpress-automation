"""Elementor golden dataset: 5 briefs run through generate → build → validate.

Relocated from the Sprint 5 offline eval (formerly
``tests/test_elementor_skill.py``) and scored instead of just asserted.
"""

from __future__ import annotations

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.skill import generate_elementor_page
from app.agent.skills.elementor.validator import validate_elementor_data
from app.evals.scoring import CheckResult, Scenario


class _FakeGenerator:
    def __init__(self, spec: PageSpec):
        self._spec = spec

    async def generate(self, brief: str) -> PageSpec:
        return self._spec


_BRIEFS: dict[str, PageSpec] = {
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


async def _run(brief: str, spec: PageSpec) -> list[CheckResult]:
    result = await generate_elementor_page(brief, generator=_FakeGenerator(spec))
    errors = validate_elementor_data(result["elementor_data"])
    section_count_ok = 3 <= len(result["sections"]) <= 4
    sections_match = result["sections"] == [s.type for s in spec.sections]
    title_ok = result["title"] == spec.title
    return [
        CheckResult("valid_elementor_data", not errors, weight=2, detail="; ".join(errors)),
        CheckResult("section_count_3_to_4", section_count_ok, weight=1),
        CheckResult("requested_sections_present", sections_match, weight=1),
        CheckResult("title_matches", title_ok, weight=1),
    ]


SCENARIOS = [
    Scenario(name=brief, run=lambda b=brief, s=spec: _run(b, s))
    for brief, spec in _BRIEFS.items()
]
