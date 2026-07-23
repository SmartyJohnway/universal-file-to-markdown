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
def test_element_locator_and_heading_changes_are_classified():
    before={'document':{'elements':[{'id':'p1','type':'paragraph','content':'a','heading_path':['A'],'source_locator':{'page':1}}]}}
    after={'document':{'elements':[{'id':'p1','type':'heading','content':'b','heading_path':['B'],'source_locator':{'page':2}}]}}
    categories={item['category'] for item in diff_models(before,after)}
    assert {'element_type_changed','locator_changed','heading_path_changed','content_changed'} <= categories
def test_table_dimension_and_merge_changes_are_classified():
    before={'tables':[{'id':'t1','dimensions':{'rows':1,'columns':2},'cells':[{'row':0,'column':0,'rowspan':1,'colspan':1}]}]}; after={'tables':[{'id':'t1','dimensions':{'rows':2,'columns':2},'cells':[{'row':0,'column':0,'rowspan':2,'colspan':1}]}]}
    categories={item['category'] for item in diff_models(before,after)}
    assert {'table_dimensions_changed','merge_changed'} <= categories
def test_added_and_removed_entities_are_classified():
    categories={item['category'] for item in diff_models({'document':{'elements':[{'id':'old'}]},'tables':[{'id':'old-table'}]},{'document':{'elements':[{'id':'new'}]},'tables':[{'id':'new-table'}]})}
    assert {'element_added','element_removed','table_added','table_removed'} <= categories
def test_multi_table_specific_diff_does_not_hide_cell_diff():
    before={'tables':[{'id':'a','dimensions':{'rows':1,'columns':1},'cells':[]},{'id':'b','dimensions':{'rows':1,'columns':1},'cells':[{'row':0,'column':0,'value':'old'}]}]}
    after={'tables':[{'id':'a','dimensions':{'rows':2,'columns':1},'cells':[]},{'id':'b','dimensions':{'rows':1,'columns':1},'cells':[{'row':0,'column':0,'value':'new'}]}]}
    categories={item['category'] for item in diff_models(before,after)}
    assert {'table_dimensions_changed','table_cell_changed'} <= categories
