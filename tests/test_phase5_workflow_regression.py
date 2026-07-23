import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from run_cross_format_regression import _workflow_errors, load_workflow_cases


def _case():
    return load_workflow_cases()[0]


def _bundle(tmp_path, *, readable=True, request=True, report=True, manifest=True, statuses=True, request_values=None):
    if manifest:
        (tmp_path / 'manifest.json').write_text(json.dumps({'source_sha256': 'a' * 64}))
    (tmp_path / 'document.json').write_text(json.dumps({'elements': []}))
    (tmp_path / 'chunks.jsonl').write_text('')
    (tmp_path / 'tables').mkdir()
    (tmp_path / 'tables' / 'index.json').write_text('[]')
    report_payload = {'status': 'passed', 'bundle_validation': {'status': 'passed'}, 'warnings': []}
    if statuses:
        report_payload.update({'ai_review_request_status': 'generated', 'ai_review_status': 'not_provided', 'readable_projection_status': 'deterministic_only'})
    if report:
        (tmp_path / 'conversion-report.json').write_text(json.dumps(report_payload))
    if request:
        values = {'schema_version': '1.0', 'request_id': 'ai-review-request-' + 'a' * 16, 'source_sha256': 'a' * 64,
                  'skill_version': '1.7.0-dev', 'canonical_bundle_fingerprint': 'wrong', 'review_scope': 'readable_projection_only',
                  'instructions': {'preserve_facts': True, 'preserve_numbers': True, 'preserve_urls': True, 'preserve_table_ids': True, 'preserve_source_order': True, 'do_not_modify_canonical': True},
                  'reason_codes': ['HTML_MERGED_TABLE_COMPLEX'], 'targets': [], 'allowed_operations': [], 'prohibited_operations': [], 'truncation': []}
        values.update(request_values or {})
        (tmp_path / 'ai-review-request.json').write_text(json.dumps(values))
    if readable:
        (tmp_path / 'document-readable.md').write_text('# Trading\n## Rates\n| Kind | Rates | Rates |\n| Stock | 1 | Two<br>- detail |')


def test_workflow_manifest_declares_one_core_case():
    case = _case()
    assert case['case_id'] == 'phase5-readable-projection-host-review'
    assert case['workflow'] == 'readable_projection_host_review'


def test_missing_readable_projection_is_structured(tmp_path, monkeypatch):
    _bundle(tmp_path, readable=False)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'READABLE_PROJECTION_MISSING' in _workflow_errors(_case(), tmp_path, 0)


def test_missing_review_request_is_structured(tmp_path, monkeypatch):
    _bundle(tmp_path, request=False)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'HOST_REVIEW_REQUEST_MISSING' in _workflow_errors(_case(), tmp_path, 0)


def test_invalid_status_is_structured(tmp_path, monkeypatch):
    _bundle(tmp_path, statuses=False)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'WORKFLOW_STATUS_MISMATCH' in _workflow_errors(_case(), tmp_path, 0)


def test_broken_request_reference_is_structured(tmp_path, monkeypatch):
    _bundle(tmp_path)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'WORKFLOW_REFERENCE_ERROR' in _workflow_errors(_case(), tmp_path, 0)


def test_semantic_rerun_mismatch_is_structured(tmp_path, monkeypatch):
    import run_cross_format_regression as runner
    source = tmp_path / 'source.html'; source.write_text('<html></html>')
    monkeypatch.setattr(runner, 'generate', lambda *_: source)
    monkeypatch.setattr(runner, '_workflow_errors', lambda *_: [])
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'returncode': 0})())
    models = iter([{'readable_projection': 'first'}, {'readable_projection': 'second'}])
    monkeypatch.setattr(runner, 'normalize_bundle', lambda _: next(models))
    result = runner.run_workflow_case(_case(), tmp_path, 2, False)
    assert result['status'] == 'failed'
    assert result['reason_codes'] == ['WORKFLOW_NONDETERMINISTIC_RERUN']


