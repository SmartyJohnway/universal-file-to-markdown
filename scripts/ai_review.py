"""Deterministic, offline contracts for host supplied readable projections."""
import hashlib,json,re
from pathlib import Path
REQUEST_SCHEMA_VERSION="1.0"; MAX_TARGET_CHARS=12000; MAX_REQUEST_CHARS=100000
ALLOWED_OPERATIONS={"improve_heading_readability","render_table_cell_links","render_table_cell_lists","reduce_duplicate_visual_labels","add_non-factual_section_spacing","annotate_uncertain_structure"}; DECISIONS={"apply_projection","no_change","needs_human_review","reject_target"}
TOKEN_RE=re.compile(r"https?://[^\s)\]>]+|\b\d{4}-\d{2}-\d{2}\b|\b\d{2,3}年\d{1,2}月\d{1,2}日|\btable-[A-Za-z0-9._-]+\b|\$[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\b")
UNSAFE_RE=re.compile(r"<\s*/?\s*(?:script|iframe|object|embed|style|svg)\b|(?:javascript|vbscript|data)\s*:|\b(?:python|shell|bash|powershell|cmd|file)\s*[:(]|(?:\.\.?[/\\]|/etc/|file://)",re.I)
AI_REVIEW_POLICY={"HTML_MERGED_TABLE_COMPLEX":"recommended","OCR_TABLE_LOW_CONFIDENCE":"recommended","OCR_TABLE_GEOMETRY_UNAVAILABLE":"recommended","OCR_TABLE_IRREGULAR_ROWS":"optional","MAIN_CONTENT_UNCERTAIN":"optional","BOILERPLATE_MAY_BE_INCLUDED":"optional","RELATIVE_URL_UNRESOLVED":"optional","TABLE_STRUCTURE_UNVERIFIED":"optional","HEADING_STRUCTURE_WEAK":"optional","READABILITY_COMPLEX_TABLE":"optional","READABILITY_LONG_FLAT_SECTION":"optional"}
def stable_json(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def load(p):
 with open(p,encoding='utf-8') as f:return json.load(f)
def _write(p,o):Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def _schema(name,value):
 try:
  from jsonschema import Draft202012Validator
  return [f"AI_REVIEW_SCHEMA_INVALID: {e.json_path}: {e.message}" for e in Draft202012Validator(load(Path(__file__).parent.parent/'schemas'/name)).iter_errors(value)]
 except Exception as e:return [f"AI_REVIEW_SCHEMA_INVALID: {e}"]
def fingerprint(bundle):
 b=Path(bundle);parts=[load(b/'manifest.json')['source_sha256']]
 for p in (b/'document.json',b/'tables'/'index.json'):
  if p.exists():parts.append(stable_json(load(p)))
 if (b/'tables').exists():parts += [stable_json(load(p)) for p in sorted((b/'tables').glob('*.json')) if p.name!='index.json']
 if (b/'chunks.jsonl').exists():parts.append((b/'chunks.jsonl').read_text(encoding='utf-8'))
 return hashlib.sha256('\n'.join(parts).encode()).hexdigest()
def table_markdown(t):
 g=t.get('grid',[])
 if not g:return ''
 e=lambda v:str(v or '').replace('|','\\|').replace('\n','<br>')
 return '\n'.join(['| '+' | '.join(map(e,g[0]))+' |','| '+' | '.join('---' for _ in g[0])+' |']+['| '+' | '.join(map(e,r))+' |' for r in g[1:]])
def assess_ai_review_eligibility(report,tables,bundle_valid=True):
 if report.get('status')=='failed' or not bundle_valid:return {'recommended':False,'priority':'none','reason_codes':[],'targets':[],'policy_status':'prohibited'}
 ws={w.get('code') for w in report.get('warnings',[]) if isinstance(w,dict)}; reasons=[];targets=[]
 for t in tables:
  if t.get('merged_cells'):reasons.append('HTML_MERGED_TABLE_COMPLEX');targets.append({'target_type':'table','target_id':t['id'],'source_locator':t.get('source_locator',{})})
 for w,c in {'LOW_OCR_CONFIDENCE_PAGES':'OCR_TABLE_LOW_CONFIDENCE','OCR_TABLE_GEOMETRY_UNAVAILABLE':'OCR_TABLE_GEOMETRY_UNAVAILABLE','OCR_TABLE_IRREGULAR_ROWS':'OCR_TABLE_IRREGULAR_ROWS','MAIN_CONTENT_NOT_IDENTIFIED':'MAIN_CONTENT_UNCERTAIN','BOILERPLATE_MAY_BE_INCLUDED':'BOILERPLATE_MAY_BE_INCLUDED','RELATIVE_URL_UNRESOLVED':'RELATIVE_URL_UNRESOLVED','TABLE_STRUCTURE_UNVERIFIED':'TABLE_STRUCTURE_UNVERIFIED'}.items():
  if w in ws:reasons.append(c)
 reasons=list(dict.fromkeys(reasons));rec=any(AI_REVIEW_POLICY.get(x)=='recommended' for x in reasons)
 return {'recommended':rec,'priority':'medium' if rec else ('low' if reasons else 'none'),'reason_codes':reasons,'targets':targets,'policy_status':'recommended' if rec else ('optional' if reasons else 'not_needed')}
def _target(t):return {'target_type':'table','target_id':t['id'],'reason_codes':['HTML_MERGED_TABLE_COMPLEX'],'source_locator':t.get('source_locator',{}),'canonical':{'dimensions':t.get('dimensions',{}),'grid':t.get('grid',[]),'merged_cells':t.get('merged_cells',[]),'cell_blocks':t.get('cell_blocks',[])},'faithful_markdown':table_markdown(t)}
def _bound(t,tr):
 while len(stable_json(t))>MAX_TARGET_CHARS:
  c=t['canonical']
  if c.get('cell_blocks'):c['cell_blocks']=[];tr.append({'target_id':t['target_id'],'reason':'cell_blocks_removed'});continue
  if len(c.get('grid',[]))>1:c['grid']=c['grid'][:max(1,len(c['grid'])//2)];tr.append({'target_id':t['target_id'],'reason':'grid_rows_reduced'});continue
  if len(t['faithful_markdown'])>200:t['faithful_markdown']=t['faithful_markdown'][:200];tr.append({'target_id':t['target_id'],'reason':'markdown_context_truncated'});continue
  raise ValueError('AI_REVIEW_CONTENT_TOO_LARGE')
def prepare_request(bundle):
 b=Path(bundle);report=load(b/'conversion-report.json');tables=[load(p) for p in sorted((b/'tables').glob('*.json')) if p.name!='index.json'] if (b/'tables').exists() else [];e=assess_ai_review_eligibility(report,tables,report.get('bundle_validation',{}).get('status','passed')=='passed')
 if e['recommended'] and not e['targets']:
  els=[x for x in load(b/'document.json').get('elements',[]) if x.get('text') or x.get('content')][:10];e['targets']=[{'target_type':'element_range','target_id':f'ocr-element-{i:04d}','source_locator':x.get('source_locator',{})} for i,x in enumerate(els,1)]
 report.update({'quality_risk_assessment':e,'ai_review_recommended':e['recommended'],'ai_review_recommendation_status':e['policy_status']})
 if not e['recommended'] or not e['targets']:report['ai_review_request_status']='not_generated_no_actionable_targets';_write(b/'conversion-report.json',report);return None
 tr=[];ts=[]; ids={x['target_id'] for x in e['targets']}
 for t in tables:
  if t['id'] in ids:x=_target(t);_bound(x,tr);ts.append(x)
 if len(ts)<len(ids):
  for i,x in enumerate([x for x in load(b/'document.json').get('elements',[]) if x.get('text') or x.get('content')],1):
   if f'ocr-element-{i:04d}' in ids:
    t={'target_type':'element_range','target_id':f'ocr-element-{i:04d}','reason_codes':[r for r in e['reason_codes'] if r.startswith('OCR_')],'source_locator':x.get('source_locator',{}),'element_ids':[x.get('id',f'element-{i}')],'heading_path':[],'canonical':{'text':x.get('text') or x.get('content')},'faithful_markdown':x.get('text') or x.get('content')};_bound(t,tr);ts.append(t)
 m=load(b/'manifest.json');r={'schema_version':'1.0','request_id':'ai-review-request-'+m['source_sha256'][:16],'source_sha256':m['source_sha256'],'skill_version':'1.7.0-dev','canonical_bundle_fingerprint':fingerprint(b),'review_scope':'readable_projection_only','instructions':{'preserve_facts':True,'preserve_numbers':True,'preserve_urls':True,'preserve_table_ids':True,'preserve_source_order':True,'do_not_modify_canonical':True},'reason_codes':e['reason_codes'],'targets':ts,'allowed_operations':sorted(ALLOWED_OPERATIONS),'prohibited_operations':['invent_content','remove_source_content','change_numbers','change_dates','change_urls','change table geometry','merge unrelated source sections','rewrite canonical JSON','change provenance'],'truncation':tr}
 errors=_schema('ai-review-request.schema.json',r)
 if len(stable_json(r))>MAX_REQUEST_CHARS:errors.append('AI_REVIEW_CONTENT_TOO_LARGE')
 if errors:raise ValueError('; '.join(errors))
 _write(b/'ai-review-request.json',r);report.update({'ai_review_request_status':'generated','ai_review_status':'not_provided'});_write(b/'conversion-report.json',report);return r
def _norm(s):return re.sub(r'\s+',' ',re.sub(r'[`*_\[\]()<>|]','',s)).strip().casefold()
def validate_review(bundle,review_path):
 b=Path(bundle)
 try:r=load(review_path);q=load(b/'ai-review-request.json')
 except Exception as e:return {'status':'failed','errors':['AI_REVIEW_SCHEMA_INVALID: '+str(e)]}
 errors=_schema('ai-review.schema.json',r)+_schema('ai-review-request.schema.json',q)
 for k,c in [('request_id','AI_REVIEW_REQUEST_ID_MISMATCH'),('source_sha256','AI_REVIEW_SOURCE_MISMATCH'),('canonical_bundle_fingerprint','AI_REVIEW_FINGERPRINT_MISMATCH')]:
  if r.get(k)!=q.get(k) or (k=='canonical_bundle_fingerprint' and r.get(k)!=fingerprint(b)):errors.append(c)
 seen=set();tm={x['target_id']:x for x in q.get('targets',[])}
 for x in r.get('target_reviews',[]):
  tid=x.get('target_id');text=x.get('readable_markdown','')
  if tid not in tm:errors.append('AI_REVIEW_TARGET_UNKNOWN')
  if tid in seen:errors.append('AI_REVIEW_TARGET_DUPLICATE')
  seen.add(tid)
  if x.get('decision') not in DECISIONS:errors.append('AI_REVIEW_DECISION_INVALID')
  if not isinstance(x.get('confidence'),(int,float)) or not 0<=x.get('confidence',-1)<=1:errors.append('AI_REVIEW_CONFIDENCE_INVALID')
  if any(not isinstance(o,dict) or o.get('operation') not in ALLOWED_OPERATIONS for o in x.get('operations',[])):errors.append('AI_REVIEW_OPERATION_INVALID')
  if x.get('decision')=='apply_projection' and (not isinstance(text,str) or not text.strip()):errors.append('AI_REVIEW_SCHEMA_INVALID')
  # Element-range targets are advisory OCR context in Phase 5.  The renderer only owns table replacement, so reject an apply request rather than report a silently ignored projection as host-applied.
  if tid in tm and tm[tid].get('target_type')=='element_range' and x.get('decision')=='apply_projection':errors.append('AI_REVIEW_ELEMENT_RANGE_APPLY_UNSUPPORTED')
  if len(text)>MAX_TARGET_CHARS:errors.append('AI_REVIEW_CONTENT_TOO_LARGE')
  if isinstance(text,str) and UNSAFE_RE.search(text):errors.append('AI_REVIEW_UNSAFE_CONTENT')
  if tid in tm and isinstance(text,str) and text:
   req=TOKEN_RE.findall(tm[tid].get('faithful_markdown',''));got=set(TOKEN_RE.findall(text))
   for z in req:
    if z not in got:errors.append('AI_REVIEW_URL_LOSS' if z.startswith('http') else 'AI_REVIEW_DATE_LOSS' if '年' in z or re.match(r'\d{4}-',z) else 'AI_REVIEW_SOURCE_TEXT_LOSS' if z.startswith('table-') else 'AI_REVIEW_NUMBER_LOSS')
   c=tm[tid].get('canonical',{}); vals=[str(v) for row in c.get('grid',[]) for v in row if str(v).strip()]+([str(c['text'])] if c.get('text') else [])
   if any(_norm(v) not in _norm(text) for v in vals):errors.append('AI_REVIEW_SOURCE_TEXT_LOSS')
 return {'status':'passed' if not errors else 'failed','errors':sorted(set(errors)),'review':r}
