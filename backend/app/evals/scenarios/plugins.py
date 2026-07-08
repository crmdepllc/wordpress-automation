"""Plugins golden dataset: 3 stated needs run through the recommend catalog.

No LLM involved (``recommend_plugin`` is a pure lookup) — still worth scoring
so a catalog edit that silently breaks a mapping shows up as a regression.
"""

from __future__ import annotations

from app.agent.skills.plugins import recommend_plugin
from app.evals.scoring import CheckResult, Scenario

_CASES: dict[str, str] = {
    "we need a contact form on the site": "contact-form-7",
    "the site feels slow, add caching": "w3-total-cache",
    "we want to set up an online shop": "woocommerce",
}


async def _run(need: str, expected_slug: str) -> list[CheckResult]:
    result = recommend_plugin(need)
    matched = result is not None and result["slug"] == expected_slug
    return [
        CheckResult("recommends_expected_plugin", matched, weight=1, detail=str(result)),
    ]


SCENARIOS = [
    Scenario(name=need, run=lambda n=need, s=slug: _run(n, s))
    for need, slug in _CASES.items()
]
