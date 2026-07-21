"""Offline OCR conversion for PNG/JPEG/TIFF/BMP/WebP images."""

import statistics

from pdf_converter import (
    _cluster_into_table, _estimate_table_likelihood, _is_majority_latin,
    _looks_glued, _ocr_page_tesseract, _reconstruct_layout, _rows_to_markdown,
)


def convert_image(path: str) -> dict:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {"markdown": "", "report": {"status": "failed",
                "reason": "rapidocr_not_installed"}, "elements": [], "tables": []}

    with open(path, "rb") as f:
        image_bytes = f.read()
    result, _ = RapidOCR()(image_bytes)
    boxes = [(row[0], row[1], row[2]) for row in result] if result else []
    combined = " ".join(box[1] for box in boxes)
    glued = _looks_glued(combined)
    fallback_used = False
    if glued and _is_majority_latin(combined):
        fallback = _ocr_page_tesseract(image_bytes)
        if fallback:
            boxes = fallback
            fallback_used = True

    confidences = [box[2] for box in boxes if box[2] is not None]
    avg_confidence = round(statistics.mean(confidences), 3) if confidences else 0.0
    table_rows = _cluster_into_table(boxes) if boxes else None
    table_likelihood = _estimate_table_likelihood(boxes) if boxes and not table_rows else 0.0
    markdown = _rows_to_markdown(table_rows) if table_rows else _reconstruct_layout(boxes)
    engine = "tesseract_fallback" if fallback_used else "rapidocr"
    tables = []
    elements = [{
        "id": "image-ocr-region-0001", "type": "table" if table_rows else "ocr_region",
        "content": markdown, "engine": engine, "confidence": avg_confidence,
        "source_locator": {"bbox": _overall_bbox(boxes)},
    }]
    if table_rows:
        tables.append({"id": "table-image-0001", "rows": table_rows,
                       "context": "image_ocr", "engine": engine,
                       "confidence": avg_confidence,
                       "source_locator": {"bbox": _overall_bbox(boxes)}})
        elements[0]["table_id"] = "table-image-0001"

    low_confidence = bool(confidences and avg_confidence < 0.75)
    report = {
        "status": "passed_with_warnings" if low_confidence or (glued and not fallback_used)
                  else "passed",
        "engine": engine,
        "ocr_used": True,
        "ocr_avg_confidence": avg_confidence,
        "ocr_low_confidence_pages": [1] if low_confidence else [],
        "glued_word_pages": [1] if glued and not fallback_used else [],
        "tesseract_fallback_pages": [1] if fallback_used else [],
        "engine_per_page": {"1": engine},
        "table_regions_detected": 1 if table_rows else 0,
        "table_likelihood": table_likelihood,
    }
    return {"markdown": markdown, "report": report, "elements": elements, "tables": tables}


def _overall_bbox(boxes):
    if not boxes:
        return None
    xs = [point[0] for box, _, _ in boxes for point in box]
    ys = [point[1] for box, _, _ in boxes for point in box]
    return [min(xs), min(ys), max(xs), max(ys)]
