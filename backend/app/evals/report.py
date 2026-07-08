"""Render eval results to markdown (CI job summary) and JSON (artifact)."""

from __future__ import annotations

import json
from dataclasses import asdict

from app.evals.scoring import SkillReport
from app.evals.thresholds import threshold_for


def regressions(reports: list[SkillReport]) -> list[str]:
    """Skill names scoring below their committed threshold."""
    return [r.skill for r in reports if r.score < threshold_for(r.skill)]


def to_json(reports: list[SkillReport]) -> str:
    payload = {
        "skills": [
            {
                "skill": r.skill,
                "score": r.score,
                "threshold": threshold_for(r.skill),
                "scenarios": [
                    {
                        "scenario": sr.scenario,
                        "score": sr.score,
                        "checks": [asdict(c) for c in sr.checks],
                    }
                    for sr in r.results
                ],
            }
            for r in reports
        ],
        "regressions": regressions(reports),
    }
    return json.dumps(payload, indent=2)


def to_markdown(reports: list[SkillReport]) -> str:
    # Plain ASCII markers (not emoji) — this renders in a GitHub Actions job
    # summary either way, and also prints cleanly on a Windows console, which
    # defaults to a non-UTF-8 codepage and chokes on emoji in `print()`.
    bad = set(regressions(reports))
    lines = ["# Eval report", ""]
    for r in reports:
        floor = threshold_for(r.skill)
        status = "FAIL" if r.skill in bad else "PASS"
        lines.append(f"## {r.skill} -- {r.score}/100 [{status}] (floor: {floor})")
        for sr in r.results:
            mark = "ok" if sr.score >= floor else "warn"
            lines.append(f"- [{mark}] {sr.scenario}: {sr.score}/100")
            for check in sr.failures:
                detail = f" -- {check.detail}" if check.detail else ""
                lines.append(f"  - failed: {check.name}{detail}")
        lines.append("")
    if bad:
        lines.append(f"**Regressions:** {', '.join(sorted(bad))}")
    else:
        lines.append("**No regressions.**")
    return "\n".join(lines)
