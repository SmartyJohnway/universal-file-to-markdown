#!/usr/bin/env python3
"""Safely render an isolated readable projection; canonical files are never written."""
import argparse, hashlib, json, os, tempfile
from pathlib import Path
from ai_review import load, table_markdown, validate_review
from validate_bundle import validate_bundle

def hashes(b):
    names=['document.md','document.json','chunks.jsonl','tables/index.json']
    paths=[b/n for n in names if (b/n).exists()]+sorted((b/'tables').glob('*.json')) if (b/'tables').exists() else [b/n for n in names if (b/n).exists()]
    return {str(p.relative_to(b)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
def enhanced(t):
    grid=[list(r) for r in t.get('grid',[])]; blocks={(x['row'],x['column']):x['blocks'] for x in t.get('cell_blocks',[])}
    for (r,c), bs in blocks.items():
        if r>=len(grid) or c>=len(grid[r]):continue
        out=[]
        for x in bs:
            if x['type']=='link' and x.get('url'):out.append(f"[{x.get('text','')}]({x['url']})")
            elif x['type']=='image' and x.get('url'):out.append(f"![{x.get('alt','')}]({x['url']})")
            elif x['type']=='list_item':out.append(('- ' if not x.get('ordered') else '1. ')+x.get('text',''))
            elif x.get('text'):out.append(x['text'])
        if out:grid[r][c]='<br>'.join(out)
    return table_markdown({'grid':grid})
def main(bundle, review_file=None):
 b=Path(bundle)
 if validate_bundle(str(b))['status']!='passed': raise SystemExit('canonical bundle validation failed')
 before=hashes(b); review=None
 if review_file:
  result=validate_review(str(b),review_file)
  if result['status']!='passed':
   report=load(b/'conversion-report.json');report['ai_review_status']='rejected';report['readable_projection_status']='not_generated';(b/'conversion-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(b/'document-readable.md').unlink(missing_ok=True);(b/'ai-review.json').unlink(missing_ok=True); raise SystemExit('review rejected: '+','.join(result['errors']))
  (b/'ai-review.json').write_text(json.dumps(result['review'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); review={x['target_id']:x for x in result['review'].get('target_reviews',[])}
 text=(b/'document.md').read_text(encoding='utf-8')
 for p in sorted((b/'tables').glob('*.json')) if (b/'tables').exists() else []:
  if p.name=='index.json':continue
  t=load(p); faithful=table_markdown(t); choice=enhanced(t); item=(review or {}).get(t['id'])
  if item and item['decision']=='apply_projection': choice=item['readable_markdown']
  elif item and item['decision'] in {'needs_human_review','reject_target'}: choice=faithful+'\n\n> Review note: structure may need human confirmation.'
  text=text.replace(faithful,choice,1)
 fd,tmp=tempfile.mkstemp(dir=b,prefix='.readable-',text=True);os.close(fd);Path(tmp).write_text(text,encoding='utf-8');os.replace(tmp,b/'document-readable.md')
 if hashes(b)!=before: raise SystemExit('AI_REVIEW_CANONICAL_MUTATION_DETECTED')
 report=load(b/'conversion-report.json');report['ai_review_status']='validated' if review else report.get('ai_review_status','not_provided');report['readable_projection_status']='host_ai_applied' if review else 'deterministic_only';(b/'conversion-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('bundle_dir');p.add_argument('--review');a=p.parse_args();main(a.bundle_dir,a.review)
