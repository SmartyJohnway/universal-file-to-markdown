from pathlib import Path

from html_structure import extract_html
from validate_bundle import _validate_table_semantics


FIXTURE = Path(__file__).parent / "fixtures" / "html" / "complex_tables.html"


def test_native_html_preserves_main_tables_merges_and_urls():
    result = extract_html(str(FIXTURE), "https://example.test/path/page.html")
    assert "outside navigation" not in result["markdown"]
    assert len(result["tables"]) == 2
    table = result["tables"][0]
    assert all(len(row) == 3 for row in table["grid"])
    assert len(table["merged_cells"]) == 2
    assert any(block["blocks"][-1]["type"] == "list_item" for block in table["cell_blocks"])
    assert result["report"]["html_structure"]["source_metrics"]["relative_link_count"] == 1
    assert all(element["heading_path"] for element in result["elements"] if element["type"] == "table")


def test_native_html_without_base_reports_unresolved_relative_url():
    result = extract_html(str(FIXTURE))
    codes = {warning["code"] for warning in result["report"]["warnings"]}
    assert {"BASE_URL_UNAVAILABLE", "RELATIVE_URL_UNRESOLVED"} <= codes


def test_top_level_links_and_nested_list_items_are_canonical():
    result = extract_html(str(FIXTURE), "https://example.test/base/page.html")
    assert "[rules](https://example.test/rules)" in result["markdown"]
    items = [element for element in result["elements"] if element["type"] == "list_item"]
    assert {item["properties"]["level"] for item in items} == {1, 2}
    assert all(item["parent_id"] for item in items)
    assert result["report"]["html_structure"]["canonical_metrics"]["resolved_link_count"] == 1


def test_html_validator_rejects_overlapping_or_out_of_bounds_merges():
    table = {"id": "table-html-0001", "source_format": "html", "source_locator": {"table_index": 1},
             "dimensions": {"rows": 2, "columns": 2}, "grid": [["A", "A"], ["A", "A"]],
             "merged_cells": [{"anchor_row": 0, "anchor_column": 0, "rowspan": 2, "colspan": 2, "value": "A"},
                              {"anchor_row": 0, "anchor_column": 1, "rowspan": 2, "colspan": 2, "value": "A"}]}
    errors = []; _validate_table_semantics(table, errors)
    assert "HTML_TABLE_SPAN_OUT_OF_BOUNDS" in errors


def test_html_validator_rejects_non_rectangular_grid():
    errors = []
    _validate_table_semantics({"id": "table-html-0001", "source_format": "html", "source_locator": {"table_index": 1},
                               "dimensions": {"rows": 2, "columns": 2}, "grid": [["a", "b"], ["c"]]}, errors)
    assert "HTML_TABLE_GRID_NOT_RECTANGULAR" in errors
