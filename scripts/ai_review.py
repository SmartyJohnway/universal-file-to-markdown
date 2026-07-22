"""Deterministic, host-only AI review contracts for readable projections."""
import hashlib, json, os, re
from pathlib import Path

REQUEST_SCHEMA_VERSION = "1.0"
ALLOWED_OPERATIONS = {"improve_heading_readability", "render_table_cell_links", "render_table_cell_lists", "reduce_duplicate_visual_labels", "add_non-factual_section_spacing", "annotate_uncertain_structure"}
DECISIONS = {"apply_projection", "no_change", "needs_human_review", "reject_target"}
TOKEN_RE = re.compile(r"https?://[^\s)\]>]+|\b\d{4}-\d{2}-\d{2}\b|\b\d{2,3}年\d{1,2}月\d{1,2}日|\btable-[A-Za-z0-9._-]+\b|\$[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\b")
UNSAFE_RE = re.compile(r"<\s*script\b|javascript:|\b(?:python|shell|bash|powershell)\s*[:(]", re.I)

AI_REVIEW_POLICY = {
 "HTML_MERGED_TABLE_COMPLEX":"recommended", "OCR_TABLE_LOW_CONFIDENCE":"recommended",
 "OCR_TABLE_GEOMETRY_UNAVAILABLE":"recommended", "OCR_TABLE_IRREGULAR_ROWS":"optional",
 "MAIN_CONTENT_UNCERTAIN":"optional", "BOILERPLATE_MAY_BE_INCLUDED":"optional",
 "RELATIVE_URL_UNRESOLVED":"optional", "TABLE_STRUCTURE_UNVERIFIED":"optional",
 "HEADING_STRUCTURE_WEAK":"optional", "READABILITY_COMPLEX_TABLE":"optional", "READABILITY_LONG_FLAT_SECTION":"optional",
}

