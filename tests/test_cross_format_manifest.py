import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from run_cross_format_regression import load_cases

def test_case_ids_are_unique():
    cases=load_cases(); assert len({c['case_id'] for c in cases}) == len(cases)
def test_core_case_cannot_be_silently_skipped():
    assert all(c['profile'] != 'core' or c['determinism']['normalized_reruns_must_match'] for c in load_cases())
