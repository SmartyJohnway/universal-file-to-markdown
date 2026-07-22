"""
pdf_converter.py
Classifies PDFs PAGE BY PAGE (not as a whole document) and routes each
page to the right extractor:
  - digital page  -> pdfplumber (text + line-based table detection)
  - scanned page  -> rasterize with PyMuPDF, OCR with RapidOCR, with a
                    Tesseract fallback for glued Latin-script text.

Why page-level, not document-level (bug found in real-world testing):
v1 summed text-layer character count across up to 3 sample pages and
compared it to a single threshold (50 chars) for the WHOLE document. A
short, genuinely digital PDF (e.g. a one-page cover sheet with ~33 total
characters) fell under that threshold and got mis-routed into the OCR
path - wasted work at best, and a hard failure if RapidOCR wasn't
installed in that environment, for a file that never needed OCR at all.
Per-page classification with a near-zero threshold (any extractable text
at all -> digital) fixes both the short-document case and the genuinely
mixed-mode case (e.g. a digital report with one scanned signature page
attached), which a single document-level verdict could never handle
correctly regardless of where the threshold was set.
"""

import re
import statistics


_CJK_RANGE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_NON_ALPHA = re.compile(r"[^A-Za-z]")
_CASE_TRANSITION = re.compile(r"[a-z][A-Z]")

VERY_LONG_TOKEN_THRESHOLD = 14
MEDIUM_TOKEN_THRESHOLD = 9
MEDIUM_TOKEN_MIN_COUNT = 2
COLUMN_TOLERANCE_PX = 20
MIN_ROWS_FOR_TABLE = 3
MIN_COLS_FOR_TABLE = 2


def convert_pdf(path: str, ocr_lang_hint: str = "auto") -> dict:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    if doc.is_encrypted:
        return {"markdown": "", "report": {"status": "failed", "reason": "password_protected"}}

    page_classes = []
    for i in range(len(doc)):
        text = doc[i].get_text("text").strip()
        page_classes.append("digital" if len(text) >= 1 else "scanned")

    if all(c == "digital" for c in page_classes):
        return _convert_digital(path, doc, list(range(len(doc))))
    if all(c == "scanned" for c in page_classes):
        return _convert_scanned(path, doc, list(range(len(doc))))
    return _convert_mixed(path, doc, page_classes)


def _convert_mixed(path: str, doc, page_classes) -> dict:
    digital_idx = [i for i, c in enumerate(page_classes) if c == "digital"]
    scanned_idx = [i for i, c in enumerate(page_classes) if c == "scanned"]

    digital_result = _convert_digital(path, doc, digital_idx) if digital_idx else None
    scanned_result = _convert_scanned(path, doc, scanned_idx) if scanned_idx else None

    # re-merge in original page order using each result's per-page markdown
    pages_md = {}
    if digital_result:
        for i, md in zip(digital_idx, digital_result["_per_page_md"]):
            pages_md[i] = md
    if scanned_result:
        for i, md in zip(scanned_idx, scanned_result["_per_page_md"]):
            pages_md[i] = md
    ordered_md = "\n\n".join(pages_md[i] for i in sorted(pages_md))

    report = {
        "status": "passed_with_warnings",
        "engine": "mixed(pdfplumber+rapidocr)",
        "page_count": len(doc),
        "digital_pages": [i + 1 for i in digital_idx],
        "scanned_pages": [i + 1 for i in scanned_idx],
        "ocr_used": bool(scanned_idx),
    }
    if digital_result:
        d = digital_result["report"]
        report["table_count"] = d.get("table_count", 0)
        report["table_row_consistency"] = d.get("table_row_consistency", "pass")
    if scanned_result:
        s = scanned_result["report"]
        for k in ("ocr_avg_confidence", "ocr_low_confidence_pages", "glued_word_pages",
                   "tesseract_fallback_pages", "engine_per_page", "table_regions_detected",
                   "table_structure_confidence", "table_likelihood"):
            if k in s:
                report[k] = s[k]

    elements = (digital_result.get("elements", []) if digital_result else []) + \
               (scanned_result.get("elements", []) if scanned_result else [])
    elements.sort(key=lambda e: e.get("page", 0))
    tables = (digital_result.get("tables", []) if digital_result else []) + \
             (scanned_result.get("tables", []) if scanned_result else [])

    return {"markdown": ordered_md, "report": report, "_per_page_md": [pages_md[i] for i in sorted(pages_md)],
            "elements": elements, "tables": tables}


