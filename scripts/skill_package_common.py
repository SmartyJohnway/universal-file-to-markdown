"""Shared, dependency-free helpers for the release-candidate skill package."""
from __future__ import annotations
import fnmatch, json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_allowlist(root: Path = ROOT) -> dict:
    return json.loads((root / "package-manifest.json").read_text(encoding="utf-8"))

def read_version(root: Path = ROOT) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION must not be empty")
    return version

def is_excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)

def allowed_files(root: Path = ROOT, allowlist: dict | None = None) -> list[Path]:
    allowlist = allowlist or load_allowlist(root)
    required = allowlist["required_paths"]
    optional = allowlist.get("optional_paths", [])
    selected: set[str] = set()
    for item in required + optional:
        candidate = root / item.rstrip("/")
        if item.endswith("/"):
            if not candidate.is_dir() and item in required:
                raise ValueError(f"required directory missing: {item}")
            if candidate.is_dir():
                selected.update(p.relative_to(root).as_posix() for p in candidate.rglob("*") if p.is_file())
        elif candidate.is_file():
            selected.add(item)
        elif item in required:
            raise ValueError(f"required path missing: {item}")
    patterns = allowlist.get("excluded_patterns", [])
    try:
        tracked = set(subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"], stderr=subprocess.DEVNULL).decode().split("\0"))
    except (OSError, subprocess.CalledProcessError):
        tracked = None
    files = []
    for relative in sorted(selected):
        if is_excluded(relative, patterns):
            continue
        if tracked is not None and relative not in tracked:
            raise ValueError(f"allowlisted path is not git-tracked: {relative}")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"allowlisted path is not a regular file: {relative}")
        files.append(path)
    return files
