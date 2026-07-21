#!/usr/bin/env python3
"""Report whether required Python modules and optional system tools exist."""

import argparse
import importlib.util
import json
import shutil
import sys


PYTHON_CAPABILITIES = {
    "openpyxl": True,
    "docx": True,
    "pptx": True,
    "pdfplumber": True,
    "fitz": True,
    "rapidocr_onnxruntime": True,
    "pytesseract": True,
    "charset_normalizer": True,
    "msoffcrypto": True,
    "jsonschema": True,
    "markitdown": False,
}
SYSTEM_CAPABILITIES = {
    "tesseract": False,
    "pandoc": False,
}


def probe() -> dict:
    python_modules = {
        name: {"available": importlib.util.find_spec(name) is not None, "required": required}
        for name, required in PYTHON_CAPABILITIES.items()
    }
    system_binaries = {
        name: {"available": shutil.which(name) is not None, "required": required}
        for name, required in SYSTEM_CAPABILITIES.items()
    }
    missing_required = [
        name for name, item in python_modules.items()
        if item["required"] and not item["available"]
    ] + [
        name for name, item in system_binaries.items()
        if item["required"] and not item["available"]
    ]
    return {
        "status": "passed" if not missing_required else "failed",
        "missing_required": missing_required,
        "python_modules": python_modules,
        "system_binaries": system_binaries,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe file-conversion capabilities")
    parser.add_argument("--json", action="store_true", help="emit JSON (default output is concise text)")
    args = parser.parse_args()
    result = probe()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"capability preflight: {result['status']}")
        if result["missing_required"]:
            print("required dependency missing: " + ", ".join(result["missing_required"]))
    sys.exit(0 if result["status"] == "passed" else 1)
