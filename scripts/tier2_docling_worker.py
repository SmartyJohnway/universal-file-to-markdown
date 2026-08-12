#!/usr/bin/env python3
"""Isolated offline Docling worker for the Tier-2 adapter protocol."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

from tier2_model_manifest import sha256_file, verify_manifest


OFFLINE_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "DO_NOT_TRACK": "1",
}


def _artifact(root: Path, path: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size}


def run(request_path: Path) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    input_path = Path(request["input_path"]).resolve()
    output_dir = Path(request["output_dir"]).resolve()
    manifest_path = Path(request["model_manifest_path"]).resolve()
    manifest, errors = verify_manifest(manifest_path)
    if errors:
        raise RuntimeError("; ".join(errors))
    if sha256_file(input_path) != request["source_sha256"]:
        raise RuntimeError("TIER2_SOURCE_HASH_MISMATCH")
    for key, value in OFFLINE_ENVIRONMENT.items():
        os.environ[key] = value

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.object_detection_engine_options import (
        OnnxRuntimeObjectDetectionEngineOptions,
    )
    from docling.datamodel.pipeline_options import (
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
    )
    from docling.document_converter import (
        DocumentConverter, ImageFormatOption, PdfFormatOption,
    )

    # The official Heron preset defaults to the Transformers engine. Its
    # torch.compile path can require a platform C++ toolchain at runtime.
    # Select the preset's official ONNX override for a portable, local CPU
    # worker; the exact ONNX artifact is still covered by the model manifest.
    layout_options = LayoutObjectDetectionOptions.from_preset(
        "layout_heron_default",
        engine_options=OnnxRuntimeObjectDetectionEngineOptions(),
    )
    options = PdfPipelineOptions(
        artifacts_path=manifest_path.parent,
        do_ocr=True,
        do_table_structure=True,
        layout_options=layout_options,
        document_timeout=float(request["document_timeout_seconds"]),
        enable_remote_services=False,
        allow_external_plugins=False,
    )
    format_option = (PdfFormatOption(pipeline_options=options)
                     if request["input_format"] == "pdf"
                     else ImageFormatOption(pipeline_options=options))
    input_format = InputFormat.PDF if request["input_format"] == "pdf" else InputFormat.IMAGE
    converter = DocumentConverter(
        allowed_formats=[input_format],
        format_options={input_format: format_option},
    )
    result = converter.convert(
        input_path,
        max_num_pages=int(request["max_num_pages"]),
        max_file_size=int(request["max_file_size_bytes"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    document_path = output_dir / "docling-document.json"
    markdown_path = output_dir / "document.md"
    exported = result.document.export_to_dict()
    document_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    markdown_path.write_text(result.document.export_to_markdown(), encoding="utf-8")
    worker_result = {
        "protocol_version": "1.0",
        "status": "succeeded",
        "adapter": {"name": "docling", "version": importlib.metadata.version("docling")},
        "source_sha256": request["source_sha256"],
        "conversion_status": str(getattr(result, "status", "unknown")),
        "model": {
            "model_id": manifest["model_id"],
            "model_version": manifest["model_version"],
            "manifest_sha256": sha256_file(manifest_path),
        },
        "security": {
            "remote_services_enabled": False,
            "external_plugins_enabled": False,
            "offline_environment_enforced": True,
        },
        "artifacts": {
            "docling_document": _artifact(output_dir, document_path),
            "markdown": _artifact(output_dir, markdown_path),
        },
    }
    (output_dir / "worker-result.json").write_text(
        json.dumps(worker_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return worker_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.request)
    except Exception as exc:
        print(json.dumps({"protocol_version": "1.0", "status": "failed",
                          "error_type": type(exc).__name__,
                          "error_message": str(exc)[:2000]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