def _convert_digital(path: str, doc, page_indices) -> dict:
    import pdfplumber

    per_page_md = []
    elements = []
    tables_out = []
    table_row_consistency = "pass"
    table_count = 0

    with pdfplumber.open(path) as pdf:
        for i in page_indices:
            page = pdf.pages[i]
            page_id = f"page-{i + 1:04d}"
            page_md = [f"<!-- page: {i + 1} -->\n"]
            tables = page.find_tables()
            table_bboxes = [t.bbox for t in tables]

            text = page.extract_text() or ""
            if not tables:
                page_md.append(text)
                _append_digital_text_elements(elements, page_id, doc[i], [], text, i + 1)
            else:
                text_no_tables = _strip_table_text(page, text, table_bboxes)
                page_md.append(text_no_tables)
                _append_digital_text_elements(elements, page_id, doc[i], table_bboxes,
                                              text_no_tables, i + 1)
                for t in tables:
                    table_count += 1
                    rows = t.extract()
                    if not rows:
                        continue
                    row_lengths = {len(r) for r in rows}
                    if len(row_lengths) > 1:
                        table_row_consistency = "warning"
                    page_md.append(_rows_to_markdown(rows))
                    table_id = f"table-p{i + 1:04d}-{table_count:04d}"
                    table_md = _rows_to_markdown(rows)
                    tables_out.append({"id": table_id, "rows": rows,
                                        "context": f"pdf_page_{i + 1}",
                                        "source_locator": {"page": i + 1, "bbox": list(t.bbox)},
                                        "engine": "pdfplumber"})
                    elements.append({
                        "id": f"{page_id}-table-{table_count:03d}",
                        "parent_id": page_id, "type": "table", "content": table_md,
                        "engine": "pdfplumber", "confidence": None,
                        "source_locator": {"page": i + 1, "bbox": list(t.bbox)},
                        "table_id": table_id,
                    })

            page_text = "\n".join(page_md)
            per_page_md.append(page_text)
            elements.insert(len(elements) - sum(1 for e in elements if e.get("parent_id") == page_id), {
                "id": page_id, "type": "page", "page": i + 1,
                "content": f"<!-- page: {i + 1} -->", "engine": "pdfplumber",
                "confidence": None, "source_locator": {"page": i + 1},
            })

    report = {
        "status": "passed",
        "engine": "pdfplumber",
        "page_count": len(doc),
        "table_count": table_count,
        "table_row_consistency": table_row_consistency,
        "ocr_used": False,
    }
    return {"markdown": "\n\n".join(per_page_md), "report": report, "_per_page_md": per_page_md,
            "elements": elements, "tables": tables_out}


def _strip_table_text(page, full_text, table_bboxes):
    """Remove words that fall inside a detected table's bounding box from the
    plain-text extraction, so table content isn't duplicated as both loose
    prose AND a Markdown table (verified as a real duplication bug: a
    table's cell values were showing up once in the running paragraph text
    and again in the rendered table, which is bad for RAG - doubles token
    count and can make a retriever return the same fact twice)."""
    if not table_bboxes:
        return full_text
    words = page.extract_words()
    kept = []
    for w in words:
        in_table = any(
            bbox[0] - 2 <= w["x0"] and w["x1"] <= bbox[2] + 2
            and bbox[1] - 2 <= w["top"] and w["bottom"] <= bbox[3] + 2
            for bbox in table_bboxes
        )
        if not in_table:
            kept.append(w["text"])
    return " ".join(kept) if kept else ""


def _append_digital_text_elements(elements, page_id, fitz_page, table_bboxes,
                                  fallback_text, page_number):
    blocks = []
    for raw in fitz_page.get_text("blocks"):
        if len(raw) < 5:
            continue
        bbox = tuple(raw[:4])
        content = (raw[4] or "").strip()
        if not content or any(_bbox_overlap_ratio(bbox, table_bbox) >= 0.5
                              for table_bbox in table_bboxes):
            continue
        blocks.append((bbox, content))
    if not blocks and fallback_text.strip():
        blocks = [(None, fallback_text.strip())]
    for index, (bbox, content) in enumerate(blocks, start=1):
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        element_type = "heading" if len(lines) == 1 and len(content) <= 120 else "paragraph"
        elements.append({
            "id": f"{page_id}-text-{index:03d}", "parent_id": page_id,
            "type": element_type, "content": content,
            "engine": "pymupdf+pdfplumber", "confidence": None,
            "source_locator": {"page": page_number,
                               "bbox": list(bbox) if bbox else None},
        })


