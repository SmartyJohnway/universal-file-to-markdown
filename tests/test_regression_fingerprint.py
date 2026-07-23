import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cross_format_regression import fingerprint, semantically_equal
def test_same_normalized_bundle_has_same_fingerprint(): assert fingerprint({'a':1}) == fingerprint({'a':1})
def test_canonical_content_change_changes_fingerprint(): assert fingerprint({'a':1})['bundle_fingerprint'] != fingerprint({'a':2})['bundle_fingerprint']
def test_ocr_confidence_within_tolerance_is_semantically_equal(): assert semantically_equal({'engine':'rapidocr','confidence':0.9},{'engine':'rapidocr','confidence':0.9000005})
def test_ocr_confidence_outside_tolerance_fails(): assert not semantically_equal({'engine':'rapidocr','confidence':0.9},{'engine':'rapidocr','confidence':0.90001})
def test_non_ocr_confidence_is_exact(): assert not semantically_equal({'engine':'pdfplumber','confidence':0.9},{'engine':'pdfplumber','confidence':0.9000001})
def test_text_change_is_never_tolerated(): assert not semantically_equal({'engine':'rapidocr','confidence':0.9,'content':'a'},{'engine':'rapidocr','confidence':0.9000001,'content':'b'})
