#!/usr/bin/env python3
"""
router.py
Entry point for the universal-file-to-markdown skill.

    python3 router.py INPUT_FILE --output OUTPUT_DIR

Produces an output bundle:
    OUTPUT_DIR/
      document.md
      conversion-report.json
      manifest.json
      assets/            (only if images/media were embedded)

Design note: this router deliberately does NOT reach for Docling / MinerU /
any torch-based engine. See references/engine_notes.md for why - in short,
those engines need multi-GB installs and a Hugging Face model download that
is blocked in network-restricted sandboxes (verified empirically for this
skill). Every engine used here is either pure-stdlib, a small structural
parser (openpyxl/python-docx/pdfplumber), or a fully self-contained
offline model (RapidOCR, ~15MB, bundled in the pip wheel).
"""

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common_utils import (
    check_office_encrypted,
    check_pdf_encrypted,
    convert_csv_native,
    convert_json_native,
    convert_eml_native,
    read_text_smart,
)
from quality_check import build_report


def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("xlsx", "xlsm"):
        return "xlsx"
    if ext == "docx":
        return "docx"
    if ext == "pptx":
        return "pptx"
    if ext == "pdf":
        return "pdf"
    if ext in ("csv", "tsv"):
        return "csv"
    if ext == "json":
        return "json"
    if ext == "eml":
        return "eml"
    if ext in ("html", "htm", "epub", "rst", "org", "tex", "latex"):
        return "pandoc"
    if ext in ("xls", "doc", "ppt"):
        return "legacy_office"
    return "unknown"


def convert(input_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")

    file_type = detect_format(input_path)
    sha256 = _sha256(input_path)

    # --- security / pre-flight gate: encryption check first, always ---
    if file_type in ("xlsx", "docx", "pptx", "legacy_office"):
        if check_office_encrypted(input_path):
            return _write_bundle(output_dir, input_path, file_type, sha256,
                                  "", {"status": "failed", "reason": "password_protected"})
    if file_type == "pdf" and check_pdf_encrypted(input_path):
        return _write_bundle(output_dir, input_path, file_type, sha256,
                              "", {"status": "failed", "reason": "password_protected"})

    if file_type == "xlsx":
        from xlsx_converter import convert_xlsx
        result = convert_xlsx(input_path, assets_dir)
        markdown, report = result["markdown"], result["report"]
        report.setdefault("status", "passed")
        report["engine"] = "openpyxl_custom"

    elif file_type == "docx":
        from docx_converter import convert_docx
        result = convert_docx(input_path, assets_dir)
        markdown, report = result["markdown"], result["report"]
        report.setdefault("status", "passed")
        report["engine"] = "python-docx_custom"

    elif file_type == "pdf":
        from pdf_converter import convert_pdf
        result = convert_pdf(input_path)
        markdown, report = result["markdown"], result["report"]

    elif file_type == "csv":
        markdown = convert_csv_native(input_path)
        report = {"status": "passed", "engine": "csv_native"}

    elif file_type == "json":
        markdown = convert_json_native(input_path)
        report = {"status": "passed", "engine": "json_native"}

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

    elif file_type == "pptx":
        # PPTX slide/table structure is out of scope for the first cut of
        # this skill; MarkItDown gives a reasonable text-level conversion.
        # See references/engine_notes.md for why this isn't a custom
        # renderer yet (pptx merged/complex tables are far less common
        # than in xlsx/docx).
        try:
            from markitdown import MarkItDown
            md_engine = MarkItDown(enable_plugins=False)
            markdown = md_engine.convert(input_path).text_content
            report = {"status": "passed", "engine": "markitdown"}
        except ImportError:
            return _write_bundle(output_dir, input_path, file_type, sha256,
                                  "", {"status": "failed", "reason": "markitdown_not_installed"})

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
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            return _write_bundle(output_dir, input_path, file_type, sha256,
                                  "", {"status": "failed", "reason": f"pandoc_failed: {e}"})

    elif file_type == "legacy_office":
        return _write_bundle(output_dir, input_path, file_type, sha256, "", {
            "status": "failed",
            "reason": "legacy_binary_office_format_not_supported. "
                      "Convert to .xlsx/.docx/.pptx first (e.g. LibreOffice "
                      "headless), then re-run.",
        })

    else:
        # last-resort fallback: try MarkItDown for anything unrecognized
        try:
            from markitdown import MarkItDown
            md_engine = MarkItDown(enable_plugins=False)
            markdown = md_engine.convert(input_path).text_content
            report = {"status": "passed_with_warnings", "engine": "markitdown_fallback",
                      "note": "unrecognized extension, used generic fallback"}
        except Exception as e:
            return _write_bundle(output_dir, input_path, file_type, sha256,
                                  "", {"status": "failed", "reason": f"unsupported_format: {e}"})

    return _write_bundle(output_dir, input_path, file_type, sha256, markdown, report)


def _write_bundle(output_dir, input_path, file_type, sha256, markdown, converter_report) -> dict:
    full_report = build_report(input_path, file_type, converter_report, markdown)

    md_path = os.path.join(output_dir, "document.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    manifest = {
        "source_file": os.path.basename(input_path),
        "source_sha256": sha256,
        "file_type": file_type,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "status": full_report["status"],
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(os.path.join(output_dir, "conversion-report.json"), "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    return full_report


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
    args = parser.parse_args()

    report = convert(args.input, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] != "failed" else 1)
