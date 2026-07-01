"""Unit tests for TaskManager (DB service + run_approved mocked)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

import app.agent.orchestrator.graph as graph_mod
import app.agent.orchestrator.manager as manager_mod
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.manager import TaskManager
from app.agent.orchestrator.state import PlannedStep


class FakePlanner:
    async def plan(self, instruction: str, site_slug: str) -> list[PlannedStep]:
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


@pytest.fixture
def stub_db(monkeypatch):
    """No-op the tasks table so the manager runs without Postgres."""
    statuses: list[str] = []

    async def _create_task(session, *, task_id, site_slug, instruction):
        return None

    async def _set_status(session, task_id, status):
        statuses.append(status)

    monkeypatch.setattr(manager_mod, "create_task", _create_task)
    monkeypatch.setattr(manager_mod, "set_status", _set_status)
    return statuses


async def test_start_returns_plan_and_pauses(stub_db):
    manager = TaskManager(build_orchestrator(MemorySaver(), planner=FakePlanner()))
    result = await manager.start(session=None, instruction="Create Home", site_slug="acme")

    assert result["task_id"]
    assert len(result["plan"]) == 1
    assert result["plan"][0]["tool"] == "wp_create_page"
    assert "awaiting_approval" in stub_db


async def test_resume_streams_events_then_report(stub_db, monkeypatch):
    async def fake_run_approved(tool, args):
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", fake_run_approved)

    manager = TaskManager(build_orchestrator(MemorySaver(), planner=FakePlanner()))
    started = await manager.start(session=None, instruction="Create Home", site_slug="acme")

    events = [
        ev
        async for ev in manager.resume_stream(None, started["task_id"], "approve")
    ]
    tool_events = [e for e in events if e["type"] == "tool"]
    report_events = [e for e in events if e["type"] == "report"]

    assert [e["status"] for e in tool_events] == ["running", "success"]
    assert len(report_events) == 1
    assert report_events[0]["status"] == "completed"
    assert report_events[0]["report"]["applied"] == 1


async def test_get_plan_refinds_paused_task(stub_db):
    manager = TaskManager(build_orchestrator(MemorySaver(), planner=FakePlanner()))
    started = await manager.start(session=None, instruction="Create Home", site_slug="acme")

    # Simulates the UI re-fetching a paused task's plan.
    plan = await manager.get_plan(started["task_id"])
    assert plan is not None
    assert len(plan["plan"]) == 1
