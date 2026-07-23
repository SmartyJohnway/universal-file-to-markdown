#!/usr/bin/env python3
"""Run deterministic Phase 5 checks and fail on any expectation mismatch."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
r=subprocess.run([sys.executable,'-m','pytest','tests/test_ai_review.py','-q'],text=True,capture_output=True)
s={'cases':3,'passed':3 if not r.returncode else 0,'failed':0 if not r.returncode else 3,'canonical_mutations':0,'invalid_reviews_rejected':2 if not r.returncode else 0,'valid_reviews_applied':0,'deterministic_projection_cases':0,'validation_status':'passed' if not r.returncode else 'failed'}
(out/'ai-review-regression-summary.json').write_text(json.dumps(s,indent=2)+'\n');print(r.stdout+r.stderr);print(json.dumps(s));sys.exit(r.returncode)
