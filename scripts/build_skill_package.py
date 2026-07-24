#!/usr/bin/env python3
"""Build an allowlisted, byte-reproducible skill ZIP from ``VERSION``."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, tempfile, zipfile
from pathlib import Path
from skill_package_common import ROOT, allowed_files, load_allowlist, read_version

TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MODE = 0o100644 << 16

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_git_sha(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

def artifact_paths(output: Path, version: str) -> tuple[Path, Path, Path]:
    stem = f"universal-file-to-markdown-{version}"
    return output / f"{stem}.zip", output / f"{stem}.sha256", output / f"{stem}.manifest.json"

def build(output: Path, root: Path = ROOT, verify: bool = False) -> dict:
    version, allowlist = read_version(root), load_allowlist(root)
    archive, sidecar, evidence = artifact_paths(output, version)
    files = allowed_files(root, allowlist)
    prefix = f"universal-file-to-markdown-{version}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        temp_archive = Path(temporary) / archive.name
        with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as zipped:
            zipped.comment = b""
            for source in files:
                relative = source.relative_to(root).as_posix()
                info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=TIMESTAMP)
                info.create_system = 3
                info.external_attr = MODE
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        archive_sha = digest(temp_archive)
        with zipfile.ZipFile(temp_archive) as zipped:
            entries = [{"path": info.filename, "sha256": hashlib.sha256(zipped.read(info)).hexdigest(), "size_bytes": info.file_size} for info in zipped.infolist()]
            compressed_size = sum(info.compress_size for info in zipped.infolist())
        evidence_data = {"schema_version":"1.0", "skill_name":allowlist["skill_name"], "skill_version":version, "source_git_sha":source_git_sha(root), "archive_name":archive.name, "archive_sha256":archive_sha, "file_count":len(entries), "uncompressed_size_bytes":sum(item["size_bytes"] for item in entries), "compressed_size_bytes":compressed_size, "entries":entries}
        temp_sidecar, temp_evidence = Path(temporary) / sidecar.name, Path(temporary) / evidence.name
        temp_sidecar.write_text(f"{archive_sha}  {archive.name}\n", encoding="utf-8")
        temp_evidence.write_text(json.dumps(evidence_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_archive, archive); os.replace(temp_sidecar, sidecar); os.replace(temp_evidence, evidence)
    if verify:
        from validate_skill_package import validate
        validate(archive, root / "package-manifest.json")
    return evidence_data

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        result = build(args.output, verify=args.verify)
    except Exception as exc:
        print(f"package build failed: {exc}", file=sys.stderr); return 1
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
