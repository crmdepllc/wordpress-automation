"""Generate a ``PostDraft`` from a brief (Gemini, lazy model).

Per AGENTS.md, Gemini writes all visible copy; Claude is reserved for page
structure/development (see ``elementor/generator.py``).
"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.skills.content.schema import PostDraft
from app.config import get_settings

_SYSTEM = (
    "You are a content writer. Given a brief, write ONE blog post: a concise, "
    "specific title; a well-structured HTML body (headings, paragraphs, lists); "
    "a one-sentence excerpt; and 1–2 categories and 2–4 tags as short human "
    "names. No lorem ipsum — write real copy on the topic."
)


class ContentGenerator(Protocol):
    async def generate(self, brief: str) -> PostDraft: ...


class LLMContentGenerator:
    def __init__(self, llm: BaseChatModel | None = None):
        self._provided = llm
        self._structured: Any = None

    def _model(self) -> Any:
        if self._structured is None:
            settings = get_settings()
            base = self._provided or ChatGoogleGenerativeAI(
                model=settings.gemini_content_model,
                api_key=settings.gemini_api_key,
                max_tokens=2048,
            )
            self._structured = base.with_structured_output(PostDraft)
        return self._structured

    async def generate(self, brief: str) -> PostDraft:
        result = await self._model().ainvoke(
            [SystemMessage(_SYSTEM), HumanMessage(brief)]
        )
        return result if isinstance(result, PostDraft) else PostDraft.model_validate(result)


def build_content_generator() -> ContentGenerator:
    return LLMContentGenerator()
