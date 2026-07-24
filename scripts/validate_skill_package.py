#!/usr/bin/env python3
"""Validate a skill archive's content boundary, integrity, and path safety."""
from __future__ import annotations
import argparse, hashlib, json, re, stat, sys, zipfile
from pathlib import PurePosixPath, Path
from skill_package_common import ROOT, allowed_files, load_allowlist, read_version

DRIVE = re.compile(r"^[A-Za-z]:")
def fail(message: str) -> None: raise ValueError(message)
def sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def safe_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or DRIVE.match(name): fail(f"unsafe archive path: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in ("", ".", "..") for part in parts): fail(f"unsafe archive path: {name!r}")
    return name

def validate(archive: Path, source_manifest: Path = ROOT / "package-manifest.json") -> dict:
    archive = Path(archive)
    allowlist = json.loads(source_manifest.read_text(encoding="utf-8"))
    version = read_version(source_manifest.parent)
    prefix = f"universal-file-to-markdown-{version}/"
    expected_relatives = [p.relative_to(source_manifest.parent).as_posix() for p in allowed_files(source_manifest.parent, allowlist)]
    expected = [prefix + p for p in expected_relatives]
    if not archive.is_file(): fail(f"archive not found: {archive}")
    sidecar = archive.with_suffix(".sha256")
    evidence = archive.with_suffix(".manifest.json")
    if not sidecar.is_file() or not evidence.is_file(): fail("SHA-256 sidecar or package manifest is missing")
    sidecar_digest = sidecar.read_text(encoding="utf-8").strip().split()[0] if sidecar.read_text(encoding="utf-8").strip() else ""
    if sidecar_digest != sha256(archive): fail("SHA-256 sidecar does not match archive")
    package_evidence = json.loads(evidence.read_text(encoding="utf-8"))
    if package_evidence.get("skill_version") != version or package_evidence.get("archive_name") != archive.name: fail("package manifest version or archive name mismatch")
    if package_evidence.get("archive_sha256") != sidecar_digest: fail("package manifest digest mismatch")
    try:
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip() is not None: fail("archive integrity check failed")
            infos = zipped.infolist(); names = [safe_name(info.filename) for info in infos]
            if len(names) != len(set(names)): fail("duplicate archive entry")
            normalized = [name.casefold() for name in names]
            if len(normalized) != len(set(normalized)): fail("case-collision archive entry")
            if not names or any(not name.startswith(prefix) for name in names): fail("archive must have exactly one expected versioned root directory")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos): fail("symlink archive entries are not allowed")
            if names != sorted(names): fail("archive entries are not lexicographically ordered")
            if any(info.date_time != (1980, 1, 1, 0, 0, 0) for info in infos): fail("archive timestamps are not deterministic")
            if names != expected: fail("archive has unexpected, missing, or non-allowlisted files")
            values = {name: zipped.read(name) for name in names}
    except zipfile.BadZipFile as exc: fail(f"archive cannot be opened: {exc}")
    for required in ("VERSION", "SKILL.md", "requirements.txt"):
        if prefix + required not in values: fail(f"required archive path missing: {required}")
    if not any(name.startswith(prefix + "schemas/") for name in names): fail("schemas are missing")
    if not any(name.startswith(prefix + "scripts/") for name in names): fail("scripts are missing")
    archived_version = values[prefix + "VERSION"].decode("utf-8").strip()
    if archived_version != version: fail("archive VERSION does not match source VERSION")
    evidence_entries = package_evidence.get("entries")
    expected_entries = [{"path":name, "sha256":hashlib.sha256(values[name]).hexdigest(), "size_bytes":len(values[name])} for name in names]
    if evidence_entries != expected_entries: fail("package manifest entries do not match archive")
    return {"status":"passed", "archive":archive.name, "file_count":len(names), "version":version}

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("archive", type=Path); parser.add_argument("--source-manifest", type=Path, default=ROOT / "package-manifest.json"); args=parser.parse_args()
    try: print(json.dumps(validate(args.archive, args.source_manifest), indent=2))
    except Exception as exc: print(f"package validation failed: {exc}", file=sys.stderr); return 1
    return 0
if __name__ == "__main__": raise SystemExit(main())
