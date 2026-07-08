"""The eval suite as a pytest gate: same runner the CI script uses.

Each skill must score at or above its committed threshold
(``app/evals/thresholds.py``) — a drop below the floor is a regression and
should fail the build, exactly like any other test failure.
"""

from __future__ import annotations

from app.evals.report import regressions, to_json, to_markdown
from app.evals.runner import run_all
from app.evals.scoring import CheckResult, ScenarioResult, SkillReport
from app.evals.thresholds import threshold_for


async def test_no_skill_regresses_below_its_threshold():
    reports = await run_all()
    bad = regressions(reports)
    detail = {r.skill: r.score for r in reports if r.skill in bad}
    assert not bad, f"skills below their threshold: {detail}"


async def test_every_skill_has_scenarios():
    reports = await run_all()
    assert len(reports) == 6
    for report in reports:
        assert report.results, f"{report.skill} has no scenarios"


async def test_golden_dataset_has_at_least_20_scenarios():
    reports = await run_all()
    total = sum(len(r.results) for r in reports)
    assert total >= 20


def test_scenario_result_scores_by_weight():
    result = ScenarioResult(
        scenario="x",
        checks=[
            CheckResult("a", passed=True, weight=3),
            CheckResult("b", passed=False, weight=1),
        ],
    )
    assert result.score == 75.0
    assert [c.name for c in result.failures] == ["b"]


def test_skill_report_averages_scenario_scores():
    report = SkillReport(
        skill="x",
        results=[
            ScenarioResult(scenario="a", checks=[CheckResult("c", True, weight=1)]),
            ScenarioResult(scenario="b", checks=[CheckResult("c", False, weight=1)]),
        ],
    )
    assert report.score == 50.0


def test_empty_skill_report_scores_zero():
    assert SkillReport(skill="x").score == 0.0


async def test_regressions_flags_skills_under_threshold():
    async def _low() -> list[CheckResult]:
        return [CheckResult("c", passed=False, weight=1)]

    report = SkillReport(
        skill="elementor",
        results=[ScenarioResult(scenario="a", checks=await _low())],
    )
    assert report.score < threshold_for("elementor")
    assert regressions([report]) == ["elementor"]


def test_markdown_and_json_report_render():
    report = SkillReport(
        skill="content",
        results=[ScenarioResult(scenario="a", checks=[CheckResult("c", True, weight=1)])],
    )
    md = to_markdown([report])
    assert "content" in md
    assert "100" in md

    payload = to_json([report])
    assert '"skill": "content"' in payload
    assert '"regressions": []' in payload
