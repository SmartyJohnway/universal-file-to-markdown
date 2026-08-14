"""Precision-first containment for heuristic OCR table reconstruction.

This is deliberately a small, auditable policy rather than a table detector.
Candidates are retained in reports; only accepted candidates become canonical tables.
"""
import re
import statistics

OCR_TABLE_POLICY = {
    "min_columns": 2, "min_rows": 3, "min_aligned_row_ratio": 0.75,
    "min_confidence_with_geometry": 0.60,
    "max_irregular_row_ratio": 0.25, "high_confidence": 0.80,
}
_KEY_VALUE = re.compile(r"^\s*[^:]{1,80}:\s*\S+")
_SUSPICIOUS_GLUE = re.compile(r"\d[A-Z]{2,}")


def _lines(boxes, tolerance=10):
    items = sorted((p[0][0][1], p[0][0][0], p[1]) for p in boxes)
    grouped = []
    for item in items:
        if not grouped or abs(item[0] - grouped[-1][-1][0]) > tolerance:
            grouped.append([item])
        else: grouped[-1].append(item)
    return [sorted(line, key=lambda item: item[1]) for line in grouped]


def assess_ocr_table(boxes, page, engine, candidate_id):
    """Return an explicit candidate decision; absence of geometry means reject."""
    lines = _lines(boxes) if boxes else []
    raw_lines = [" ".join(x[2] for x in line) for line in lines]
    kv_ratio = sum(bool(_KEY_VALUE.match(line)) for line in raw_lines) / len(raw_lines) if raw_lines else 0.0
    xs = sorted(x for line in lines for _, x, _ in line)
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= 20: clusters[-1].append(x)
        else: clusters.append([x])
    bins = [statistics.mean(cluster) for cluster in clusters if len(cluster) >= OCR_TABLE_POLICY["min_rows"]]
    rows = []
    hits = []
    if len(bins) >= 2:
        for line in lines:
            row = [""] * len(bins); used = set()
            for _, x, text in line:
                col = min(range(len(bins)), key=lambda n: abs(bins[n] - x))
                row[col] = (row[col] + " " + text).strip(); used.add(col)
            rows.append(row); hits.append(len(used))
    column_count = len(bins)
    row_count = len(rows)
    aligned = sum(n >= 2 for n in hits) / row_count if row_count else 0.0
    irregular = sum(n < 2 for n in hits) / row_count if row_count else 1.0
    numeric = sum(cell.replace('.', '', 1).isdigit() for row in rows for cell in row if cell) / max(1, sum(bool(cell) for row in rows for cell in row))
    signals = {"row_count": row_count, "column_count": column_count,
        "aligned_row_ratio": round(aligned, 3), "consistent_column_ratio": round(aligned, 3),
        "numeric_column_ratio": round(numeric, 3), "key_value_pattern_ratio": round(kv_ratio, 3),
        "irregular_row_ratio": round(irregular, 3), "bounding_box_geometry_available": bool(boxes)}
    confidence = max(0.0, min(1.0, .30 + .35 * aligned + .15 * min(column_count / 3, 1) + .10 * min(row_count / 4, 1) + .10 * numeric - .55 * kv_ratio - .35 * irregular))
    suspicious_glue = any(_SUSPICIOUS_GLUE.search(cell) for row in rows for cell in row if cell)
    signals["suspicious_glued_token"] = suspicious_glue
    reasons = []
    if not boxes: reasons.append("OCR_TABLE_GEOMETRY_UNAVAILABLE")
    if kv_ratio >= .5: reasons.append("OCR_TABLE_KEY_VALUE_PATTERN")
    if row_count < OCR_TABLE_POLICY["min_rows"]: reasons.append("OCR_TABLE_INSUFFICIENT_ROWS")
    if column_count < OCR_TABLE_POLICY["min_columns"] or aligned < OCR_TABLE_POLICY["min_aligned_row_ratio"]: reasons.append("OCR_TABLE_COLUMN_INCONSISTENT")
    if irregular > OCR_TABLE_POLICY["max_irregular_row_ratio"]: reasons.append("OCR_TABLE_IRREGULAR_ROWS")
    if suspicious_glue: reasons.append("OCR_TABLE_SUSPICIOUS_GLUED_TOKEN")
    if not rows: reasons.append("OCR_TABLE_EMPTY")
    accepted = not reasons and confidence >= OCR_TABLE_POLICY["min_confidence_with_geometry"]
    if not accepted:
        reasons.extend(["OCR_TABLE_LOW_CONFIDENCE", "OCR_TABLE_REJECTED", "OCR_TABLE_FALLBACK_TO_TEXT"])
    else: reasons.append("OCR_TABLE_CANDIDATE_ACCEPTED")
    return {"candidate_id": candidate_id, "source_locator": {"format": "pdf", "page_start": page, "page_end": page}, "rows": rows,
        "signals": signals, "confidence": round(confidence, 3), "decision": "accepted" if accepted else "fallback_to_text", "reason_codes": list(dict.fromkeys(reasons)), "engine": engine, "raw_text": "\n".join(raw_lines)}
