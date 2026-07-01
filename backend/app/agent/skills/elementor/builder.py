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


def _fill_tokens(value: Any, mapping: dict[str, str]) -> Any:
    """Deep-walk a value, replacing ``{{token}}`` with mapping values ("" if absent)."""
    if isinstance(value, str):
        return _TOKEN.sub(lambda m: str(mapping.get(m.group(1), "")), value)
    if isinstance(value, dict):
        return {k: _fill_tokens(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_tokens(v, mapping) for v in value]
    return value


def _build_single(tmpl: SectionTemplate, section: SectionSpec) -> dict[str, Any]:
    node = copy.deepcopy(tmpl.template)
    return _fill_tokens(node, section.content)


def _build_grid(tmpl: SectionTemplate, section: SectionSpec) -> dict[str, Any]:
    node = copy.deepcopy(tmpl.template)
    prototype = node["elements"][0]  # grid templates have exactly one column
    items = section.items or [{}]  # keep one column even if no items given
    size = round(100 / len(items))

    columns: list[dict[str, Any]] = []
    for item in items:
        col = copy.deepcopy(prototype)
        col = _fill_tokens(col, {f"item.{k}": v for k, v in item.items()})
        col.setdefault("settings", {})["_column_size"] = size
        columns.append(col)

    node["elements"] = columns
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
        else:
            data.append(_build_single(tmpl, section))

    used: set[str] = set()
    for element in data:
        _regenerate_ids(element, used)
    return data
