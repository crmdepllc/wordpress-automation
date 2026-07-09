"""Planning step: natural language → a dependency-ordered task graph.

The planner asks the orchestrator model to select the tool calls needed to
satisfy the instruction (e.g. install plugin → create pages → theme → SEO →
menu). Write steps get a dry-run preview and are marked ``requires_approval``
— nothing is executed here.

The LLM does not author step ordering or dependencies itself — that would risk
a hallucinated graph (invalid step ids, cycles). Instead ``_decompose`` tags
each step with a deterministic ``category`` and computes ``depends_on`` from a
fixed category-precedence table (see ``state.CATEGORY_PRECEDENCE``), then
topologically sorts the plan. This mirrors the constrained-IR pattern used by
the Elementor skill: the model proposes, code assembles the fragile part.

For a step to target content created earlier in the *same* plan (e.g. apply
SEO to a page step-1 just created, or add step-1's page to a menu), the model
emits a ``"$ref:<step-id>:<path>"`` string instead of a guessed id — resolved
against that step's real result at execution time (``graph.resolve_refs``).
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.tools import WP_TOOLS
from app.agent.wp_agent import TOOLS_BY_NAME, WRITE_TOOL_NAMES
from app.agent.orchestrator.state import (
    CATEGORY_PRECEDENCE,
    PlannedStep,
    category_for_tool,
    channel_for_tool,
)
from app.config import get_settings

_SYSTEM = (
    "You are a WordPress automation orchestrator. Break the user's instruction "
    "into the tool calls needed to accomplish it for the site '{site_slug}'. "
    "Emit one tool call per step. Always pass site_slug='{site_slug}'. Never set "
    "the 'approved' argument — a human approves writes separately.\n\n"
    "You don't need to worry about ordering categories of work (plugins, theme, "
    "pages, content, SEO, menus) — that is sorted automatically.\n\n"
    "If a step needs the id of a page or post that ANOTHER step in this same "
    "plan is creating (e.g. applying SEO to a page you're also creating, or "
    "adding new pages to a menu), do not guess a numeric id. Instead pass the "
    "string \"$ref:<step-id>:<path>\" for that argument, where <step-id> is the "
    "other step's id ('step-0', 'step-1', ...) and <path> is 'page.id' for a "
    "step that creates a page (wp_create_page / wp_create_elementor_page) or "
    "'post.id' for a step that creates a post (wp_create_post / "
    "wp_publish_post). Example: target_id=\"$ref:step-1:page.id\". For "
    "wp_assemble_menu's page_refs, mix concrete ids and $ref strings as needed."
)

_REF_RE = re.compile(r"^\$ref:(?P<step>[^:]+):(?P<path>.+)$")


def _find_refs(value: Any) -> set[str]:
    """Collect every step id referenced by a `$ref:step-id:path` token in value."""
    if isinstance(value, str):
        m = _REF_RE.match(value)
        return {m.group("step")} if m else set()
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found |= _find_refs(item)
        return found
    if isinstance(value, dict):
        found = set()
        for item in value.values():
            found |= _find_refs(item)
        return found
    return set()


def _decompose(steps: list[PlannedStep]) -> list[PlannedStep]:
    """Assign categories + dependencies, then topologically order the steps."""
    for step in steps:
        step.category = category_for_tool(step.tool)

    rank = {cat: i for i, cat in enumerate(CATEGORY_PRECEDENCE)}
    by_id = {s.id: s for s in steps}
    for step in steps:
        deps: set[str] = set()
        step_rank = rank[step.category]
        for other in steps:
            if other.id == step.id:
                continue
            if rank[other.category] < step_rank:
                deps.add(other.id)
        for arg_value in step.args.values():
            deps |= {ref for ref in _find_refs(arg_value) if ref in by_id and ref != step.id}
        step.depends_on = sorted(deps)

    # Kahn's algorithm, stable on the original emission order for ties.
    remaining = {s.id: set(s.depends_on) for s in steps}
    ordered: list[PlannedStep] = []
    while remaining:
        ready = [s for s in steps if s.id in remaining and not remaining[s.id]]
        if not ready:
            # A cycle should be impossible (category precedence is a strict
            # order and refs only point at earlier-known step ids), but never
            # hang the planner — fall back to emission order for what's left.
            ready = [s for s in steps if s.id in remaining]
        for step in ready:
            ordered.append(step)
            del remaining[step.id]
        for deps in remaining.values():
            deps -= {s.id for s in ready}
    return ordered


def _title(tool: str, args: dict[str, Any]) -> str:
    label = tool.removeprefix("wp_").replace("_", " ")
    detail = (
        args.get("title")
        or args.get("plugin_slug")
        or (f"#{args['page_id']}" if "page_id" in args else "")
    )
    return f"{label} {detail}".strip().capitalize()


async def _to_step(
    index: int, name: str, raw_args: dict[str, Any], site_slug: str, instruction: str
) -> PlannedStep:
    args = {**raw_args, "site_slug": site_slug}
    if "brief" not in args and "brief" in TOOLS_BY_NAME[name].args_schema.model_fields:
        # The model occasionally omits `brief` on brief-taking tools (e.g.
        # wp_create_elementor_page, wp_publish_post, wp_apply_theme) when the
        # user's whole instruction already reads as the brief. Fall back to
        # the raw instruction rather than failing pydantic validation and
        # aborting the entire plan over one step.
        args["brief"] = instruction
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
            steps.append(await _to_step(i, call["name"], call["args"], site_slug, instruction))
        return _decompose(steps)


def build_planner() -> Planner:
    return LLMPlanner()