def _bbox_overlap_ratio(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    width = max(0, min(ax1, bx1) - max(ax0, bx0))
    height = max(0, min(ay1, by1) - max(ay0, by0))
    intersection = width * height
    area = max((ax1 - ax0) * (ay1 - ay0), 1)
    return intersection / area


def _convert_scanned(path: str, doc, page_indices) -> dict:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {
            "markdown": "",
            "report": {"status": "failed", "reason": "rapidocr_not_installed"},
            "_per_page_md": ["" for _ in page_indices],
            "elements": [], "tables": [],
        }

    engine = RapidOCR()
    per_page_md = []
    elements = []
    tables_out = []
    all_confidences = []
    low_confidence_pages = []
    glued_word_pages = []
    tesseract_fallback_pages = []
    table_regions_detected = 0
    engine_per_page = {}
    page_likelihoods = []
    ocr_candidates = []

    for i in page_indices:
        page = doc[i]
        page_id = f"page-{i + 1:04d}"
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")

        result, _ = engine(img_bytes)
        boxes = [(r[0], r[1], r[2]) for r in result] if result else []

        combined_text = " ".join(b[1] for b in boxes)
        glued = _looks_glued(combined_text)
        script_is_latin = _is_majority_latin(combined_text)

        page_engine = "rapidocr"
        if glued and script_is_latin:
            tess_boxes = _ocr_page_tesseract(img_bytes)
            if tess_boxes:
                boxes = tess_boxes
                page_engine = "tesseract_fallback"
                tesseract_fallback_pages.append(i + 1)
            else:
                glued_word_pages.append(i + 1)
        elif glued:
            glued_word_pages.append(i + 1)

        engine_per_page[str(i + 1)] = page_engine

        if not boxes:
            page_text = f"<!-- page: {i + 1} (no text detected) -->\n"
            per_page_md.append(page_text)
            elements.append({"id": page_id, "type": "page", "page": i + 1,
                              "content": page_text, "engine": page_engine, "confidence": None,
                              "source_locator": {"page": i + 1}})
            continue

        page_confidences = [b[2] for b in boxes if b[2] is not None]
        all_confidences.extend(page_confidences)
        page_avg_conf = round(statistics.mean(page_confidences), 3) if page_confidences else None
        if page_confidences and statistics.mean(page_confidences) < 0.75:
            low_confidence_pages.append(i + 1)

        from ocr_table import assess_ocr_table
        candidate = assess_ocr_table(boxes, i + 1, page_engine,
                                      f"ocr-table-candidate-{i + 1:04d}")
        ocr_candidates.append(candidate)
        table_rows = candidate["rows"] if candidate["decision"] == "accepted" else None
        if table_rows:
            table_regions_detected += 1
            page_text = _rows_to_markdown(table_rows)
            table_id = f"table-ocr-p{i + 1:04d}-{table_regions_detected:04d}"
            tables_out.append({"id": table_id, "rows": table_rows,
                                "context": f"pdf_scanned_page_{i + 1}",
                                "source_locator": {"format": "pdf", "page_start": i + 1, "page_end": i + 1},
                                "engine": page_engine, "confidence": candidate["confidence"],
                                "properties": {"origin": "ocr_table_candidate", "candidate_id": candidate["candidate_id"], "decision": "accepted", "signals": candidate["signals"]}})
        else:
            page_text = _reconstruct_layout(boxes)
            page_likelihoods.append(_estimate_table_likelihood(boxes))

        full_page_text = f"<!-- page: {i + 1} -->\n\n{page_text}"
        per_page_md.append(full_page_text)
        elements.append({"id": page_id, "type": "page", "page": i + 1,
                          "content": f"<!-- page: {i + 1} -->", "engine": page_engine,
                          "confidence": page_avg_conf, "source_locator": {"page": i + 1}})
        elements.append({
            "id": f"{page_id}-{'table' if table_rows else 'text'}-001",
            "parent_id": page_id, "type": "table" if table_rows else "text",
            "content": page_text, "engine": page_engine,
            "confidence": page_avg_conf, "source_locator": {"page": i + 1},
            **({"table_id": table_id} if table_rows else {}),
        })

    avg_conf = round(statistics.mean(all_confidences), 3) if all_confidences else 0.0
    status = "passed"
    if glued_word_pages or low_confidence_pages:
        status = "passed_with_warnings"

    # Max, not average: one page that looks strongly tabular is reason
    # enough to flag TABLE_STRUCTURE_UNVERIFIED even if most other pages
    # in the document are plain prose (averaging would dilute it away).
    max_likelihood = max(page_likelihoods) if page_likelihoods else 0.0

    report = {
        "status": status,
        "engine": "rapidocr_onnxruntime",
        "page_count": len(doc),
        "ocr_used": True,
        "ocr_avg_confidence": avg_conf,
        "ocr_low_confidence_pages": low_confidence_pages,
        "glued_word_pages": glued_word_pages,
        "tesseract_fallback_pages": tesseract_fallback_pages,
        "engine_per_page": engine_per_page,
        "table_regions_detected": table_regions_detected,
        "table_likelihood": round(max_likelihood, 3),
        "ocr_table_candidates": ocr_candidates,
        "ocr_table_assessment": {"candidate_count": len(ocr_candidates), "accepted_count": sum(c["decision"] == "accepted" for c in ocr_candidates), "rejected_count": sum(c["decision"] != "accepted" for c in ocr_candidates), "fallback_to_text_count": sum(c["decision"] == "fallback_to_text" for c in ocr_candidates), "low_confidence_count": sum(c["confidence"] < .60 for c in ocr_candidates)},
        "table_structure_confidence": (
            "clustered (column-heuristic table detected)"
            if table_regions_detected else
            "low (no column-aligned table pattern found; bounding-box "
            "reading-order text only)"
        ),
    }
    return {"markdown": "\n\n".join(per_page_md), "report": report, "_per_page_md": per_page_md,
            "elements": elements, "tables": tables_out}


def _looks_glued(text: str) -> bool:
    tokens = [t for t in re.split(r"\s+", text) if t]
    if not tokens:
        return False
    cores = [_NON_ALPHA.sub("", t) for t in tokens]
    if any(len(c) >= 6 and _CASE_TRANSITION.search(c) for c in cores):
        return True
    if any(len(c) >= VERY_LONG_TOKEN_THRESHOLD for c in cores):
        return True
    medium = [c for c in cores if len(c) >= MEDIUM_TOKEN_THRESHOLD]
    if len(medium) >= MEDIUM_TOKEN_MIN_COUNT:
        return True
    return False


def _is_majority_latin(text: str) -> bool:
    cjk_count = len(_CJK_RANGE.findall(text))
    latin_count = len(_LATIN_LETTER.findall(text))
    if cjk_count + latin_count == 0:
        return False
    return latin_count > cjk_count


def _ocr_page_tesseract(img_bytes: bytes):
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(img_bytes))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    boxes = []
    n = len(data.get("text", []))
    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue
        try:
            conf = max(0.0, float(data["conf"][i])) / 100.0
        except (ValueError, TypeError):
            conf = 0.0
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        boxes.append((pts, text, conf))
    return boxes


