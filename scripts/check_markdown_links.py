#!/usr/bin/env python3
"""Validate repository-local links in Markdown files.

External HTTP(S), mailto, and fragment-only links are intentionally ignored.
The release gate should not fail because a third-party site is unavailable,
rate-limited, or requires authentication.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
IGNORED_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:")
IGNORED_DIRS = {
    ".git", ".hermes", ".qualification", ".venv", "venv", "env",
    ".cache", ".deps", ".mypy_cache", ".nox", ".pytest_cache",
    ".ruff_cache", ".tox", ".uv", "build", "dist", "htmlcov",
    "local-fixtures", "models", "node_modules", "private-fixtures", "scratch",
}


def iter_markdown_files(root: Path):
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        yield path


def normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    # Markdown links may optionally contain a quoted title after whitespace.
    if " \"" in target:
        target = target.split(" \"", 1)[0]
    if " '" in target:
        target = target.split(" '", 1)[0]
    return unquote(target)


def validate(root: Path) -> list[str]:
    failures: list[str] = []
    for md_path in iter_markdown_files(root):
        text = md_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                target = normalize_target(match.group(1))
                if not target or target.startswith("#") or target.startswith(IGNORED_PREFIXES):
                    continue
                path_part = target.split("#", 1)[0].split("?", 1)[0]
                if not path_part:
                    continue
                resolved = (md_path.parent / path_part).resolve()
                try:
                    resolved.relative_to(root.resolve())
                except ValueError:
                    failures.append(
                        f"{md_path.relative_to(root)}:{line_no}: link escapes repository: {target}"
                    )
                    continue
                if not resolved.exists():
                    failures.append(
                        f"{md_path.relative_to(root)}:{line_no}: missing local target: {target}"
                    )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local links in Markdown files")
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    failures = validate(root)
    if failures:
        print("Local Markdown link validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Local Markdown link validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
