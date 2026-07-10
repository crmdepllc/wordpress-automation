"""The Elementor page-generation pipeline: brief → validated ``_elementor_data``.

Ties the pieces together (Claude structure → Gemini copy → build JSON →
validate) but does NOT write to any site — the write + flush-css live in the
``wp_create_elementor_page`` tool so they pass through the approval gate.
"""

from __future__ import annotations

from typing import Any

from app.agent.skills.elementor.builder import build_page
from app.agent.skills.elementor.generator import (
    CopyGenerator,
    Generator,
    build_copy_generator,
    build_generator,
)
from app.agent.skills.elementor.icons import safe_icon
from app.agent.skills.elementor.library import load_library
from app.agent.skills.elementor.schema import PageSpec
from app.agent.skills.elementor.validator import validate_elementor_data


class ElementorValidationError(Exception):
    """Raised when generated ``_elementor_data`` fails validation (never written)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid Elementor data: " + "; ".join(errors))


def _sanitize_icons(spec: PageSpec) -> PageSpec:
    """Clamp every ``icon`` item slot to Elementor's bundled-safe icon set.

    Elementor's SVG icon renderer only knows icons present in its own bundled
    (older) Font Awesome dataset — an out-of-range value causes PHP warnings
    and a broken icon on the live page, not a clean validation failure. This
    runs regardless of what the model returned, so it's a hard guarantee, not
    a prompt-compliance hope.
    """
    sections = [
        s.model_copy(
            update={
                "items": [
                    {**item, "icon": safe_icon(item["icon"])} if "icon" in item else item
                    for item in s.items
                ]
            }
        )
        if s.items
        else s
        for s in spec.sections
    ]
    return spec.model_copy(update={"sections": sections})


def build_and_validate(spec: PageSpec) -> list[dict[str, Any]]:
    """Compile a spec to ``_elementor_data`` and validate it, or raise."""
    # Drop any section whose type isn't in the library (defensive).
    known = set(load_library())
    spec = spec.model_copy(
        update={"sections": [s for s in spec.sections if s.type in known]}
    )
    spec = _sanitize_icons(spec)
    data = build_page(spec)
    errors = validate_elementor_data(data)
    if errors:
        raise ElementorValidationError(errors)
    return data


async def generate_page_spec(
    brief: str,
    *,
    generator: Generator | None = None,
    copy_generator: CopyGenerator | None = None,
) -> PageSpec:
    """Brief → a filled ``PageSpec`` (structure + copy, no image resolution yet).

    Two-pass generation per AGENTS.md: ``generator`` (Claude) decides page
    structure/design; ``copy_generator`` (Gemini) then fills the visible text.
    Any ``image_prompt`` design slot Claude set is left as-is — turning it into
    a real image is a separate, WP-writing step (``images/resolver.py``) that
    only runs post-approval, not part of this offline pipeline.
    """
    skeleton = await (generator or build_generator()).generate(brief)
    # Keep only sections we have templates for; report what was actually built.
    known = set(load_library())
    skeleton = skeleton.model_copy(
        update={"sections": [s for s in skeleton.sections if s.type in known]}
    )
    return await (copy_generator or build_copy_generator()).fill(brief, skeleton)


async def generate_elementor_page(
    brief: str,
    *,
    generator: Generator | None = None,
    copy_generator: CopyGenerator | None = None,
) -> dict[str, Any]:
    """Brief → {title, elementor_data, sections}. Raises on invalid output.

    Convenience wrapper for callers that don't need image resolution (tests,
    offline evals): any unresolved ``image_prompt`` slot simply builds without
    an image, since its ``{{image_url}}`` token never gets filled.
    """
    spec = await generate_page_spec(brief, generator=generator, copy_generator=copy_generator)
    data = build_and_validate(spec)
    return {
        "title": spec.title,
        "elementor_data": data,
        "sections": [s.type for s in spec.sections],
    }
