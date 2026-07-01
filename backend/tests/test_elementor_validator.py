"""Validator tests — it must catch the ways Elementor JSON breaks."""

from __future__ import annotations

from app.agent.skills.elementor.validator import validate_elementor_data


def _valid_page():
    return [
        {
            "id": "sec0001",
            "elType": "section",
            "settings": {},
            "elements": [
                {
                    "id": "col0001",
                    "elType": "column",
                    "settings": {"_column_size": 100},
                    "elements": [
                        {
                            "id": "wid0001",
                            "elType": "widget",
                            "widgetType": "heading",
                            "settings": {"title": "Hi"},
                        }
                    ],
                }
            ],
        }
    ]


def test_valid_page_has_no_errors():
    assert validate_elementor_data(_valid_page()) == []


def test_not_a_list():
    assert validate_elementor_data({"nope": 1})


def test_top_level_must_be_section():
    data = _valid_page()
    data[0]["elType"] = "column"
    assert any("top-level" in e for e in validate_elementor_data(data))


def test_widget_missing_widget_type():
    data = _valid_page()
    del data[0]["elements"][0]["elements"][0]["widgetType"]
    assert any("widgetType" in e for e in validate_elementor_data(data))


def test_missing_id():
    data = _valid_page()
    del data[0]["id"]
    assert any("id" in e for e in validate_elementor_data(data))


def test_duplicate_ids():
    data = _valid_page()
    data[0]["elements"][0]["id"] = "sec0001"  # same as section
    assert any("duplicate" in e for e in validate_elementor_data(data))


def test_bad_nesting_widget_under_section():
    data = _valid_page()
    # put a widget directly under the section
    data[0]["elements"].append(
        {"id": "wbad001", "elType": "widget", "widgetType": "heading", "settings": {}}
    )
    assert any("must be a column" in e for e in validate_elementor_data(data))


def test_widget_with_children_rejected():
    data = _valid_page()
    data[0]["elements"][0]["elements"][0]["elements"] = [
        {"id": "x1234567", "elType": "widget", "widgetType": "heading", "settings": {}}
    ]
    assert any("must not have child" in e for e in validate_elementor_data(data))


def test_column_sizes_must_sum_to_100():
    data = _valid_page()
    data[0]["elements"].append(
        {"id": "col0002", "elType": "column", "settings": {"_column_size": 80}, "elements": []}
    )
    # 100 + 80 = 180 → error
    assert any("column sizes sum" in e for e in validate_elementor_data(data))
