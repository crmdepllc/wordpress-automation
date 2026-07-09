"""The constrained intermediate representation (IR) for a generated page.

Claude fills this — a short, validated spec — instead of emitting raw
``_elementor_data``. The builder compiles it into Elementor JSON deterministically.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# The catalog of section types the agent may compose. Adding a section type
# means adding an example template + (optional) slot metadata — not touching
# the builder (unless it needs a new layout kind; see builder.py's "stack").
SectionType = Literal[
    "hero", "features", "pricing", "contact", "footer",
    "testimonials", "stats", "faq", "cta_banner",
    "about", "badges",
]


class SectionSpec(BaseModel):
    """One section in the page.

    ``content`` holds scalar slots (e.g. heading, subheading, cta_text).
    ``items`` holds repeated entries for grid sections (features/pricing).
    """

    type: SectionType
    content: dict[str, str] = Field(default_factory=dict)
    items: list[dict[str, str]] = Field(default_factory=list)


class PageSpec(BaseModel):
    """The whole page: a title and an ordered list of sections."""

    title: str
    sections: list[SectionSpec] = Field(default_factory=list)
