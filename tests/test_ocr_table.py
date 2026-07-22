import sys
sys.path.insert(0, 'scripts')
from ocr_table import assess_ocr_table

def boxes(rows):
    return [([[x,y * 20],[x+10,y * 20],[x+10,y * 20+8],[x,y * 20+8]], text, .9) for y, row in enumerate(rows) for x, text in row]

def test_label_value_lines_are_not_table():
    c=assess_ocr_table(boxes([[(0,'Name: Alice')],[(0,'Department: Engineering')],[(0,'Status: Active')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text' and 'OCR_TABLE_KEY_VALUE_PATTERN' in c['reason_codes']
def test_colon_sentences_are_not_table():
    c=assess_ocr_table(boxes([[(0,'Note: important information.')],[(0,'Warning: do not disconnect power.')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text'
def test_clear_aligned_table_is_accepted():
    c=assess_ocr_table(boxes([[(0,'Item'),(100,'Quantity')],[(0,'Motor'),(100,'2')],[(0,'Pump'),(100,'4')],[(0,'Valve'),(100,'12')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'accepted' and c['confidence'] >= .6 and c['signals']['column_count'] == 2
def test_two_sparse_rows_rejected():
    c=assess_ocr_table(boxes([[(0,'Model'),(100,'ABC-100')],[(0,'Voltage'),(100,'480 V')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text' and 'OCR_TABLE_INSUFFICIENT_ROWS' in c['reason_codes']
def test_irregular_columns_rejected():
    c=assess_ocr_table(boxes([[(0,'Item'),(60,'Qty'),(120,'Price')],[(0,'Motor'),(60,'2')],[(0,'Pump'),(120,'4'),(180,'800')],[(0,'Remark: spare unit')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text'
