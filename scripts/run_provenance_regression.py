#!/usr/bin/env python3
"""Emit machine-readable Phase 2 provenance acceptance metrics for bundles."""
import argparse
import json
from pathlib import Path


def metrics(bundle: Path) -> dict:
    document = json.loads((bundle / "document.json").read_text(encoding="utf-8"))
    chunks = [json.loads(line) for line in (bundle / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    elements = {item["id"] for item in document["elements"]}
    index = bundle / "tables" / "index.json"
    tables = {item["id"] for item in json.loads(index.read_text(encoding="utf-8"))} if index.exists() else set()
    def locators(chunk): return [chunk["source_locator"]] if chunk.get("source_locator") else chunk.get("source_locators", [])
    def format_metrics(name, predicate):
        selected = [chunk for chunk in chunks if any(locator.get("format") == name for locator in locators(chunk))]
        located = sum(predicate(chunk) for chunk in selected)
        return {"eligible_chunks": len(selected), "located_chunks": located,
                "coverage": located / len(selected) if selected else None,
                "status": "passed" if selected and located == len(selected) else "not_applicable" if not selected else "failed"}
    return {"bundle": str(bundle), "chunks_total": len(chunks),
        "unresolved_element_refs": sum(ref not in elements for c in chunks for ref in c.get("element_ids", [])),
        "unresolved_table_refs": sum(ref not in tables for c in chunks for ref in c.get("table_ids", [])),
        "chunks_without_precision": sum("locator_precision" not in c for c in chunks),
        "chunks_over_2000": sum(len(c.get("text", "")) > 2000 for c in chunks),
        "formats": {"xlsx": format_metrics("xlsx", lambda c: any(x.get("sheet_name") and x.get("cell_range") for x in locators(c))),
                    "pptx": format_metrics("pptx", lambda c: any(x.get("slide_number") for x in locators(c))),
                    "pdf": format_metrics("pdf", lambda c: any(x.get("page_start") for x in locators(c)))}}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("bundle", type=Path)
    print(json.dumps(metrics(parser.parse_args().bundle), ensure_ascii=False, indent=2))
