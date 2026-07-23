"""Reference failures exercised against a router-produced XLSX bundle."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import openpyxl
import router
from run_cross_format_regression import assert_contract
from validate_bundle import validate_bundle


def _json(path): return json.loads(path.read_text(encoding="utf-8"))
def _write(path, value): path.write_text(json.dumps(value), encoding="utf-8")

def _case():
    return {"expected_status":["passed"], "expected_bundle_validation":"passed",
            "expected_engine":"openpyxl", "required_warning_codes":[], "allowed_warning_codes":[],
            "forbidden_warning_codes":[], "required_element_types":[], "required_locator_fields":[],
            "table_count":{"min":0}, "asset_count":{"min":0}, "max_chunk_chars":2000}

def _bundle(tmp_path):
    source = tmp_path / "source.xlsx"; book = openpyxl.Workbook(); book.active.append(["name", "value"]); book.active.append(["A", 1]); book.save(source)
    output = tmp_path / "valid"; assert router.convert(str(source), str(output))["status"] == "passed"
    assert validate_bundle(str(output))["status"] == "passed"
    return output

def _mutated(tmp_path, valid, name):
    target = tmp_path / name; shutil.copytree(valid, target); return target

def _reference_failure(bundle):
    assert validate_bundle(str(bundle))["status"] == "failed"
    errors, _ = assert_contract(_case(), bundle, 0)
    assert "REFERENCE_ERROR" in errors

def _malformed_failure(bundle):
    assert "TABLE_INDEX_MALFORMED" in validate_bundle(str(bundle))["errors"]
    errors, _ = assert_contract(_case(), bundle, 0)
    assert "TABLE_INDEX_MALFORMED" in errors

def test_production_bundle_reference_mutation_matrix(tmp_path):
    valid = _bundle(tmp_path)
    # Each copy receives exactly one reference-category mutation.
    child = _mutated(tmp_path, valid, "child"); doc = _json(child / "document.json"); doc["elements"][0]["children"].append("missing-element"); _write(child / "document.json", doc); _reference_failure(child)
    element = _mutated(tmp_path, valid, "element"); lines = (element / "chunks.jsonl").read_text().splitlines(); chunk = json.loads(lines[0]); chunk["element_ids"].append("missing-element"); lines[0] = json.dumps(chunk); (element / "chunks.jsonl").write_text("\n".join(lines)+"\n"); _reference_failure(element)
    table = _mutated(tmp_path, valid, "table"); lines = (table / "chunks.jsonl").read_text().splitlines(); chunk = json.loads(lines[0]); chunk["table_ids"].append("missing-table"); lines[0] = json.dumps(chunk); (table / "chunks.jsonl").write_text("\n".join(lines)+"\n"); _reference_failure(table)
    target = _mutated(tmp_path, valid, "target"); index = _json(target / "tables/index.json"); index[0]["id"] = "missing-table"; _write(target / "tables/index.json", index); _reference_failure(target)

def test_production_table_index_assets_and_malformed_shapes(tmp_path):
    valid = _bundle(tmp_path)
    for name, replacement in (("missing", "nope.csv"), ("traversal", "../outside.csv"), ("absolute", "/tmp/outside.csv"), ("nonstring", 7)):
        bundle = _mutated(tmp_path, valid, name); index = _json(bundle / "tables/index.json"); index[0]["assets"]["csv"] = replacement; _write(bundle / "tables/index.json", index); _reference_failure(bundle)
    for name, content in (("invalid", "{"), ("shape", json.dumps({})), ("entry", json.dumps([7]))):
        bundle = _mutated(tmp_path, valid, name); (bundle / "tables/index.json").write_text(content); _malformed_failure(bundle)

def test_production_table_index_symlink_escape_is_rejected(tmp_path):
    valid = _bundle(tmp_path); bundle = _mutated(tmp_path, valid, "symlink")
    outside = tmp_path / "outside.csv"; outside.write_text("outside", encoding="utf-8")
    link = bundle / "tables" / "escape.csv"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")
    index = _json(bundle / "tables/index.json"); index[0]["assets"]["csv"] = link.name; _write(bundle / "tables/index.json", index)
    _reference_failure(bundle)
