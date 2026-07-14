"""Unit tests for the required theme/plugin pre-flight check (WpCli mocked)."""

from __future__ import annotations

import pytest

from app.agent.skills.stack import (
    REQUIRED_PLUGINS,
    REQUIRED_THEME,
    RequiredStackError,
    ensure_required_stack,
)
from app.wp.schemas import CliResult


def _ok(cmd: str = "x") -> CliResult:
    return CliResult(command=cmd, exit_code=0)


def _fail(cmd: str = "x", stderr: str = "") -> CliResult:
    return CliResult(command=cmd, exit_code=1, stderr=stderr)


class FakeCli:
    """Every call recorded; behavior driven by simple per-slug maps so each
    test only sets up the state it cares about."""

    def __init__(self, *, active: set[str] | None = None, installed: set[str] | None = None,
                 install_fails: set[str] | None = None, activate_fails: set[str] | None = None):
        self.active = active or set()
        self.installed = installed or set()
        self.install_fails = install_fails or set()
        self.activate_fails = activate_fails or set()
        self.calls: list[tuple[str, str]] = []

    async def plugin_is_active(self, slug):
        self.calls.append(("plugin_is_active", slug))
        return _ok() if slug in self.active else _fail()

    async def plugin_is_installed(self, slug):
        self.calls.append(("plugin_is_installed", slug))
        return _ok() if slug in self.installed else _fail()

    async def activate_plugin(self, slug):
        self.calls.append(("activate_plugin", slug))
        return _fail(stderr="activate failed") if slug in self.activate_fails else _ok()

    async def install_plugin(self, slug, *, activate=True):
        self.calls.append(("install_plugin", slug))
        return _fail(stderr="install failed") if slug in self.install_fails else _ok()

    async def theme_is_active(self, slug):
        self.calls.append(("theme_is_active", slug))
        return _ok() if slug in self.active else _fail()

    async def theme_is_installed(self, slug):
        self.calls.append(("theme_is_installed", slug))
        return _ok() if slug in self.installed else _fail()

    async def activate_theme(self, slug):
        self.calls.append(("activate_theme", slug))
        return _fail(stderr="activate failed") if slug in self.activate_fails else _ok()

    async def install_theme(self, slug, *, activate=True):
        self.calls.append(("install_theme", slug))
        return _fail(stderr="install failed") if slug in self.install_fails else _ok()


def _all_slugs() -> set[str]:
    return {REQUIRED_THEME} | {slug for slug, _ in REQUIRED_PLUGINS}


async def test_everything_already_active_is_a_cheap_noop():
    cli = FakeCli(active=_all_slugs())
    result = await ensure_required_stack(cli)

    assert {i.name: i.status for i in result.items} == {
        REQUIRED_THEME: "already_active",
        **{slug: "already_active" for slug, _ in REQUIRED_PLUGINS},
    }
    # Only the cheap "is active" check ran — no install/activate calls.
    kinds = {call[0] for call in cli.calls}
    assert kinds == {"plugin_is_active", "theme_is_active"}


async def test_installed_but_inactive_only_activates():
    cli = FakeCli(installed=_all_slugs())  # nothing active yet, everything installed
    result = await ensure_required_stack(cli)

    by_name = {i.name: i.status for i in result.items}
    assert by_name[REQUIRED_THEME] == "activated"
    for slug, _ in REQUIRED_PLUGINS:
        assert by_name[slug] == "activated"
    assert ("install_plugin", "elementor") not in cli.calls
    assert ("install_theme", REQUIRED_THEME) not in cli.calls


async def test_missing_entirely_installs_and_activates():
    cli = FakeCli()  # nothing active, nothing installed
    result = await ensure_required_stack(cli)

    by_name = {i.name: i.status for i in result.items}
    assert by_name[REQUIRED_THEME] == "installed"
    for slug, _ in REQUIRED_PLUGINS:
        assert by_name[slug] == "installed"


async def test_elementor_install_failure_raises_and_stops():
    cli = FakeCli(install_fails={"elementor"})
    with pytest.raises(RequiredStackError) as exc_info:
        await ensure_required_stack(cli)
    assert "elementor" in exc_info.value.errors[0]


async def test_optional_plugin_failure_is_reported_not_raised():
    cli = FakeCli(active={REQUIRED_THEME, "elementor", "elementskit-lite"},
                   install_fails={"royal-elementor-addons"})
    result = await ensure_required_stack(cli)  # must not raise

    by_name = {i.name: i.status for i in result.items}
    assert by_name["royal-elementor-addons"] == "failed"
    failed_item = next(i for i in result.items if i.name == "royal-elementor-addons")
    assert "install failed" in failed_item.detail


async def test_optional_theme_failure_is_reported_not_raised():
    cli = FakeCli(active={slug for slug, _ in REQUIRED_PLUGINS}, install_fails={REQUIRED_THEME})
    result = await ensure_required_stack(cli)  # must not raise

    theme_item = next(i for i in result.items if i.name == REQUIRED_THEME)
    assert theme_item.status == "failed"
