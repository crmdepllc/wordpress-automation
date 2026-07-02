"""Generate ``SeoMeta`` for a subject (Claude, lazy model)."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.skills.seo.schema import SeoMeta
from app.config import get_settings

_SYSTEM = (
    "You are an SEO specialist. Given a page subject, write a compelling meta "
    "title (≤ 60 characters) and meta description (≤ 160 characters), and pick "
    "the most fitting schema.org type. Be specific and keyword-aware; do not "
    "keyword-stuff."
)


class SeoGenerator(Protocol):
    async def generate(self, subject: str) -> SeoMeta: ...


class LLMSeoGenerator:
    def __init__(self, llm: BaseChatModel | None = None):
        self._provided = llm
        self._structured: Any = None

    def _model(self) -> Any:
        if self._structured is None:
            settings = get_settings()
            base = self._provided or ChatAnthropic(
                model=settings.fast_model,
                api_key=settings.anthropic_api_key,
                max_tokens=512,
            )
            self._structured = base.with_structured_output(SeoMeta)
        return self._structured

    async def generate(self, subject: str) -> SeoMeta:
        result = await self._model().ainvoke(
            [SystemMessage(_SYSTEM), HumanMessage(subject)]
        )
        return result if isinstance(result, SeoMeta) else SeoMeta.model_validate(result)


def build_seo_generator() -> SeoGenerator:
    return LLMSeoGenerator()
