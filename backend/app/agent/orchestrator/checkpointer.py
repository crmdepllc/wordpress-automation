"""Checkpointer wiring.

The app uses ``AsyncPostgresSaver`` so a paused (interrupted) task survives a
server restart. Unit tests pass a ``MemorySaver`` instead, so they run without
Postgres. The Postgres saver is created as an async context manager and kept
open for the app's lifetime (see app.main lifespan).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _psycopg_conn_string() -> str:
    # AsyncPostgresSaver uses psycopg (not asyncpg); strip the SQLAlchemy driver.
    url = get_settings().database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


@asynccontextmanager
async def open_postgres_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield a set-up Postgres checkpointer; runs ``setup()`` once on entry."""
    async with AsyncPostgresSaver.from_conn_string(_psycopg_conn_string()) as saver:
        await saver.setup()
        yield saver