def stable_json(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def load(path):
    with open(path, encoding="utf-8") as f: return json.load(f)
def fingerprint(bundle):
    b=Path(bundle); manifest=load(b/'manifest.json'); parts=[manifest['source_sha256']]
    for p in [b/'document.json', b/'tables'/'index.json']:
        if p.exists(): parts.append(stable_json(load(p)))
    if (b/'tables').exists():
        for p in sorted((b/'tables').glob('*.json')):
            if p.name!='index.json': parts.append(stable_json(load(p)))
    if (b/'chunks.jsonl').exists(): parts.append((b/'chunks.jsonl').read_text(encoding='utf-8'))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
def assess_ai_review_eligibility(report, tables, bundle_valid=True):
    if report.get('status')=='failed' or not bundle_valid: return {'recommended':False,'priority':'none','reason_codes':[],'targets':[],'policy_status':'prohibited'}
    warnings={w.get('code') for w in report.get('warnings',[]) if isinstance(w,dict)}; reasons=[]; targets=[]
    for t in tables:
        if t.get('merged_cells'): reasons.append('HTML_MERGED_TABLE_COMPLEX'); targets.append({'target_type':'table','target_id':t['id'],'source_locator':t.get('source_locator',{})})
    ocr_codes={'LOW_OCR_CONFIDENCE_PAGES':'OCR_TABLE_LOW_CONFIDENCE','OCR_TABLE_GEOMETRY_UNAVAILABLE':'OCR_TABLE_GEOMETRY_UNAVAILABLE','OCR_TABLE_IRREGULAR_ROWS':'OCR_TABLE_IRREGULAR_ROWS'}
    for w,c in ocr_codes.items():
        if w in warnings: reasons.append(c)
    mapping={'MAIN_CONTENT_NOT_IDENTIFIED':'MAIN_CONTENT_UNCERTAIN','BOILERPLATE_MAY_BE_INCLUDED':'BOILERPLATE_MAY_BE_INCLUDED','RELATIVE_URL_UNRESOLVED':'RELATIVE_URL_UNRESOLVED','TABLE_STRUCTURE_UNVERIFIED':'TABLE_STRUCTURE_UNVERIFIED'}
    reasons += [c for w,c in mapping.items() if w in warnings]
    reasons=list(dict.fromkeys(reasons)); recommended=any(AI_REVIEW_POLICY.get(x)=='recommended' for x in reasons)
    return {'recommended':recommended,'priority':'medium' if recommended else ('low' if reasons else 'none'),'reason_codes':reasons,'targets':targets,'policy_status':'recommended' if recommended else ('optional' if reasons else 'not_needed')}
def _target(table):
    return {'target_type':'table','target_id':table['id'],'reason_codes':['HTML_MERGED_TABLE_COMPLEX'] if table.get('merged_cells') else [],'source_locator':table.get('source_locator',{}),'canonical':{'dimensions':table.get('dimensions',{}),'grid':table.get('grid',[]),'merged_cells':table.get('merged_cells',[]),'cell_blocks':table.get('cell_blocks',[])},'faithful_markdown':table_markdown(table)}
def table_markdown(t):
    grid=t.get('grid',[])
    if not grid:return ''
    e=lambda x:str(x or '').replace('|','\\|').replace('\n','<br>')
    return '\n'.join(['| '+' | '.join(map(e,grid[0]))+' |','| '+' | '.join('---' for _ in grid[0])+' |']+['| '+' | '.join(map(e,r))+' |' for r in grid[1:]])
def prepare_request(bundle):
    b=Path(bundle); report=load(b/'conversion-report.json'); tables=[load(p) for p in sorted((b/'tables').glob('*.json')) if p.name!='index.json'] if (b/'tables').exists() else []
    eligibility=assess_ai_review_eligibility(report,tables, report.get('bundle_validation',{}).get('status','passed')=='passed')
    report['quality_risk_assessment']=eligibility; report['ai_review_recommended']=eligibility['recommended']; report['ai_review_recommendation_status']=eligibility['policy_status']
    if not eligibility['recommended']:
        report['ai_review_request_status']='not_generated_not_recommended'; _write(b/'conversion-report.json',report); return None
    targets=[]; truncated=[]
    for t in tables:
        if t['id'] not in {x['target_id'] for x in eligibility['targets']}:continue
        x=_target(t); raw=stable_json(x)
        if len(raw)>12000: x['canonical']['cell_blocks']=[]; x['canonical']['grid']=x['canonical']['grid'][:20]; truncated.append({'target_id':t['id'],'reason':'target_context_limit'})
        targets.append(x)
    manifest=load(b/'manifest.json'); req={'schema_version':REQUEST_SCHEMA_VERSION,'request_id':'ai-review-request-'+manifest['source_sha256'][:16],'source_sha256':manifest['source_sha256'],'skill_version':'1.7.0-dev','canonical_bundle_fingerprint':fingerprint(b),'review_scope':'readable_projection_only','instructions':{'preserve_facts':True,'preserve_numbers':True,'preserve_urls':True,'preserve_table_ids':True,'preserve_source_order':True,'do_not_modify_canonical':True},'reason_codes':eligibility['reason_codes'],'targets':targets,'allowed_operations':sorted(ALLOWED_OPERATIONS),'prohibited_operations':['invent_content','remove_source_content','change_numbers','change_dates','change_urls','change table geometry','merge unrelated source sections','rewrite canonical JSON','change provenance'],'truncation':truncated}
    if len(stable_json(req))>100000: raise ValueError('AI_REVIEW_CONTENT_TOO_LARGE')
    _write(b/'ai-review-request.json',req); report['ai_review_request_status']='generated'; report['ai_review_status']='not_provided'; _write(b/'conversion-report.json',report); return req
def validate_review(bundle, review_path):
    b=Path(bundle); errors=[]
    try: review=load(review_path); req=load(b/'ai-review-request.json')
    except Exception as e:return {'status':'failed','errors':['AI_REVIEW_SCHEMA_INVALID: '+str(e)]}
    for key,code in [('request_id','AI_REVIEW_REQUEST_ID_MISMATCH'),('source_sha256','AI_REVIEW_SOURCE_MISMATCH'),('canonical_bundle_fingerprint','AI_REVIEW_FINGERPRINT_MISMATCH')]:
        if review.get(key)!=req.get(key) or (key=='canonical_bundle_fingerprint' and review.get(key)!=fingerprint(b)): errors.append(code)
    seen=set(); target_map={x['target_id']:x for x in req['targets']}
    for item in review.get('target_reviews',[]):
        tid=item.get('target_id')
        if tid not in target_map: errors.append('AI_REVIEW_TARGET_UNKNOWN')
        if tid in seen: errors.append('AI_REVIEW_TARGET_DUPLICATE')
        seen.add(tid)
        if item.get('decision') not in DECISIONS: errors.append('AI_REVIEW_DECISION_INVALID')
        if not isinstance(item.get('confidence'),(int,float)) or not 0<=item['confidence']<=1: errors.append('AI_REVIEW_CONFIDENCE_INVALID')
        ops=item.get('operations',[])
        if any(not isinstance(x,dict) or x.get('operation') not in ALLOWED_OPERATIONS for x in ops): errors.append('AI_REVIEW_OPERATION_INVALID')
        text=item.get('readable_markdown','')
        if item.get('decision')=='apply_projection' and not isinstance(text,str): errors.append('AI_REVIEW_SCHEMA_INVALID')
        if item.get('decision')!='apply_projection' and 'readable_markdown' in item: errors.append('AI_REVIEW_SCHEMA_INVALID')
        if len(text)>12000: errors.append('AI_REVIEW_CONTENT_TOO_LARGE')
        if UNSAFE_RE.search(text): errors.append('AI_REVIEW_UNSAFE_CONTENT')
        if text:
            required=TOKEN_RE.findall(target_map.get(tid,{}).get('faithful_markdown',''))
            got=set(TOKEN_RE.findall(text))
            for token in required:
                if token not in got: errors.append('AI_REVIEW_URL_LOSS' if token.startswith('http') else 'AI_REVIEW_DATE_LOSS' if '年' in token or re.match(r'\d{4}-',token) else 'AI_REVIEW_SOURCE_TEXT_LOSS' if token.startswith('table-') else 'AI_REVIEW_NUMBER_LOSS')
    return {'status':'passed' if not errors else 'failed','errors':sorted(set(errors)),'review':review}
def _write(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
