"""v1.8.1 chunk context and consumer scorecard regressions."""

import json

import pytest

from chunker import build_chunks
from score_chunk_context import score_bundles
from validate_bundle import validate_bundle


CONTEXT_FIELDS = {
    "consumer_contract_version", "ancestor_element_ids", "section_element_id",
    "unit_element_id", "related_element_ids", "relation_types", "relationships",
    "layout_region_ids", "layout_zones", "layout_order_methods", "column_indexes",
    "context_element_ids", "context_policy", "context_prefix", "context_char_count",
    "context_truncated", "embedding_text", "embedding_char_count",
}


def _edge(relation, target):
    return {"relation": relation, "target_id": target, "confidence": 0.95,
            "evidence": ["caption_prefix", "vertical_proximity"],
            "method": "deterministic_rule_v1"}


def _context_elements(text="Table 1: Results"):
    return [
        {"id": "root", "type": "document", "parent_id": None,
         "children": ["slide"], "child_ids": ["slide"]},
        {"id": "slide", "type": "slide", "parent_id": "root",
         "children": ["heading"], "child_ids": ["heading"], "slide": 1,
         "source_locator": {"format": "pptx", "slide_number": 1}},
        {"id": "heading", "type": "heading", "parent_id": "slide",
         "children": ["caption", "table"], "child_ids": ["caption", "table"],
         "content": "Results", "source_locator": {"format": "pptx", "slide_number": 1,
                                                        "shape_id": 1},
         "locator_precision": "exact"},
        {"id": "caption", "type": "caption", "parent_id": "heading",
         "children": [], "child_ids": [], "content": text,
         "heading_path": ["Results"],
         "source_locator": {"format": "pptx", "slide_number": 1, "shape_id": 2},
         "locator_precision": "exact",
         "properties": {"layout": {"reading_order": 1, "region_id": "slide-1-main",
                                      "layout_zone": "main", "column_index": 0,
                                      "order_method": "pptx_layout_flow_v1"},
                        "associations": [_edge("caption_of", "table")]}},
        {"id": "table", "type": "table", "parent_id": "heading",
         "children": [], "child_ids": [], "content": "",
         "heading_path": ["Results"],
         "source_locator": {"format": "pptx", "slide_number": 1, "shape_id": 3},
         "locator_precision": "exact",
         "properties": {"layout": {"reading_order": 2, "region_id": "slide-1-main",
                                      "layout_zone": "main", "column_index": 0,
                                      "order_method": "pptx_layout_flow_v1"},
                        "associations": [_edge("captioned_by", "caption")]}},
    ]


def _csv_bundle(tmp_path):
    import router
    source = tmp_path / "source.csv"
    source.write_text("name,value\nA,1\n", encoding="utf-8")
    output = tmp_path / "bundle"
    assert router.convert(str(source), str(output))["status"] == "passed"
    return output


def test_chunk_context_is_deterministic_id_only_and_embedding_safe():
    chunks = build_chunks("", _context_elements(), "a" * 64)
    caption = next(chunk for chunk in chunks if chunk["element_ids"] == ["caption"])
    assert caption["consumer_contract_version"] == "1.0"
    assert caption["ancestor_element_ids"] == ["slide", "heading"]
    assert caption["section_element_id"] == "heading"
    assert caption["unit_element_id"] == "slide"
    assert caption["related_element_ids"] == ["table"]
    assert caption["relation_types"] == ["caption_of"]
    assert caption["context_element_ids"] == ["slide", "heading", "table"]
    assert caption["layout_region_ids"] == ["slide-1-main"]
    assert caption["embedding_text"] == caption["context_prefix"] + caption["text"]
    assert caption["embedding_char_count"] <= 2000
    assert "| A | B |" not in caption["context_prefix"]


def test_source_text_wins_when_context_budget_is_exhausted():
    elements = _context_elements("x" * 2000)
    chunks = build_chunks("", elements, "a" * 64)
    parts = [chunk for chunk in chunks if chunk["element_ids"] == ["caption"]]
    assert len(parts) == 1
    assert parts[0]["text"] == "x" * 2000
    assert parts[0]["context_prefix"] == ""
    assert parts[0]["context_truncated"] is True
    assert parts[0]["embedding_char_count"] == 2000


@pytest.mark.parametrize("length", [1, 50, 499, 999, 1500, 1900, 1999, 2000, 2001, 4200])
def test_ten_synthetic_lengths_preserve_every_source_character(length):
    elements = _context_elements("z" * length)
    chunks = [chunk for chunk in build_chunks("", elements, "b" * 64)
              if chunk["element_ids"] == ["caption"]]
    assert "".join(chunk["text"] for chunk in chunks) == "z" * length
    assert all(chunk["embedding_char_count"] <= 2000 for chunk in chunks)
    assert all(chunk["embedding_text"].endswith(chunk["text"]) for chunk in chunks)


def test_current_bundle_validates_and_legacy_chunk_stays_compatible(tmp_path):
    bundle = _csv_bundle(tmp_path)
    assert validate_bundle(str(bundle))["status"] == "passed"
    path = bundle / "chunks.jsonl"
    chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for chunk in chunks:
        for field in CONTEXT_FIELDS:
            chunk.pop(field, None)
    path.write_text("".join(json.dumps(chunk) + "\n" for chunk in chunks), encoding="utf-8")
    assert validate_bundle(str(bundle))["status"] == "passed"


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        (lambda chunk: chunk.__setitem__("context_char_count", 999),
         "CHUNK_CONTEXT_CHAR_COUNT_MISMATCH"),
        (lambda chunk: chunk.__setitem__("embedding_text", "tampered"),
         "CHUNK_EMBEDDING_TEXT_MISMATCH"),
        (lambda chunk: chunk.__setitem__("context_element_ids", ["missing"]),
         "CHUNK_CONTEXT_REFERENCE_MISSING"),
        (lambda chunk: chunk.__setitem__("layout_region_ids", ["fabricated"]),
         "CHUNK_CONTEXT_DERIVATION_MISMATCH"),
    ],
)
def test_validator_rejects_consumer_projection_tampering(tmp_path, mutation, error_code):
    bundle = _csv_bundle(tmp_path)
    path = bundle / "chunks.jsonl"
    chunk = json.loads(path.read_text(encoding="utf-8"))
    mutation(chunk)
    path.write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    result = validate_bundle(str(bundle))
    assert result["status"] == "failed"
    assert any(error_code in error for error in result["errors"])


def test_scorecard_reports_contract_locator_and_limits(tmp_path):
    bundle = _csv_bundle(tmp_path)
    report = score_bundles([bundle])
    assert report["status"] == "passed"
    assert report["bundle_count"] == 1
    assert report["consumer_contract_coverage"] == 1.0
    assert report["context_prefix_coverage"] == 0.0
    assert report["related_element_coverage"] == 0.0
    assert report["locator_coverage"] == 1.0
    scored = report["bundles"][0]
    assert scored["locator_coverage"] == 1.0
    assert scored["embedding_hard_limit_violations"] == 0
    assert scored["embedding_chars"]["max"] <= 2000
