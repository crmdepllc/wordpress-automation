"""Compile a ``PageSpec`` into Elementor ``_elementor_data`` deterministically.

For each section we take its real example template, fill the ``{{slot}}`` tokens
from the spec's content/items, clone the prototype column for grid sections, and
regenerate every element id so the page is unique. No Elementor structure is
invented here — it all comes from the example library.
"""

from __future__ import annotations

import copy
import re
import secrets
from typing import Any

from app.agent.skills.elementor.library import SectionTemplate, get_template
from app.agent.skills.elementor.schema import PageSpec, SectionSpec

_TOKEN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _new_id() -> str:
    # Elementor element ids are short hex-ish strings (7 chars).
    return secrets.token_hex(4)[:7]


def _fill_tokens(value: Any, mapping: dict[str, str], *, blank_unmatched: bool = True) -> Any:
    """Deep-walk a value, replacing ``{{token}}`` with mapping values.

    Grid/stack item prototypes can contain *both* ``{{item.x}}`` tokens and
    section-level scalar tokens (e.g. an icon-box's ``primary_color`` fed by
    ``{{accent_color}}``) — the item pass only knows the item mapping, so a
    scalar token surviving that pass must be left as ``{{accent_color}}``
    (``blank_unmatched=False``) rather than blanked, or the later
    section-content pass would have nothing left to fill (found via live
    verification: icon-circle backgrounds rendered as Elementor's default
    instead of the page's accent color because this exact token was being
    wiped out one pass too early). Only the final, section-content pass
    (``blank_unmatched=True``, the default) should blank anything still
    unresolved — by then it's genuinely an omitted optional slot.
    """
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key in mapping:
                return str(mapping[key])
            return "" if blank_unmatched else m.group(0)

        return _TOKEN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _fill_tokens(v, mapping, blank_unmatched=blank_unmatched) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_tokens(v, mapping, blank_unmatched=blank_unmatched) for v in value]
    return value


def _build_single(tmpl: SectionTemplate, section: SectionSpec) -> dict[str, Any]:
    node = copy.deepcopy(tmpl.template)
    return _fill_tokens(node, section.content)


def _inner_grid_section(node: dict[str, Any]) -> dict[str, Any]:
    """Grid/stack templates wrap their repeated content in a nested Elementor
    section (``outer section -> column -> [optional heading widgets...,
    inner section]``) so a heading can sit above the repeated items — an
    outer section's columns lay out side by side, so a heading can't live
    next to the item columns in the same row; nesting a section one level
    deeper is the real Elementor pattern for a title-above-grid layout, and
    ``validator.py`` already permits a section as a column's child. The inner
    section is always the *last* element in the outer column."""
    outer_column = node["elements"][0]
    return outer_column["elements"][-1]


def _build_grid(tmpl: SectionTemplate, section: SectionSpec) -> dict[str, Any]:
    node = copy.deepcopy(tmpl.template)
    inner = _inner_grid_section(node)
    prototype = inner["elements"][0]  # grid templates have exactly one column
    items = section.items or [{}]  # keep one column even if no items given
    size = round(100 / len(items))

    columns: list[dict[str, Any]] = []
    for item in items:
        col = copy.deepcopy(prototype)
        col = _fill_tokens(col, {f"item.{k}": v for k, v in item.items()}, blank_unmatched=False)
        col.setdefault("settings", {})["_column_size"] = size
        columns.append(col)

    inner["elements"] = columns
    return _fill_tokens(node, section.content)


def _build_stack(tmpl: SectionTemplate, section: SectionSpec) -> dict[str, Any]:
    """Clone one widget prototype once per item into a single column, stacked
    vertically (unlike ``grid``, which clones a whole column side by side)."""
    node = copy.deepcopy(tmpl.template)
    inner = _inner_grid_section(node)
    column = inner["elements"][0]  # stack templates have exactly one column
    prototype = column["elements"][0]  # ...containing exactly one widget
    items = section.items or [{}]

    widgets: list[dict[str, Any]] = []
    for item in items:
        widget = copy.deepcopy(prototype)
        widget = _fill_tokens(widget, {f"item.{k}": v for k, v in item.items()}, blank_unmatched=False)
        widgets.append(widget)

    column["elements"] = widgets
    return _fill_tokens(node, section.content)


def _regenerate_ids(element: dict[str, Any], used: set[str]) -> None:
    new_id = _new_id()
    while new_id in used:
        new_id = _new_id()
    used.add(new_id)
    element["id"] = new_id
    for child in element.get("elements", []):
        _regenerate_ids(child, used)


def build_page(spec: PageSpec) -> list[dict[str, Any]]:
    """Return the ``_elementor_data`` list for a page spec."""
    data: list[dict[str, Any]] = []
    for section in spec.sections:
        tmpl = get_template(section.type)
        if tmpl.layout == "grid":
            data.append(_build_grid(tmpl, section))
        elif tmpl.layout == "stack":
            data.append(_build_stack(tmpl, section))
        else:
            data.append(_build_single(tmpl, section))

    used: set[str] = set()
    for element in data:
        _regenerate_ids(element, used)
    return data
