"""Orchestrator golden dataset: 4 cases exercising Sprint 7's dependency-ordered
decomposition (``planner._decompose``) directly — category precedence, `$ref`
dependency capture, and menu-depends-on-content — without needing the LLM,
Docker, or a real WP site (structural/offline, like the other skill evals).
"""

from __future__ import annotations

from app.agent.orchestrator.planner import _decompose
from app.agent.orchestrator.state import PlannedStep
from app.evals.scoring import CheckResult, Scenario


def _step(step_id: str, tool: str, args: dict) -> PlannedStep:
    return PlannedStep(
        id=step_id,
        tool=tool,
        args=args,
        title=tool,
        channel="REST API",
        requires_approval=True,
    )


async def _run_category_precedence() -> list[CheckResult]:
    steps = [
        _step("step-0", "wp_publish_post", {"brief": "news"}),
        _step("step-1", "wp_apply_theme", {"brief": "dark"}),
        _step("step-2", "wp_create_page", {"title": "Home"}),
    ]
    ordered = _decompose(steps)
    order_ok = [s.tool for s in ordered] == [
        "wp_apply_theme", "wp_create_page", "wp_publish_post"
    ]
    categories_ok = [s.category for s in ordered] == ["theme", "page", "content"]
    return [
        CheckResult("theme_before_page_before_content", order_ok, weight=2),
        CheckResult("categories_assigned", categories_ok, weight=1),
    ]


async def _run_ref_dependency() -> list[CheckResult]:
    steps = [
        _step(
            "step-0", "wp_apply_seo",
            {"target_id": "$ref:step-1:page.id", "target_type": "page", "subject": "About"},
        ),
        _step("step-1", "wp_create_page", {"title": "About"}),
    ]
    ordered = _decompose(steps)
    order_ok = [s.id for s in ordered] == ["step-1", "step-0"]
    seo_step = next(s for s in ordered if s.tool == "wp_apply_seo")
    deps_ok = seo_step.depends_on == ["step-1"]
    return [
        CheckResult("page_runs_before_seo", order_ok, weight=2),
        CheckResult("ref_dependency_captured", deps_ok, weight=2),
    ]


async def _run_menu_dependency() -> list[CheckResult]:
    steps = [
        _step("step-0", "wp_create_page", {"title": "Home"}),
        _step("step-1", "wp_publish_post", {"brief": "news"}),
        _step(
            "step-2", "wp_assemble_menu",
            {"menu_name": "Main", "page_refs": ["$ref:step-0:page.id"]},
        ),
    ]
    ordered = _decompose(steps)
    menu_step = next(s for s in ordered if s.tool == "wp_assemble_menu")
    deps_ok = set(menu_step.depends_on) == {"step-0", "step-1"}
    runs_last = ordered[-1].tool == "wp_assemble_menu"
    return [
        CheckResult("menu_depends_on_pages_and_posts", deps_ok, weight=2),
        CheckResult("menu_runs_last", runs_last, weight=1),
    ]


async def _run_plugin_first() -> list[CheckResult]:
    steps = [
        _step("step-0", "wp_create_page", {"title": "Home"}),
        _step("step-1", "wp_install_plugin", {"plugin_slug": "elementor"}),
        _step("step-2", "wp_apply_theme", {"brief": "dark"}),
    ]
    ordered = _decompose(steps)
    tools = [s.tool for s in ordered]
    plugin_first = tools[0] == "wp_install_plugin"
    theme_before_page = tools.index("wp_apply_theme") < tools.index("wp_create_page")
    return [
        CheckResult("plugin_installed_first", plugin_first, weight=2),
        CheckResult("theme_before_page", theme_before_page, weight=1),
    ]


SCENARIOS = [
    Scenario(name="theme, page, content ordering", run=_run_category_precedence),
    Scenario(name="SEO $ref resolves to a same-plan page", run=_run_ref_dependency),
    Scenario(name="menu depends on pages and posts", run=_run_menu_dependency),
    Scenario(name="plugin install runs first", run=_run_plugin_first),
]
