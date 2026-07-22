#!/usr/bin/env python3
"""Run native HTML conversion and emit a machine-readable acceptance summary."""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from router import convert

p=argparse.ArgumentParser(); p.add_argument("input"); p.add_argument("--source-url"); p.add_argument("--output", required=True); a=p.parse_args()
shutil.rmtree(a.output, ignore_errors=True)
report=convert(a.input, a.output, source_url=a.source_url)
details=report.get("details", {}).get("html_structure", {})
summary={"status":report.get("status"), "source_url":a.source_url, **details,
         "structural_fidelity":report.get("structural_fidelity"), "quality_risk_assessment":report.get("quality_risk_assessment")}
with open(os.path.join(a.output,"html-acceptance-summary.json"),"w",encoding="utf-8") as f: json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2)); sys.exit(0 if report.get("status") != "failed" else 1)
