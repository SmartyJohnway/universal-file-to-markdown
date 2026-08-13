from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_markdown_links import iter_markdown_files, validate


def test_local_runtime_and_scratch_directories_are_ignored(tmp_path):
    (tmp_path / "README.md").write_text("[ok](target.md)\n", encoding="utf-8")
    (tmp_path / "target.md").write_text("target\n", encoding="utf-8")
    for directory in (".qualification", ".hermes", "scratch", ".pytest_cache"):
        path = tmp_path / directory
        path.mkdir()
        (path / "third-party.md").write_text("[missing](not-shipped.md)\n", encoding="utf-8")

    assert validate(tmp_path) == []
    names = {path.relative_to(tmp_path).as_posix() for path in iter_markdown_files(tmp_path)}
    assert names == {"README.md", "target.md"}
