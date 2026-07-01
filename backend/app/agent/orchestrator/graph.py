"""The orchestration state machine: plan → approve(interrupt) → execute → report.

``approve`` calls ``interrupt()`` with the plan, pausing the graph until a
``Command(resume=decision)`` arrives. Only ``decision == "approve"`` routes to
``execute``, which runs each step through ``run_approved`` (the sole
approval-granting path) and streams a live event per tool call.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.orchestrator.planner import Planner, build_planner
from app.agent.orchestrator.state import ExecEvent, OrchestratorState
from app.agent.wp_agent import run_approved

logger = logging.getLogger("agent.orchestrator")

_APPLIED = {"applied", "ok"}


def _emit(event: ExecEvent) -> None:
    """Emit a custom stream event if a run is streaming; noop otherwise."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event.model_dump())


def build_orchestrator(checkpointer: Any, planner: Planner | None = None):
    """Compile the orchestrator graph with the given checkpointer + planner."""
    planner = planner or build_planner()

    async def plan_node(state: OrchestratorState) -> dict[str, Any]:
        steps = await planner.plan(state["instruction"], state["site_slug"])
        plan = [s.model_dump() for s in steps]
        writes = sum(1 for s in steps if s.requires_approval)
        summary = (
            f"{len(steps)} step(s) planned "
            f"({writes} write{'s' if writes != 1 else ''}) for: "
            f"“{state['instruction']}”."
        )
        logger.info("planned %d steps for site=%s", len(steps), state["site_slug"])
        return {"plan": plan, "summary": summary, "status": "awaiting_approval"}

    async def approve_node(state: OrchestratorState) -> dict[str, Any]:
        # Pauses here until resumed with a decision. The payload is what the
        # frontend renders in the approval modal.
        decision = interrupt(
            {
                "type": "approval_request",
                "summary": state.get("summary", ""),
                "plan": state.get("plan", []),
            }
        )
        if isinstance(decision, dict):
            decision = decision.get("decision", "reject")
        return {"decision": str(decision)}

    def route_after_approval(state: OrchestratorState) -> str:
        return "execute" if state.get("decision") == "approve" else "report"

    async def execute_node(state: OrchestratorState) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for step in state.get("plan", []):
            _emit(
                ExecEvent(
                    id=f"{step['id']}-run",
                    step_id=step["id"],
                    tool=step["tool"],
                    channel=step["channel"],
                    status="running",
                    message=f"{step['title']}…",
                )
            )
            try:
                result = await run_approved(step["tool"], step["args"])
                ok = result.get("status") in _APPLIED
                status = "success" if ok else "error"
                message = f"{step['title']} — {'done' if ok else 'failed'}"
            except Exception as exc:  # keep executing/report the failure
                result = {"status": "error", "error": str(exc)}
                status = "error"
                message = f"{step['title']} — error: {exc}"
            _emit(
                ExecEvent(
                    id=f"{step['id']}-done",
                    step_id=step["id"],
                    tool=step["tool"],
                    channel=step["channel"],
                    status=status,
                    message=message,
                )
            )
            results.append(
                {"step_id": step["id"], "tool": step["tool"], "result": result}
            )
        return {"results": results, "status": "executing"}

    async def report_node(state: OrchestratorState) -> dict[str, Any]:
        if state.get("decision") != "approve":
            return {
                "report": {
                    "outcome": "rejected",
                    "message": "Plan rejected — no changes were made.",
                },
                "status": "rejected",
            }
        results = state.get("results", [])
        applied = sum(1 for r in results if r["result"].get("status") in _APPLIED)
        failed = len(results) - applied
        return {
            "report": {
                "outcome": "completed",
                "applied": applied,
                "failed": failed,
                "total": len(results),
            },
            "status": "completed",
        }

    builder = StateGraph(OrchestratorState)
    builder.add_node("plan", plan_node)
    builder.add_node("approve", approve_node)
    builder.add_node("execute", execute_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "approve")
    builder.add_conditional_edges(
        "approve", route_after_approval, {"execute": "execute", "report": "report"}
    )
    builder.add_edge("execute", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)
