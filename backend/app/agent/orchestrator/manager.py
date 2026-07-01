"""Task runtime: drive the orchestrator graph to its approval interrupt and
resume it after a decision, streaming execution events.

Holds a single compiled graph (with the app's checkpointer). Because the
checkpoint thread id is the task id, a task interrupted before a restart can be
re-found (``get_plan``) and resumed afterwards.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator.tasks_service import (
    create_task,
    new_task_id,
    set_status,
)


def _config(task_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": task_id}}


class TaskManager:
    def __init__(self, graph: Any):
        self._graph = graph

    async def _interrupt_payload(self, task_id: str) -> dict[str, Any] | None:
        snapshot = await self._graph.aget_state(_config(task_id))
        for task in snapshot.tasks:
            if task.interrupts:
                return task.interrupts[0].value
        return None

    async def start(
        self, session: AsyncSession, instruction: str, site_slug: str
    ) -> dict[str, Any]:
        """Create a task, run the graph until the approval interrupt, return the plan."""
        task_id = new_task_id()
        await create_task(
            session, task_id=task_id, site_slug=site_slug, instruction=instruction
        )
        await self._graph.ainvoke(
            {"instruction": instruction, "site_slug": site_slug, "status": "planning"},
            config=_config(task_id),
        )
        payload = await self._interrupt_payload(task_id)
        await set_status(session, task_id, "awaiting_approval")
        return {
            "task_id": task_id,
            "summary": (payload or {}).get("summary", ""),
            "plan": (payload or {}).get("plan", []),
        }

    async def get_plan(self, task_id: str) -> dict[str, Any] | None:
        """Re-find a paused task's plan (e.g. after a server restart)."""
        payload = await self._interrupt_payload(task_id)
        if payload is not None:
            return {"summary": payload.get("summary", ""), "plan": payload.get("plan", [])}
        snapshot = await self._graph.aget_state(_config(task_id))
        values = snapshot.values or {}
        if "plan" in values:
            return {"summary": values.get("summary", ""), "plan": values["plan"]}
        return None

    async def resume_stream(
        self, session: AsyncSession, task_id: str, decision: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume the graph with a decision; yield execution events then a report."""
        await set_status(
            session, task_id, "executing" if decision == "approve" else "rejected"
        )
        async for chunk in self._graph.astream(
            Command(resume=decision), config=_config(task_id), stream_mode="custom"
        ):
            yield {"type": "tool", **chunk}

        snapshot = await self._graph.aget_state(_config(task_id))
        values = snapshot.values or {}
        status = values.get("status", "completed")
        await set_status(session, task_id, status)
        yield {"type": "report", "status": status, "report": values.get("report", {})}
