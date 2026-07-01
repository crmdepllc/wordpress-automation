"""Builder property tests — every section type builds valid, unique-id data."""

from __future__ import annotations

import json

import pytest

from app.agent.skills.elementor.builder import build_page
from app.agent.skills.elementor.library import catalog, load_library
from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.validator import validate_elementor_data


def _all_ids(data):
    ids = []

    def walk(el):
        ids.append(el["id"])
        for c in el.get("elements", []):
            walk(c)

    for el in data:
        walk(el)
    return ids


def _sample_section(section_type: str) -> SectionSpec:
    tmpl = load_library()[section_type]
    if tmpl.layout == "grid":
        items = [{s: f"{s}-{i}" for s in tmpl.item_slots} for i in range(3)]
        return SectionSpec(type=section_type, items=items)
    content = {s: f"{s} value" for s in tmpl.scalar_slots}
    return SectionSpec(type=section_type, content=content)


@pytest.mark.parametrize("section_type", [c["type"] for c in catalog()])
def test_each_section_type_builds_valid(section_type):
    spec = PageSpec(title="T", sections=[_sample_section(section_type)])
    data = build_page(spec)
    assert validate_elementor_data(data) == []


def test_ids_are_regenerated_and_unique():
    spec = PageSpec(title="T", sections=[_sample_section("hero"), _sample_section("features")])
    ids = _all_ids(build_page(spec))
    assert len(ids) == len(set(ids))
    # Placeholder ids from the templates must not survive.
    assert "hero000" not in ids and "featcol" not in ids


def test_grid_columns_match_item_count_and_sizes():
    spec = PageSpec(
        title="T",
        sections=[
            SectionSpec(
                type="features",
                items=[{"title": "a", "text": "x"}, {"title": "b", "text": "y"}],
            )
        ],
    )
    section = build_page(spec)[0]
    assert len(section["elements"]) == 2
    assert [c["settings"]["_column_size"] for c in section["elements"]] == [50, 50]


def test_tokens_are_fully_filled():
    spec = PageSpec(
        title="T",
        sections=[
            SectionSpec(
                type="hero",
                content={"heading": "Hi", "subheading": "Yo", "cta_text": "Go"},
            )
        ],
    )
    blob = json.dumps(build_page(spec))
    assert "{{" not in blob
    assert "Hi" in blob and "Go" in blob


def test_two_pages_get_different_ids():
    spec = PageSpec(title="T", sections=[_sample_section("hero")])
    assert set(_all_ids(build_page(spec))) != set(_all_ids(build_page(spec)))
