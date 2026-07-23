import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cross_format_regression import fingerprint
def test_same_normalized_bundle_has_same_fingerprint(): assert fingerprint({'a':1}) == fingerprint({'a':1})
def test_canonical_content_change_changes_fingerprint(): assert fingerprint({'a':1})['bundle_fingerprint'] != fingerprint({'a':2})['bundle_fingerprint']
