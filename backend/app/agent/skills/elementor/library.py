"""Loads the section example library from ``examples/``.

Each example is a section template plus a ``meta`` header describing its layout
and slots. The builder and generator both read from here so nothing invents
Elementor structure from scratch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

EXAMPLES_DIR = Path(__file__).parent / "examples"


@dataclass(frozen=True)
class SectionTemplate:
    section_type: str
    layout: str  # "single" | "grid"
    scalar_slots: tuple[str, ...]
    item_slots: tuple[str, ...]
    template: dict[str, Any]


@lru_cache
def load_library() -> dict[str, SectionTemplate]:
    """Load every ``*.json`` template, keyed by section type."""
    library: dict[str, SectionTemplate] = {}
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        meta = raw["meta"]
        library[meta["section_type"]] = SectionTemplate(
            section_type=meta["section_type"],
            layout=meta["layout"],
            scalar_slots=tuple(meta.get("scalar_slots", [])),
            item_slots=tuple(meta.get("item_slots", [])),
            template=raw["template"],
        )
    return library


def get_template(section_type: str) -> SectionTemplate:
    library = load_library()
    if section_type not in library:
        raise KeyError(
            f"No Elementor example for section type '{section_type}'. "
            f"Available: {sorted(library)}"
        )
    return library[section_type]


def catalog() -> list[dict[str, Any]]:
    """A compact description of available sections + their slots.

    Fed to the generator so the model only fills slots that exist.
    """
    return [
        {
            "type": t.section_type,
            "layout": t.layout,
            "content_slots": list(t.scalar_slots),
            "item_slots": list(t.item_slots),
        }
        for t in load_library().values()
    ]
