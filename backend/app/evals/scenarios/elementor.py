"""Elementor golden dataset: 5 briefs run through generate → build → validate.

Relocated from the Sprint 5 offline eval (formerly
``tests/test_elementor_skill.py``) and scored instead of just asserted.
"""

from __future__ import annotations

from app.agent.skills.elementor.icons import ALLOWED_ICONS
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
            SectionSpec(type="hero", content={"heading": "Lens & Light", "subheading": "Portrait photography", "cta_text": "Book a shoot", "background_color": "#0d0d0d", "heading_color": "#ffffff"}),
            SectionSpec(type="features", items=[{"title": "Portraits", "text": "Studio & natural light", "icon": "fas fa-camera"}, {"title": "Events", "text": "Weddings & parties", "icon": "fas fa-glass-cheers"}, {"title": "Editorial", "text": "Brand stories", "icon": "fas fa-pen-nib"}]),
            SectionSpec(type="testimonials", items=[{"quote": "Best shoot we've ever had.", "author": "Mia R.", "role": "Bride"}, {"quote": "Professional and creative.", "author": "Sam T.", "role": "Founder"}]),
            SectionSpec(type="contact", content={"heading": "Get in touch", "subheading": "Let's plan your session", "email": "hi@lensandlight.test", "background_color": "#0d0d0d", "heading_color": "#ffffff"}),
        ],
    ),
    "SaaS pricing landing page": PageSpec(
        title="FlowPad",
        sections=[
            SectionSpec(type="hero", content={"heading": "Ship faster with FlowPad", "subheading": "Docs that write themselves", "cta_text": "Start free"}),
            SectionSpec(type="pricing", items=[{"plan_name": "Free", "price": "$0", "tagline": "For side projects", "cta_text": "Start"}, {"plan_name": "Team", "price": "$12", "tagline": "For growing teams", "cta_text": "Try"}, {"plan_name": "Business", "price": "$29", "tagline": "For scaling companies", "cta_text": "Buy"}]),
            SectionSpec(type="faq", items=[{"question": "Can I cancel anytime?", "answer": "Yes, no lock-in contracts."}, {"question": "Is there a free trial?", "answer": "Yes, 14 days on any paid plan."}]),
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
            SectionSpec(type="features", items=[{"title": "Offline", "text": "Works with no signal", "icon": "fas fa-mountain-sun"}, {"title": "Live GPS", "text": "Track your route", "icon": "fas fa-compass"}, {"title": "Share", "text": "Send routes to friends", "icon": "fas fa-route"}]),
            SectionSpec(type="pricing", items=[{"plan_name": "Free", "price": "$0", "cta_text": "Get"}, {"plan_name": "Pro", "price": "$5", "cta_text": "Upgrade"}]),
        ],
    ),
}


def _icon_values(elementor_data) -> list[str]:
    found = []

    def walk(el):
        settings = el.get("settings", {}) if isinstance(el, dict) else {}
        icon = settings.get("selected_icon", {}).get("value") if settings else None
        if icon:
            found.append(icon)
        for child in (el.get("elements", []) if isinstance(el, dict) else []):
            walk(child)

    for el in elementor_data:
        walk(el)
    return found


async def _run(brief: str, spec: PageSpec) -> list[CheckResult]:
    result = await generate_elementor_page(brief, generator=_FakeGenerator(spec))
    errors = validate_elementor_data(result["elementor_data"])
    section_count_ok = 3 <= len(result["sections"]) <= 6
    sections_match = result["sections"] == [s.type for s in spec.sections]
    title_ok = result["title"] == spec.title
    icons = _icon_values(result["elementor_data"])
    # Every icon must be one Elementor's bundled Font Awesome set actually has
    # — an out-of-range value produces PHP warnings and a broken icon live.
    icons_safe = all(icon.split()[-1].removeprefix("fa-") in ALLOWED_ICONS for icon in icons)
    return [
        CheckResult("valid_elementor_data", not errors, weight=2, detail="; ".join(errors)),
        CheckResult("section_count_3_to_6", section_count_ok, weight=1),
        CheckResult("requested_sections_present", sections_match, weight=1),
        CheckResult("title_matches", title_ok, weight=1),
        CheckResult("icons_are_safe", icons_safe, weight=2, detail=str(icons)),
    ]


SCENARIOS = [
    Scenario(name=brief, run=lambda b=brief, s=spec: _run(b, s))
    for brief, spec in _BRIEFS.items()
]
