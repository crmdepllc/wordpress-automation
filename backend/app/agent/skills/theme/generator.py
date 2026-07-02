"""Generate a ``ThemeSpec`` from a brief (Claude, lazy model)."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.skills.theme.schema import ThemeSpec
from app.config import get_settings

_SYSTEM = (
    "You are a brand designer. Given a brief, produce a cohesive theme: a color "
    "palette (primary, secondary, accent, text, background) as hex codes with "
    "good contrast, heading/body font families (real Google Fonts), and a short "
    "footer line. Match the requested mood (e.g. dark, minimal, playful)."
)


class ThemeGenerator(Protocol):
    async def generate(self, brief: str) -> ThemeSpec: ...


class LLMThemeGenerator:
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
            self._structured = base.with_structured_output(ThemeSpec)
        return self._structured

    async def generate(self, brief: str) -> ThemeSpec:
        result = await self._model().ainvoke(
            [SystemMessage(_SYSTEM), HumanMessage(brief)]
        )
        return result if isinstance(result, ThemeSpec) else ThemeSpec.model_validate(result)


def build_theme_generator() -> ThemeGenerator:
    return LLMThemeGenerator()
