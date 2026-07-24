"""Unit tests for native Markdown converter (convert_markdown.py)."""
import tempfile
from pathlib import Path

from convert_markdown import convert_markdown_native
from router import convert


def test_native_markdown_converter_basic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / "sample.md"
        input_file.write_text("# Heading 1\n\nSome **bold** paragraph.\n", encoding="utf-8")

        res = convert_markdown_native(str(input_file))
        assert res["markdown"] == "# Heading 1\n\nSome **bold** paragraph.\n"
        assert res["report"]["engine"] == "markdown_native"
        assert res["report"]["status"] == "passed"
        assert len(res["elements"]) == 1
        assert res["elements"][0]["source_locator"]["line_end"] == 4


def test_native_markdown_router_integration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / "test_readme.markdown"
        input_file.write_text("## Subsection\n- Item 1\n- Item 2\n", encoding="utf-8")

        output_dir = Path(tmp_dir) / "bundle"
        report = convert(str(input_file), str(output_dir))

        assert report["status"] == "passed"
        assert report["engine"] == "markdown_native"
        assert (output_dir / "document.md").read_text(encoding="utf-8") == "## Subsection\n- Item 1\n- Item 2\n"
