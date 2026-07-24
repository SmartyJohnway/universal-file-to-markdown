import hashlib, json, shutil, sys, zipfile
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_skill_package import build
from validate_skill_package import validate
from skill_package_common import read_version

ROOT = Path(__file__).resolve().parents[1]

def test_release_package_build_is_reproducible_and_valid(tmp_path):
    first = build(tmp_path / 'a', profile='release', verify=True)
    second = build(tmp_path / 'b', profile='release', verify=True)
    a = tmp_path / 'a' / first['archive_name']
    b = tmp_path / 'b' / second['archive_name']
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    assert first['entries'] == second['entries']
    with zipfile.ZipFile(a) as z:
        names = z.namelist()
        prefix = f"universal-file-to-markdown-{first['skill_version']}/"
        assert prefix + 'VERSION' in names and prefix + 'SKILL.md' in names
        assert any(n.startswith(prefix + 'schemas/') for n in names)
        assert all(not any(x in n for x in ('.venv/', '.qualification/', '__pycache__/', '.git/', 'dist/')) for n in names)
    assert validate(a, profile='release')['status'] == 'passed'

def test_agent_skill_package_build_is_reproducible_and_valid(tmp_path):
    first = build(tmp_path / 'a', profile='agent-skill', verify=True)
    second = build(tmp_path / 'b', profile='agent-skill', verify=True)
    a = tmp_path / 'a' / first['archive_name']
    b = tmp_path / 'b' / second['archive_name']
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    assert first['entries'] == second['entries']
    with zipfile.ZipFile(a) as z:
        names = z.namelist()
        prefix = "universal-file-to-markdown/"
        assert prefix + 'VERSION' in names and prefix + 'SKILL.md' in names
        # Agent skill profile excludes tests and docs
        assert not any(n.startswith(prefix + 'tests/') for n in names)
        assert not any(n.startswith(prefix + 'docs/') for n in names)
        assert not any(n.startswith(prefix + 'package-manifest') for n in names)
    assert validate(a, profile='agent-skill')['status'] == 'passed'

def test_agent_skill_validator_rejects_excluded_files_or_invalid_frontmatter(tmp_path):
    result = build(tmp_path / 'build', profile='agent-skill')
    archive = tmp_path / 'build' / result['archive_name']
    prefix = "universal-file-to-markdown/"
    bad_archive = tmp_path / 'bad_frontmatter.zip'
    with zipfile.ZipFile(archive) as zin, zipfile.ZipFile(bad_archive, 'w') as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == prefix + 'SKILL.md':
                content = b'invalid frontmatter without fences'
            info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            info.create_system = item.create_system
            info.external_attr = item.external_attr
            zout.writestr(info, content)
    with pytest.raises(ValueError, match='YAML frontmatter'):
        validate(bad_archive, profile='agent-skill')

def test_agent_skill_validator_rejects_unresolved_markdown_links(tmp_path):
    result = build(tmp_path / 'build', profile='agent-skill')
    archive = tmp_path / 'build' / result['archive_name']
    prefix = "universal-file-to-markdown/"
    bad_archive = tmp_path / 'bad_link.zip'
    with zipfile.ZipFile(archive) as zin, zipfile.ZipFile(bad_archive, 'w') as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == prefix + 'SKILL.md':
                content = content + b"\n[broken link](missing_file.md)\n"
            info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            info.create_system = item.create_system
            info.external_attr = item.external_attr
            zout.writestr(info, content)
    with pytest.raises(ValueError, match='unresolved link'):
        validate(bad_archive, profile='agent-skill')

def test_validator_rejects_unsafe_duplicate_or_wrong_version(tmp_path):
    version = read_version(ROOT)
    prefix = f"universal-file-to-markdown-{version}/"
    data = (ROOT / 'SKILL.md').read_bytes()
    for label, names in [('traversal', [prefix + '../bad']), ('absolute', ['/bad']), ('duplicate', [prefix + 'SKILL.md'] * 2), ('wrong', ['universal-file-to-markdown-wrong/SKILL.md'])]:
        archive = tmp_path / f'{label}.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for name in names:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, data)
        with pytest.raises(ValueError):
            validate(archive, profile='release')

def test_validator_rejects_hash_mismatch(tmp_path):
    result = build(tmp_path, profile='release')
    archive = tmp_path / result['archive_name']
    archive.with_suffix('.sha256').write_text('0' * 64 + '  x\n')
    with pytest.raises(ValueError, match='SHA-256'):
        validate(archive, profile='release')

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
        returncode = 0
        stdout = 'Python 3.11.9\n'
        stderr = ''
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ['-m', 'venv']:
            target = Path(command[-1])
            bindir = target / ('Scripts' if sys.platform == 'win32' else 'bin')
            pyexe = bindir / ('python.exe' if sys.platform == 'win32' else 'python')
            bindir.mkdir(parents=True, exist_ok=True)
            pyexe.touch()
        return Result()
    monkeypatch.setattr('qualify_release_package.subprocess.run', fake_run)
    results = {}
    python = make_venv('/requested/python', tmp_path / 'venv', results)
    assert calls[0] == ['/requested/python', '-m', 'venv', '--clear', str(tmp_path / 'venv')]
    assert python.name in ('python', 'python.exe')
    assert results['effective_python']['version'] == 'Python 3.11.9'

def test_make_venv_fails_for_unavailable_requested_interpreter(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_venv(str(tmp_path / 'missing-python'), tmp_path / 'venv', {})

def test_qualification_requires_all_conversion_and_bundle_steps(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    calls = []
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def successful_run(command, cwd, results, name):
        calls.append(name)
        results[name] = {'status': 'passed'}
    monkeypatch.setattr(qualifier, 'run', successful_run)
    qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})
    assert calls == [item for ext in ('docx', 'xlsx', 'pptx', 'pdf', 'png', 'csv', 'json', 'html') for item in (f'convert_{ext}', f'bundle_{ext}')]

def test_conversion_failure_prevents_remaining_bundle_validation(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def failing_run(command, cwd, results, name):
        if name == 'convert_docx':
            raise RuntimeError('conversion failed')
    monkeypatch.setattr(qualifier, 'run', failing_run)
    with pytest.raises(RuntimeError, match='conversion failed'):
        qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})

def test_bundle_validation_failure_propagates(tmp_path, monkeypatch):
    import qualify_release_package as qualifier
    monkeypatch.setattr(qualifier, 'make_fixtures', lambda directory, python: None)
    def failing_run(command, cwd, results, name):
        if name == 'bundle_docx':
            raise RuntimeError('bundle validation failed')
    monkeypatch.setattr(qualifier, 'run', failing_run)
    with pytest.raises(RuntimeError, match='bundle validation failed'):
        qualifier.qualify_conversions(tmp_path, Path('/python'), tmp_path, {})
