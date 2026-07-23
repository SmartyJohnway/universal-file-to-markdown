import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from run_cross_format_regression import load_cases, main, assert_contract, _table_index_errors
def test_summary_manifest_has_at_least_twelve_core_cases(): assert len([c for c in load_cases() if c['profile']=='core']) >= 12
def test_optional_missing_tool_is_declared(): assert any(c['profile']=='optional-pandoc' for c in load_cases())

def _passing_case(case_id='json-unicode'):
    return {'case_id':case_id,'format':'json','status':'passed','reason_codes':[],'fingerprints':[{'bundle_fingerprint':'new'}],'normalized_snapshot':{}}
def test_partial_case_baseline_update_preserves_unselected_cases(tmp_path, monkeypatch):
    monkeypatch.setattr('run_cross_format_regression.run_case',lambda *args: _passing_case())
    baseline=tmp_path/'baseline'; baseline.mkdir(); (baseline/'fingerprints.json').write_text(json.dumps({'unselected':'keep'}))
    args=type('Args',(),{'update_baseline':True,'confirm_baseline_update':True,'profile':'core','case':'json-unicode','format':None,'output':str(tmp_path/'out'),'reruns':1,'keep_bundles':False,'baseline_dir':str(baseline)})()
    assert main(args)==0
    assert json.loads((baseline/'fingerprints.json').read_text())['unselected']=='keep'

