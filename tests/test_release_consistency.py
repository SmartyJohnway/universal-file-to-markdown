from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_release_consistency import adjacent_duplicate_headings, validate_release_consistency


def test_repository_release_truth_is_consistent():
    assert validate_release_consistency(ROOT) == []


def test_adjacent_duplicate_heading_detection_ignores_separated_reuse():
    assert adjacent_duplicate_headings("## Same\n\n## Same\n") == ["## Same"]
    assert adjacent_duplicate_headings("## Same\ntext\n## Same\n") == []
