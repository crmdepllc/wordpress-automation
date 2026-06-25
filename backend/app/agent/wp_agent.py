"""A thin, approval-gated natural-language path to the WP tools.

Sprint 3 scope: turn an instruction into a single proposed tool call, show its
preview, and execute it only after explicit approval. This deliberately is NOT
the full LangGraph plan→approve→execute interrupt graph — that arrives in
Sprint 4. The approval invariant is still honored: ``propose`` never writes
(write tools dry-run to a preview), and ``run_approved`` is the only path that
sets ``approved=True``.
"""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agent.tools import WP_TOOLS, WRITE_TOOLS
from app.config import get_settings

TOOLS_BY_NAME = {t.name: t for t in WP_TOOLS}
WRITE_TOOL_NAMES = {t.name for t in WRITE_TOOLS}

_SYSTEM = (
    "You are a WordPress automation agent. Choose exactly one tool to accomplish "
    "the user's instruction for the site '{site_slug}'. Always pass "
    "site_slug='{site_slug}'. Never set the 'approved' argument — a human "
    "approves writes separately."
)


class ProposedAction(BaseModel):
    """A single tool call the agent proposes, pending approval for writes."""

    tool: str
    args: dict[str, Any]
    requires_approval: bool
    preview: dict[str, Any] | None = None


async def run_approved(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool, granting approval for write tools.

    This is the ONLY place ``approved=True`` is set, so every applied write is
    traceable to an explicit approval.
    """
    if tool_name not in TOOLS_BY_NAME:
        raise KeyError(f"Unknown tool: {tool_name}")
    call_args = dict(args)
    if tool_name in WRITE_TOOL_NAMES:
        call_args["approved"] = True
    return await TOOLS_BY_NAME[tool_name].ainvoke(call_args)


class WpAgent:
    """Plans one tool call from natural language; never writes during planning."""

    def __init__(self, llm: BaseChatModel | None = None):
        settings = get_settings()
        base = llm or ChatAnthropic(
            model=settings.orchestrator_model,
            api_key=settings.anthropic_api_key,
            max_tokens=settings.max_tokens,
        )
        self._llm = base.bind_tools(WP_TOOLS)

    async def propose(self, instruction: str, site_slug: str) -> ProposedAction | None:
        """Ask the model to pick a tool; return the proposal (write preview only)."""
        response = await self._llm.ainvoke(
            [
                SystemMessage(_SYSTEM.format(site_slug=site_slug)),
                HumanMessage(instruction),
            ]
        )
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return None

        call = tool_calls[0]
        args = {**call["args"], "site_slug": site_slug}
        requires = call["name"] in WRITE_TOOL_NAMES

        preview: dict[str, Any] | None = None
        if requires:
            # Dry-run: write tools short-circuit to a needs_approval preview
            # before touching credentials or the live site.
            preview = await TOOLS_BY_NAME[call["name"]].ainvoke(args)

        return ProposedAction(
            tool=call["name"], args=args, requires_approval=requires, preview=preview
        )
