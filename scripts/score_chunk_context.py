#!/usr/bin/env python3
"""Score bundle chunk context for downstream retrieval consumers."""

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from validate_bundle import validate_bundle


HARD_MAX_CHUNK_CHARS = 2000


def _chunks(bundle: Path) -> list[dict]:
    path = bundle / "chunks.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def score_bundle(bundle: Path) -> dict:
    bundle = bundle.resolve()
    validation = validate_bundle(str(bundle))
    chunks = _chunks(bundle)
    text_lengths = [len(chunk.get("text", "")) for chunk in chunks]
    embedding_lengths = [len(chunk.get("embedding_text", chunk.get("text", "")))
                         for chunk in chunks]
    normalized = [_normalized_text(chunk.get("text", "")) for chunk in chunks]
    duplicate_chunks = sum(count - 1 for value, count in Counter(normalized).items()
                           if value and count > 1)
    contract_chunks = [chunk for chunk in chunks
                       if chunk.get("consumer_contract_version") == "1.0"]
    located_chunks = [chunk for chunk in chunks
                      if chunk.get("source_locator") or chunk.get("source_locators")]
    context_chunks = [chunk for chunk in contract_chunks if chunk.get("context_prefix")]
    related_chunks = [chunk for chunk in contract_chunks
                      if chunk.get("related_element_ids")]
    hard_limit_violations = sum(length > HARD_MAX_CHUNK_CHARS
                                for length in embedding_lengths)
    return {
        "bundle": str(bundle),
        "status": "passed" if validation["status"] == "passed"
                  and hard_limit_violations == 0 else "failed",
        "bundle_validation_status": validation["status"],
        "validation_errors": validation.get("errors", []),
        "chunk_count": len(chunks),
        "consumer_contract_chunks": len(contract_chunks),
        "consumer_contract_coverage": (
            len(contract_chunks) / len(chunks) if chunks else None
        ),
        "context_prefix_chunks": len(context_chunks),
        "context_prefix_coverage": (
            len(context_chunks) / len(contract_chunks) if contract_chunks else None
        ),
        "related_element_chunks": len(related_chunks),
        "related_element_coverage": (
            len(related_chunks) / len(contract_chunks) if contract_chunks else None
        ),
        "locator_chunks": len(located_chunks),
        "locator_coverage": len(located_chunks) / len(chunks) if chunks else None,
        "context_truncated_chunks": sum(
            bool(chunk.get("context_truncated")) for chunk in contract_chunks
        ),
        "duplicate_text_chunks": duplicate_chunks,
        "duplicate_text_rate": duplicate_chunks / len(chunks) if chunks else None,
        "text_chars": {
            "mean": round(sum(text_lengths) / len(text_lengths), 2) if text_lengths else 0,
            "p95": _percentile(text_lengths, 0.95),
            "max": max(text_lengths, default=0),
        },
        "embedding_chars": {
            "mean": round(sum(embedding_lengths) / len(embedding_lengths), 2)
                    if embedding_lengths else 0,
            "p95": _percentile(embedding_lengths, 0.95),
            "max": max(embedding_lengths, default=0),
        },
        "embedding_hard_limit_violations": hard_limit_violations,
    }


def score_bundles(bundles: list[Path]) -> dict:
    results = [score_bundle(bundle) for bundle in bundles]
    chunks = sum(result["chunk_count"] for result in results)
    contract_chunks = sum(result["consumer_contract_chunks"] for result in results)
    context_prefix_chunks = sum(result["context_prefix_chunks"] for result in results)
    related_element_chunks = sum(result["related_element_chunks"] for result in results)
    locator_chunks = sum(result["locator_chunks"] for result in results)
    return {
        "scorecard_version": "1.0",
        "status": "passed" if results and all(result["status"] == "passed"
                                                for result in results) else "failed",
        "bundle_count": len(results),
        "chunk_count": chunks,
        "consumer_contract_coverage": (
            contract_chunks / chunks if chunks else None
        ),
        "context_prefix_coverage": (
            context_prefix_chunks / contract_chunks if contract_chunks else None
        ),
        "related_element_coverage": (
            related_element_chunks / contract_chunks if contract_chunks else None
        ),
        "locator_coverage": locator_chunks / chunks if chunks else None,
        "embedding_hard_limit_violations": sum(
            result["embedding_hard_limit_violations"] for result in results
        ),
        "duplicate_text_chunks": sum(result["duplicate_text_chunks"] for result in results),
        "bundles": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score v1.8.1 chunk context across one or more bundles."
    )
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = score_bundles(args.bundles)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
