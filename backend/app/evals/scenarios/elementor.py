"""Elementor golden dataset: 6 briefs run through generate → build → validate.

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
            SectionSpec(type="hero", content={"heading": "Lens & Light", "subheading": "Portrait photography", "cta_text": "Book a shoot", "background_color": "#0d0d0d", "heading_color": "#ffffff", "accent_color": "#c9a15a"}),
            SectionSpec(type="features", content={"heading": "What I shoot", "accent_color": "#c9a15a"}, items=[{"title": "Portraits", "text": "Studio & natural light", "icon": "fas fa-camera"}, {"title": "Events", "text": "Weddings & parties", "icon": "fas fa-glass-cheers"}, {"title": "Editorial", "text": "Brand stories", "icon": "fas fa-pen-nib"}]),
            SectionSpec(type="testimonials", content={"heading": "Kind words", "accent_color": "#c9a15a"}, items=[{"quote": "Best shoot we've ever had.", "author": "Mia R.", "role": "Bride"}, {"quote": "Professional and creative.", "author": "Sam T.", "role": "Founder"}]),
            SectionSpec(type="contact", content={"heading": "Get in touch", "subheading": "Let's plan your session", "email": "hi@lensandlight.test", "background_color": "#0d0d0d", "heading_color": "#ffffff", "accent_color": "#c9a15a"}),
        ],
    ),
    "SaaS pricing landing page": PageSpec(
        title="FlowPad",
        sections=[
            SectionSpec(type="hero", content={"heading": "Ship faster with FlowPad", "subheading": "Docs that write themselves", "cta_text": "Start free", "accent_color": "#2d6cdf"}),
            SectionSpec(type="pricing", content={"heading": "Plans for every team", "accent_color": "#2d6cdf"}, items=[{"plan_name": "Free", "price": "$0", "tagline": "For side projects", "cta_text": "Start"}, {"plan_name": "Team", "price": "$12", "tagline": "For growing teams", "cta_text": "Try"}, {"plan_name": "Business", "price": "$29", "tagline": "For scaling companies", "cta_text": "Buy"}]),
            SectionSpec(type="faq", content={"heading": "Questions", "accent_color": "#2d6cdf"}, items=[{"question": "Can I cancel anytime?", "answer": "Yes, no lock-in contracts."}, {"question": "Is there a free trial?", "answer": "Yes, 14 days on any paid plan."}]),
            SectionSpec(type="footer", content={"tagline": "FlowPad", "accent_color": "#2d6cdf"}, items=[{"column_title": "Product", "column_text": "Pricing\nDocs"}, {"column_title": "Legal", "column_text": "© FlowPad"}]),
        ],
    ),
    "restaurant one-pager": PageSpec(
        title="Riverside Bistro",
        sections=[
            SectionSpec(type="hero", content={"heading": "Riverside Bistro", "subheading": "Seasonal riverside dining", "cta_text": "Reserve a table"}),
            SectionSpec(type="features", content={"heading": "Hours"}, items=[{"title": "Brunch", "text": "Weekends 9–2"}, {"title": "Dinner", "text": "Nightly from 5"}]),
            SectionSpec(type="contact", content={"heading": "Find us", "subheading": "On the river", "email": "eat@riverside.test"}),
        ],
    ),
    "agency site": PageSpec(
        title="North Studio",
        sections=[
            SectionSpec(type="hero", content={"heading": "We build brands", "subheading": "Design & strategy", "cta_text": "Work with us"}),
            SectionSpec(type="features", content={"heading": "What we do"}, items=[{"title": "Branding", "text": "Identity systems"}, {"title": "Web", "text": "Sites that convert"}, {"title": "Content", "text": "Story-led"}]),
            SectionSpec(type="footer", content={"tagline": "North Studio"}, items=[{"column_title": "Studio", "column_text": "© North Studio"}]),
        ],
    ),
    "mobile app landing": PageSpec(
        title="Trailmark",
        sections=[
            SectionSpec(type="hero", content={"heading": "Never lose the trail", "subheading": "Offline hiking maps", "cta_text": "Download"}),
            SectionSpec(type="features", content={"heading": "Built for the backcountry"}, items=[{"title": "Offline", "text": "Works with no signal", "icon": "fas fa-mountain-sun"}, {"title": "Live GPS", "text": "Track your route", "icon": "fas fa-compass"}, {"title": "Share", "text": "Send routes to friends", "icon": "fas fa-route"}]),
            SectionSpec(type="pricing", content={"heading": "Choose your plan"}, items=[{"plan_name": "Free", "price": "$0", "cta_text": "Get"}, {"plan_name": "Pro", "price": "$5", "cta_text": "Upgrade"}]),
        ],
    ),
    "notary and mobile signing service": PageSpec(
        title="Colibri Notary Services",
        sections=[
            SectionSpec(type="hero", content={"eyebrow": "Colibri Notary Services LLC", "heading": "Mobile & Online Notary Services", "subheading": "Real estate closings, loan signings, and estate planning", "cta_text": "Schedule an appointment", "accent_color": "#7a1f2b"}),
            SectionSpec(type="about", content={"eyebrow": "About", "heading": "Meet Your Notary", "text": "15 years of experience bringing precision and confidentiality to every appointment.", "cta_text": "Get in touch", "accent_color": "#7a1f2b"}),
            SectionSpec(type="features", content={"eyebrow": "Services", "heading": "Services We Provide", "accent_color": "#7a1f2b"}, items=[{"title": "Mobile Notary", "text": "We come to you, day or night", "icon": "fas fa-car"}, {"title": "Loan Signings", "text": "Real estate and refinance documents", "icon": "fas fa-briefcase"}, {"title": "Remote Online Notary", "text": "Secure video notarization", "icon": "fas fa-laptop-code"}]),
            SectionSpec(type="badges", content={"heading": "Certified & Trusted", "accent_color": "#7a1f2b"}, items=[{"label": "NNA Certified", "icon": "fas fa-certificate"}, {"label": "Background Screened", "icon": "fas fa-shield-alt"}, {"label": "Bonded & Insured", "icon": "fas fa-award"}]),
            SectionSpec(type="testimonials", content={"heading": "Reviews From Clients", "background_color": "#1a1a1a", "heading_color": "#ffffff", "accent_color": "#7a1f2b"}, items=[{"quote": "Efficient and professional.", "author": "Rod G.", "role": "Client"}, {"quote": "Great communication and quality of service.", "author": "Krista N.", "role": "Client"}]),
            SectionSpec(type="footer", content={"tagline": "Colibri Notary Services LLC", "accent_color": "#7a1f2b"}, items=[{"column_title": "Services", "column_text": "Mobile Notary\nLoan Signings"}, {"column_title": "Contact", "column_text": "(609) 222-4176"}]),
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


def _find_widgets(el, widget_type: str) -> list[dict]:
    found = []
    if isinstance(el, dict):
        if el.get("widgetType") == widget_type:
            found.append(el)
        for child in el.get("elements", []):
            found.extend(_find_widgets(child, widget_type))
    return found


def _accent_color_applied(elementor_data, spec: PageSpec) -> bool:
    """Any section that set accent_color must have that exact color on its
    button widgets' background and its icon-box widgets' primary_color —
    otherwise Elementor falls back to generic defaults that clash with the
    rest of the page (found via live design review)."""
    for section_spec, built in zip(spec.sections, elementor_data):
        expected = (section_spec.content or {}).get("accent_color")
        if not expected:
            continue
        for button in _find_widgets(built, "button"):
            if button["settings"].get("background_color") != expected:
                return False
        for icon_box in _find_widgets(built, "icon-box"):
            if icon_box["settings"].get("primary_color") != expected:
                return False
    return True


def _accent_color_consistent(spec: PageSpec) -> bool:
    """A page should use exactly one accent color throughout — a different
    accent per section breaks the consistent, on-brand look the generator is
    instructed to produce."""
    values = {
        s.content["accent_color"]
        for s in spec.sections
        if s.content.get("accent_color")
    }
    return len(values) <= 1


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
    accent_applied_ok = _accent_color_applied(result["elementor_data"], spec)
    accent_consistent_ok = _accent_color_consistent(spec)
    return [
        CheckResult("valid_elementor_data", not errors, weight=2, detail="; ".join(errors)),
        CheckResult("section_count_3_to_6", section_count_ok, weight=1),
        CheckResult("accent_color_applied", accent_applied_ok, weight=1),
        CheckResult("accent_color_consistent", accent_consistent_ok, weight=1),
        CheckResult("requested_sections_present", sections_match, weight=1),
        CheckResult("title_matches", title_ok, weight=1),
        CheckResult("icons_are_safe", icons_safe, weight=2, detail=str(icons)),
    ]


SCENARIOS = [
    Scenario(name=brief, run=lambda b=brief, s=spec: _run(b, s))
    for brief, spec in _BRIEFS.items()
]
