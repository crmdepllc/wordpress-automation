"""Ensure the required theme/plugin stack is installed and active.

Runs as an internal precondition inside ``wp_create_elementor_page`` — the
same "mandatory, not user-interesting" pattern as the auto CSS-flush and
image resolution, not a separately-approved planner step. Per AGENTS.md's
page-builder-plugin-stack rule: every site build needs Elementor + Royal
Addons for Elementor + ElementsKit, plus the Astra theme.

Elementor is a hard dependency — nothing can be built without it, so a
failure there aborts page creation (``RequiredStackError``). The theme and
the other two plugins are best-effort: a failure is logged and page creation
proceeds anyway, since core Elementor widgets still work without them.

Only ever called from inside the already-gated ``wp_create_elementor_page``
tool, after approval — installing/activating a theme or plugin is a real
site write, so per AGENTS.md rule 1 it may not happen during planning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.wp.wpcli import WpCli

logger = logging.getLogger("agent.skills.stack")

REQUIRED_THEME = "astra"

# (slug, hard_required) — Elementor is the only one page creation can't work without.
REQUIRED_PLUGINS: list[tuple[str, bool]] = [
    ("elementor", True),
    ("royal-elementor-addons", False),
    ("elementskit-lite", False),
]


class RequiredStackError(Exception):
    """Raised when a hard-required item (Elementor) can't be verified active."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Required stack check failed: " + "; ".join(errors))


@dataclass
class StackItemStatus:
    name: str
    kind: str  # "theme" | "plugin"
    status: str  # "already_active" | "installed" | "activated" | "failed"
    detail: str = ""


@dataclass
class StackResult:
    items: list[StackItemStatus] = field(default_factory=list)


async def _ensure_plugin(cli: WpCli, slug: str, *, hard_required: bool) -> StackItemStatus:
    active = await cli.plugin_is_active(slug)
    if active.ok:
        return StackItemStatus(slug, "plugin", "already_active")

    try:
        installed = await cli.plugin_is_installed(slug)
        if installed.ok:
            result = await cli.activate_plugin(slug)
            action = "activated"
        else:
            result = await cli.install_plugin(slug, activate=True)
            action = "installed"
        if not result.ok:
            raise RuntimeError(result.stderr or result.stdout or "unknown WP-CLI error")
        return StackItemStatus(slug, "plugin", action)
    except Exception as exc:
        detail = f"{slug}: {exc}"
        if hard_required:
            logger.error("required plugin %s failed: %s", slug, detail)
            raise RequiredStackError([detail]) from exc
        logger.warning(
            "optional plugin %s failed, continuing without it: %s", slug, detail
        )
        return StackItemStatus(slug, "plugin", "failed", detail)


async def _ensure_theme(cli: WpCli, slug: str) -> StackItemStatus:
    active = await cli.theme_is_active(slug)
    if active.ok:
        return StackItemStatus(slug, "theme", "already_active")

    try:
        installed = await cli.theme_is_installed(slug)
        if installed.ok:
            result = await cli.activate_theme(slug)
            action = "activated"
        else:
            result = await cli.install_theme(slug, activate=True)
            action = "installed"
        if not result.ok:
            raise RuntimeError(result.stderr or result.stdout or "unknown WP-CLI error")
        return StackItemStatus(slug, "theme", action)
    except Exception as exc:
        detail = f"{slug}: {exc}"
        logger.warning(
            "optional theme %s failed, continuing with current theme: %s", slug, detail
        )
        return StackItemStatus(slug, "theme", "failed", detail)


async def ensure_required_stack(cli: WpCli) -> StackResult:
    """Check-then-act on the required theme + plugin stack.

    Already-active items cost one cheap status check; only what's actually
    missing gets installed/activated. Raises ``RequiredStackError`` only if
    Elementor can't be verified active — everything else degrades gracefully.
    """
    items: list[StackItemStatus] = [await _ensure_theme(cli, REQUIRED_THEME)]
    for slug, hard_required in REQUIRED_PLUGINS:
        items.append(await _ensure_plugin(cli, slug, hard_required=hard_required))
    return StackResult(items=items)
