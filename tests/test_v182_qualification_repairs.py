import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import router


def test_irregular_csv_preserves_extra_field_and_warns(tmp_path):
    source = tmp_path / "irregular.csv"
    source.write_text("a,b,c\ntwo,columns,but_file_has_more,extra\nshort,row\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    report = router.convert(str(source), str(bundle))
    markdown = (bundle / "document.md").read_text(encoding="utf-8")
    assert report["status"] == "passed_with_warnings"
    assert "CSV_INCONSISTENT_COLUMN_COUNT" in [warning["code"] for warning in report["warnings"]]
    assert "__extra_1" in markdown and "extra" in markdown


def test_json_nesting_limit_has_stable_failure_reason(tmp_path):
    value = "leaf"
    for _ in range(1100):
        value = {"a": value}
    source = tmp_path / "deep.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    report = router.convert(str(source), str(tmp_path / "bundle"))
    assert report["status"] == "failed"
    assert report["reason"] == "JSON_NESTING_LIMIT_EXCEEDED"
    assert report["maximum_depth"] > report["configured_limit"]


def test_email_attachment_is_visible_in_readable_projection_and_chunk_has_source_file(tmp_path):
    source = tmp_path / "message.eml"
    source.write_text(
        "From: sender@example.com\nTo: recipient@example.com\nSubject: test\n"
        "MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=boundary\n\n"
        "--boundary\nContent-Type: text/plain\n\nBody\n"
        "--boundary\nContent-Type: text/plain; name=report.txt\n"
        "Content-Disposition: attachment; filename=report.txt\n"
        "Content-Transfer-Encoding: base64\n\nY29udGVudAo=\n--boundary--\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle"
    report = router.convert(str(source), str(bundle))
    assert report["status"] == "passed"
    assert "[report.txt](assets/report.txt)" in (bundle / "document.md").read_text(encoding="utf-8")
    chunks = [json.loads(line) for line in (bundle / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert chunks and all(chunk["source_file"] == "message.eml" for chunk in chunks)
