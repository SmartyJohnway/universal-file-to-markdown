import argparse,json,sys
from ai_review import validate_review
p=argparse.ArgumentParser();p.add_argument('bundle_dir');p.add_argument('review');a=p.parse_args();r=validate_review(a.bundle_dir,a.review);print(json.dumps(r,ensure_ascii=False,indent=2));sys.exit(r['status']!='passed')
