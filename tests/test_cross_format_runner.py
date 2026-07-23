import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from run_cross_format_regression import load_cases
def test_summary_manifest_has_at_least_twelve_core_cases(): assert len([c for c in load_cases() if c['profile']=='core']) >= 12
def test_optional_missing_tool_is_declared(): assert any(c['profile']=='optional-pandoc' for c in load_cases())
