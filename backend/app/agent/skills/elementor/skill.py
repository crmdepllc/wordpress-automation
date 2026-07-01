"""The Elementor page-generation pipeline: brief → validated ``_elementor_data``.

Ties the pieces together (generate IR → build JSON → validate) but does NOT
write to any site — the write + flush-css live in the ``wp_create_elementor_page``
tool so they pass through the approval gate.
"""

from __future__ import annotations

from typing import Any

from app.agent.skills.elementor.builder import build_page
from app.agent.skills.elementor.generator import Generator, build_generator
from app.agent.skills.elementor.library import load_library
from app.agent.skills.elementor.schema import PageSpec
from app.agent.skills.elementor.validator import validate_elementor_data


class ElementorValidationError(Exception):
    """Raised when generated ``_elementor_data`` fails validation (never written)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid Elementor data: " + "; ".join(errors))


def build_and_validate(spec: PageSpec) -> list[dict[str, Any]]:
    """Compile a spec to ``_elementor_data`` and validate it, or raise."""
    # Drop any section whose type isn't in the library (defensive).
    known = set(load_library())
    spec = spec.model_copy(
        update={"sections": [s for s in spec.sections if s.type in known]}
    )
    data = build_page(spec)
    errors = validate_elementor_data(data)
    if errors:
        raise ElementorValidationError(errors)
    return data


async def generate_elementor_page(
    brief: str, *, generator: Generator | None = None
) -> dict[str, Any]:
    """Brief → {title, elementor_data, sections}. Raises on invalid output."""
    spec = await (generator or build_generator()).generate(brief)
    # Keep only sections we have templates for; report what was actually built.
    known = set(load_library())
    spec = spec.model_copy(
        update={"sections": [s for s in spec.sections if s.type in known]}
    )
    data = build_and_validate(spec)
    return {
        "title": spec.title,
        "elementor_data": data,
        "sections": [s.type for s in spec.sections],
    }
