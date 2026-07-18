"""
pdf_converter.py
Routes PDFs by whether they carry a real text layer:
  - digital PDF  -> pdfplumber (text + line-based table detection)
  - scanned PDF  -> rasterize each page with PyMuPDF, OCR with RapidOCR,
                    with a Tesseract fallback for Latin-script pages
                    (see "glued word" fix below), plus a bounding-box
                    column-clustering pass for table reconstruction.

--- Revision history / why this file looks the way it does -----------------

v1 shipped RapidOCR as the only scanned-page engine and a flat
`TABLE_STRUCTURE_UNVERIFIED` warning on every scanned page regardless of
whether the page actually contained a table. Real-world testing (a mixed
Chinese/English scanned invoice with a fee table) surfaced two concrete,
root-caused problems, not just "quality is imperfect":

1. GLUED WORDS ON LATIN-SCRIPT TEXT (root cause, not random noise):
   RapidOCR's bundled recognition model (PP-OCRv4) is trained for
   CJK text, where there is no inter-word spacing to begin with. Its
   recognition head was never trained to predict a space token the way
   an English-trained model is, so when the *same detection box*
   actually spans multiple English words, the recognizer transcribes
   them as one glued string. Adding spaces *between* detection boxes
   (which is all v1 did) does not fix this, because the missing spaces
   are *inside* a single box's output, not between boxes.
   FIX: detect the symptom directly in the recognized text (very long
   average token length is diagnostic of this specific failure mode),
   and only for pages whose content is mostly Latin script, re-OCR that
   page with Tesseract, which detects at word granularity and does not
   have this failure mode. CJK pages are untouched and keep using
   RapidOCR, which is the right tool for that content.

2. NO TABLE DETECTION ON THE SCANNED PATH: the digital-PDF path uses
   pdfplumber's real table/line detection; the scanned path had no
   equivalent and just poured every text box through a reading-order
   text reconstruction, which silently misaligns multi-column tables.
   FIX: a column-clustering pass on OCR box x-coordinates. If a
   repeated set of column start-positions appears across several lines,
   treat that region as a table and render it as a real Markdown table
   instead of flattened prose.

3. THE WARNING SYSTEM DIDN'T ACTUALLY CHECK THE OUTPUT: v1's
   `TABLE_STRUCTURE_UNVERIFIED` fired unconditionally on every scanned
   page, and average OCR confidence (which was high, ~0.94) didn't
   catch the glued-word problem because RapidOCR was confident about
   its (wrong) glued transcription. FIX: content-level heuristics
   (average token length, long-token ratio) that inspect what actually
   came out, not just which code path ran.
------------------------------------------------------------------------- """

import re
import statistics


_CJK_RANGE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_NON_ALPHA = re.compile(r"[^A-Za-z]")
# lower-follows-by-upper inside a token is the single strongest signature of
# two glued English words (e.g. "eTotalAmount" from "e" + "Total Amount");
# a page-wide average token length is NOT a reliable signal on its own,
# because a handful of short function words ("the", "a", "30") dilute the
# average even when a page clearly has glued tokens - this is exactly the
# gap that let a real glued-word page through undetected during testing.
_CASE_TRANSITION = re.compile(r"[a-z][A-Z]")

VERY_LONG_TOKEN_THRESHOLD = 14      # a single token this long, alone, is suspicious
MEDIUM_TOKEN_THRESHOLD = 9          # two or more tokens this long is suspicious
MEDIUM_TOKEN_MIN_COUNT = 2
COLUMN_TOLERANCE_PX = 20            # x-coordinates within this are "the same column"
MIN_ROWS_FOR_TABLE = 3              # need at least this many aligned rows to call it a table
MIN_COLS_FOR_TABLE = 2


def convert_pdf(path: str, ocr_lang_hint: str = "auto") -> dict:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    if doc.is_encrypted:
        return {"markdown": "", "report": {"status": "failed", "reason": "password_protected"}}

    sample_pages = min(3, len(doc))
    text_chars = sum(len(doc[i].get_text()) for i in range(sample_pages))
    is_digital = text_chars > 50  # empirical threshold; scanned pages yield ~0

    if is_digital:
        return _convert_digital(path, doc)
    else:
        return _convert_scanned(path, doc)


def _convert_digital(path: str, doc) -> dict:
    import pdfplumber

    pages_md = []
    table_row_consistency = "pass"
    table_count = 0

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_md = [f"<!-- page: {i + 1} -->\n"]
            tables = page.find_tables()

            text = page.extract_text() or ""
            if not tables:
                page_md.append(text)
            else:
                page_md.append(text)
                for t in tables:
                    table_count += 1
                    rows = t.extract()
                    if not rows:
                        continue
                    row_lengths = {len(r) for r in rows}
                    if len(row_lengths) > 1:
                        table_row_consistency = "warning"
                    page_md.append(_rows_to_markdown(rows))

            pages_md.append("\n".join(page_md))

    report = {
        "status": "passed",
        "engine": "pdfplumber",
        "page_count": len(doc),
        "table_count": table_count,
        "table_row_consistency": table_row_consistency,
        "ocr_used": False,
    }
    return {"markdown": "\n\n".join(pages_md), "report": report}


