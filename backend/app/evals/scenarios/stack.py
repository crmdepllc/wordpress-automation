"""Required theme/plugin pre-flight golden dataset: ensure_required_stack
against a fake WpCli (no real WP-CLI/network calls)."""

from __future__ import annotations

from app.agent.skills.stack import (
    REQUIRED_PLUGINS,
    REQUIRED_THEME,
    RequiredStackError,
    ensure_required_stack,
)
from app.evals.scoring import CheckResult, Scenario
from app.wp.schemas import CliResult


def _ok() -> CliResult:
    return CliResult(command="x", exit_code=0)


def _fail(stderr: str = "") -> CliResult:
    return CliResult(command="x", exit_code=1, stderr=stderr)


class _FakeCli:
    def __init__(self, *, active=None, installed=None, install_fails=None):
        self.active = active or set()
        self.installed = installed or set()
        self.install_fails = install_fails or set()

    async def plugin_is_active(self, slug):
        return _ok() if slug in self.active else _fail()

    async def plugin_is_installed(self, slug):
        return _ok() if slug in self.installed else _fail()

    async def activate_plugin(self, slug):
        return _ok()

    async def install_plugin(self, slug, *, activate=True):
        return _fail("install failed") if slug in self.install_fails else _ok()

    async def theme_is_active(self, slug):
        return _ok() if slug in self.active else _fail()

    async def theme_is_installed(self, slug):
        return _ok() if slug in self.installed else _fail()

    async def activate_theme(self, slug):
        return _ok()

    async def install_theme(self, slug, *, activate=True):
        return _fail("install failed") if slug in self.install_fails else _ok()


def _all_slugs() -> set[str]:
    return {REQUIRED_THEME} | {slug for slug, _ in REQUIRED_PLUGINS}


async def _run_already_satisfied_is_a_noop() -> list[CheckResult]:
    cli = _FakeCli(active=_all_slugs())
    result = await ensure_required_stack(cli)
    statuses = {i.name for i in result.items if i.status == "already_active"}

    return [
        CheckResult("all_four_checked", len(result.items) == 4, weight=2),
        CheckResult("all_already_active", statuses == _all_slugs(), weight=2),
    ]


async def _run_missing_items_get_installed() -> list[CheckResult]:
    cli = _FakeCli()  # nothing installed or active
    result = await ensure_required_stack(cli)
    by_name = {i.name: i.status for i in result.items}

    return [
        CheckResult("theme_installed", by_name[REQUIRED_THEME] == "installed", weight=1),
        CheckResult(
            "all_plugins_installed",
            all(by_name[slug] == "installed" for slug, _ in REQUIRED_PLUGINS),
            weight=2,
        ),
    ]


async def _run_elementor_failure_aborts() -> list[CheckResult]:
    cli = _FakeCli(install_fails={"elementor"})
    raised = False
    try:
        await ensure_required_stack(cli)
    except RequiredStackError as exc:
        raised = "elementor" in exc.errors[0]

    return [
        CheckResult("raises_required_stack_error", raised, weight=3),
    ]


async def _run_optional_failure_does_not_abort() -> list[CheckResult]:
    cli = _FakeCli(
        active={REQUIRED_THEME, "elementor", "elementskit-lite"},
        install_fails={"royal-elementor-addons"},
    )
    did_not_raise = True
    result = None
    try:
        result = await ensure_required_stack(cli)
    except RequiredStackError:
        did_not_raise = False

    by_name = {i.name: i.status for i in result.items} if result else {}
    return [
        CheckResult("does_not_raise", did_not_raise, weight=2),
        CheckResult(
            "failed_item_reported", by_name.get("royal-elementor-addons") == "failed", weight=2
        ),
    ]


SCENARIOS = [
    Scenario(name="already-satisfied stack is a cheap no-op", run=_run_already_satisfied_is_a_noop),
    Scenario(name="missing items get installed", run=_run_missing_items_get_installed),
    Scenario(name="Elementor failure aborts (hard-required)", run=_run_elementor_failure_aborts),
    Scenario(name="optional item failure does not abort", run=_run_optional_failure_does_not_abort),
]
