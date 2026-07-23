import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from run_cross_format_regression import load_cases

def test_case_ids_are_unique():
    cases=load_cases(); assert len({c['case_id'] for c in cases}) == len(cases)
def test_core_case_cannot_be_silently_skipped():
    assert all(c['profile'] != 'core' or c['determinism']['normalized_reruns_must_match'] for c in load_cases())

import json
import pytest

def test_invalid_list_semantic_regex_is_rejected_during_loading(tmp_path):
    path=tmp_path/'cases.json'
    path.write_text(json.dumps({'cases':[{'case_id':'regex','format':'json','profile':'core','fixture':'json_unicode','expected_status':['passed'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000,'required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'determinism':{'normalized_reruns_must_match':True},'required_list_markdown_patterns':['[']}]}))
    with pytest.raises(AssertionError, match='invalid required_list_markdown_patterns regex'):
        load_cases(path)

def test_empty_required_ancestor_type_is_rejected_during_loading(tmp_path):
    path=tmp_path/'cases.json'
    path.write_text(json.dumps({'cases':[{'case_id':'ancestor','format':'json','profile':'core','fixture':'json_unicode','expected_status':['passed'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000,'required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'determinism':{'normalized_reruns_must_match':True},'required_element_ancestor_types':{'table':['']}}]}))
    with pytest.raises(AssertionError): load_cases(path)

def test_invalid_ocr_contract_is_rejected_during_loading(tmp_path):
    import json
    path=tmp_path/'cases.json'
    path.write_text(json.dumps({'cases':[{'case_id':'ocr','format':'pdf','profile':'core','fixture':'pdf_ocr_text','expected_status':['passed'],'table_count':{'min':0},'asset_count':{'min':0},'max_chunk_chars':2000,'required_warning_codes':[],'allowed_warning_codes':[],'forbidden_warning_codes':[],'determinism':{'normalized_reruns_must_match':True},'required_ocr':{'min_accepted_tables':'one'}}]}))
    with pytest.raises(AssertionError): load_cases(path)
