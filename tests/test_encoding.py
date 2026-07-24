"""Unit tests for encoding detection and ambiguity containment (common_utils.py)."""
import tempfile
from pathlib import Path

import pytest

from common_utils import read_text_smart
from convert_text import convert_text_native


def test_read_text_smart_utf8():
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "utf8.txt"
        f.write_text("張偉, 臺北市, UTF-8 測試", encoding="utf-8")

        text, encoding_used, ambiguous, candidates = read_text_smart(str(f))
        assert text == "張偉, 臺北市, UTF-8 測試"
        assert encoding_used == "utf-8"
        assert ambiguous is False


def test_read_text_smart_explicit_override():
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "big5.txt"
        f.write_bytes("張偉, 臺北市".encode("big5"))

        text, encoding_used, ambiguous, candidates = read_text_smart(str(f), encoding_hint="big5")
        assert text == "張偉, 臺北市"
        assert encoding_used == "big5"
        assert candidates[0]["user_selected"] is True

        with pytest.raises(ValueError, match="cannot decode"):
            read_text_smart(str(f), encoding_hint="utf-8")


def test_encoding_ambiguity_warning_reported():
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "cjk.txt"
        # Short CJK bytes where big5, cp950, and gb18030 decode similarly
        f.write_bytes("測試".encode("big5"))

        res = convert_text_native(str(f))
        assert res["report"]["encoding_used"] in ("big5", "cp950", "gb18030")
        if res["report"]["encoding_ambiguous"]:
            assert res["report"]["status"] == "passed_with_warnings"
            assert any(w["code"] == "ENCODING_AMBIGUOUS" for w in res["report"]["warnings"])
