"""Unit tests for the LLM planner (model mocked)."""

from __future__ import annotations

from app.agent.orchestrator.planner import LLMPlanner


class FakeResponse:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class FakeLLM:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return FakeResponse(self._tool_calls)


async def test_plan_builds_ordered_steps_with_previews():
    llm = FakeLLM(
        [
            {"name": "wp_install_plugin", "args": {"plugin_slug": "elementor"}},
            {"name": "wp_create_page", "args": {"title": "Home"}},
        ]
    )
    steps = await LLMPlanner(llm=llm).plan("install then create home", "acme")

    assert [s.tool for s in steps] == ["wp_install_plugin", "wp_create_page"]
    assert [s.id for s in steps] == ["step-0", "step-1"]
    # site_slug is injected into every step regardless of model output.
    assert all(s.args["site_slug"] == "acme" for s in steps)
    # Both are writes → gated, with a needs_approval preview (no site touched).
    assert all(s.requires_approval for s in steps)
    assert steps[0].preview["status"] == "needs_approval"
    assert steps[0].channel == "WP-CLI"
    assert steps[1].channel == "REST API"


async def test_plan_empty_when_no_tool_calls():
    steps = await LLMPlanner(llm=FakeLLM([])).plan("hello", "acme")
    assert steps == []
