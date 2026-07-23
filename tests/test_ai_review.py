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

def test_duplicate_target_is_rejected(tmp_path):
 b=bundle(tmp_path);q=prepare_request(b);r=review(q,'Motor https://example.test/pump');r['target_reviews'].append(dict(r['target_reviews'][0]));e=check(b,r,tmp_path)['errors'];assert 'AI_REVIEW_TARGET_DUPLICATE' in e

def test_request_source_and_fingerprint_mismatches(tmp_path):
 b=bundle(tmp_path);q=prepare_request(b);r=review(q,'Motor https://example.test/pump');r['request_id']='ai-review-request-'+'b'*16;r['source_sha256']='b'*64;r['canonical_bundle_fingerprint']='b'*64;e=check(b,r,tmp_path)['errors'];assert {'AI_REVIEW_REQUEST_ID_MISMATCH','AI_REVIEW_SOURCE_MISMATCH','AI_REVIEW_FINGERPRINT_MISMATCH'} <= set(e)

def test_valid_table_review_renders_and_preserves_canonical(tmp_path,monkeypatch):
 b=bundle(tmp_path);q=prepare_request(b);r=review(q,'| Motor | [pump](https://example.test/pump) |\n| --- | --- |');p=tmp_path/'review.json';p.write_text(json.dumps(r))
 import render_readable_projection as renderer
 monkeypatch.setattr(renderer,'validate_bundle',lambda _: {'status':'passed'})
 before={x.name:x.read_bytes() for x in [b/'document.json',b/'chunks.jsonl',b/'tables/index.json',b/'tables/table-html-0001.json']}
 (b/'document.md').write_text('| Motor | https://example.test/pump |\n| --- | --- |')
 renderer.main(b,p)
 assert (b/'ai-review.json').exists() and '[pump]' in (b/'document-readable.md').read_text()
 assert before=={x.name:x.read_bytes() for x in [b/'document.json',b/'chunks.jsonl',b/'tables/index.json',b/'tables/table-html-0001.json']}

def test_rejected_review_removes_stale_artifacts(tmp_path,monkeypatch):
 b=bundle(tmp_path);q=prepare_request(b);p=tmp_path/'bad.json';p.write_text(json.dumps(review(q,'wrong')))
 (b/'document.md').write_text('| Motor | https://example.test/pump |\n| --- | --- |');(b/'ai-review.json').write_text('{}');(b/'document-readable.md').write_text('old')
 import render_readable_projection as renderer
 monkeypatch.setattr(renderer,'validate_bundle',lambda _: {'status':'passed'})
 try: renderer.main(b,p)
 except SystemExit: pass
 assert not (b/'ai-review.json').exists() and not (b/'document-readable.md').exists()