def _group_lines(boxes, y_tolerance: int = 10):
    items = []
    for pts, text, conf in boxes:
        y = pts[0][1]
        x = pts[0][0]
        items.append((y, x, text))
    items.sort(key=lambda t: t[0])

    lines = []
    current_line = [items[0]]
    for item in items[1:]:
        if abs(item[0] - current_line[-1][0]) <= y_tolerance:
            current_line.append(item)
        else:
            lines.append(current_line)
            current_line = [item]
    lines.append(current_line)
    for line in lines:
        line.sort(key=lambda t: t[1])
    return lines


def _reconstruct_layout(boxes, y_tolerance: int = 10) -> str:
    if not boxes:
        return ""
    lines = _group_lines(boxes, y_tolerance)
    return "\n".join(" ".join(t[2] for t in line) for line in lines)


def _cluster_into_table(boxes, y_tolerance: int = 10):
    if len(boxes) < MIN_ROWS_FOR_TABLE * MIN_COLS_FOR_TABLE:
        return None
    lines = _group_lines(boxes, y_tolerance)
    if len(lines) < MIN_ROWS_FOR_TABLE:
        return None

    all_x = sorted(x for line in lines for (_, x, _) in line)
    clusters = []
    for x in all_x:
        if clusters and x - clusters[-1][-1] <= COLUMN_TOLERANCE_PX:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    column_bins = [statistics.mean(c) for c in clusters if len(c) >= MIN_ROWS_FOR_TABLE]
    if len(column_bins) < MIN_COLS_FOR_TABLE:
        return None

    def nearest_bin(x):
        return min(range(len(column_bins)), key=lambda i: abs(column_bins[i] - x))

    rows = []
    lines_with_multi_cols = 0
    for line in lines:
        row = [""] * len(column_bins)
        hit_bins = set()
        for (_, x, text) in line:
            b = nearest_bin(x)
            row[b] = (row[b] + " " + text).strip() if row[b] else text
            hit_bins.add(b)
        if len(hit_bins) >= MIN_COLS_FOR_TABLE:
            lines_with_multi_cols += 1
        rows.append(row)

    if lines_with_multi_cols < MIN_ROWS_FOR_TABLE:
        return None
    return rows


