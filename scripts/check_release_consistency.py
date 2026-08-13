#!/usr/bin/env python3
"""Validate repository release truth across human and machine contracts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _text(root: Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8")


def _match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def adjacent_duplicate_headings(text: str) -> list[str]:
    duplicates = []
    previous_nonempty = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and stripped == previous_nonempty:
            duplicates.append(stripped)
        previous_nonempty = stripped
    return duplicates


def validate_release_consistency(root: Path) -> list[str]:
    failures = []
    version = _text(root, "VERSION").strip()
    if not SEMVER_RE.match(version):
        failures.append(f"VERSION_INVALID:{version}")

    skill = _text(root, "SKILL.md")
    skill_version = _match(r"^version:\s*(\S+)\s*$", skill)
    release_status = _match(r"^release_status:\s*(\S+)\s*$", skill)
    published = _match(r"^published_stable_version:\s*(\S+)\s*$", skill)
    if skill_version != version:
        failures.append(f"SKILL_VERSION_MISMATCH:{skill_version}")
    if release_status not in {"development", "candidate", "stable"}:
        failures.append(f"SKILL_RELEASE_STATUS_INVALID:{release_status}")
    if not published or not SEMVER_RE.match(published):
        failures.append(f"PUBLISHED_STABLE_VERSION_INVALID:{published}")
    if release_status == "stable" and published != version:
        failures.append("STABLE_VERSION_NOT_PUBLISHED_VERSION")
    if f"# Universal File to Markdown v{version}" not in skill:
        failures.append("SKILL_TITLE_VERSION_MISMATCH")
    if f"skill_version: {version} ({release_status})" not in skill:
        failures.append("SKILL_BODY_RELEASE_STATE_MISMATCH")

    readme = _text(root, "README.md")
    readme_zh = _text(root, "README.zh-TW.md")
    expected = (
        {"README_CURRENT_VERSION_MISMATCH": f"Current stable release: `{version}`"}
        if release_status == "stable" else {
            "README_CURRENT_VERSION_MISMATCH": f"Current development target: `{version}`",
            "README_STABLE_VERSION_MISMATCH": f"Latest published stable release: `{published}`",
        }
    )
    for code, phrase in expected.items():
        if phrase not in readme:
            failures.append(code)
    expected_zh = (
        {"README_ZH_CURRENT_VERSION_MISMATCH": f"目前 stable release：`{version}`"}
        if release_status == "stable" else {
            "README_ZH_CURRENT_VERSION_MISMATCH": f"目前開發目標：`{version}`",
            "README_ZH_STABLE_VERSION_MISMATCH": f"最新已發布 stable release：`{published}`",
        }
    )
    for code, phrase in expected_zh.items():
        if phrase not in readme_zh:
            failures.append(code)
    for name, content in (("README.md", readme), ("README.zh-TW.md", readme_zh)):
        for heading in adjacent_duplicate_headings(content):
            failures.append(f"ADJACENT_DUPLICATE_HEADING:{name}:{heading}")

    project_status = _text(root, "docs/PROJECT_STATUS.md")
    project_status_current = (
        f"Current stable release: `v{version}`"
        if release_status == "stable" else f"Current development target: `v{version}`"
    )
    if project_status_current not in project_status:
        failures.append("PROJECT_STATUS_CURRENT_VERSION_MISMATCH")
    if (release_status != "stable"
            and f"Latest published stable release: `v{published}`" not in project_status):
        failures.append("PROJECT_STATUS_STABLE_VERSION_MISMATCH")

    citation = _text(root, "CITATION.cff")
    if _match(r"^version:\s*(\S+)\s*$", citation) != published:
        failures.append("CITATION_STABLE_VERSION_MISMATCH")

    schema = json.loads(_text(root, "schemas/ai-review-request.schema.json"))
    if schema["properties"]["skill_version"]["const"] != version:
        failures.append("AI_REVIEW_SCHEMA_VERSION_MISMATCH")
    if f'- `skill_version`: `"{version}"`' not in _text(root, "references/ai_review_workflow.md"):
        failures.append("AI_REVIEW_WORKFLOW_VERSION_MISMATCH")
    if f"## [{version}]" not in _text(root, "CHANGELOG.md"):
        failures.append("CHANGELOG_VERSION_MISSING")
    if f"## [{version}]" not in _text(root, "CHANGELOG.zh-TW.md"):
        failures.append("CHANGELOG_ZH_VERSION_MISSING")
    versioning = _text(root, "VERSIONING.md")
    versioning_current = (
        f"`{version}` is the latest published stable skill version"
        if release_status == "stable" else f"`{version}` is the current development version"
    )
    if versioning_current not in versioning:
        failures.append("VERSIONING_CURRENT_VERSION_MISMATCH")
    if f"`{published}` is the latest published stable skill version" not in versioning:
        failures.append("VERSIONING_STABLE_VERSION_MISMATCH")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = validate_release_consistency(root)
    if failures:
        print("Release consistency validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Release consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
