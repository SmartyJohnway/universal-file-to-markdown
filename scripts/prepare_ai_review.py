#!/usr/bin/env python3
"""CLI helper to prepare AI Review requests, including controlled user-requested triggers."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ai_review import prepare_request

def main():
    parser = argparse.ArgumentParser(description="Prepare AI review request for a canonical bundle.")
    parser.add_argument("bundle_dir", help="Path to canonical output bundle directory")
    parser.add_argument("--force-user-request", action="store_true", help="Explicitly request AI review even when automatic triggers were not met")
    parser.add_argument("--target-table", type=str, help="Specific table ID to target for AI review (e.g. table-0001)")
    parser.add_argument("--target-element", type=str, help="Specific element ID to target for AI review")
    parser.add_argument("--all-eligible-targets", action="store_true", help="Target all eligible targets for AI review")

    args = parser.parse_args()
    try:
        req = prepare_request(
            args.bundle_dir,
            force_user_request=args.force_user_request,
            target_table=args.target_table,
            target_element=args.target_element,
            all_eligible_targets=args.all_eligible_targets,
        )
        print(json.dumps(req or {"status": "not_generated"}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
