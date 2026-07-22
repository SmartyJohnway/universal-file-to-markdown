from pathlib import Path

from html_structure import extract_html


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
