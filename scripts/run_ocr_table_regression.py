#!/usr/bin/env python3
"""Run deterministic, expectation-driven OCR table containment checks."""
import argparse
import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from ocr_table import assess_ocr_table


def boxes(rows):
    return [([[x, y * 20], [x + 1, y * 20], [x + 1, y * 20 + 1], [x, y * 20 + 1]], text, .9)
            for y, row in enumerate(rows) for x, text in row]


CASES = [
    ("label_value", "fallback_to_text", [[(0, "Name: Alice")], [(0, "Address: X")], [(0, "Phone: 1")]]),
    ("colon_sentences", "fallback_to_text", [[(0, "Note: x")], [(0, "Warning: y")]]),
    ("clear_aligned_rows", "accepted", [[(0, "Item"), (100, "Qty")], [(0, "Motor"), (100, "2")], [(0, "Pump"), (100, "4")]]),
    ("irregular_rows", "fallback_to_text", [[(0, "Item"), (50, "Qty")], [(0, "Motor")], [(100, "4")]]),
    ("sparse_two_rows", "fallback_to_text", [[(0, "Model"), (100, "ABC")], [(0, "Voltage"), (100, "480")]]),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = []
    for ordinal, (name, expected, rows) in enumerate(CASES, 1):
        candidate = assess_ocr_table(boxes(rows), 1, "rapidocr", f"regression-{ordinal:04d}")
        actual = candidate["decision"]
        results.append({"name": name, "expected": expected, "actual": actual, "passed": actual == expected})
    mismatches = [result for result in results if not result["passed"]]
    accepted = sum(result["actual"] == "accepted" for result in results)
    false_positive = sum(result["actual"] == "accepted" and result["expected"] != "accepted" for result in results)
    false_negative = sum(result["actual"] != "accepted" and result["expected"] == "accepted" for result in results)
    summary = {"cases": len(results), "results": results, "accepted": accepted,
               "rejected": len(results) - accepted, "false_positive_cases": false_positive,
               "false_negative_cases": false_negative, "mismatches": mismatches,
               "canonical_table_count": accepted, "validation_status": "passed" if not mismatches else "failed"}
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "ocr-table-regression-summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
