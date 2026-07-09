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
    if tmpl.layout in ("grid", "stack"):
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


def _inner_grid(section):
    """Grid/stack sections nest as section -> column -> [...heading, inner
    section] so a heading can sit above the repeated items; the inner section
    (last child of the outer column) holds the actual item columns."""
    outer_column = section["elements"][0]
    return outer_column["elements"][-1]


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
    inner = _inner_grid(section)
    assert len(inner["elements"]) == 2
    assert [c["settings"]["_column_size"] for c in inner["elements"]] == [50, 50]


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


def test_stack_clones_one_widget_per_item_in_a_single_column():
    spec = PageSpec(
        title="T",
        sections=[
            SectionSpec(
                type="faq",
                items=[
                    {"question": "Q1", "answer": "A1"},
                    {"question": "Q2", "answer": "A2"},
                    {"question": "Q3", "answer": "A3"},
                ],
            )
        ],
    )
    section = build_page(spec)[0]
    inner = _inner_grid(section)
    # One column (not one per item, unlike grid) containing one widget per item.
    assert len(inner["elements"]) == 1
    column = inner["elements"][0]
    assert column["elType"] == "column"
    assert len(column["elements"]) == 3
    assert all(w["widgetType"] == "toggle" for w in column["elements"])
    assert column["elements"][1]["settings"]["tabs"][0]["tab_title"] == "Q2"


def test_section_scalar_token_survives_inside_a_cloned_item_prototype():
    """A grid item prototype can contain a section-level scalar token (e.g.
    icon-box's primary_color fed by {{accent_color}}) alongside {{item.*}}
    tokens. Found live: the item-only fill pass was blanking accent_color
    before the section-content pass ever ran, so icon-circle backgrounds
    rendered as Elementor's default instead of the page's accent color."""
    spec = PageSpec(
        title="T",
        sections=[
            SectionSpec(
                type="features",
                content={"accent_color": "#7a1f2b"},
                items=[{"title": "a", "text": "x", "icon": "fas fa-star"}],
            )
        ],
    )
    section = build_page(spec)[0]
    inner = _inner_grid(section)
    icon_box = inner["elements"][0]["elements"][0]
    assert icon_box["settings"]["primary_color"] == "#7a1f2b"


def test_grid_section_heading_is_filled_and_items_still_clone():
    """A heading above the grid (outside the inner section) must fill from
    section.content while the inner section still clones per-item, proving
    the two token-fill passes (item then content) both reach their targets."""
    spec = PageSpec(
        title="T",
        sections=[
            SectionSpec(
                type="features",
                content={"heading": "Our Services", "accent_color": "#7a1f2b"},
                items=[{"title": "a", "text": "x"}, {"title": "b", "text": "y"}],
            )
        ],
    )
    section = build_page(spec)[0]
    blob = json.dumps(section)
    assert "Our Services" in blob
    inner = _inner_grid(section)
    assert len(inner["elements"]) == 2
