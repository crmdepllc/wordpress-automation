"""Execute every skill's scenario set and roll the results up per skill."""

from __future__ import annotations

from app.evals.scoring import Scenario, ScenarioResult, SkillReport


async def run_skill(skill: str, scenarios: list[Scenario]) -> SkillReport:
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        checks = await scenario.run()
        results.append(ScenarioResult(scenario=scenario.name, checks=checks))
    return SkillReport(skill=skill, results=results)


async def run_all() -> list[SkillReport]:
    # Imported lazily so importing the runner doesn't require every skill's
    # (LLM/WP-CLI) dependencies to be importable in every context.
    from app.evals.scenarios import content, elementor, orchestrator, plugins, seo, theme

    skills: list[tuple[str, list[Scenario]]] = [
        ("elementor", elementor.SCENARIOS),
        ("content", content.SCENARIOS),
        ("seo", seo.SCENARIOS),
        ("theme", theme.SCENARIOS),
        ("plugins", plugins.SCENARIOS),
        ("orchestrator", orchestrator.SCENARIOS),
    ]
    return [await run_skill(name, scenarios) for name, scenarios in skills]
