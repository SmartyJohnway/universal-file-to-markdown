#!/usr/bin/env python3
"""
router.py
Entry point for the universal-file-to-markdown skill.

    python3 router.py INPUT_FILE --output OUTPUT_DIR

Produces an output bundle:
    OUTPUT_DIR/
      document.md              human/LLM-readable Markdown
      document.json            canonical schema 1.0 (introduced in skill v1.6)
      chunks.jsonl              bounded RAG chunks, canonical schema 1.0
      tables/                  canonical JSON plus standalone CSV/HTML assets
      manifest.json
      conversion-report.json
      assets/                  embedded images/media, if any

Design note: this router deliberately does NOT reach for Docling / MinerU /
any torch-based engine. See references/engine_notes.md for why - in short,
those engines need multi-GB installs and a Hugging Face model download that
is blocked in network-restricted sandboxes (verified empirically for this
skill). Every engine used here is either pure-stdlib, a small structural
parser (openpyxl/python-docx/pdfplumber/python-pptx), or a fully
self-contained offline model (RapidOCR, ~15MB, bundled in the pip wheel).
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common_utils import (
    check_office_encrypted,
    check_pdf_encrypted,
    convert_csv_native,
    convert_json_native,
    convert_eml_native,
)
from format_detector import resolve_format
from quality_check import build_report
from document_model import build_document_json
from chunker import build_chunks
from table_export import export_tables
from table_model import normalize_tables

SKILL_VERSION = "1.7.0-dev"
_GENERATED_FILES = (
    "document.md", "document.json", "chunks.jsonl", "manifest.json",
    "conversion-report.json", "_pandoc_tmp.md",
)
_GENERATED_DIRS = ("assets", "tables")


def convert(input_path: str, output_dir: str, encoding_hint: str = None, source_url: str = None) -> dict:
    """Convert one file and always return a structured report.

    v1.6 makes the public entry point exception-safe and clears only known
    bundle artifacts before each run.  A failed second conversion can no
    longer leave successful JSON/chunks/tables from the previous run behind.
    """
    original_path = os.path.abspath(input_path)
    output_dir = os.path.abspath(output_dir)
    try:
        os.makedirs(output_dir, exist_ok=True)
        if not os.path.isfile(original_path):
            raise FileNotFoundError("input file does not exist or is not a regular file")
        if original_path == output_dir:
            raise ValueError("output path must be a directory, not the input file")
        _clear_previous_bundle(output_dir, protected_path=original_path)
        return _convert_unchecked(original_path, output_dir, encoding_hint, source_url)
    except Exception as exc:
        # If the output directory itself cannot be created/written there is no
        # honest bundle to return, so re-raise that I/O failure.
        if not os.path.isdir(output_dir):
            raise
        _clear_previous_bundle(output_dir, protected_path=original_path)
        file_type = resolve_format(original_path)["resolved"] if os.path.isfile(original_path) else "unknown"
        sha256 = _sha256(original_path) if os.path.isfile(original_path) else None
        return _write_bundle(output_dir, original_path, file_type, sha256, "", {
            "status": "failed",
            "reason": "conversion_error",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
        })


def _convert_unchecked(input_path: str, output_dir: str, encoding_hint: str = None, source_url: str = None) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")

    fmt_info = resolve_format(input_path)
    file_type = fmt_info["resolved"]
    sha256 = _sha256(input_path)

    # openpyxl/python-docx/python-pptx validate the FILENAME extension
    # themselves, independent of actual content - so a mismatch (detected
    # via magic bytes) needs the underlying library handed a temp path with
    # the correct extension, or it rejects a perfectly valid file just
    # because its name lies. Verified: a real .xlsx renamed to .pdf made
    # openpyxl raise InvalidFileException even though format_detector had
    # already correctly identified it as xlsx from the zip container.
    _EXT_FOR_FORMAT = {"xlsx": ".xlsx", "docx": ".docx", "pptx": ".pptx"}
    effective_path = input_path
    temp_path = None
    if fmt_info["mismatch"] and file_type in _EXT_FOR_FORMAT:
        fd, temp_path = tempfile.mkstemp(suffix=_EXT_FOR_FORMAT[file_type])
        os.close(fd)
        shutil.copyfile(input_path, temp_path)
        effective_path = temp_path

    try:
        return _convert_inner(effective_path, input_path, output_dir, assets_dir,
                               file_type, sha256, fmt_info, encoding_hint, source_url)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _convert_inner(input_path: str, original_path: str, output_dir: str, assets_dir: str,
                    file_type: str, sha256: str, fmt_info: dict,
                    encoding_hint: str = None, source_url: str = None) -> dict:

    # --- security / pre-flight gate: encryption check first, always ---
    # Tri-state (encrypted / not_encrypted / unknown) - "unknown" (parser
    # error, unsupported variant) is NOT silently treated as "safe to
    # proceed"; it's surfaced as a warning instead of being swallowed.
    encryption_status = None
    if file_type in ("xlsx", "docx", "pptx", "legacy_office"):
        encryption_status = check_office_encrypted(input_path)
    elif file_type == "pdf":
        encryption_status = check_pdf_encrypted(input_path)

    if encryption_status == "encrypted":
        return _write_bundle(output_dir, original_path, file_type, sha256,
                              "", {"status": "failed", "reason": "password_protected"}, fmt_info)
    if encryption_status == "corrupt":
        return _write_bundle(output_dir, original_path, file_type, sha256, "", {
            "status": "failed",
            "reason": "corrupt_or_invalid_office_container",
        }, fmt_info)

    elements, tables = [], []

    if file_type == "html":
        try:
            from html_structure import extract_html
            result = extract_html(input_path, source_url)
            markdown, report = result["markdown"], result["report"]
            elements, tables = result["elements"], result["tables"]
        except Exception as exc:
            return _write_bundle(output_dir, original_path, file_type, sha256, "", {"status":"failed", "reason":"HTML_NATIVE_PARSE_FAILED", "error_type":type(exc).__name__, "error_message":str(exc)}, fmt_info)

    elif file_type == "xlsx":
        from xlsx_converter import convert_xlsx
        result = convert_xlsx(input_path, assets_dir)
        markdown, report = result["markdown"], result["report"]
        elements, tables = result.get("elements", []), result.get("tables", [])

    elif file_type == "image":
        from image_converter import convert_image
        result = convert_image(input_path)
        markdown, report = result["markdown"], result["report"]
        elements, tables = result.get("elements", []), result.get("tables", [])
        report.setdefault("status", "passed")
        report.setdefault("engine", "rapidocr_onnxruntime")

    elif file_type == "docx":
        from docx_converter import convert_docx
        result = convert_docx(input_path, assets_dir)
        markdown, report = result["markdown"], result["report"]
        elements, tables = result.get("elements", []), result.get("tables", [])
        report.setdefault("status", "passed")
        report["engine"] = "python-docx_custom"

    elif file_type == "pptx":
        from pptx_converter import convert_pptx
        result = convert_pptx(input_path, assets_dir)
        markdown, report = result["markdown"], result["report"]
        elements, tables = result.get("elements", []), result.get("tables", [])
        report.setdefault("status", "passed")
        report["engine"] = "python-pptx_custom"

    elif file_type == "pdf":
        from pdf_converter import convert_pdf
        result = convert_pdf(input_path)
        markdown, report = result["markdown"], result["report"]
        elements, tables = result.get("elements", []), result.get("tables", [])

    elif file_type == "csv":
        csv_result = convert_csv_native(input_path, encoding_hint)
        markdown = csv_result["markdown"]
        report = {
            "status": "passed",
            "engine": "csv_native",
            "encoding_used": csv_result["encoding"],
            "encoding_ambiguous": csv_result["ambiguous"],
            "encoding_candidates": csv_result["candidates"],
            "encoding_user_selected": bool(encoding_hint),
        }
        if csv_result.get("rows"):
            tables = [{"id": "table-0001", "rows": csv_result["rows"], "context": "csv", "source_locator": {"format": "csv", "row_start": 1, "row_end": len(csv_result["rows"])}}]
            elements = [{
                "id": "csv-table-0001", "type": "table", "content": markdown,
                "engine": "csv_native", "confidence": None,
                "source_locator": {"format": "csv", "row_start": 1, "row_end": len(csv_result["rows"])}, "table_id": "table-0001",
            }]

    elif file_type == "json":
        json_result = convert_json_native(input_path, encoding_hint)
        markdown = json_result["markdown"]
        report = {"status": "passed", "engine": "json_native",
                  "json_valid": json_result["valid"],
                  "encoding_used": json_result["encoding"],
                  "encoding_ambiguous": json_result["ambiguous"],
                  "encoding_candidates": json_result["candidates"],
                  "encoding_user_selected": bool(encoding_hint)}
        elements = [{"id": "json-block-0001", "type": "structured_block",
                     "content": markdown, "engine": "json_native",
                     "confidence": None, "source_locator": {"format": "json", "json_path": "$"}}]

    elif file_type == "eml":
        result = convert_eml_native(input_path)
        markdown = result["markdown"]
        if result["attachments"]:
            os.makedirs(assets_dir, exist_ok=True)
            for att in result["attachments"]:
                with open(os.path.join(assets_dir, att["filename"]), "wb") as f:
                    f.write(att["content"] or b"")
        report = {"status": "passed", "engine": "email_stdlib",
                  "attachments_extracted": len(result["attachments"])}
        elements = [{"id": "email-content-0001", "type": "email",
                     "content": markdown, "engine": "email_stdlib",
                     "confidence": None, "source_locator": {"format": "eml", "mime_part": "1", "section": "body"}}]
        for index, att in enumerate(result["attachments"], start=1):
            elements.append({
                "id": f"email-attachment-{index:04d}", "type": "attachment",
                "content": f"[{att['original_filename']}](assets/{att['filename']})",
                "engine": "email_stdlib", "confidence": None,
                "source_locator": {"format": "eml", "mime_part": f"1.{index}", "section": "attachment", "filename": att["original_filename"]},
                "properties": {"original_filename": att["original_filename"]},
            })

    elif file_type == "pandoc":
        import subprocess
        out_md = os.path.join(output_dir, "_pandoc_tmp.md")
        try:
            subprocess.run(["pandoc", input_path, "-o", out_md, "-t", "gfm"],
                            check=True, capture_output=True)
            with open(out_md, "r", encoding="utf-8") as f:
                markdown = f.read()
            os.remove(out_md)
            report = {"status": "passed", "engine": "pandoc"}
            elements = [{"id": "pandoc-block-0001", "type": "structured_block",
                         "content": markdown, "engine": "pandoc",
                         "confidence": None, "source_locator": {}}]
        except FileNotFoundError:
            return _write_bundle(output_dir, original_path, file_type, sha256, "",
                                  {"status": "failed", "reason": "pandoc_not_installed"}, fmt_info)
        except subprocess.CalledProcessError as e:
            return _write_bundle(output_dir, original_path, file_type, sha256, "",
                                  {"status": "failed", "reason": f"pandoc_failed: {e}"}, fmt_info)

    elif file_type == "legacy_office":
        return _write_bundle(output_dir, original_path, file_type, sha256, "", {
            "status": "failed",
            "reason": "legacy_binary_office_format_not_supported. "
                      "Convert to .xlsx/.docx/.pptx first (e.g. LibreOffice "
                      "headless), then re-run.",
        }, fmt_info)

    else:
        try:
            from markitdown import MarkItDown
            md_engine = MarkItDown(enable_plugins=False)
            markdown = md_engine.convert(input_path).text_content
            report = {"status": "passed_with_warnings", "engine": "markitdown_fallback",
                      "note": "unrecognized extension, used generic fallback",
                      "warnings": [{"code": "GENERIC_FALLBACK_USED",
                                    "message": "The input extension is not natively supported; generic MarkItDown fallback was used.",
                                    "details": {"extension": os.path.splitext(original_path)[1].lower(), "engine": "markitdown_fallback"}}]}
            elements = [{"id": "fallback-block-0001", "type": "structured_block",
                         "content": markdown, "engine": "markitdown_fallback",
                         "confidence": None, "source_locator": {}}]
        except Exception as e:
            return _write_bundle(output_dir, original_path, file_type, sha256,
                                  "", {"status": "failed", "reason": f"unsupported_format: {e}"}, fmt_info)

    if encryption_status == "unknown":
        report["encryption_check"] = "unknown"

    return _write_bundle(output_dir, original_path, file_type, sha256, markdown, report,
                          fmt_info, elements, tables, source_url)


def _write_bundle(output_dir, original_path, file_type, sha256, markdown, converter_report,
                   fmt_info=None, elements=None, tables=None, source_url=None) -> dict:
    elements = elements or []
    tables = tables or []
    full_report = build_report(original_path, file_type, converter_report, markdown, fmt_info)
    tables = normalize_tables(tables, file_type, full_report.get("engine"))

    md_path = os.path.join(output_dir, "document.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    manifest = {
        "schema_version": "1.0",
        "skill_version": SKILL_VERSION,
        "schema_versions": {"document": "1.0", "table": "1.0", "chunk": "1.0"},
        "source_file": os.path.basename(original_path),
        "source_sha256": sha256,
        "file_type": file_type,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "status": full_report["status"],
    }
    if source_url: manifest["source_url"] = source_url
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(os.path.join(output_dir, "conversion-report.json"), "w", encoding="utf-8") as f:
        full_report["skill_version"] = SKILL_VERSION
        full_report["schema_version"] = "1.0"
        full_report["schema_versions"] = {"document": "1.0", "table": "1.0", "chunk": "1.0"}
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    if full_report["status"] != "failed":
        doc_json = build_document_json(original_path, sha256, file_type, elements,
                                        default_engine=full_report.get("engine"))
        if source_url: doc_json["metadata"] = {"source_url": source_url}
        with open(os.path.join(output_dir, "document.json"), "w", encoding="utf-8") as f:
            json.dump(doc_json, f, indent=2, ensure_ascii=False)

        chunks = build_chunks(markdown, doc_json["elements"], sha256)
        structure = full_report.get("details", {}).get("html_structure")
        if structure:
            cm = structure["canonical_metrics"]; cm["chunks_total"] = len(chunks); cm["chunks_with_heading_path"] = sum(bool(c.get("heading_path")) for c in chunks)
            sf_warnings = [w.get("code") for w in full_report.get("warnings", [])]
            from html_structure import assess_html_structural_fidelity
            full_report["structural_fidelity"] = assess_html_structural_fidelity(structure, tables, doc_json["elements"], chunks, sf_warnings)
            full_report["deterministic_conversion_status"] = "passed"
            full_report["structural_fidelity_status"] = full_report["structural_fidelity"]["status"]
            full_report["ai_review_recommended"] = bool(structure["source_metrics"]["merged_cell_anchor_count"] or sf_warnings)
            full_report["quality_risk_assessment"] = {"ai_review_recommended":full_report["ai_review_recommended"], "reasons":[{"code":"HTML_MERGED_TABLE_COMPLEX","severity":"medium","targets":[t["id"] for t in tables if t.get("merged_cells")]}]}
        with open(os.path.join(output_dir, "chunks.jsonl"), "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        if tables:
            export_tables(tables, output_dir)

        from validate_bundle import validate_bundle
        validation = validate_bundle(output_dir)
        full_report["bundle_validation"] = validation
        if structure:
            full_report["structural_fidelity"] = assess_html_structural_fidelity(
                structure, tables, doc_json["elements"], chunks,
                [w.get("code") for w in full_report.get("warnings", [])], validation)
            full_report["structural_fidelity_status"] = full_report["structural_fidelity"]["status"]
        if validation["status"] != "passed":
            full_report["status"] = "failed"
            full_report["reason"] = "bundle_validation_failed"
            manifest["status"] = "failed"
        with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        with open(os.path.join(output_dir, "conversion-report.json"), "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)

    return full_report


def _clear_previous_bundle(output_dir: str, protected_path: str = None) -> None:
    protected = os.path.realpath(protected_path) if protected_path else None
    for name in _GENERATED_FILES:
        path = os.path.join(output_dir, name)
        if protected and os.path.realpath(path) == protected:
            raise ValueError(f"output directory would overwrite input file: {name}")
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
    for name in _GENERATED_DIRS:
        path = os.path.join(output_dir, name)
        if os.path.isdir(path):
            if protected and os.path.commonpath([protected, os.path.realpath(path)]) == os.path.realpath(path):
                raise ValueError(f"output directory contains the input inside generated path: {name}")
            shutil.rmtree(path)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal file to Markdown converter")
    parser.add_argument("input", help="Path to the input file")
    parser.add_argument("--output", required=True, help="Output directory for the bundle")
    parser.add_argument("--encoding", help="Explicit text encoding for CSV/TSV/JSON (e.g. big5, gb18030, shift_jis)")
    parser.add_argument("--source-url", help="Original HTTP(S) URL used to resolve HTML relative links")
    args = parser.parse_args()

    report = convert(args.input, args.output, args.encoding, args.source_url)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] != "failed" else 1)
