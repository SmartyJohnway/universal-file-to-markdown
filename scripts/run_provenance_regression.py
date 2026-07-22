#!/usr/bin/env python3
"""Emit machine-readable Phase 2 provenance acceptance metrics for bundles."""
import argparse
import json
from pathlib import Path


def metrics(bundle: Path) -> dict:
    document = json.loads((bundle / "document.json").read_text(encoding="utf-8"))
    chunks = [json.loads(line) for line in (bundle / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    elements = {item["id"] for item in document["elements"]}
    table_index = bundle / "tables" / "index.json"
    tables = {item["id"] for item in json.loads(table_index.read_text(encoding="utf-8"))} if table_index.exists() else set()
    def locators(chunk): return [chunk["source_locator"]] if chunk.get("source_locator") else chunk.get("source_locators", [])
    typed = lambda name: [chunk for chunk in chunks if any(locator.get("format") == name for locator in locators(chunk))]
    coverage = lambda selected, predicate: 1.0 if not selected else sum(predicate(x) for x in selected) / len(selected)
    return {
        "bundle": str(bundle), "chunks_total": len(chunks),
        "unresolved_element_refs": sum(reference not in elements for chunk in chunks for reference in chunk.get("element_ids", [])),
        "unresolved_table_refs": sum(reference not in tables for chunk in chunks for reference in chunk.get("table_ids", [])),
        "chunks_without_precision": sum("locator_precision" not in chunk for chunk in chunks),
        "chunks_over_2000": sum(len(chunk.get("text", "")) > 2000 for chunk in chunks),
        "xlsx_locator_coverage": coverage(typed("xlsx"), lambda c: any(x.get("sheet_name") and x.get("cell_range") for x in locators(c))),
        "pptx_locator_coverage": coverage(typed("pptx"), lambda c: any(x.get("slide_number") for x in locators(c))),
        "pdf_page_locator_coverage": coverage(typed("pdf"), lambda c: any(x.get("page_start") for x in locators(c))),
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("bundle", type=Path)
    print(json.dumps(metrics(parser.parse_args().bundle), ensure_ascii=False, indent=2))
