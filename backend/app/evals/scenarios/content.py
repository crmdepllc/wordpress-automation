"""Content golden dataset: 4 briefs run through the content skill."""

from __future__ import annotations

from app.agent.skills.content.schema import PostDraft
from app.agent.skills.content.skill import generate_post_draft
from app.evals.scoring import CheckResult, Scenario


class _FakeGenerator:
    def __init__(self, draft: PostDraft):
        self._draft = draft

    async def generate(self, brief: str) -> PostDraft:
        return self._draft


_BRIEFS: dict[str, PostDraft] = {
    "announce a product launch": PostDraft(
        title="Introducing Acme Flow",
        content="<p>" + "Acme Flow ships today. " * 10 + "</p>",
        excerpt="Big news from Acme.",
        categories=["Product"],
        tags=["launch", "product"],
    ),
    "explain a how-to for beginners": PostDraft(
        title="How to Get Started with Acme",
        content="<p>" + "Follow these steps to get set up. " * 10 + "</p>",
        excerpt="A beginner's guide.",
        categories=["Guides"],
        tags=["howto", "beginner"],
    ),
    "recap a company milestone": PostDraft(
        title="We Just Hit 10,000 Users",
        content="<p>" + "Thank you to everyone who got us here. " * 10 + "</p>",
        excerpt="A milestone worth celebrating.",
        categories=["News"],
        tags=["milestone"],
    ),
    "write an opinion piece on industry trends": PostDraft(
        title="Why 2026 Is the Year of Agentic Sites",
        content="<p>" + "Agentic tooling is reshaping how sites get built. " * 10 + "</p>",
        excerpt="A look at where the industry is headed.",
        categories=["Opinion"],
        tags=["trends", "ai"],
    ),
}


async def _run(brief: str, draft: PostDraft) -> list[CheckResult]:
    result = await generate_post_draft(brief, generator=_FakeGenerator(draft))
    return [
        CheckResult("title_present", bool(result.title.strip()), weight=1),
        CheckResult(
            "body_substantial", len(result.content) >= 100, weight=2,
            detail=f"len={len(result.content)}",
        ),
        CheckResult("has_category", len(result.categories) >= 1, weight=1),
        CheckResult("has_tags", len(result.tags) >= 1, weight=1),
    ]


SCENARIOS = [
    Scenario(name=brief, run=lambda b=brief, d=draft: _run(b, d))
    for brief, draft in _BRIEFS.items()
]
