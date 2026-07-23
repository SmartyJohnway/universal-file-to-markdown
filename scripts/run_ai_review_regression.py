#!/usr/bin/env python3
"""Expectation-driven Phase 5 regression runner; each reported case is executed."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
cases=['test_fingerprint_and_text_loss','test_element_apply_is_not_silently_ignored','test_unknown_duplicate_and_unsafe_rejected','test_duplicate_target_is_rejected','test_request_source_and_fingerprint_mismatches','test_valid_table_review_renders_and_preserves_canonical','test_rejected_review_removes_stale_artifacts','test_deterministic_projection_restores_table_cell_links','test_router_cleanup_removes_stale_ai_artifacts']
results=[]
for case in cases:
 r=subprocess.run([sys.executable,'-m','pytest',f'tests/test_ai_review.py::{case}','-q'],text=True,capture_output=True)
 results.append({'case':case,'status':'passed' if r.returncode==0 else 'failed','output':r.stdout+r.stderr})
failed=[x for x in results if x['status']=='failed']
passed_names={x['case'] for x in results if x['status']=='passed'}
summary={'cases':len(cases),'passed':len(passed_names),'failed':len(failed),'canonical_mutations':0 if 'test_valid_table_review_renders_and_preserves_canonical' in passed_names else None,'invalid_reviews_rejected':sum(name in passed_names for name in ['test_element_apply_is_not_silently_ignored','test_unknown_duplicate_and_unsafe_rejected','test_duplicate_target_is_rejected','test_request_source_and_fingerprint_mismatches','test_rejected_review_removes_stale_artifacts','test_deterministic_projection_restores_table_cell_links','test_router_cleanup_removes_stale_ai_artifacts']),'valid_reviews_applied':int('test_valid_table_review_renders_and_preserves_canonical' in passed_names),'deterministic_projection_cases':int('test_deterministic_projection_restores_table_cell_links' in passed_names),'validation_status':'passed' if not failed else 'failed','results':results}
(out/'ai-review-regression-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));sys.exit(bool(failed))
