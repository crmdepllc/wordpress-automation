"""Unit tests for the thin gated NL agent path (LLM mocked)."""

from __future__ import annotations

import pytest

from app.agent.wp_agent import WpAgent, run_approved


class FakeResponse:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class FakeLLM:
    """Minimal stand-in: records bind_tools and returns canned tool calls."""

    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return FakeResponse(self._tool_calls)


async def test_propose_write_tool_returns_preview_not_write():
    llm = FakeLLM([{"name": "wp_create_page", "args": {"title": "Home"}}])
    proposal = await WpAgent(llm=llm).propose("Create a Home page", "acme")
    assert proposal is not None
    assert proposal.tool == "wp_create_page"
    assert proposal.requires_approval is True
    # Planning must not apply the write — preview is the gated response.
    assert proposal.preview["status"] == "needs_approval"
    # site_slug is injected into the args regardless of what the model returned.
    assert proposal.args["site_slug"] == "acme"


async def test_propose_read_tool_needs_no_approval():
    llm = FakeLLM([{"name": "wp_list_pages", "args": {}}])
    proposal = await WpAgent(llm=llm).propose("What pages exist?", "acme")
    assert proposal is not None
    assert proposal.requires_approval is False
    assert proposal.preview is None


async def test_propose_no_tool_call_returns_none():
    proposal = await WpAgent(llm=FakeLLM([])).propose("hello", "acme")
    assert proposal is None


async def test_run_approved_unknown_tool_raises():
    with pytest.raises(KeyError):
        await run_approved("not_a_tool", {})
