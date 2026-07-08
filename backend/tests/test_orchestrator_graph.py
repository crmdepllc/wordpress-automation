"""Unit tests for the orchestration graph:
plan → approve(interrupt) → snapshot → execute → report.

Uses MemorySaver and a fake planner, and monkeypatches ``run_approved`` (and,
for the snapshot node, ``_site_credentials``/``WpCli``) so no real tools/DB are
touched. Covers the interrupt pause, the approve path (snapshot + execute +
stream events), the reject path (no writes), and halt-on-first-failure with
downstream steps reported ``skipped``.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import app.agent.orchestrator.graph as graph_mod
from app.agent.orchestrator.graph import build_orchestrator
from app.agent.orchestrator.state import PlannedStep
from app.wp.schemas import CliResult


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


class ThreeStepPlanner:
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
            PlannedStep(
                id="step-2",
                tool="wp_apply_theme",
                args={"site_slug": site_slug, "brief": "dark minimal"},
                title="Apply theme",
                channel="WP-CLI",
                requires_approval=True,
                preview={"status": "needs_approval"},
            ),
        ]


def _graph(planner=None):
    return build_orchestrator(MemorySaver(), planner=planner or FakePlanner())


async def _run_to_interrupt(graph, thread_id, planner_instruction="install elementor then create Home"):
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(
        {"instruction": planner_instruction, "site_slug": "acme"},
        config=config,
    )
    return config


class FakeCreds:
    slug = "acme"


async def _fake_site_credentials(site_slug: str):
    return FakeCreds()


class FakeWpCliSnapshotOk:
    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def export_db(self, filename):
        return CliResult(command=f"db export {filename}", exit_code=0, stdout="ok")


class FakeWpCliSnapshotFails:
    @classmethod
    def from_credentials(cls, creds):
        return cls()

    async def export_db(self, filename):
        return CliResult(command=f"db export {filename}", exit_code=1, stderr="no db")


def _mock_snapshot(monkeypatch, wpcli_cls=FakeWpCliSnapshotOk):
    monkeypatch.setattr(graph_mod, "_site_credentials", _fake_site_credentials)
    monkeypatch.setattr(graph_mod, "WpCli", wpcli_cls)


async def test_pauses_at_approval_interrupt():
    graph = _graph()
    config = await _run_to_interrupt(graph, "t-pause")
    snap = await graph.aget_state(config)

    # Paused at the approve node, plan already computed and persisted.
    assert snap.next == ("approve",)
    assert len(snap.values["plan"]) == 2
    interrupts = [i for task in snap.tasks for i in task.interrupts]
    assert interrupts and interrupts[0].value["type"] == "approval_request"


async def test_approve_takes_snapshot_then_executes_and_streams_events(monkeypatch):
    calls: list[str] = []

    async def fake_run_approved(tool, args):
        calls.append(tool)
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", fake_run_approved)
    _mock_snapshot(monkeypatch)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-approve")

    events = []
    async for chunk in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        events.append(chunk)

    # Two steps → a running + a success event each (snapshot emits nothing).
    assert [e["status"] for e in events] == ["running", "success", "running", "success"]
    assert calls == ["wp_install_plugin", "wp_create_page"]

    snap = await graph.aget_state(config)
    assert snap.values["status"] == "completed"
    assert snap.values["snapshot"]["taken"] is True
    assert snap.values["report"] == {
        "outcome": "completed",
        "applied": 2,
        "failed": 0,
        "skipped": 0,
        "total": 2,
        "snapshot": snap.values["snapshot"],
    }


async def test_snapshot_skipped_when_plan_has_no_writes(monkeypatch):
    class ReadOnlyPlanner:
        async def plan(self, instruction, site_slug):
            return [
                PlannedStep(
                    id="step-0",
                    tool="wp_list_pages",
                    args={"site_slug": site_slug},
                    title="List pages",
                    channel="REST API",
                    requires_approval=False,
                    preview=None,
                )
            ]

    async def must_not_be_called(site_slug):
        raise AssertionError("credentials fetched for a read-only plan!")

    monkeypatch.setattr(graph_mod, "_site_credentials", must_not_be_called)
    monkeypatch.setattr(graph_mod, "run_approved", lambda tool, args: {"status": "ok"})

    graph = _graph(planner=ReadOnlyPlanner())
    config = await _run_to_interrupt(graph, "t-readonly")
    async for _ in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.values["snapshot"] == {"taken": False, "reason": "no writes in plan"}


async def test_snapshot_failure_is_non_fatal(monkeypatch):
    async def fake_run_approved(tool, args):
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", fake_run_approved)
    _mock_snapshot(monkeypatch, wpcli_cls=FakeWpCliSnapshotFails)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-snapshot-fail")
    async for _ in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        pass

    snap = await graph.aget_state(config)
    # Execution still completes even though the snapshot failed.
    assert snap.values["snapshot"]["taken"] is False
    assert snap.values["report"]["outcome"] == "completed"


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


async def test_failed_step_is_reported_and_marks_outcome_failed(monkeypatch):
    async def failing(tool, args):
        if tool == "wp_create_page":
            raise RuntimeError("boom")
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", failing)
    _mock_snapshot(monkeypatch)

    graph = _graph()
    config = await _run_to_interrupt(graph, "t-fail")
    async for _ in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.values["report"] == {
        "outcome": "failed",
        "applied": 1,
        "failed": 1,
        "skipped": 0,
        "total": 2,
        "snapshot": snap.values["snapshot"],
    }


async def test_step_after_failure_is_skipped_not_run(monkeypatch):
    calls: list[str] = []

    async def failing(tool, args):
        calls.append(tool)
        if tool == "wp_create_page":
            raise RuntimeError("boom")
        return {"status": "applied"}

    monkeypatch.setattr(graph_mod, "run_approved", failing)
    _mock_snapshot(monkeypatch)

    graph = _graph(planner=ThreeStepPlanner())
    config = await _run_to_interrupt(graph, "t-skip")

    events = []
    async for chunk in graph.astream(
        Command(resume="approve"), config=config, stream_mode="custom"
    ):
        events.append(chunk)

    # step-2 (theme) is never actually invoked — only step-0 and step-1 ran.
    assert calls == ["wp_install_plugin", "wp_create_page"]
    assert [e["status"] for e in events] == [
        "running", "success",  # step-0
        "running", "error",    # step-1
        "skipped",              # step-2
    ]

    snap = await graph.aget_state(config)
    assert snap.values["report"] == {
        "outcome": "failed",
        "applied": 1,
        "failed": 1,
        "skipped": 1,
        "total": 3,
        "snapshot": snap.values["snapshot"],
    }
