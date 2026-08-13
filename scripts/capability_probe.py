#!/usr/bin/env python3
"""Report whether required Python modules and optional system tools exist."""

import argparse
import importlib.util
import json
import platform
import shutil
import sys

from native_probe import (
    DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS,
    probe_pymupdf,
    probe_rapidocr,
)


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

OPTIONAL_DEPENDENCY_METADATA = {
    "markitdown": {
        "severity": "optional_route_unavailable",
        "required_for": ["generic fallback routes"],
        "affected_formats": ["unknown or fallback-supported formats"],
    },
    "pandoc": {
        "severity": "optional_route_unavailable",
        "required_for": ["Pandoc markup routes"],
        "affected_formats": ["epub", "rst", "org", "tex", "latex"],
    },
    "tesseract": {
        "severity": "optional_fallback_unavailable",
        "required_for": ["Tesseract OCR fallback"],
        "affected_formats": ["scanned PDF fallback", "image OCR fallback"],
    },
}


def probe(timeout_seconds: float = DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS) -> dict:
    python_modules = {
        name: {"available": importlib.util.find_spec(name) is not None, "required": required}
        for name, required in PYTHON_CAPABILITIES.items()
    }
    system_binaries = {
        name: {"available": shutil.which(name) is not None, "required": required}
        for name, required in SYSTEM_CAPABILITIES.items()
    }
    pymupdf = probe_pymupdf(timeout_seconds=timeout_seconds)
    rapidocr = probe_rapidocr(timeout_seconds=timeout_seconds)
    python_modules["fitz"].update(pymupdf)
    python_modules["rapidocr_onnxruntime"].update(rapidocr)

    python_modules["fitz"]["available"] = pymupdf.get("module_discovered", python_modules["fitz"]["available"])
    python_modules["rapidocr_onnxruntime"]["available"] = rapidocr.get("module_discovered", python_modules["rapidocr_onnxruntime"]["available"])

    for dep, meta in OPTIONAL_DEPENDENCY_METADATA.items():
        if dep in python_modules:
            python_modules[dep].update(meta)
        elif dep in system_binaries:
            system_binaries[dep].update(meta)

    missing_core = [
        name for name, item in python_modules.items()
        if item["required"] and not item["available"]
    ] + ([] if pymupdf["status"] == "passed" else ["pymupdf"]) + ([] if rapidocr["status"] == "passed" else ["rapidocr-onnxruntime"]) + [
        name for name, item in system_binaries.items()
        if item["required"] and not item["available"]
    ]

    missing_optional = [
        name for name, item in python_modules.items()
        if not item["required"] and not item["available"]
    ] + [
        name for name, item in system_binaries.items()
        if not item["required"] and not item["available"]
    ]

    core_required = [
        name for name, item in python_modules.items() if item["required"] and item["available"]
    ] + [
        name for name, item in system_binaries.items() if item["required"] and item["available"]
    ]

    optional_route_deps = {
        name: item for name, item in {**python_modules, **system_binaries}.items() if not item["required"]
    }

    affected_routes = {}
    for dep in missing_optional:
        if dep in OPTIONAL_DEPENDENCY_METADATA:
            affected_routes[dep] = OPTIONAL_DEPENDENCY_METADATA[dep]["affected_formats"]

    if missing_core:
        status = "failed"
    elif missing_optional:
        status = "passed_with_caveats"
    else:
        status = "passed"

    return {
        "status": status,
        "missing_required": missing_core,
        "missing_core_dependencies": missing_core,
        "missing_optional_dependencies": missing_optional,
        "core_required_dependencies": core_required,
        "optional_route_dependencies": optional_route_deps,
        "affected_routes": affected_routes,
        "native_probe_timeout_seconds": timeout_seconds,
        "python_modules": python_modules,
        "system_binaries": system_binaries,
        "environment": {
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "platform_machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe file-conversion capabilities")
    parser.add_argument("--json", action="store_true", help="emit JSON (default output is concise text)")
    parser.add_argument(
        "--native-timeout-seconds",
        type=float,
        default=DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS,
        help="per-child native import/smoke timeout (default: 30 seconds)",
    )
    args = parser.parse_args()
    if args.native_timeout_seconds <= 0:
        parser.error("--native-timeout-seconds must be greater than zero")
    result = probe(timeout_seconds=args.native_timeout_seconds)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"capability preflight: {result['status']}")
        if result["missing_core_dependencies"]:
            print("required dependency missing: " + ", ".join(result["missing_core_dependencies"]))
        if result["missing_optional_dependencies"]:
            print("optional dependency missing: " + ", ".join(result["missing_optional_dependencies"]))
    sys.exit(0 if result["status"] in ("passed", "passed_with_caveats") else 1)
