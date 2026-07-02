"""Orchestrator graph state and the plan-step shape."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel

# WP-CLI-backed tools write through SSH/CLI; everything else is REST.
_WPCLI_TOOLS = {
    "wp_install_plugin",
    "wp_activate_plugin",
    "wp_flush_elementor_css",
    "wp_apply_theme",
    "wp_search_plugins",
    "wp_configure_plugin",
}

Channel = Literal["REST API", "WP-CLI"]


def channel_for_tool(tool: str) -> Channel:
    return "WP-CLI" if tool in _WPCLI_TOOLS else "REST API"


class PlannedStep(BaseModel):
    """One tool call in the plan, with UI-facing preview fields."""

    id: str
    tool: str
    args: dict[str, Any]
    title: str
    channel: Channel
    requires_approval: bool
    preview: dict[str, Any] | None = None


class ExecEvent(BaseModel):
    """A streamed execution event (mirrors the frontend ToolLogEntry)."""

    id: str
    step_id: str
    tool: str
    channel: Channel
    status: Literal["running", "success", "error"]
    message: str


class OrchestratorState(TypedDict, total=False):
    """State threaded through the graph and persisted by the checkpointer."""

    instruction: str
    site_slug: str
    plan: list[dict[str, Any]]  # serialized PlannedStep list
    summary: str
    decision: str  # "approve" | "reject" (from the interrupt resume)
    results: list[dict[str, Any]]
    report: dict[str, Any]
    status: str
