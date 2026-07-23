import argparse,json
from ai_review import prepare_request
p=argparse.ArgumentParser();p.add_argument('bundle_dir');a=p.parse_args(); r=prepare_request(a.bundle_dir); print(json.dumps(r or {'status':'not_generated'},ensure_ascii=False,indent=2))