def _convert_scanned(path: str, doc) -> dict:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {
            "markdown": "",
            "report": {"status": "failed", "reason": "rapidocr_not_installed"},
        }

    engine = RapidOCR()
    pages_md = []
    all_confidences = []
    low_confidence_pages = []
    glued_word_pages = []
    tesseract_fallback_pages = []
    table_regions_detected = 0
    engine_per_page = {}

    for i in range(len(doc)):
        page = doc[i]
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
                glued_word_pages.append(i + 1)  # fallback unavailable; still flag it
        elif glued:
            # glued but not clearly Latin script (e.g. mixed CJK/Latin) -
            # Tesseract wouldn't reliably help either; just flag it honestly
            glued_word_pages.append(i + 1)

        engine_per_page[str(i + 1)] = page_engine

        if not boxes:
            pages_md.append(f"<!-- page: {i + 1} (no text detected) -->\n")
            continue

        page_confidences = [b[2] for b in boxes if b[2] is not None]
        all_confidences.extend(page_confidences)
        if page_confidences and statistics.mean(page_confidences) < 0.75:
            low_confidence_pages.append(i + 1)

        table_rows = _cluster_into_table(boxes)
        if table_rows:
            table_regions_detected += 1
            page_text = _rows_to_markdown(table_rows)
        else:
            page_text = _reconstruct_layout(boxes)

        pages_md.append(f"<!-- page: {i + 1} -->\n\n{page_text}")

    avg_conf = round(statistics.mean(all_confidences), 3) if all_confidences else 0.0
    status = "passed"
    if glued_word_pages or low_confidence_pages:
        status = "passed_with_warnings"

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
        "table_structure_confidence": (
            "clustered (column-heuristic table detected)"
            if table_regions_detected else
            "low (no column-aligned table pattern found; bounding-box "
            "reading-order text only)"
        ),
    }
    return {"markdown": "\n\n".join(pages_md), "report": report}


# ---------------------------------------------------------------------------
# Content-level heuristics (inspect the actual OCR output, not just which
# code path ran)
# ---------------------------------------------------------------------------

def _looks_glued(text: str) -> bool:
    """Detect the 'CJK-model-swallowed-the-spaces' symptom: a single
    detection box's recognized text is actually two or more English words
    with no space between them.

    Deliberately per-token, not a page-wide average - an average dilutes
    the signal to nothing on a page that mixes a few glued tokens with
    many short normal words (verified: a real glued-word test page had
    tokens ['eTotalAmount'(12), 'Pleaseremit'(11), ...] alongside ['Due'(3),
    '30'(2), 't'(1)...], giving a page average of ~5.8 - well under any
    reasonable single threshold, even though the page clearly had a
    gluing problem)."""
    tokens = [t for t in re.split(r"\s+", text) if t]
    if not tokens:
        return False

    cores = [_NON_ALPHA.sub("", t) for t in tokens]

    # signal 1 (strongest): lower-to-upper transition inside a token, e.g.
    # "eTotalAmount" - real English words essentially never do this.
    if any(len(c) >= 6 and _CASE_TRANSITION.search(c) for c in cores):
        return True

    # signal 2: a single implausibly long alphabetic run
    if any(len(c) >= VERY_LONG_TOKEN_THRESHOLD for c in cores):
        return True

    # signal 3: multiple moderately-long tokens together (cumulative signal;
    # a lone long-but-real word like "International" shouldn't trip this,
    # but two or more on one page is a real pattern worth flagging)
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


# ---------------------------------------------------------------------------
# Tesseract fallback for Latin-script pages that RapidOCR glued together
# ---------------------------------------------------------------------------

def _ocr_page_tesseract(img_bytes: bytes):
    """Re-OCR a page with Tesseract, which detects at word granularity and
    doesn't have the CJK-model space-swallowing problem. Returns boxes in
    the same (points, text, confidence) shape the RapidOCR path uses, so
    downstream layout/table code doesn't need to know which engine ran."""
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
        conf_raw = data["conf"][i]
        try:
            conf = max(0.0, float(conf_raw)) / 100.0
        except (ValueError, TypeError):
            conf = 0.0
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        boxes.append((pts, text, conf))
    return boxes


# ---------------------------------------------------------------------------
# Layout reconstruction: plain reading order, or a clustered table
# ---------------------------------------------------------------------------

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
    """Group OCR boxes into lines by y-coordinate, order left-to-right.
    Simple, honest heuristic - not a layout model. Used when
    `_cluster_into_table` doesn't find a table-like pattern on the page."""
    if not boxes:
        return ""
    lines = _group_lines(boxes, y_tolerance)
    return "\n".join(" ".join(t[2] for t in line) for line in lines)


def _cluster_into_table(boxes, y_tolerance: int = 10):
    """Heuristic column-clustering table reconstruction.

    Collects the left-edge x-coordinate of every box, clusters nearby
    x-values into candidate column boundaries, then checks whether those
    boundaries repeat consistently across enough lines to be a real table
    (as opposed to justified paragraph text, which won't have repeated
    column starts). Returns a list-of-rows table if found, else None.

    This is explicitly a heuristic, not a layout model - see engine_notes.md
    for the honest limitations of this approach vs. a real table-structure
    model (e.g. Docling's TableFormer).
    """
    if len(boxes) < MIN_ROWS_FOR_TABLE * MIN_COLS_FOR_TABLE:
        return None

    lines = _group_lines(boxes, y_tolerance)
    if len(lines) < MIN_ROWS_FOR_TABLE:
        return None

    # candidate column x-starts, clustered across the whole page
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

    # how many lines actually have a box landing in each bin?
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
        return None  # doesn't look tabular enough; let plain reconstruction handle it

    return rows


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