def _estimate_table_likelihood(boxes, y_tolerance: int = 10) -> float:
    """Score (0.0-1.0) of how much a page's OCR boxes LOOK tabular, used
    so TABLE_STRUCTURE_UNVERIFIED can be reserved for pages that actually
    resemble a table but fell just short of _cluster_into_table's stricter
    thresholds - not fired as a blanket disclaimer on every scanned page
    with zero table content (the v1.5 behavior: `table_structure_confidence`
    was set to "low" for literally every page where no table was detected,
    including a plain scanned letter with no tabular content at all, so
    the warning carried no actual information about whether a table might
    have been missed).

    Deliberately looser than _cluster_into_table (which requires >=3 rows
    and >=2 repeated column positions before rendering an actual table):
    this only has to notice "this page has some column-aligned structure",
    not confirm it well enough to safely reconstruct row/column content.
    Combines:
      - row_ratio: fraction of lines that hit >=2 distinct column bins
      - col_score: how many repeated column positions were found (capped)
      - density_score: roughly how "filled in" the implied grid is
    """
    if len(boxes) < 4:
        return 0.0
    lines = _group_lines(boxes, y_tolerance)
    if len(lines) < 2:
        return 0.0

    all_x = sorted(x for line in lines for (_, x, _) in line)
    clusters = []
    for x in all_x:
        if clusters and x - clusters[-1][-1] <= COLUMN_TOLERANCE_PX:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    # relaxed vs _cluster_into_table: only 2 hits needed to count a
    # column position as "repeated", not MIN_ROWS_FOR_TABLE
    repeated_bins = [c for c in clusters if len(c) >= 2]
    if not repeated_bins:
        return 0.0
    column_bins = [statistics.mean(c) for c in repeated_bins]

    def nearest_bin(x):
        return min(range(len(column_bins)), key=lambda i: abs(column_bins[i] - x))

    lines_with_multi = 0
    for line in lines:
        hit_bins = {nearest_bin(x) for (_, x, _) in line}
        if len(hit_bins) >= 2:
            lines_with_multi += 1

    row_ratio = lines_with_multi / len(lines)
    col_score = min(len(column_bins) / 4.0, 1.0)
    density_score = min(len(boxes) / (len(lines) * max(len(column_bins), 1)), 1.0)

    likelihood = 0.5 * row_ratio + 0.3 * col_score + 0.2 * density_score
    return round(min(likelihood, 1.0), 3)


def _rows_to_markdown(rows) -> str:
    if not rows:
        return ""
    header = rows[0]
    lines = ["| " + " | ".join(_c(x) for x in header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows[1:]:
        row = list(row) + [None] * (len(header) - len(row))
        lines.append("| " + " | ".join(_c(x) for x in row[:len(header)]) + " |")
    return "\n".join(lines)


def _c(v) -> str:
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", "<br>")
