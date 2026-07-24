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
        assert res["report"]["encoding_ambiguous"] is True
        assert res["report"]["status"] == "passed_with_warnings"
        assert any(w["code"] == "ENCODING_AMBIGUOUS" for w in res["report"]["warnings"])


def test_gb18030_simplified_chinese_ambiguity_containment_and_recovery():
    """Reproduces the external Claude issue with GB18030 Simplified Chinese content.

    Verifies that un-annotated GB18030 text triggers ENCODING_AMBIGUOUS warning,
    marks explicit_encoding_recommended, and recovers exact text when --encoding
    gb18030 is supplied.
    """
    raw_content = "张伟\n北京市\nGB18030"
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "gb18030_sample.txt"
        f.write_bytes(raw_content.encode("gb18030"))

        # 1. Automatic decode without encoding hint must detect ambiguity
        text_auto, encoding_used, ambiguous, candidates = read_text_smart(str(f))
        assert ambiguous is True, "Un-annotated CJK GB18030 text must be flagged as ambiguous"
        assert len(candidates) >= 2, "Must report multiple candidate CJK encodings"

        # 2. Native text converter report must emit warning and recommendation
        res = convert_text_native(str(f))
        assert res["report"]["encoding_ambiguous"] is True
        assert res["report"]["status"] == "passed_with_warnings"
        assert any(w["code"] == "ENCODING_AMBIGUOUS" for w in res["report"]["warnings"])
        assert res["report"]["explicit_encoding_recommended"] is True

        # 3. Explicit encoding override recovers exact original text cleanly
        text_recovered, enc_used, ambig, candidates_exp = read_text_smart(str(f), encoding_hint="gb18030")
        assert text_recovered == raw_content
        assert enc_used == "gb18030"
        assert ambig is False
        assert candidates_exp[0]["user_selected"] is True

