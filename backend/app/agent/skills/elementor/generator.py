"""Generate a ``PageSpec`` (the constrained IR) from a plain-language brief.

Claude only fills this small, validated spec — never raw Elementor JSON. The
model is given the section catalog (types + slot names) so it can only reference
sections and slots that actually exist. Constructed lazily so importing the
skill doesn't require an API key.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.skills.elementor.library import catalog
from app.agent.skills.elementor.schema import PageSpec
from app.config import get_settings

_SYSTEM = (
    "You are a landing-page designer. Given a brief, produce a PageSpec: a title "
    "and an ordered list of 3–4 sections that make a coherent landing page.\n"
    "Only use section types from this catalog, and only fill the listed slots:\n"
    "{catalog}\n"
    "Rules: start with a 'hero'. Use 'features' or 'pricing' (grid sections) by "
    "providing an `items` list — each item fills the item_slots. Fill scalar "
    "slots via `content`. Keep copy concise and real (no lorem ipsum)."
)


class Generator(Protocol):
    async def generate(self, brief: str) -> PageSpec: ...


class LLMGenerator:
    def __init__(self, llm: BaseChatModel | None = None):
        self._provided = llm
        self._structured: Any = None

    def _model(self) -> Any:
        if self._structured is None:
            settings = get_settings()
            base = self._provided or ChatAnthropic(
                model=settings.orchestrator_model,
                api_key=settings.anthropic_api_key,
                max_tokens=2048,
            )
            self._structured = base.with_structured_output(PageSpec)
        return self._structured

    async def generate(self, brief: str) -> PageSpec:
        system = _SYSTEM.format(catalog=json.dumps(catalog(), indent=2))
        result = await self._model().ainvoke(
            [SystemMessage(system), HumanMessage(brief)]
        )
        # with_structured_output yields a PageSpec; be defensive if a dict comes back.
        return result if isinstance(result, PageSpec) else PageSpec.model_validate(result)


def build_generator() -> Generator:
    return LLMGenerator()
