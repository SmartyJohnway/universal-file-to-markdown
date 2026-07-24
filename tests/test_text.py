"""Unit tests for native text converter (convert_text.py)."""
import tempfile
from pathlib import Path
import pytest

from convert_text import convert_text_native
from router import convert


def test_native_text_converter_basic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / "sample.txt"
        input_file.write_text("Hello World\nSecond line of plain text.\n", encoding="utf-8")

        res = convert_text_native(str(input_file))
        assert res["markdown"] == "Hello World\nSecond line of plain text.\n"
        assert res["report"]["engine"] == "text_native"
        assert res["report"]["status"] == "passed"
        assert len(res["elements"]) == 1
        assert res["elements"][0]["source_locator"]["line_end"] == 3


def test_native_text_router_integration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / "test_doc.log"
        input_file.write_text("2026-07-24 INFO System startup complete\n", encoding="utf-8")

        output_dir = Path(tmp_dir) / "bundle"
        report = convert(str(input_file), str(output_dir))

        assert report["status"] == "passed"
        assert report["engine"] == "text_native"
        assert (output_dir / "document.md").read_text(encoding="utf-8") == "2026-07-24 INFO System startup complete\n"


def test_native_text_binary_rejection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / "fake.txt"
        input_file.write_bytes(b"\x00\x00\x00\x00\x00\x00\x00\x00" * 20)

        with pytest.raises(ValueError, match="binary content cannot be parsed as plain text"):
            convert_text_native(str(input_file))
