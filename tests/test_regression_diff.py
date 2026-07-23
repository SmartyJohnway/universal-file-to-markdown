import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cross_format_regression import diff_models
def test_element_content_change_is_reported():
    assert any(x['category']=='content_changed' for x in diff_models({'document':{'x':'a'}},{'document':{'x':'b'}}))
def test_diff_excerpt_is_bounded(): assert len(diff_models({'document':{'x':'a'*999}},{'document':{'x':'b'*999}})[0]['before']) <= 240
def test_warning_changes_are_classified():
    changes=diff_models({'report_contract':{'warnings':[{'code':'OLD'}]}},{'report_contract':{'warnings':[{'code':'NEW'}]}})
    assert {item['category'] for item in changes} >= {'warning_added','warning_removed'}