def test_missing_format_locator_fails(tmp_path, monkeypatch):
    bundle=tmp_path; (bundle/'conversion-report.json').write_text(json.dumps({'status':'passed','engine':'native','bundle_validation':{'status':'passed'},'warnings':[]})); (bundle/'document.json').write_text(json.dumps({'elements':[{'id':'a','type':'document','source_locator':{}}]})); (bundle/'chunks.jsonl').write_text('')
    import validate_bundle; monkeypatch.setattr(validate_bundle,'validate_bundle',lambda _: {'status':'passed'})
    case={'expected_status':['passed'],'expected_bundle_validation':'passed','expected_engine':'native','required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'required_element_types':['document'],'required_locator_fields':['format'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000}
    assert 'LOCATOR_MISSING' in assert_contract(case,bundle,0)[0]

def test_confirmed_baseline_update_accepts_baseline_drift(tmp_path, monkeypatch):
    monkeypatch.setattr('run_cross_format_regression.run_case',lambda *args: _passing_case())
    baseline=tmp_path/'baseline'; baseline.mkdir(); (baseline/'fingerprints.json').write_text(json.dumps({'json-unicode':'intentionally-old'}))
    args=type('Args',(),{'update_baseline':True,'confirm_baseline_update':True,'profile':'core','case':'json-unicode','format':None,'output':str(tmp_path/'out'),'reruns':1,'keep_bundles':False,'baseline_dir':str(baseline)})()
    assert main(args)==0
    assert json.loads((baseline/'fingerprints.json').read_text())['json-unicode'] != 'intentionally-old'

def test_malformed_table_index_is_structured_failure(tmp_path):
    path=tmp_path/'index.json'; path.write_text('{')
    assert _table_index_errors(path,set()) == ['TABLE_INDEX_MALFORMED']

def test_unsafe_table_index_asset_fails(tmp_path):
    path=tmp_path/'index.json'; path.write_text(json.dumps([{'id':'table-1','assets':{'csv':'../outside.csv'}}]))
    assert 'REFERENCE_ERROR' in _table_index_errors(path,{'table-1'})

def test_baseline_update_refuses_contract_failures_without_writing(tmp_path, monkeypatch):
    baseline=tmp_path/'baseline'; baseline.mkdir(); fingerprints=baseline/'fingerprints.json'; snapshot=baseline/'json-unicode.normalized.json'
    fingerprints.write_bytes(b'{"json-unicode":"old"}\n'); snapshot.write_bytes(b'{"old":true}\n'); before=(fingerprints.read_bytes(),snapshot.read_bytes())
    failed=_passing_case(); failed['status']='failed'; failed['reason_codes']=['REFERENCE_ERROR']
    monkeypatch.setattr('run_cross_format_regression.run_case',lambda *args: failed)
    args=type('Args',(),{'update_baseline':True,'confirm_baseline_update':True,'profile':'core','case':'json-unicode','format':None,'output':str(tmp_path/'out'),'reruns':1,'keep_bundles':False,'baseline_dir':str(baseline)})()
    import pytest
    with pytest.raises(SystemExit): main(args)
    assert (fingerprints.read_bytes(),snapshot.read_bytes()) == before

def test_non_update_baseline_drift_fails_without_writing(tmp_path, monkeypatch):
    baseline=tmp_path/'baseline'; baseline.mkdir(); path=baseline/'fingerprints.json'; path.write_bytes(b'{"json-unicode":"old"}\n'); before=path.read_bytes()
    monkeypatch.setattr('run_cross_format_regression.run_case',lambda *args: _passing_case())
    args=type('Args',(),{'update_baseline':False,'confirm_baseline_update':False,'profile':'core','case':'json-unicode','format':None,'output':str(tmp_path/'out'),'reruns':1,'keep_bundles':False,'baseline_dir':str(baseline)})()
    assert main(args)==1 and path.read_bytes()==before

def _semantic_bundle(tmp_path, content, parent_type='slide'):
    (tmp_path/'conversion-report.json').write_text(json.dumps({'status':'passed','engine':'python-pptx_custom','bundle_validation':{'status':'passed'},'warnings':[]}))
    elements=[{'id':'slide','type':parent_type,'source_locator':{'format':'pptx'}}, {'id':'item','parent_id':'slide','type':'list','content':content,'source_locator':{'format':'pptx'}}]
    (tmp_path/'document.json').write_text(json.dumps({'elements':elements})); (tmp_path/'chunks.jsonl').write_text('')

def _semantic_case(**optional):
    case={'expected_status':['passed'],'expected_bundle_validation':'passed','expected_engine':'python-pptx','required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'required_element_types':['list'],'required_locator_fields':['format'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000}; case.update(optional); return case

def test_list_markdown_semantics_require_each_kind(tmp_path, monkeypatch):
    import validate_bundle; monkeypatch.setattr(validate_bundle,'validate_bundle',lambda _: {'status':'passed'})
    case=_semantic_case(required_list_markdown_patterns=[r'^- bullet$', r'^1\. number$'])
    _semantic_bundle(tmp_path, '- bullet\n1. number'); assert not assert_contract(case,tmp_path,0)[0]
    _semantic_bundle(tmp_path, '- bullet'); assert 'LIST_SEMANTIC_MISSING' in assert_contract(case,tmp_path,0)[0]
    _semantic_bundle(tmp_path, '• bullet\n1. number'); assert 'LIST_SEMANTIC_MISSING' in assert_contract(case,tmp_path,0)[0]

def test_required_ancestor_types_distinguishes_grouped_table(tmp_path, monkeypatch):
    import validate_bundle; monkeypatch.setattr(validate_bundle,'validate_bundle',lambda _: {'status':'passed'})
    (tmp_path/'conversion-report.json').write_text(json.dumps({'status':'passed','engine':'python-pptx_custom','bundle_validation':{'status':'passed'},'warnings':[]})); (tmp_path/'chunks.jsonl').write_text('')
    case=_semantic_case(required_element_types=['table'], required_element_ancestor_types={'table':['group','slide']})
    grouped=[{'id':'slide','type':'slide','source_locator':{'format':'pptx'}},{'id':'group','parent_id':'slide','type':'group','source_locator':{'format':'pptx'}},{'id':'table','parent_id':'group','type':'table','source_locator':{'format':'pptx'}}]
    (tmp_path/'document.json').write_text(json.dumps({'elements':grouped})); assert not assert_contract(case,tmp_path,0)[0]
    grouped[-1]['parent_id']='slide'; (tmp_path/'document.json').write_text(json.dumps({'elements':grouped})); assert 'ANCESTOR_SEMANTIC_MISSING' in assert_contract(case,tmp_path,0)[0]

def test_ancestor_cycle_is_a_structured_reference_error(tmp_path, monkeypatch):
    import validate_bundle; monkeypatch.setattr(validate_bundle,'validate_bundle',lambda _: {'status':'passed'})
    (tmp_path/'conversion-report.json').write_text(json.dumps({'status':'passed','engine':'python-pptx_custom','bundle_validation':{'status':'passed'},'warnings':[]})); (tmp_path/'chunks.jsonl').write_text('')
    case=_semantic_case(required_element_types=['table'], required_element_ancestor_types={'table':['group']})
    cyclic=[{'id':'group','parent_id':'table','type':'group','source_locator':{'format':'pptx'}},{'id':'table','parent_id':'group','type':'table','source_locator':{'format':'pptx'}}]
    (tmp_path/'document.json').write_text(json.dumps({'elements':cyclic}))
    errors,_=assert_contract(case,tmp_path,0)
    assert 'REFERENCE_ERROR' in errors and 'ANCESTOR_SEMANTIC_MISSING' in errors

def test_ocr_contract_reports_missing_evidence(tmp_path, monkeypatch):
    import validate_bundle; monkeypatch.setattr(validate_bundle,'validate_bundle',lambda _: {'status':'passed'})
    (tmp_path/'conversion-report.json').write_text(json.dumps({'status':'passed','engine':'rapidocr_onnxruntime','bundle_validation':{'status':'passed'},'warnings':[], 'details':{'ocr_used':False,'ocr_table_candidates':[],'ocr_table_assessment':{}}}))
    (tmp_path/'document.json').write_text(json.dumps({'elements':[{'id':'page','type':'page','content':'wrong','engine':'rapidocr','source_locator':{'format':'pdf','page':1}}]})); (tmp_path/'chunks.jsonl').write_text('')
    case={'expected_status':['passed'],'expected_bundle_validation':'passed','expected_engine':'rapidocr','required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'required_element_types':['page'],'required_locator_fields':['format'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000,'required_ocr':{'content_patterns':['TOKEN'],'element_types':['text'],'locator_fields':['page'],'min_rejected_tables':1}}
    errors,_=assert_contract(case,tmp_path,0)
    assert {'OCR_EVIDENCE_MISSING','OCR_CONTENT_MISSING','OCR_TABLE_REJECTION_MISSING'} <= set(errors)
