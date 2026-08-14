import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cross_format_regression import normalize_bundle
def test_timestamps_are_removed_from_normalized_contract(tmp_path):
    (tmp_path/'document.md').write_text('x\r\n');(tmp_path/'document.json').write_text('{}');(tmp_path/'manifest.json').write_text('{"converted_at":"now","status":"passed"}');(tmp_path/'conversion-report.json').write_text('{"generated_at":"now","status":"passed"}')
    assert 'converted_at' not in normalize_bundle(tmp_path)['manifest_contract']
def test_original_bundle_is_not_modified(tmp_path):
    source=tmp_path/'document.md';source.write_text('a\r\n');(tmp_path/'document.json').write_text('{}'); before=source.read_bytes();normalize_bundle(tmp_path);assert source.read_bytes()==before

def test_semantic_normalization_excludes_source_provenance(tmp_path):
    (tmp_path/'document.md').write_text('same');(tmp_path/'document.json').write_text('{}')
    (tmp_path/'manifest.json').write_text('{"status":"passed","file_type":"xlsx","source_sha256":"bytes-differ"}')
    (tmp_path/'conversion-report.json').write_text('{"status":"passed","source_sha256":"bytes-differ"}')
    normalized=normalize_bundle(tmp_path)
    assert normalized['manifest_contract']=={'status':'passed','file_type':'xlsx'}
    assert 'source_sha256' not in str(normalized)
