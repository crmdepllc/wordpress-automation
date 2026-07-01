"""Celery tasks.

``execute_task`` resumes a paused orchestration task in the worker, off the
HTTP request path. It rebuilds the graph against the shared Postgres
checkpointer so it resumes exactly the interrupted task the API created.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agent.orchestrator.checkpointer import open_postgres_checkpointer
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.manager import TaskManager
from app.db.session import get_sessionmaker
from app.worker.celery_app import celery_app


async def _resume(task_id: str, decision: str) -> list[dict[str, Any]]:
    async with open_postgres_checkpointer() as saver:
        manager = TaskManager(build_orchestrator(saver))
        async with get_sessionmaker()() as session:
            return [
                event
                async for event in manager.resume_stream(session, task_id, decision)
            ]


@celery_app.task(name="orchestrator.execute")
def execute_task(task_id: str, decision: str) -> list[dict[str, Any]]:
    """Resume a task and return its execution events (worker-side)."""
    return asyncio.run(_resume(task_id, decision))
