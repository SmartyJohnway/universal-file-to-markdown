#!/usr/bin/env python3
"""Expectation-driven Phase 5 regression runner; each summary metric has a case class."""
import argparse, json, subprocess, sys
from pathlib import Path

INVALID_REVIEW_CASES = {
    'test_element_apply_is_not_silently_ignored',
    'test_unknown_duplicate_and_unsafe_rejected',
    'test_duplicate_target_is_rejected',
    'test_request_source_and_fingerprint_mismatches',
    'test_rejected_review_removes_stale_artifacts',
}
VALID_APPLY_CASES = {'test_valid_table_review_renders_and_preserves_canonical'}
DETERMINISTIC_PROJECTION_CASES = {'test_deterministic_projection_restores_table_cell_links'}
STALE_CLEANUP_CASES = {'test_router_cleanup_removes_stale_ai_artifacts'}
OTHER_CASES = {'test_fingerprint_and_text_loss'}
CASES = sorted(INVALID_REVIEW_CASES | VALID_APPLY_CASES | DETERMINISTIC_PROJECTION_CASES | STALE_CLEANUP_CASES | OTHER_CASES)
EXPECTED_CASES = 9
assert len(CASES) == EXPECTED_CASES, 'update expected regression case count'

def passed_count(passed, category): return len(passed & category)
def main(output):
    root = Path(__file__).resolve().parents[1]
    if not (root / "tests").is_dir():
        print(
            "This regression runner requires the complete source repository "
            "and cannot run from the Release Package or Agent Skill archive.",
            file=sys.stderr,
        )
        return 2

    output.mkdir(parents=True, exist_ok=True); results=[]
    pytest_temp_root = output / "pytest-temp"
    pytest_temp_root.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        result=subprocess.run(
            [
                sys.executable, '-m', 'pytest', f'tests/test_ai_review.py::{case}', '-q',
                '--basetemp', str(pytest_temp_root / case),
            ],
            cwd=root,
            text=True,
            capture_output=True,
        )
        results.append({'case':case,'status':'passed' if result.returncode==0 else 'failed','output':result.stdout+result.stderr})
    failed=[result for result in results if result['status']=='failed']; passed={result['case'] for result in results if result['status']=='passed'}
    summary={'cases':len(CASES),'passed':len(passed),'failed':len(failed),'canonical_mutations':0 if passed_count(passed,VALID_APPLY_CASES) else None,'invalid_reviews_rejected':passed_count(passed,INVALID_REVIEW_CASES),'valid_reviews_applied':passed_count(passed,VALID_APPLY_CASES),'deterministic_projection_cases':passed_count(passed,DETERMINISTIC_PROJECTION_CASES),'stale_cleanup_cases':passed_count(passed,STALE_CLEANUP_CASES),'validation_status':'passed' if not failed else 'failed','results':results}
    if not failed:
        assert {key:summary[key] for key in ('cases','invalid_reviews_rejected','valid_reviews_applied','deterministic_projection_cases','stale_cleanup_cases','canonical_mutations')} == {'cases':9,'invalid_reviews_rejected':5,'valid_reviews_applied':1,'deterministic_projection_cases':1,'stale_cleanup_cases':1,'canonical_mutations':0}
    (output/'ai-review-regression-summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2)); return bool(failed)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();sys.exit(main(Path(args.output)))
