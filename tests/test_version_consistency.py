import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def current_version():
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_canonical_version_matches_skill_and_readmes():
    version = current_version()
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(rf"^version: {re.escape(version)}$", skill, re.MULTILINE)
    for name in ("README.md", "README.zh-TW.md"):
        assert f"`{version}`" in (ROOT / name).read_text(encoding="utf-8")


def test_schema_versions_are_independent_from_skill_version():
    version = current_version()
    assert version != "1.0"
    assert '"const": "1.0"' in (ROOT / "schemas" / "document.schema.json").read_text(encoding="utf-8")
    assert '"const": "1.0"' in (ROOT / "schemas" / "table.schema.json").read_text(encoding="utf-8")
