#!/usr/bin/env python3
"""Create and verify deterministic manifests for offline Tier-2 model files."""

import argparse
import hashlib
import json
from pathlib import Path


MANIFEST_NAME = "tier2-model-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError(f"unsafe model artifact path: {relative}")
    return relative


def create_manifest(root: Path, model_id: str, model_version: str,
                    output: Path | None = None) -> dict:
    root = root.resolve()
    output = (output or root / MANIFEST_NAME).resolve()
    if not root.is_dir():
        raise ValueError("model artifact root is not a directory")
    files = []
    for path in sorted(root.rglob("*")):
        if path == output:
            continue
        if path.is_symlink():
            raise ValueError(f"model artifact symlink is not allowed: {path}")
        if path.is_file():
            files.append({
                "path": _safe_relative(root, path),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            })
    if not files:
        raise ValueError("model artifact root contains no files")
    manifest = {"schema_version": "1.0", "model_id": model_id,
                "model_version": model_version, "files": files}
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return manifest


def verify_manifest(manifest_path: Path) -> tuple[dict | None, list[str]]:
    manifest_candidate = Path(manifest_path)
    if manifest_candidate.is_symlink():
        return None, ["TIER2_MODEL_MANIFEST_SYMLINK_NOT_ALLOWED"]
    manifest_path = manifest_candidate.resolve()
    errors = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"TIER2_MODEL_MANIFEST_UNREADABLE: {exc}"]
    try:
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).parents[1] / "schemas" /
                             "tier2-model-manifest.schema.json").read_text(encoding="utf-8"))
        errors.extend(
            f"TIER2_MODEL_MANIFEST_SCHEMA_INVALID: {error.json_path}: {error.message}"
            for error in Draft202012Validator(schema).iter_errors(manifest)
        )
    except Exception as exc:
        errors.append(f"TIER2_MODEL_MANIFEST_SCHEMA_INVALID: {exc}")
    root = manifest_path.parent
    seen = set()
    for item in manifest.get("files", []):
        relative = item.get("path")
        if not isinstance(relative, str):
            continue
        if relative in seen:
            errors.append(f"TIER2_MODEL_MANIFEST_DUPLICATE_PATH: {relative}")
            continue
        seen.add(relative)
        candidate = root / relative
        if candidate.is_symlink():
            errors.append(f"TIER2_MODEL_ARTIFACT_SYMLINK_NOT_ALLOWED: {relative}")
            continue
        target = candidate.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"TIER2_MODEL_MANIFEST_PATH_ESCAPE: {relative}")
            continue
        if not target.is_file():
            errors.append(f"TIER2_MODEL_ARTIFACT_MISSING: {relative}")
            continue
        if target.stat().st_size != item.get("size_bytes"):
            errors.append(f"TIER2_MODEL_ARTIFACT_SIZE_MISMATCH: {relative}")
        if sha256_file(target) != item.get("sha256"):
            errors.append(f"TIER2_MODEL_ARTIFACT_HASH_MISMATCH: {relative}")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            errors.append(f"TIER2_MODEL_ARTIFACT_SYMLINK_NOT_ALLOWED: {_safe_relative(root, path)}")
            continue
        if path.is_file() and path.resolve() != manifest_path:
            actual.add(_safe_relative(root, path))
    if actual != seen:
        errors.append("TIER2_MODEL_MANIFEST_FILE_SET_MISMATCH")
    return manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("root", type=Path)
    create.add_argument("--model-id", required=True)
    create.add_argument("--model-version", required=True)
    create.add_argument("--output", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        manifest = create_manifest(args.root, args.model_id, args.model_version,
                                   args.output)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    manifest, errors = verify_manifest(args.manifest)
    print(json.dumps({"status": "passed" if not errors else "failed",
                      "errors": errors, "manifest": manifest}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
