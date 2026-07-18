"""
quality_check.py
Turns each converter's raw report into a single, honest
conversion-report.json. The goal stated throughout this skill's design:
no silent success. Anything degraded, skipped, or uncertain must show up
here, not just in a nicely formatted Markdown file that looks fine at a
glance.
"""

import re

_MOJIBAKE_PATTERN = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")


def build_report(source_path: str, file_type: str, converter_report: dict, markdown: str) -> dict:
    warnings = []
    status = converter_report.get("status", "passed")

    if status == "failed":
        return {
            "source_file": source_path,
            "file_type": file_type,
            "status": "failed",
            "reason": converter_report.get("reason", "unknown"),
        }

    # 1. mojibake / control-character sniff
    mojibake_hits = len(_MOJIBAKE_PATTERN.findall(markdown))
    if mojibake_hits > 0:
        warnings.append({
            "code": "POSSIBLE_MOJIBAKE",
            "count": mojibake_hits,
            "message": "Replacement characters or control bytes found in output; "
                       "check source encoding detection.",
        })

    # 2. text coverage sanity (near-empty output from a non-trivial file)
    if len(markdown.strip()) < 20:
        warnings.append({
            "code": "NEAR_EMPTY_OUTPUT",
            "message": "Converted Markdown is nearly empty; conversion may have "
                       "silently failed.",
        })
        status = "failed"

    # 3. per-format specific carry-overs
    if file_type == "xlsx":
        total = converter_report.get("total_merged_ranges", 0)
        rendered = converter_report.get("merged_ranges_rendered", 0)
        if total != rendered:
            warnings.append({
                "code": "MERGED_CELLS_INCOMPLETE",
                "message": f"{total} merged ranges found but only {rendered} rendered.",
            })

    if file_type == "pdf" and converter_report.get("ocr_used"):
        low_pages = converter_report.get("ocr_low_confidence_pages", [])
        if low_pages:
            warnings.append({
                "code": "LOW_OCR_CONFIDENCE_PAGES",
                "pages": low_pages,
                "message": "These pages had average OCR confidence below 0.75; "
                           "manual review recommended.",
            })

        glued_pages = converter_report.get("glued_word_pages", [])
        if glued_pages:
            warnings.append({
                "code": "MISSING_WORD_SPACING",
                "pages": glued_pages,
                "message": "Recognized text on these pages has abnormally long "
                           "tokens (average token length or long-token count "
                           "exceeded threshold) - a symptom of a CJK-tuned OCR "
                           "model swallowing spaces inside a single detection "
                           "box on Latin-script content. A Tesseract re-OCR was "
                           "attempted where the page looked majority-Latin; if "
                           "this page is still flagged, either Tesseract wasn't "
                           "available or the script mix was ambiguous - "
                           "spot-check this page's text manually.",
            })

        tesseract_pages = converter_report.get("tesseract_fallback_pages", [])
        if tesseract_pages:
            warnings.append({
                "code": "TESSERACT_FALLBACK_USED",
                "pages": tesseract_pages,
                "message": "These pages were re-OCR'd with Tesseract instead of "
                           "the default RapidOCR because the initial pass looked "
                           "like glued Latin-script text. Informational, not "
                           "necessarily a problem.",
            })

        # Only warn about unverified table structure when the page actually
        # looked tabular but column-clustering couldn't confirm it - not as
        # a blanket disclaimer on every scanned page.
        table_conf = converter_report.get("table_structure_confidence", "")
        if table_conf.startswith("low") and converter_report.get("table_regions_detected", 0) == 0:
            warnings.append({
                "code": "TABLE_STRUCTURE_UNVERIFIED",
                "message": "No column-aligned table pattern was detected on the "
                           "scanned pages, so text was reconstructed in plain "
                           "reading order. If this document actually contains a "
                           "table, its row/column structure was NOT reconstructed "
                           "- verify manually or escalate to a Tier-2 engine "
                           "(Docling/MinerU) on a less-constrained environment.",
            })
        elif converter_report.get("table_regions_detected", 0) > 0:
            warnings.append({
                "code": "TABLE_STRUCTURE_HEURISTIC",
                "regions": converter_report["table_regions_detected"],
                "message": "A column-aligned pattern was detected and rendered "
                           "as a table via x-coordinate clustering (not a "
                           "trained table-structure model). Spot-check column "
                           "alignment, especially for merged/spanning cells.",
            })

    if file_type == "pdf" and converter_report.get("table_row_consistency") == "warning":
        warnings.append({
            "code": "INCONSISTENT_TABLE_ROW_LENGTHS",
            "message": "Some extracted table rows have differing column counts; "
                       "check for merged cells or split rows in the source PDF.",
        })

    if warnings and status == "passed":
        status = "passed_with_warnings"

    return {
        "source_file": source_path,
        "file_type": file_type,
        "status": status,
        "engine": converter_report.get("engine"),
        "warnings": warnings,
        "details": converter_report,
    }
