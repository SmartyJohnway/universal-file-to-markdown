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
