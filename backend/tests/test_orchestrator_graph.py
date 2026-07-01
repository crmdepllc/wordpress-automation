"""Unit tests for the orchestration graph: plan → approve(interrupt) → execute.

Uses MemorySaver and a fake planner, and monkeypatches ``run_approved`` so no
real tools/DB are touched. Covers the interrupt pause, the approve path
(executes + streams events), and the reject path (no writes).
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import app.agent.orchestrator.graph as graph_mod
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.state import PlannedStep


class FakePlanner:
    async def plan(self, instruction: str, site_slug: str) -> list[PlannedStep]:
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


def _graph():
    return build_orchestrator(MemorySaver(), planner=FakePlanner())


async def _run_to_interrupt(graph, thread_id):
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(
        {"instruction": "install elementor then create Home", "site_slug": "acme"},
        config=config,
    )
    return config


async def test_pauses_at_approval_interrupt():
    graph = _graph()
    config = await _run_to_interrupt(graph, "t-pause")
    snap = await graph.aget_state(config)

    # Paused at the approve node, plan already computed and persisted.
    assert snap.next == ("approve",)
    assert len(snap.values["plan"]) == 2
    interrupts = [i for task in snap.tasks for i in task.interrupts]
    assert interrupts and interrupts[0].value["type"] == "approval_request"


async def test_approve_executes_and_streams_events(monkeypatch):
    calls: list[str] = []

    async def fake_run_approved(tool, args):
        calls.append(tool)
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", fake_run_approved)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-approve")

    events = []
    async for chunk in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        events.append(chunk)

    # Two steps → a running + a success event each.
    assert [e["status"] for e in events] == ["running", "success", "running", "success"]
    assert calls == ["wp_install_plugin", "wp_create_page"]

    snap = await graph.aget_state(config)
    assert snap.values["status"] == "completed"
    assert snap.values["report"] == {
        "outcome": "completed",
        "applied": 2,
        "failed": 0,
        "total": 2,
    }


async def test_reject_makes_no_writes(monkeypatch):
    async def must_not_run(tool, args):
        raise AssertionError("run_approved called on a rejected plan!")

    monkeypatch.setattr(graph_mod, "run_approved", must_not_run)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-reject")

    events = [
        chunk
        async for chunk in graph.astream(
            Command(resume="reject"), config=config, stream_mode="custom"
        )
    ]
    assert events == []  # nothing executed

    snap = await graph.aget_state(config)
    assert snap.values["status"] == "rejected"
    assert snap.values["report"]["outcome"] == "rejected"


async def test_failed_step_is_reported(monkeypatch):
    async def failing(tool, args):
        if tool == "wp_create_page":
            raise RuntimeError("boom")
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", failing)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-fail")
    async for _ in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.values["report"] == {
        "outcome": "completed",
        "applied": 1,
        "failed": 1,
        "total": 2,
    }
