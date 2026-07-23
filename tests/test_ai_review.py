import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from ai_review import prepare_request, validate_review, fingerprint

def bundle(tmp_path, warning=None):
 b=tmp_path/'bundle';(b/'tables').mkdir(parents=True);sha='a'*64
 for name,data in {'manifest.json':{'source_sha256':sha},'document.json':{'elements':[{'id':'e1','text':'Motor Pump Valve','source_locator':{'format':'pdf','page_start':1}}]},'tables/index.json':[],'conversion-report.json':{'status':'passed','bundle_validation':{'status':'passed'},'warnings':([{'code':warning}] if warning else [])}}.items():(b/name).write_text(json.dumps(data))
 (b/'chunks.jsonl').write_text('{}\n');(b/'tables/table-html-0001.json').write_text(json.dumps({'id':'table-html-0001','source_locator':{'format':'html','table_index':1},'grid':[['Motor','https://example.test/pump']], 'merged_cells':([] if warning else [{}]), 'cell_blocks':[]}));return b
def review(q,text,tid=None):return {'schema_version':'1.0','request_id':q['request_id'],'source_sha256':q['source_sha256'],'canonical_bundle_fingerprint':q['canonical_bundle_fingerprint'],'reviewer':{'type':'host_ai','provider':'test','model':'test'},'review_status':'completed','target_reviews':[{'target_id':tid or q['targets'][0]['target_id'],'decision':'apply_projection','confidence':1,'operations':[],'readable_markdown':text,'notes':[],'uncertainties':[]}]}
def check(b,r,tmp):p=tmp/'review.json';p.write_text(json.dumps(r));return validate_review(b,p)
def test_fingerprint_and_text_loss(tmp_path):
 b=bundle(tmp_path);q=prepare_request(b);assert fingerprint(b)==q['canonical_bundle_fingerprint'];assert 'AI_REVIEW_SOURCE_TEXT_LOSS' in check(b,review(q,'other https://example.test/pump'),tmp_path)['errors']
def test_element_apply_is_not_silently_ignored(tmp_path):
 b=bundle(tmp_path,'LOW_OCR_CONFIDENCE_PAGES');q=prepare_request(b);assert q['targets'][0]['target_type']=='element_range';r=check(b,review(q,'Motor Pump Valve'),tmp_path);assert r['status']=='failed' and 'AI_REVIEW_ELEMENT_RANGE_APPLY_UNSUPPORTED' in r['errors']
def test_unknown_duplicate_and_unsafe_rejected(tmp_path):
 b=bundle(tmp_path);q=prepare_request(b);r=review(q,'Motor https://example.test/pump<script>x</script>');r['target_reviews'].append(dict(r['target_reviews'][0]));r['target_reviews'][1]['target_id']='unknown';e=check(b,r,tmp_path)['errors'];assert 'AI_REVIEW_UNSAFE_CONTENT' in e and 'AI_REVIEW_TARGET_UNKNOWN' in e
