"""SEO golden dataset: 4 subjects run through the SEO skill."""

from __future__ import annotations

from app.agent.skills.seo.schema import SeoMeta
from app.agent.skills.seo.skill import generate_seo, seo_to_meta
from app.evals.scoring import CheckResult, Scenario


class _FakeGenerator:
    def __init__(self, meta: SeoMeta):
        self._meta = meta

    async def generate(self, subject: str) -> SeoMeta:
        return self._meta


_SUBJECTS: dict[str, SeoMeta] = {
    "About page for a design agency": SeoMeta(
        title="About North Studio | Brand & Web Design",
        description="Learn about North Studio, a branding and web design agency "
        "helping companies build memorable identities.",
        schema_type="Organization",
    ),
    "Product page for hiking boots": SeoMeta(
        title="Trailblazer Hiking Boots | Waterproof & Durable",
        description="Shop Trailblazer hiking boots built for rugged trails, "
        "all-day comfort, and total waterproofing.",
        schema_type="Product",
    ),
    "Blog post about remote work tips": SeoMeta(
        title="10 Remote Work Tips That Actually Work",
        description="Practical, tested tips to stay focused, connected, and "
        "productive while working remotely.",
        schema_type="Article",
    ),
    "Local bakery homepage": SeoMeta(
        title="Riverside Bakery | Fresh Bread Daily in Riverside",
        description="Riverside Bakery bakes fresh sourdough, pastries, and cakes "
        "daily. Visit us on the riverfront.",
        schema_type="LocalBusiness",
    ),
}


async def _run(subject: str, meta: SeoMeta) -> list[CheckResult]:
    seo = await generate_seo(subject, generator=_FakeGenerator(meta))
    provider_meta = seo_to_meta(seo, provider="yoast", name="Test", url="http://test.example")
    return [
        CheckResult(
            "title_length_ok", len(seo.title) <= 60, weight=1, detail=f"len={len(seo.title)}"
        ),
        CheckResult(
            "description_length_ok", len(seo.description) <= 160, weight=1,
            detail=f"len={len(seo.description)}",
        ),
        CheckResult("meta_has_title_key", "_yoast_wpseo_title" in provider_meta, weight=1),
        CheckResult("meta_has_jsonld", "_seo_schema_jsonld" in provider_meta, weight=1),
    ]


SCENARIOS = [
    Scenario(name=subject, run=lambda s=subject, m=meta: _run(s, m))
    for subject, meta in _SUBJECTS.items()
]
