"""HTTP-contract tests for /api/tasks (DB + planner + run_approved mocked).

Verifies the wire format the frontend proxies depend on: start returns a plan
with a task id; resume streams ndjson tool events then a report.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

import app.agent.orchestrator.graph as graph_mod
import app.agent.orchestrator.manager as manager_mod
import app.api.task_routes as task_routes
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.manager import TaskManager
from app.agent.orchestrator.state import PlannedStep
from app.db.session import get_session
from app.main import app


class FakePlanner:
    async def plan(self, instruction, site_slug):
        return [
            PlannedStep(
                id="step-0",
                tool="wp_install_plugin",
                args={"site_slug": site_slug, "plugin_slug": "elementor"},
                title="Install plugin: elementor",
                channel="WP-CLI",
                requires_approval=True,
                preview={"status": "needs_approval"},
            ),
            PlannedStep(
                id="step-1",
                tool="wp_create_page",
                args={"site_slug": site_slug, "title": "Home"},
                title="Create page: Home",
                channel="REST API",
                requires_approval=True,
                preview={"status": "needs_approval"},
            ),
        ]


class _DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


@pytest.fixture
def client(monkeypatch):
    # No-op the DB layer used by the routes/manager.
    async def _noop_create(session, *, task_id, site_slug, instruction):
        return None

    async def _noop_status(session, task_id, status):
        return None

    async def _fake_get_task(session, task_id):
        return object()  # truthy → route proceeds

    async def _fake_run_approved(tool, args):
        return {"status": "applied"}

    async def _fake_site_credentials(site_slug):
        raise LookupError("no site registered in this unit test")

    monkeypatch.setattr(manager_mod, "create_task", _noop_create)
    monkeypatch.setattr(manager_mod, "set_status", _noop_status)
    monkeypatch.setattr(task_routes, "get_task", _fake_get_task)
    monkeypatch.setattr(task_routes, "get_sessionmaker", lambda: (lambda: _DummySession()))
    monkeypatch.setattr(graph_mod, "run_approved", _fake_run_approved)
    # Snapshot degrades gracefully without a DB; mock it for a fast, hermetic test.
    monkeypatch.setattr(graph_mod, "_site_credentials", _fake_site_credentials)

    async def _fake_session():
        yield _DummySession()

    app.dependency_overrides[get_session] = _fake_session
    with TestClient(app) as c:
        # Replace the lifespan-built (real-planner) manager with a fake one.
        app.state.orchestrator = TaskManager(
            build_orchestrator(MemorySaver(), planner=FakePlanner())
        )
        yield c
    app.dependency_overrides.clear()


def test_start_returns_plan_with_task_id(client):
    resp = client.post(
        "/api/tasks",
        json={"instruction": "install elementor then create Home", "site_slug": "acme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "awaiting_approval"
    assert data["task_id"]
    assert len(data["plan"]) == 2
    assert data["plan"][0]["tool"] == "wp_install_plugin"


def test_approve_streams_events_then_report(client):
    start = client.post(
        "/api/tasks", json={"instruction": "do it", "site_slug": "acme"}
    ).json()
    task_id = start["task_id"]

    resp = client.post(f"/api/tasks/{task_id}/resume", json={"decision": "approve"})
    assert resp.status_code == 200
    lines = [json.loads(l) for l in resp.text.splitlines() if l.strip()]

    tool_events = [e for e in lines if e["type"] == "tool"]
    reports = [e for e in lines if e["type"] == "report"]
    assert [e["status"] for e in tool_events] == ["running", "success", "running", "success"]
    assert reports[-1]["status"] == "completed"
    assert reports[-1]["report"]["applied"] == 2


def test_reject_reports_without_executing(client):
    start = client.post(
        "/api/tasks", json={"instruction": "do it", "site_slug": "acme"}
    ).json()
    resp = client.post(
        f"/api/tasks/{start['task_id']}/resume", json={"decision": "reject"}
    )
    lines = [json.loads(l) for l in resp.text.splitlines() if l.strip()]
    assert all(e["type"] == "report" for e in lines)
    assert lines[-1]["status"] == "rejected"
