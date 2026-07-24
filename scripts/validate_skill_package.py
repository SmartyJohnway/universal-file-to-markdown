#!/usr/bin/env python3
"""Validate a skill archive's content boundary, integrity, and path safety."""
from __future__ import annotations
import argparse, hashlib, json, re, stat, sys, zipfile
from pathlib import PurePosixPath, Path
from skill_package_common import ROOT, allowed_files, load_profile_manifest, read_version

DRIVE = re.compile(r"^[A-Za-z]:")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def fail(message: str) -> None:
    raise ValueError(message)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or DRIVE.match(name):
        fail(f"unsafe archive path: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in ("", ".", "..") for part in parts):
        fail(f"unsafe archive path: {name!r}")
    return name

def check_yaml_frontmatter(skill_content: str) -> None:
    if not skill_content.startswith("---"):
        fail("SKILL.md missing YAML frontmatter opening '---'")
    parts = skill_content.split("---", 2)
    if len(parts) < 3:
        fail("SKILL.md YAML frontmatter missing closing '---'")
    frontmatter = parts[1]
    has_name = any(re.match(r"^name:\s*[a-z0-9-]+$", line.strip()) for line in frontmatter.splitlines())
    if not has_name:
        fail("SKILL.md YAML frontmatter missing or invalid 'name' field")
    has_desc = any(line.strip().startswith("description:") for line in frontmatter.splitlines())
    if not has_desc:
        fail("SKILL.md YAML frontmatter missing 'description' field")

def check_package_markdown_links(values: dict[str, bytes], prefix: str) -> None:
    for path, content in values.items():
        if not path.endswith(".md"):
            continue
        text = content.decode("utf-8", errors="replace")
        rel_dir = PurePosixPath(path[len(prefix):]).parent
        for match in LINK_PATTERN.finditer(text):
            target = match.group(2).strip()
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if target.startswith("file://") or target.startswith("/") or DRIVE.match(target):
                fail(f"forbidden link format in {path}: {target}")
            target_path_str = target.split("#")[0]
            if not target_path_str:
                continue
            resolved = (rel_dir / target_path_str).as_posix()
            # Clean dot navigation if any
            parts = []
            for part in resolved.split("/"):
                if part == "." or not part:
                    continue
                if part == "..":
                    if parts:
                        parts.pop()
                else:
                    parts.append(part)
            resolved_clean = "/".join(parts)
            expected_full = prefix + resolved_clean
            if expected_full not in values:
                fail(f"unresolved link in {path}: {target} -> {expected_full} not found in archive")

def validate(archive: Path, profile: str = "release", source_manifest: Path | None = None) -> dict:
    archive = Path(archive)
    root = ROOT
    if source_manifest is None:
        source_manifest = root / "package-manifests" / f"{profile}.json"
        if not source_manifest.is_file():
            source_manifest = root / "package-manifest.json"
    allowlist = json.loads(source_manifest.read_text(encoding="utf-8"))
    version = read_version(root)
    top_level_format = allowlist.get("top_level_dir_format", f"universal-file-to-markdown-{{version}}")
    prefix = top_level_format.format(version=version) + "/"
    expected_relatives = [p.relative_to(root).as_posix() for p in allowed_files(root, allowlist)]
    expected = [prefix + p for p in expected_relatives]

    if not archive.is_file():
        fail(f"archive not found: {archive}")

    sidecar = archive.with_suffix(".sha256")
    evidence = archive.with_suffix(".manifest.json")

    if profile == "release":
        if not sidecar.is_file() or not evidence.is_file():
            fail("SHA-256 sidecar or package manifest is missing")
        sidecar_digest = sidecar.read_text(encoding="utf-8").strip().split()[0] if sidecar.read_text(encoding="utf-8").strip() else ""
        if sidecar_digest != sha256(archive):
            fail("SHA-256 sidecar does not match archive")
        package_evidence = json.loads(evidence.read_text(encoding="utf-8"))
        if package_evidence.get("skill_version") != version or package_evidence.get("archive_name") != archive.name:
            fail("package manifest version or archive name mismatch")
        if package_evidence.get("archive_sha256") != sidecar_digest:
            fail("package manifest digest mismatch")
    else:  # agent-skill profile
        if sidecar.is_file():
            sidecar_digest = sidecar.read_text(encoding="utf-8").strip().split()[0] if sidecar.read_text(encoding="utf-8").strip() else ""
            if sidecar_digest != sha256(archive):
                fail("SHA-256 sidecar does not match archive")

    try:
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip() is not None:
                fail("archive integrity check failed")
            infos = zipped.infolist()
            names = [safe_name(info.filename) for info in infos]
            if len(names) != len(set(names)):
                fail("duplicate archive entry")
            normalized = [name.casefold() for name in names]
            if len(normalized) != len(set(normalized)):
                fail("case-collision archive entry")
            if not names or any(not name.startswith(prefix) for name in names):
                fail("archive must have exactly one expected root directory")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                fail("symlink archive entries are not allowed")
            if names != sorted(names):
                fail("archive entries are not lexicographically ordered")
            if any(info.date_time != (1980, 1, 1, 0, 0, 0) for info in infos):
                fail("archive timestamps are not deterministic")
            if names != expected:
                fail("archive has unexpected, missing, or non-allowlisted files")
            values = {name: zipped.read(name) for name in names}
    except zipfile.BadZipFile as exc:
        fail(f"archive cannot be opened: {exc}")

    for required in ("VERSION", "SKILL.md", "requirements.txt"):
        if prefix + required not in values:
            fail(f"required archive path missing: {required}")

    if not any(name.startswith(prefix + "schemas/") for name in names):
        fail("schemas are missing")
    if not any(name.startswith(prefix + "scripts/") for name in names):
        fail("scripts are missing")

    archived_version = values[prefix + "VERSION"].decode("utf-8").strip()
    if archived_version != version:
        fail("archive VERSION does not match source VERSION")

    # Validate SKILL.md frontmatter
    skill_text = values[prefix + "SKILL.md"].decode("utf-8", errors="replace")
    check_yaml_frontmatter(skill_text)

    # Validate Markdown links inside package
    check_package_markdown_links(values, prefix)

    if profile == "release":
        evidence_entries = package_evidence.get("entries")
        expected_entries = [{"path": name, "sha256": hashlib.sha256(values[name]).hexdigest(), "size_bytes": len(values[name])} for name in names]
        if evidence_entries != expected_entries:
            fail("package manifest entries do not match archive")

    return {"status": "passed", "archive": archive.name, "profile": profile, "file_count": len(names), "version": version}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--profile", choices=["release", "agent-skill"], default="release", help="package profile to validate")
    parser.add_argument("--source-manifest", type=Path, default=None)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.archive, profile=args.profile, source_manifest=args.source_manifest), indent=2))
    except Exception as exc:
        print(f"package validation failed: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
