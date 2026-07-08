"""Orchestrator graph state and the plan-step shape."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

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


# Multi-step decomposition (Sprint 7): every tool falls into one category, and
# categories run in a fixed precedence order — e.g. a theme is applied before
# content is written, and pages exist before a menu tries to collect them.
# This is deterministic, code-owned ordering; the LLM never authors the graph
# itself (mirrors the constrained-IR pattern used by the Elementor skill).
Category = Literal["plugin", "theme", "page", "content", "seo", "menu", "other"]

CATEGORY_PRECEDENCE: list[Category] = [
    "plugin",
    "theme",
    "page",
    "content",
    "seo",
    "menu",
    "other",
]

_CATEGORY_BY_TOOL: dict[str, Category] = {
    "wp_install_plugin": "plugin",
    "wp_activate_plugin": "plugin",
    "wp_configure_plugin": "plugin",
    "wp_search_plugins": "plugin",
    "wp_apply_theme": "theme",
    "wp_create_page": "page",
    "wp_update_page": "page",
    "wp_delete_page": "page",
    "wp_create_elementor_page": "page",
    "wp_flush_elementor_css": "page",
    "wp_list_pages": "page",
    "wp_get_page": "page",
    "wp_create_post": "content",
    "wp_publish_post": "content",
    "wp_list_posts": "content",
    "wp_apply_seo": "seo",
    "wp_assemble_menu": "menu",
    "wp_list_menus": "menu",
}


def category_for_tool(tool: str) -> Category:
    return _CATEGORY_BY_TOOL.get(tool, "other")


class PlannedStep(BaseModel):
    """One tool call in the plan, with UI-facing preview fields."""

    id: str
    tool: str
    args: dict[str, Any]
    title: str
    channel: Channel
    requires_approval: bool
    preview: dict[str, Any] | None = None
    category: Category = "other"
    # Step ids that must run (and, if writes, succeed) before this one.
    depends_on: list[str] = Field(default_factory=list)


class ExecEvent(BaseModel):
    """A streamed execution event (mirrors the frontend ToolLogEntry)."""

    id: str
    step_id: str
    tool: str
    channel: Channel
    status: Literal["running", "success", "error", "skipped"]
    message: str


class OrchestratorState(TypedDict, total=False):
    """State threaded through the graph and persisted by the checkpointer."""

    instruction: str
    site_slug: str
    plan: list[dict[str, Any]]  # serialized PlannedStep list
    summary: str
    decision: str  # "approve" | "reject" (from the interrupt resume)
    snapshot: dict[str, Any]  # pre-execution DB export reference, if taken
    results: list[dict[str, Any]]
    report: dict[str, Any]
    status: str
