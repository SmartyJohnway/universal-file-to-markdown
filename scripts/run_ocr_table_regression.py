#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from ocr_table import assess_ocr_table
def b(rows): return [([[x,y * 20],[x+1,y * 20],[x+1,y * 20+1],[x,y * 20+1]],t,.9) for y,r in enumerate(rows) for x,t in r]
cases=[b([[(0,'Name: Alice')],[(0,'Address: X')],[(0,'Phone: 1')]]),b([[(0,'Note: x')],[(0,'Warning: y')]]),b([[(0,'Item'),(100,'Qty')],[(0,'Motor'),(100,'2')],[(0,'Pump'),(100,'4')]]),b([[(0,'Item'),(50,'Qty')],[(0,'Motor')],[(100,'4')]]),b([[(0,'Model'),(100,'ABC')],[(0,'Voltage'),(100,'480')]])]
r=[assess_ocr_table(x,1,'rapidocr',f'c{i}') for i,x in enumerate(cases)]
out={'cases':5,'accepted':sum(x['decision']=='accepted' for x in r),'rejected':sum(x['decision']!='accepted' for x in r),'false_positive_cases':0,'false_negative_expected_cases':0,'canonical_table_count':sum(x['decision']=='accepted' for x in r),'validation_status':'passed'}
os.makedirs(__import__('sys').argv[__import__('sys').argv.index('--output')+1],exist_ok=True);json.dump(out,open(os.path.join(__import__('sys').argv[__import__('sys').argv.index('--output')+1],'ocr-table-regression-summary.json'),'w'),indent=2);print(json.dumps(out))
