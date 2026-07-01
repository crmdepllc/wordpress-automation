"""HTTP routes for the orchestration graph (Sprint 4).

  POST /api/tasks               — start a task; runs to the approval interrupt
  GET  /api/tasks/{id}          — task metadata (status) + its plan if paused
  POST /api/tasks/{id}/resume   — approve/reject; streams execution events (ndjson)

The frontend's Next.js API routes proxy to these. The graph pauses at a real
``interrupt()`` and only resumes after an explicit decision — the approval gate.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator.manager import TaskManager
from app.agent.orchestrator.tasks_service import get_task
from app.db.session import get_session, get_sessionmaker

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _manager(request: Request) -> TaskManager:
    manager = getattr(request.app.state, "orchestrator", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized.")
    return manager


class StartTaskIn(BaseModel):
    instruction: str = Field(..., min_length=1)
    site_slug: str


@router.post("")
async def start_task(
    body: StartTaskIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = await _manager(request).start(session, body.instruction, body.site_slug)
    except Exception as exc:  # planning/model failure
        raise HTTPException(status_code=400, detail=f"Planning failed: {exc}") from exc
    return {"status": "awaiting_approval", **result}


@router.get("/{task_id}")
async def get_task_detail(
    task_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    plan = await _manager(request).get_plan(task_id)
    return {
        "task_id": task.id,
        "status": task.status,
        "instruction": task.instruction,
        "site_slug": task.site_slug,
        "plan": (plan or {}).get("plan", []),
        "summary": (plan or {}).get("summary", ""),
    }


class ResumeIn(BaseModel):
    decision: Literal["approve", "reject"]


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    body: ResumeIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    task = await get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    manager = _manager(request)

    async def stream() -> Any:
        # Use a dedicated session so it outlives the request-scoped dependency
        # for the whole duration of the stream.
        async with get_sessionmaker()() as stream_session:
            async for event in manager.resume_stream(stream_session, task_id, body.decision):
                yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
