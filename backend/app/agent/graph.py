"""The Sprint 1 architecture spike: a one-node LangGraph that pings Claude.

This is deliberately minimal — it proves the end-to-end path
(frontend → FastAPI → LangGraph → Claude → back) works before any WordPress
capability is built. It uses ``langchain_anthropic.ChatAnthropic`` so that
later skill nodes share the same model interface (tool-calling, structured
output) rather than raw SDK calls.
"""

from __future__ import annotations

from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.config import get_settings


class PingState(TypedDict):
    """State threaded through the ping graph."""

    prompt: str
    response: str


def _extract_text(message: AIMessage) -> str:
    """Flatten an AIMessage's content into plain text.

    ChatAnthropic returns either a string or a list of content blocks; we only
    care about the text here.
    """
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


async def ping_node(state: PingState) -> dict[str, str]:
    """Single agent node: send the prompt to Claude and return its reply.

    Uses the fast/narrow model per the AGENTS.md routing rule — this is a
    cheap, single-shot call, not orchestrator-level reasoning.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env "
            "(see .env.example) before calling the agent."
        )

    llm = ChatAnthropic(
        model=settings.fast_model,
        api_key=settings.anthropic_api_key,
        max_tokens=settings.max_tokens,
    )
    reply = await llm.ainvoke([HumanMessage(content=state["prompt"])])
    return {"response": _extract_text(reply)}


def build_ping_graph():
    """Compile and return the single-node ping graph."""
    builder = StateGraph(PingState)
    builder.add_node("ping", ping_node)
    builder.add_edge(START, "ping")
    builder.add_edge("ping", END)
    return builder.compile()


# Compiled once at import; the graph is stateless and safe to reuse.
ping_graph = build_ping_graph()
