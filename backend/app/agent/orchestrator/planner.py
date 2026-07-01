"""Planning step: natural language → an ordered list of tool calls.

The planner asks the orchestrator model to select the tool calls needed to
satisfy the instruction. Multiple tool calls in one response become the ordered
plan (e.g. install plugin → create page). Write steps get a dry-run preview and
are marked ``requires_approval`` — nothing is executed here.
"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.tools import WP_TOOLS
from app.agent.wp_agent import TOOLS_BY_NAME, WRITE_TOOL_NAMES
from app.agent.orchestrator.state import PlannedStep, channel_for_tool
from app.config import get_settings

_SYSTEM = (
    "You are a WordPress automation orchestrator. Break the user's instruction "
    "into the ordered sequence of tool calls needed to accomplish it for the "
    "site '{site_slug}'. Emit one tool call per step, in execution order. Always "
    "pass site_slug='{site_slug}'. Never set the 'approved' argument — a human "
    "approves writes separately."
)


def _title(tool: str, args: dict[str, Any]) -> str:
    label = tool.removeprefix("wp_").replace("_", " ")
    detail = (
        args.get("title")
        or args.get("plugin_slug")
        or (f"#{args['page_id']}" if "page_id" in args else "")
    )
    return f"{label} {detail}".strip().capitalize()


async def _to_step(index: int, name: str, raw_args: dict[str, Any], site_slug: str) -> PlannedStep:
    args = {**raw_args, "site_slug": site_slug}
    requires = name in WRITE_TOOL_NAMES
    preview: dict[str, Any] | None = None
    if requires:
        # Write tools short-circuit to a needs_approval preview without writing.
        preview = await TOOLS_BY_NAME[name].ainvoke(args)
    return PlannedStep(
        id=f"step-{index}",
        tool=name,
        args=args,
        title=_title(name, args),
        channel=channel_for_tool(name),
        requires_approval=requires,
        preview=preview,
    )


class Planner(Protocol):
    async def plan(self, instruction: str, site_slug: str) -> list[PlannedStep]: ...


class LLMPlanner:
    """Default planner backed by Claude with the WP tools bound.

    The model is constructed lazily on first use so the app (and graph) can be
    built without an Anthropic key present — the key is only needed to plan.
    """

    def __init__(self, llm: BaseChatModel | None = None):
        self._provided = llm
        self._bound: Any = None

    def _model(self) -> Any:
        if self._bound is None:
            settings = get_settings()
            base = self._provided or ChatAnthropic(
                model=settings.orchestrator_model,
                api_key=settings.anthropic_api_key,
                max_tokens=settings.max_tokens,
            )
            self._bound = base.bind_tools(WP_TOOLS)
        return self._bound

    async def plan(self, instruction: str, site_slug: str) -> list[PlannedStep]:
        response = await self._model().ainvoke(
            [
                SystemMessage(_SYSTEM.format(site_slug=site_slug)),
                HumanMessage(instruction),
            ]
        )
        tool_calls = getattr(response, "tool_calls", None) or []
        steps: list[PlannedStep] = []
        for i, call in enumerate(tool_calls):
            steps.append(await _to_step(i, call["name"], call["args"], site_slug))
        return steps


def build_planner() -> Planner:
    return LLMPlanner()
