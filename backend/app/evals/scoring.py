"""Generic weighted-checklist scoring for eval scenarios.

A scenario is scored by a small checklist of pass/fail assertions, each with a
weight. The scenario's score is the percentage of weight satisfied — this is
more informative than plain pass/fail: a skill that starts failing one minor
check out of five is a partial regression, not a cliff.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """One weighted assertion within a scenario."""

    name: str
    passed: bool
    weight: float = 1.0
    detail: str = ""


@dataclass
class ScenarioResult:
    """A scenario's checklist, scored."""

    scenario: str
    checks: list[CheckResult]

    @property
    def score(self) -> float:
        total = sum(c.weight for c in self.checks)
        if total <= 0:
            return 0.0
        earned = sum(c.weight for c in self.checks if c.passed)
        return round(100 * earned / total, 1)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass
class Scenario:
    """One golden-dataset case: a name and an async runner producing checks."""

    name: str
    run: Callable[[], Awaitable[list[CheckResult]]]


@dataclass
class SkillReport:
    """Every scenario result for one skill, and the skill's rolled-up score."""

    skill: str
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(r.score for r in self.results) / len(self.results), 1)
