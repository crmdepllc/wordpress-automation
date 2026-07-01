"""Validate ``_elementor_data`` before it's written to a site.

Catches the structural mistakes that break Elementor rendering: missing ids,
bad ``elType``/``widgetType``, illegal nesting (widget under section, children
under a widget), duplicate ids, and column widths that don't add up. Returns a
list of human-readable errors — empty means it's safe to write.
"""

from __future__ import annotations

from typing import Any

_EL_TYPES = {"section", "column", "widget"}


def validate_elementor_data(data: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(data, list):
        return ["_elementor_data must be a list of section elements"]
    if not data:
        errors.append("page has no sections")

    ids: list[str] = []

    def walk(element: Any, path: str) -> None:
        if not isinstance(element, dict):
            errors.append(f"{path}: element must be an object")
            return

        el_type = element.get("elType")
        el_id = element.get("id")
        if not el_id or not isinstance(el_id, str):
            errors.append(f"{path}: missing/invalid id")
        else:
            ids.append(el_id)

        if el_type not in _EL_TYPES:
            errors.append(f"{path}: invalid elType {el_type!r}")
            return

        children = element.get("elements", []) or []

        if el_type == "widget":
            if not element.get("widgetType"):
                errors.append(f"{path}: widget missing widgetType")
            if children:
                errors.append(f"{path}: widget must not have child elements")

        if el_type == "section":
            for i, child in enumerate(children):
                if isinstance(child, dict) and child.get("elType") != "column":
                    errors.append(
                        f"{path}.elements[{i}]: section child must be a column, "
                        f"got {child.get('elType')!r}"
                    )
            sizes = [
                c.get("settings", {}).get("_column_size")
                for c in children
                if isinstance(c, dict)
            ]
            numeric = [s for s in sizes if isinstance(s, (int, float))]
            if numeric and abs(sum(numeric) - 100) > 5:
                errors.append(
                    f"{path}: column sizes sum to {sum(numeric)} (expected ~100)"
                )

        if el_type == "column":
            for i, child in enumerate(children):
                if isinstance(child, dict) and child.get("elType") not in {
                    "widget",
                    "section",
                }:
                    errors.append(
                        f"{path}.elements[{i}]: column child must be widget or "
                        f"section, got {child.get('elType')!r}"
                    )

        for i, child in enumerate(children):
            walk(child, f"{path}.elements[{i}]")

    for i, element in enumerate(data):
        if isinstance(element, dict) and element.get("elType") != "section":
            errors.append(
                f"[{i}]: top-level element must be a section, "
                f"got {element.get('elType')!r}"
            )
        walk(element, f"[{i}]")

    seen: set[str] = set()
    dupes = sorted({i for i in ids if i in seen or seen.add(i)})
    if dupes:
        errors.append(f"duplicate element ids: {dupes}")

    return errors
