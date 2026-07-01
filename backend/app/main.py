"""FastAPI application entry point.

Creates the app, configures CORS for the dashboard, and mounts the API
routers. On startup a lifespan opens the Postgres checkpointer, compiles the
orchestration graph, and stores a TaskManager on ``app.state`` — falling back
to an in-memory checkpointer (no persistence) if Postgres is unavailable so the
app still boots. Run locally with ``fastapi dev app/main.py`` or, in Docker,
``fastapi run app/main.py``.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import MemorySaver

from app.agent.orchestrator.checkpointer import open_postgres_checkpointer
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.manager import TaskManager
from app.api.routes import router
from app.api.task_routes import router as task_router
from app.api.wp_routes import router as wp_router
from app.config import get_settings

logger = logging.getLogger("app")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.configure_langsmith():
        logger.info("LangSmith tracing enabled (project=%s).", settings.langsmith_project)

    checkpointer_cm = None
    try:
        checkpointer_cm = open_postgres_checkpointer()
        saver = await checkpointer_cm.__aenter__()
        graph = build_orchestrator(saver)
        logger.info("Orchestrator ready (Postgres checkpointer).")
    except Exception as exc:  # Postgres down — still boot, without persistence
        logger.warning(
            "Postgres checkpointer unavailable (%s); using in-memory checkpointer "
            "(paused tasks will NOT survive a restart).",
            exc,
        )
        checkpointer_cm = None
        graph = build_orchestrator(MemorySaver())

    app.state.orchestrator = TaskManager(graph)
    try:
        yield
    finally:
        if checkpointer_cm is not None:
            await checkpointer_cm.__aexit__(None, None, None)


app = FastAPI(
    title="WordPress Automation Agent",
    version="0.1.0",
    description="Agentic WordPress site builder — orchestration graph & approval gate.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(wp_router)
app.include_router(task_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"service": "wordpress-automation-agent", "status": "running"}