def test_review_step_failure_has_its_own_reason(tmp_path, monkeypatch):
    _bundle(tmp_path)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'WORKFLOW_REVIEW_REQUEST_FAILED' in _workflow_errors(_case(), tmp_path, 0, 1, 0)
    assert 'WORKFLOW_ROUTER_FAILED' not in _workflow_errors(_case(), tmp_path, 0, 1, 0)


def test_projection_step_failure_has_its_own_reason(tmp_path, monkeypatch):
    _bundle(tmp_path)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    assert 'WORKFLOW_READABLE_PROJECTION_FAILED' in _workflow_errors(_case(), tmp_path, 0, 0, 1)
    assert 'WORKFLOW_ROUTER_FAILED' not in _workflow_errors(_case(), tmp_path, 0, 0, 1)


@pytest.mark.parametrize(('artifact', 'bundle_args', 'code'), [
    ('conversion-report.json', {'report': False}, 'WORKFLOW_REPORT_MISSING'),
    ('manifest.json', {'manifest': False}, 'WORKFLOW_MANIFEST_MISSING'),
    ('ai-review-request.json', {'request': False}, 'HOST_REVIEW_REQUEST_MISSING'),
    ('document-readable.md', {'readable': False}, 'READABLE_PROJECTION_MISSING'),
])
def test_missing_workflow_artifact_is_structured(tmp_path, monkeypatch, artifact, bundle_args, code):
    _bundle(tmp_path, **bundle_args)
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    errors = _workflow_errors(_case(), tmp_path, 0)
    assert code in errors


@pytest.mark.parametrize(('artifact', 'code'), [
    ('conversion-report.json', 'WORKFLOW_REPORT_MALFORMED'),
    ('manifest.json', 'WORKFLOW_MANIFEST_MALFORMED'),
    ('ai-review-request.json', 'WORKFLOW_REQUEST_MALFORMED'),
])
def test_malformed_workflow_json_is_structured(tmp_path, monkeypatch, artifact, code):
    _bundle(tmp_path)
    (tmp_path / artifact).write_text('{not json')
    monkeypatch.setattr('validate_bundle.validate_bundle', lambda _: {'status': 'passed'})
    errors = _workflow_errors(_case(), tmp_path, 0)
    assert code in errors


@pytest.mark.parametrize(('artifact', 'code'), [
    ('conversion-report.json', 'WORKFLOW_REPORT_MALFORMED'),
    ('manifest.json', 'WORKFLOW_MANIFEST_MALFORMED'),
])
def test_real_validator_malformed_artifact_remains_structured(tmp_path, artifact, code):
    """The production validator must not prevent workflow-specific diagnosis."""
    _bundle(tmp_path)
    (tmp_path / artifact).write_text('{not json')
    errors = _workflow_errors(_case(), tmp_path, 0)
    assert {'BUNDLE_VALIDATION_FAILED', code} <= set(errors)


@pytest.mark.parametrize(('artifact', 'code'), [
    ('conversion-report.json', 'WORKFLOW_REPORT_MALFORMED'),
    ('manifest.json', 'WORKFLOW_MANIFEST_MALFORMED'),
])
def test_run_workflow_case_survives_real_validator_malformed_artifact(tmp_path, monkeypatch, artifact, code):
    import run_cross_format_regression as runner
    source = tmp_path / 'source.html'; source.write_text('<html></html>')
    monkeypatch.setattr(runner, 'generate', lambda *_: source)
    def fake_run(args, **kwargs):
        if str(args[1]).endswith('router.py'):
            bundle = Path(args[args.index('--output') + 1])
            _bundle(bundle)
            (bundle / artifact).write_text('{not json')
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(runner.subprocess, 'run', fake_run)
    result = runner.run_workflow_case(_case(), tmp_path, 1, False)
    assert result['status'] == 'failed'
    assert {'BUNDLE_VALIDATION_FAILED', code} <= set(result['reason_codes'])
