import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))


def test_environment_manifest_declares_ocr_engine_profile(monkeypatch):
    import regression_environment
    monkeypatch.setattr(regression_environment.shutil, 'which', lambda name: '/tool' if name == 'tesseract' else None)
    manifest = regression_environment.environment_manifest()
    assert manifest['ocr_engine_profile'] == 'rapidocr+tesseract-fallback'
