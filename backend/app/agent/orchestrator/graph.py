"""The orchestration state machine:
plan → approve(interrupt) → snapshot → execute → report.

``approve`` calls ``interrupt()`` with the plan, pausing the graph until a
``Command(resume=decision)`` arrives. Only ``decision == "approve"`` routes
onward: ``snapshot`` takes a pre-execution DB export (a manual restore point —
never an automatic rollback), then ``execute`` runs each step through
``run_approved`` (the sole approval-granting path), resolving any ``$ref``
placeholders against earlier steps' real results first. Execution halts at the
first failed step — everything after it is reported ``skipped`` rather than
silently attempted.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.orchestrator.planner import Planner, build_planner
from app.agent.orchestrator.state import ExecEvent, OrchestratorState
from app.agent.wp_agent import run_approved
from app.db.session import get_sessionmaker
from app.wp.credentials import get_site_credentials
from app.wp.wpcli import WpCli

logger = logging.getLogger("agent.orchestrator")

_APPLIED = {"applied", "ok"}
_REF_RE = re.compile(r"^\$ref:(?P<step>[^:]+):(?P<path>.+)$")


def _emit(event: ExecEvent) -> None:
    """Emit a custom stream event if a run is streaming; noop otherwise."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event.model_dump())


def _resolve_value(value: Any, results_by_step: dict[str, Any]) -> Any:
    if isinstance(value, str):
        match = _REF_RE.match(value)
        if not match:
            return value
        data: Any = results_by_step.get(match.group("step"), {})
        for part in match.group("path").split("."):
            data = data.get(part) if isinstance(data, dict) else None
        return data
    if isinstance(value, list):
        return [_resolve_value(v, results_by_step) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_value(v, results_by_step) for k, v in value.items()}
    return value


def resolve_refs(args: dict[str, Any], results_by_step: dict[str, Any]) -> dict[str, Any]:
    """Substitute ``$ref:step-id:path`` tokens with values from earlier results.

    ``results_by_step`` maps a step id to that step's raw tool result (e.g.
    ``{"status": "applied", "page": {"id": 99, ...}}``). Only referenced steps
    that have already executed are available, which the planner's dependency
    ordering guarantees for any valid ``$ref``.
    """
    return {k: _resolve_value(v, results_by_step) for k, v in args.items()}


async def _site_credentials(site_slug: str):
    async with get_sessionmaker()() as session:
        return await get_site_credentials(session, site_slug)


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
        return "snapshot" if state.get("decision") == "approve" else "report"

    async def snapshot_node(state: OrchestratorState) -> dict[str, Any]:
        plan = state.get("plan", [])
        if not any(step.get("requires_approval") for step in plan):
            return {"snapshot": {"taken": False, "reason": "no writes in plan"}}

        site_slug = state["site_slug"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"snapshot-{site_slug}-{stamp}.sql"
        try:
            creds = await _site_credentials(site_slug)
            result = await WpCli.from_credentials(creds).export_db(filename)
            if result.ok:
                snapshot = {
                    "taken": True,
                    "file": filename,
                    "message": (
                        f"Pre-execution DB snapshot exported to {filename} on the "
                        "site's WP-CLI target. Restore manually with `wp db import` "
                        "if needed — this is not applied automatically."
                    ),
                }
            else:
                snapshot = {
                    "taken": False,
                    "message": f"Snapshot export failed: {result.stderr or result.stdout}",
                }
        except Exception as exc:
            # A failed snapshot is a safety-net miss, not a reason to block
            # writes the human already approved — surface it and continue.
            logger.warning("pre-execution snapshot failed for site=%s: %s", site_slug, exc)
            snapshot = {"taken": False, "message": f"Snapshot export failed: {exc}"}
        return {"snapshot": snapshot}

    async def execute_node(state: OrchestratorState) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        results_by_step: dict[str, Any] = {}
        halted = False

        for step in state.get("plan", []):
            if halted:
                _emit(
                    ExecEvent(
                        id=f"{step['id']}-skip",
                        step_id=step["id"],
                        tool=step["tool"],
                        channel=step["channel"],
                        status="skipped",
                        message=f"{step['title']} — skipped (an earlier step failed)",
                    )
                )
                results.append(
                    {
                        "step_id": step["id"],
                        "tool": step["tool"],
                        "result": {"status": "skipped"},
                    }
                )
                continue

            args = resolve_refs(step["args"], results_by_step)
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
                result = await run_approved(step["tool"], args)
                ok = result.get("status") in _APPLIED
                status = "success" if ok else "error"
                message = f"{step['title']} — {'done' if ok else 'failed'}"
            except Exception as exc:  # halt after reporting the failure
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
            results_by_step[step["id"]] = result
            if status == "error":
                halted = True
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
        skipped = sum(1 for r in results if r["result"].get("status") == "skipped")
        failed = len(results) - applied - skipped
        outcome = "completed" if failed == 0 else "failed"
        return {
            "report": {
                "outcome": outcome,
                "applied": applied,
                "failed": failed,
                "skipped": skipped,
                "total": len(results),
                "snapshot": state.get("snapshot"),
            },
            "status": outcome,
        }

    builder = StateGraph(OrchestratorState)
    builder.add_node("plan", plan_node)
    builder.add_node("approve", approve_node)
    builder.add_node("snapshot", snapshot_node)
    builder.add_node("execute", execute_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "approve")
    builder.add_conditional_edges(
        "approve", route_after_approval, {"snapshot": "snapshot", "report": "report"}
    )
    builder.add_edge("snapshot", "execute")
    builder.add_edge("execute", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)
