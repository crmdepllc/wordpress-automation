"""Generate a ``PageSpec`` (the constrained IR) from a plain-language brief.

Two models, two jobs, one IR — never raw Elementor JSON:

- ``LLMGenerator`` (Claude) fills page *structure*: which sections, in what
  order, with how many items, plus design slots (icon/background_color/
  accent_color/heading_color/image_prompt). It leaves every text slot empty.
- ``LLMCopyGenerator`` (Gemini) takes that skeleton and fills the empty text
  slots (heading/subheading/cta_text/item titles/etc.) with real copy. It
  never touches structure or design slots — including ``image_prompt``,
  which a later step (``images/resolver.py``) turns into a real, uploaded
  image, never the copywriter.

Both are given the section catalog (types + slot names) so neither can
reference a section or slot that doesn't exist. Constructed lazily so
importing the skill doesn't require an API key.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.skills.elementor.icons import ALLOWED_ICONS
from app.agent.skills.elementor.library import catalog
from app.agent.skills.elementor.schema import PageSpec
from app.config import get_settings

# Slots that are design/structural decisions, not visible copy — Claude fills
# these (if it wants to); everything else is text and is left blank for the
# Gemini copy pass to fill in. ``image_prompt`` is a structural decision (does
# this section want an image, and roughly what should it show) rather than
# visible text — the prompt itself is never shown on the page, so it belongs
# to Claude's structural pass, not the Gemini copywriter.
DESIGN_SLOTS = frozenset(
    {"icon", "background_color", "accent_color", "heading_color", "image_prompt"}
)

_SYSTEM = (
    "You are a landing-page architect. Given a brief, produce a PageSpec: a title "
    "and an ordered list of 3–6 sections that make a coherent page for the "
    "brief's type of site (e.g. a portfolio favors testimonials over pricing; "
    "a SaaS product favors pricing/faq over testimonials; a local service "
    "business — a notary, clinic, law firm, salon — favors 'about' and "
    "'badges' alongside 'features' and 'testimonials' to read as credible and "
    "established).\n"
    "Only use section types from this catalog, and only fill the listed slots:\n"
    "{catalog}\n"
    "Rules: start with a 'hero'. Any section whose catalog entry lists "
    "item_slots (e.g. features, pricing, testimonials, stats, faq, badges, "
    "footer) takes an `items` list — decide how many items it needs (typically "
    "2–4) and include one dict per item, but ONLY set the design slots below "
    "on each item/section — leave every other listed slot (heading, "
    "subheading, cta_text, eyebrow, item titles/descriptions/quotes/etc., "
    "any text slot) OUT of the dict entirely. A separate writer fills those "
    "in afterward; you are choosing structure, not copy.\n"
    "The only slots you may set values for are these design slots, where the "
    "section's catalog entry lists them: 'icon' must be one of this exact "
    "list (the site's Elementor install only has these icons available — "
    "anything else silently breaks): {icons}. Format it as 'fas fa-<name>', "
    "e.g. 'fas fa-bolt'. 'background_color' is optional (a hex code) — omit "
    "it to use the site's default background. Alternate background_color "
    "across consecutive sections (e.g. default, then a light tint, then "
    "default, then a dark band) so the page reads as distinct blocks rather "
    "than one undifferentiated scroll — don't leave every section on the "
    "same background. If you set 'background_color' to something dark, also "
    "set 'heading_color' (where offered) to a light hex code such as "
    "'#ffffff' so text stays readable, and vice versa for a light "
    "background. 'accent_color' is optional — if omitted, buttons and icon "
    "badges fall back to a generic default that can clash with the rest of "
    "the page, so pick one bold accent hex up front and reuse the *exact "
    "same* value for every 'accent_color' slot on the page (it drives "
    "buttons, icon-circle backgrounds, and small accent details "
    "consistently) — never pick a different accent per section. 'image_prompt' "
    "is optional, only where the section's catalog entry lists it: set it to a "
    "specific, vivid description of a real photo/illustration that suits the "
    "brief (e.g. 'a warm, natural-light portrait of a notary signing documents "
    "at a wooden desk') if the section would genuinely benefit from an image — "
    "omit it entirely if it wouldn't (not every page needs one, and not every "
    "section that supports it should use it). This is an instruction for an "
    "image generator, not visible page text — never put an 'image_prompt' "
    "value in front of a user."
)

_COPY_SYSTEM = (
    "You are a copywriter. You are given a brief and a page skeleton — an "
    "ordered list of sections, each with the exact text slots that need "
    "copy (design slots like icon/color/image_prompt are already set and "
    "must not be touched — 'image_prompt' in particular is an instruction "
    "for a separate image generator, not something to rewrite as text). "
    "Write concise, specific, real copy for every listed slot — no lorem "
    "ipsum, no placeholder text. 'eyebrow' is a short overline label (e.g. "
    "'WHY CHOOSE US'), not a repeat of the heading. Sections that list "
    "'heading' render a title above their items — always fill it so the "
    "section reads as a distinct, titled block. Match tone and subject to "
    "the brief throughout. Return the same structure you were given, with "
    "every empty text slot filled in."
)


class Generator(Protocol):
    async def generate(self, brief: str) -> PageSpec: ...


class LLMGenerator:
    """Claude: brief -> structural skeleton (design slots only, text slots empty)."""

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
        system = _SYSTEM.format(
            catalog=json.dumps(catalog(), indent=2),
            icons=", ".join(sorted(ALLOWED_ICONS)),
        )
        result = await self._model().ainvoke(
            [SystemMessage(system), HumanMessage(brief)]
        )
        # with_structured_output yields a PageSpec; be defensive if a dict comes back.
        spec = result if isinstance(result, PageSpec) else PageSpec.model_validate(result)
        return _strip_non_design_text(spec)


def _strip_non_design_text(spec: PageSpec) -> PageSpec:
    """Defensively drop any non-design text the structural pass produced
    anyway, so the copy pass always has a clean slate to fill."""

    def _keep_design(d: dict[str, str]) -> dict[str, str]:
        return {k: v for k, v in d.items() if k in DESIGN_SLOTS}

    return spec.model_copy(
        update={
            "sections": [
                s.model_copy(
                    update={
                        "content": _keep_design(s.content),
                        "items": [_keep_design(item) for item in s.items],
                    }
                )
                for s in spec.sections
            ]
        }
    )


def build_generator() -> Generator:
    return LLMGenerator()


class CopyGenerator(Protocol):
    async def fill(self, brief: str, skeleton: PageSpec) -> PageSpec: ...


class LLMCopyGenerator:
    """Gemini: (brief, skeleton) -> skeleton with every text slot filled."""

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
            self._structured = base.with_structured_output(PageSpec)
        return self._structured

    async def fill(self, brief: str, skeleton: PageSpec) -> PageSpec:
        payload = (
            f"Brief: {brief}\n\nPage skeleton (fill every text slot the "
            f"catalog defines for each section type; leave design slots "
            f"exactly as given):\n{skeleton.model_dump_json(indent=2)}\n\n"
            f"Section catalog (for the full slot list per type):\n"
            f"{json.dumps(catalog(), indent=2)}"
        )
        result = await self._model().ainvoke(
            [SystemMessage(_COPY_SYSTEM), HumanMessage(payload)]
        )
        filled = result if isinstance(result, PageSpec) else PageSpec.model_validate(result)
        return _merge_design_slots(skeleton, filled)


def _merge_design_slots(skeleton: PageSpec, filled: PageSpec) -> PageSpec:
    """Re-apply the skeleton's design slots over the copy pass's output, so a
    copy-writing model can never silently change structure/design decisions."""
    sections = []
    for original, written in zip(skeleton.sections, filled.sections):
        content = {**written.content, **original.content}  # design slots win
        items = [
            {**w, **o} for o, w in zip(original.items, written.items)
        ] or written.items
        sections.append(
            written.model_copy(update={"type": original.type, "content": content, "items": items})
        )
    return filled.model_copy(update={"title": filled.title or skeleton.title, "sections": sections})


def build_copy_generator() -> CopyGenerator:
    return LLMCopyGenerator()
