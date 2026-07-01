"""Integration test: a paused task survives a 'restart' (Postgres checkpointer).

Marked ``integration`` and self-skipping when Postgres is unavailable. Proves
the Sprint 4 persistence claim: a task interrupted for approval can be re-loaded
and resumed by a freshly built graph on a new connection — i.e. after a server
restart.

    docker compose up -d postgres
    uv run pytest -m integration -k persistence
"""

from __future__ import annotations

import pytest
from langgraph.types import Command

import app.agent.orchestrator.graph as graph_mod
from app.agent.orchestrator.checkpointer import open_postgres_checkpointer
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.state import PlannedStep

pytestmark = pytest.mark.integration

THREAD = "integration-persistence-1"


class FakePlanner:
    async def plan(self, instruction, site_slug):
        return [
            PlannedStep(
                id="step-0",
                tool="wp_create_page",
                args={"site_slug": site_slug, "title": "Home"},
                title="Create page: Home",
                channel="REST API",
                requires_approval=True,
                preview={"status": "needs_approval"},
            )
        ]


async def _try_checkpointer():
    cm = open_postgres_checkpointer()
    try:
        saver = await cm.__aenter__()
    except Exception:
        return None, None
    return cm, saver


async def test_paused_task_survives_restart(monkeypatch):
    config = {"configurable": {"thread_id": THREAD}}

    # --- "process 1": plan and pause at the approval interrupt ---
    cm1, saver1 = await _try_checkpointer()
    if saver1 is None:
        pytest.skip("Postgres checkpointer unavailable")
    try:
        graph1 = build_orchestrator(saver1, planner=FakePlanner())
        await graph1.ainvoke(
            {"instruction": "create Home", "site_slug": "acme"}, config=config
        )
        snap = await graph1.aget_state(config)
        assert snap.next == ("approve",)
    finally:
        await cm1.__aexit__(None, None, None)

    # --- "process 2" (fresh graph + connection): resume the persisted task ---
    async def fake_run_approved(tool, args):
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", fake_run_approved)

    cm2, saver2 = await _try_checkpointer()
    assert saver2 is not None
    try:
        graph2 = build_orchestrator(saver2, planner=FakePlanner())
        reloaded = await graph2.aget_state(config)
        assert reloaded.values["plan"], "plan did not survive the restart"

        async for _ in graph2.astream(
            Command(resume="approve"), config=config, stream_mode="custom"
        ):
            pass
        final = await graph2.aget_state(config)
        assert final.values["status"] == "completed"
    finally:
        await cm2.__aexit__(None, None, None)
