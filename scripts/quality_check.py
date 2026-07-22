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


def build_report(source_path: str, file_type: str, converter_report: dict, markdown: str,
                  fmt_info: dict = None) -> dict:
    warnings = list(converter_report.get("warnings", []))
    status = converter_report.get("status", "passed")

    if status == "failed":
        failed = {
            "source_file": source_path,
            "file_type": file_type,
            "status": "failed",
            "reason": converter_report.get("reason", "unknown"),
        }
        for key in ("error_type", "error_message"):
            if converter_report.get(key) is not None:
                failed[key] = converter_report[key]
        return failed

    if fmt_info and fmt_info.get("mismatch"):
        warnings.append({
            "code": "FORMAT_EXTENSION_MISMATCH",
            "declared_extension": fmt_info.get("declared_extension"),
            "detected_by_magic": fmt_info.get("detected_by_magic"),
            "message": f"The file's extension suggests '{fmt_info.get('declared_extension')}' "
                       f"but its actual content signature indicates "
                       f"'{fmt_info.get('detected_by_magic')}'. The detected format was used "
                       "for conversion, not the declared extension.",
        })

    if converter_report.get("encryption_check") == "unknown":
        warnings.append({
            "code": "ENCRYPTION_CHECK_INCONCLUSIVE",
            "message": "Could not conclusively determine whether this file is "
                       "password-protected (parser error on an unusual/corrupt "
                       "file, or the encryption-detection dependency wasn't "
                       "available). Conversion proceeded, but if the output looks "
                       "empty or garbled, a missed encryption check is one "
                       "possible cause.",
        })

    # 1. mojibake / control-character sniff
    mojibake_hits = len(_MOJIBAKE_PATTERN.findall(markdown))
    if mojibake_hits > 0:
        warnings.append({
            "code": "POSSIBLE_MOJIBAKE",
            "count": mojibake_hits,
            "message": "Replacement characters or control bytes found in output; "
                       "check source encoding detection.",
        })

    # 2. Empty output is a failure. Do not use an arbitrary minimum character
    # count: a valid JSON scalar, one-cell sheet, short slide, or OCR label can
    # legitimately contain fewer than 20 characters.
    if not markdown.strip():
        warnings.append({
            "code": "EMPTY_OUTPUT",
            "message": "Converted Markdown is empty; conversion did not recover content.",
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
        missing_formula_cells = converter_report.get("formula_cached_values_missing", 0)
        if missing_formula_cells:
            warnings.append({
                "code": "FORMULA_RESULT_UNAVAILABLE",
                "count": missing_formula_cells,
                "cells": converter_report.get("formula_cached_values_missing_cells", []),
                "message": f"{missing_formula_cells} formula cell(s) have no cached "
                           "value stored in the file (the workbook was saved without "
                           "being recalculated by Excel/LibreOffice, or was written "
                           "by a tool that doesn't compute formulas). The formula "
                           "text itself is preserved in the output instead of a "
                           "blank cell, but no computed result is available - open "
                           "the file in a spreadsheet app and re-save to populate it "
                           "if the value is needed.",
            })
        if converter_report.get("charts_found", 0):
            warnings.append({
                "code": "XLSX_CHART_NOT_RENDERED",
                "count": converter_report["charts_found"],
                "message": "Excel chart object(s) were detected and represented as canonical references, "
                           "but their plotted series were not rendered into Markdown.",
            })

    if file_type in ("csv", "tsv") and converter_report.get("encoding_ambiguous"):
        warnings.append({
            "code": "ENCODING_AMBIGUOUS",
            "candidates": converter_report.get("encoding_candidates", []),
            "message": "More than one text encoding decoded this file with a similar "
                       "plausibility score. The top candidate was used, but if the "
                       "output looks wrong, this file's encoding could not be "
                       "determined with high confidence - check the "
                       "encoding_candidates list and consider re-specifying it "
                       "manually.",
        })

    if file_type == "json":
        if not converter_report.get("json_valid", True):
            warnings.append({
                "code": "INVALID_JSON_PRESERVED",
                "message": "The input did not parse as valid JSON. Its text was preserved in a JSON code block, but no structured JSON guarantee is possible.",
            })
        if converter_report.get("encoding_ambiguous"):
            warnings.append({
                "code": "ENCODING_AMBIGUOUS",
                "candidates": converter_report.get("encoding_candidates", []),
                "message": "The JSON file's text encoding is ambiguous; rerun with --encoding if the output looks wrong.",
            })

    if file_type == "pdf" and converter_report.get("digital_pages") is not None:
        warnings.append({
            "code": "MIXED_PDF_MODE",
            "digital_pages": converter_report.get("digital_pages", []),
            "scanned_pages": converter_report.get("scanned_pages", []),
            "message": "This PDF has both digital-text and scanned/image pages. "
                       "Each page was routed to the right extractor individually "
                       "(pdfplumber for digital, OCR for scanned) rather than "
                       "forcing the whole document through one path.",
        })

    if file_type in ("pdf", "image") and converter_report.get("ocr_used"):
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
        # looked tabular (table_likelihood score) but clustering couldn't
        # confirm it - not as a blanket disclaimer on every scanned page.
        # v1.5.1 fix: the old condition (`table_structure_confidence`
        # startswith "low") fired on EVERY scanned page with zero detected
        # tables, including plain prose letters with no tabular content at
        # all, because that string was hardcoded to "low" whenever
        # table_regions_detected == 0 - it never actually measured how
        # tabular the page looked. table_likelihood (see pdf_converter.py)
        # is a real per-page heuristic score, so the warning now only
        # fires when the page plausibly contained a table that wasn't
        # confidently reconstructed.
        table_likelihood = converter_report.get("table_likelihood", 0.0)
        if converter_report.get("table_regions_detected", 0) == 0 and table_likelihood >= 0.4:
            warnings.append({
                "code": "TABLE_STRUCTURE_UNVERIFIED",
                "table_likelihood": table_likelihood,
                "message": "This page's text layout looks column-aligned "
                           "(possible table) but a column-aligned pattern "
                           "confident enough to reconstruct rows/columns "
                           "was NOT detected, so text was reconstructed in "
                           "plain reading order instead. If this document "
                           "actually contains a table, its row/column "
                           "structure was NOT preserved - verify manually "
                           "or escalate to a Tier-2 engine (Docling/MinerU) "
                           "on a less-constrained environment.",
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

    if file_type == "pptx":
        smartart_count = converter_report.get("smartart_parts_found", 0)
        ole_count = converter_report.get("ole_objects_found", 0)
        if smartart_count:
            warnings.append({
                "code": "SMARTART_NOT_EXTRACTED",
                "count": smartart_count,
                "occurrences": converter_report.get("smartart_occurrences", []),
                "message": f"{smartart_count} SmartArt diagram part(s) detected in this "
                           "presentation. SmartArt content is stored as separate diagram "
                           "data, not plain text, and is out of scope for this converter "
                           "- its text/shapes were NOT extracted into the Markdown output. "
                           "Open the original file to view this content.",
            })
        if ole_count:
            warnings.append({
                "code": "EMBEDDED_OLE_NOT_EXTRACTED",
                "count": ole_count,
                "occurrences": converter_report.get("ole_occurrences", []),
                "message": f"{ole_count} embedded OLE object(s) detected (e.g. an embedded "
                           "Excel/Word object placed on a slide). OLE object content is out "
                           "of scope for this converter and was NOT extracted into the "
                           "Markdown output. Open the original file to view this content.",
            })

    # Status is derived from formal warnings, never from an informational note.
    if status != "failed":
        status = "passed_with_warnings" if warnings else "passed"
    if status != "failed" and not isinstance(converter_report.get("engine"), str):
        raise ValueError("successful conversion report requires a non-empty primary engine")
    if status != "failed" and not converter_report.get("engine", "").strip():
        raise ValueError("successful conversion report requires a non-empty primary engine")

    return {
        "source_file": source_path,
        "file_type": file_type,
        "status": status,
        "engine": converter_report.get("engine"),
        "warnings": warnings,
        "details": converter_report,
    }
