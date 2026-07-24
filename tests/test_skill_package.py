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
