import hashlib, json, shutil, sys, zipfile
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_skill_package import build
from validate_skill_package import validate

ROOT=Path(__file__).resolve().parents[1]
def test_package_build_is_reproducible_and_valid(tmp_path):
    first=build(tmp_path/'a', verify=True); second=build(tmp_path/'b', verify=True)
    a=tmp_path/'a'/first['archive_name']; b=tmp_path/'b'/second['archive_name']
    assert hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()
    assert first['entries']==second['entries']
    with zipfile.ZipFile(a) as z:
        names=z.namelist(); prefix=f"universal-file-to-markdown-{first['skill_version']}/"
        assert prefix+'VERSION' in names and prefix+'SKILL.md' in names
        assert any(n.startswith(prefix+'schemas/') for n in names)
        assert all(not any(x in n for x in ('.venv/', '.qualification/', '__pycache__/', '.git/', 'dist/')) for n in names)
    assert validate(a)['status']=='passed'

def test_validator_rejects_unsafe_duplicate_or_wrong_version(tmp_path):
    data=(ROOT/'SKILL.md').read_bytes()
    for label,names in [('traversal',['universal-file-to-markdown-1.7.0-rc1/../bad']), ('absolute',['/bad']), ('duplicate',['universal-file-to-markdown-1.7.0-rc1/SKILL.md']*2), ('wrong',['universal-file-to-markdown-wrong/SKILL.md'])]:
        archive=tmp_path/f'{label}.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name in names:z.writestr(name,data)
        with pytest.raises(ValueError): validate(archive)

def test_validator_rejects_hash_mismatch(tmp_path):
    result=build(tmp_path); archive=tmp_path/result['archive_name']; archive.with_suffix('.sha256').write_text('0'*64+'  x\n')
    with pytest.raises(ValueError, match='SHA-256'): validate(archive)

from qualify_release_package import safe_extract, make_venv

def test_safe_extract_rejects_traversal_before_writing(tmp_path):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('../escaped.txt', b'bad')
    destination = tmp_path / 'extract'
    with pytest.raises(ValueError, match='unsafe extraction path'):
        safe_extract(archive, destination)
    assert not (tmp_path / 'escaped.txt').exists()

def test_make_venv_uses_requested_interpreter_and_records_version(tmp_path, monkeypatch):
    calls = []
    class Result:
        returncode = 0; stdout = 'Python 3.11.9\n'; stderr = ''
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ['-m', 'venv']:
            target = Path(command[-1]); (target / 'bin').mkdir(parents=True); (target / 'bin' / 'python').touch()
        return Result()
    monkeypatch.setattr('qualify_release_package.subprocess.run', fake_run)
    results = {}
    python = make_venv('/requested/python', tmp_path / 'venv', results)
    assert calls[0] == ['/requested/python', '-m', 'venv', '--clear', str(tmp_path / 'venv')]
    assert python.name == 'python'
    assert results['effective_python']['version'] == 'Python 3.11.9'

def test_make_venv_fails_for_unavailable_requested_interpreter(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_venv(str(tmp_path / 'missing-python'), tmp_path / 'venv', {})

def test_qualification_requires_all_conversion_and_bundle_steps(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    calls = []
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def successful_run(command, cwd, results, name):
        calls.append(name); results[name] = {'status': 'passed'}
    monkeypatch.setattr(qualifier, 'run', successful_run)
    qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})
    assert calls == [item for ext in ('docx','xlsx','pptx','pdf','png','csv','json','html') for item in (f'convert_{ext}', f'bundle_{ext}')]

def test_conversion_failure_prevents_remaining_bundle_validation(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def failing_run(command, cwd, results, name):
        if name == 'convert_docx': raise RuntimeError('conversion failed')
    monkeypatch.setattr(qualifier, 'run', failing_run)
    with pytest.raises(RuntimeError, match='conversion failed'):
        qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})

def test_bundle_validation_failure_propagates(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def failing_run(command, cwd, results, name):
        if name == 'bundle_docx': raise RuntimeError('bundle validation failed')
    monkeypatch.setattr(qualifier, 'run', failing_run)
    with pytest.raises(RuntimeError, match='bundle validation failed'):
        qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})
