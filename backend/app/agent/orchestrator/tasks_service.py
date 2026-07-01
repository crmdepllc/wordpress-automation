"""CRUD for the tasks metadata table (create / get / list / status update)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task


def new_task_id() -> str:
    return str(uuid.uuid4())


async def create_task(
    session: AsyncSession, *, task_id: str, site_slug: str, instruction: str
) -> Task:
    task = Task(
        id=task_id, site_slug=site_slug, instruction=instruction, status="planning"
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, task_id: str) -> Task | None:
    return await session.get(Task, task_id)


async def set_status(session: AsyncSession, task_id: str, status: str) -> None:
    task = await session.get(Task, task_id)
    if task is not None:
        task.status = status
        await session.commit()


async def list_tasks(session: AsyncSession, site_slug: str | None = None) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if site_slug:
        stmt = stmt.where(Task.site_slug == site_slug)
    return list(await session.scalars(stmt))
