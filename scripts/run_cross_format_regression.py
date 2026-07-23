#!/usr/bin/env python3
"""Run the declared, reproducible cross-format corpus through production router."""
import argparse, hashlib, json, shutil, subprocess, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from cross_format_regression import normalize_bundle, fingerprint, write_diff
from regression_environment import environment_manifest

ROOT=Path(__file__).resolve().parents[1]; MANIFEST=ROOT/'tests/cross_format/cases.json'; KNOWN={"docx_basic","docx_horizontal_merge","docx_vertical_merge","xlsx_merged","xlsx_two_blocks","xlsx_formula","pptx_text","pptx_table","pptx_picture","pptx_grouped","pdf_digital","csv_big5","json_unicode","html_complex"}; FORMATS={"docx","xlsx","pptx","pdf","csv","json","html"}
def load_cases(path=MANIFEST):
    data=json.loads(Path(path).read_text()); seen=set()
    for case in data['cases']:
        assert case['case_id'] not in seen, 'duplicate case_id'; seen.add(case['case_id'])
        assert case['format'] in FORMATS and case['profile'] in {'core','optional-pandoc'}
        assert case['fixture'] in KNOWN and case['expected_status']
        for key in ('table_count','asset_count'):
            value=case[key]; assert value.get('min',0)>=0 and value.get('max', value.get('min',0)) >= value.get('min',0)
        assert case['max_chunk_chars'] <= 2000 and all(len(x)==len(set(x)) for x in (case['required_warning_codes'],case['allowed_warning_codes'],case['forbidden_warning_codes']))
        assert case['determinism'] == {'normalized_reruns_must_match':True}
    return data['cases']
def generate(name, directory):
    directory.mkdir(parents=True,exist_ok=True)
    if name=='html_complex': return ROOT/'tests/fixtures/html/complex_tables.html'
    if name.startswith('docx'):
        from docx import Document
        d=Document(); p=d.add_paragraph(); p.add_run('bold').bold=True; p.add_run(' italic').italic=True
        if name!='docx_basic':
            t=d.add_table(rows=2,cols=2); a=t.cell(0,0); a.merge(t.cell(0,1) if name.endswith('horizontal_merge') else t.cell(1,0)); a.text='Merged'; t.cell(1,0).text='A';t.cell(1,1).text='B'
        p=directory/(name+'.docx');d.save(p);return p
    if name.startswith('xlsx'):
        import openpyxl
        w=openpyxl.Workbook();s=w.active;s['A1']='Header';s['B1']='Value';s['A2']='A';s['B2']=1
        if name=='xlsx_merged':s.merge_cells('A1:B1')
        if name=='xlsx_two_blocks':s['A5']='Second';s['B5']='Value';s['A6']='B';s['B6']=2
        if name=='xlsx_formula':s['C3']='=A2+B2'
        p=directory/(name+'.xlsx');w.save(p);return p
    if name.startswith('pptx'):
        from pptx import Presentation
        from pptx.util import Inches
        p=Presentation(); slide=p.slides.add_slide(p.slide_layouts[6])
        if name=='pptx_text': slide.shapes.add_textbox(Inches(1),Inches(1),Inches(4),Inches(2)).text_frame.text='Slide title\nBullet one'
        elif name=='pptx_picture':
            from PIL import Image
            image=directory/'pixel.png';Image.new('RGB',(4,4),'red').save(image);slide.shapes.add_picture(str(image),Inches(1),Inches(1),Inches(1),Inches(1))
        else:
            shape=slide.shapes.add_table(2,2,Inches(1),Inches(1),Inches(4),Inches(2)); shape.table.cell(0,0).text='Merged';shape.table.cell(0,0).merge(shape.table.cell(0,1));shape.table.cell(1,0).text='A';shape.table.cell(1,1).text='B'
        out=directory/(name+'.pptx');p.save(out);return out
    if name=='pdf_digital':
        from reportlab.pdfgen import canvas
        p=directory/'digital.pdf';c=canvas.Canvas(str(p));c.drawString(100,700,'Digital PDF Test 123');c.save();return p
    if name=='csv_big5':
        p=directory/'big5.csv';p.write_bytes('名稱,數量\n鋼管,10\n'.encode('big5'));return p
    if name=='json_unicode':
        p=directory/'unicode.json';p.write_text(json.dumps({'名稱':'繁體中文','items':['α','資料']},ensure_ascii=False));return p
def warning_codes(report): return {w.get('code') for w in report.get('warnings',[]) if w.get('code')}
def _safe_table_asset(tables_dir, value):
    """Resolve canonical table assets without permitting bundle traversal."""
    if not isinstance(value, str): return False
    candidate=(tables_dir/value).resolve()
    try: candidate.relative_to(tables_dir.resolve())
    except ValueError: return False
    return candidate.is_file()
def _table_index_errors(index_path, table_ids):
    try: entries=json.loads(index_path.read_text())
    except (OSError, json.JSONDecodeError): return ['TABLE_INDEX_MALFORMED']
    # Production table_export writes a list. Reject other shapes structurally,
    # rather than accidentally iterating mapping keys or crashing the runner.
    if not isinstance(entries,list): return ['TABLE_INDEX_MALFORMED']
    errors=[]
    for entry in entries:
        if not isinstance(entry,dict) or entry.get('id') not in table_ids: errors.append('REFERENCE_ERROR'); continue
        assets=entry.get('assets',{})
        if not isinstance(assets,dict) or any(not _safe_table_asset(index_path.parent,path) for path in assets.values()): errors.append('REFERENCE_ERROR')
    return errors
def assert_contract(case,bundle,router_rc):
    errors=[]
    if not (bundle/'conversion-report.json').exists() or not (bundle/'document.json').exists(): return ['ROUTER_BUNDLE_MISSING'], {}
    report=json.loads((bundle/'conversion-report.json').read_text()); doc=json.loads((bundle/'document.json').read_text())
    if router_rc or report.get('status') not in case['expected_status']: errors.append('STATUS_MISMATCH')
    if report.get('bundle_validation',{}).get('status') != case['expected_bundle_validation']: errors.append('BUNDLE_VALIDATION_FAILED')
    from validate_bundle import validate_bundle
    if validate_bundle(str(bundle)).get('status') != case['expected_bundle_validation']: errors.append('INDEPENDENT_BUNDLE_VALIDATION_FAILED')
    if case.get('expected_engine') and case['expected_engine'] not in str(report.get('engine','')): errors.append('ENGINE_MISMATCH')
    codes=warning_codes(report); required=set(case['required_warning_codes']); allowed=required|set(case['allowed_warning_codes'])
    if not required <= codes: errors.append('REQUIRED_WARNING_MISSING')
    if codes-allowed: errors.append('UNEXPECTED_WARNING')
    if codes & set(case['forbidden_warning_codes']): errors.append('FORBIDDEN_WARNING')
    types={e.get('type') for e in doc.get('elements',[])}
    if not set(case['required_element_types']) <= types: errors.append('ELEMENT_TYPE_MISSING')
    elements=doc.get('elements',[]); ids=[e.get('id') for e in elements]
    if len(ids)!=len(set(ids)) or any(not ident for ident in ids): errors.append('ELEMENT_ID_INVALID')
    idset=set(ids)
    for element in elements:
        locator=element.get('source_locator',{})
        if not all(field in locator for field in case['required_locator_fields']): errors.append('LOCATOR_MISSING')
        if element.get('parent_id') and element['parent_id'] not in idset: errors.append('REFERENCE_ERROR')
        if any(child not in idset for child in element.get('children',element.get('child_ids',[]))): errors.append('REFERENCE_ERROR')
    tables=list((bundle/'tables').glob('*.json')) if (bundle/'tables').exists() else []; tables=[p for p in tables if p.name!='index.json']
    table_ids={path.stem for path in tables}
    index_path=bundle/'tables'/'index.json'
    if index_path.exists():
        errors.extend(_table_index_errors(index_path,table_ids))
    lo,hi=case['table_count'].get('min',0),case['table_count'].get('max',10**9)
    if not lo<=len(tables)<=hi: errors.append('TABLE_COUNT')
    assets=list((bundle/'assets').rglob('*')) if (bundle/'assets').exists() else []
    asset_count=len([x for x in assets if x.is_file()])
    if asset_count<case['asset_count'].get('min',0) or asset_count>case['asset_count'].get('max',10**9): errors.append('ASSET_COUNT')
    chunks=[json.loads(x) for x in (bundle/'chunks.jsonl').read_text().splitlines() if x] if (bundle/'chunks.jsonl').exists() else []
    for chunk in chunks:
        if any(value not in idset for value in chunk.get('element_ids',[])) or any(value not in table_ids for value in chunk.get('table_ids',[])): errors.append('REFERENCE_ERROR')
    if any(len(c.get('content',''))>case['max_chunk_chars'] for c in chunks): errors.append('CHUNK_LIMIT')
    return errors, report
def run_case(case, root, reruns, keep):
    if case['profile']=='optional-pandoc' and not shutil.which('pandoc'): return {'case_id':case['case_id'],'format':case['format'],'status':'skipped','skip_reason':'pandoc binary unavailable'}
    source=generate(case['fixture'],root/'sources'/case['case_id']); source_sha=hashlib.sha256(Path(source).read_bytes()).hexdigest(); models=[]; fps=[]; errors=[]; bundles=[]
    for run in range(reruns):
        bundle=root/'work'/case['case_id']/str(run); bundle.mkdir(parents=True,exist_ok=True)
        args=[sys.executable,str(ROOT/'scripts/router.py'),str(source),'--output',str(bundle)]
        if case['format']=='html': args += ['--source-url','https://example.test/page/index.html']
        process=subprocess.run(args,text=True,capture_output=True); current,report=assert_contract(case,bundle,process.returncode); errors += current; models.append(normalize_bundle(bundle));fps.append(fingerprint(models[-1]));bundles.append(bundle)
    rerun_mismatch=len(set(fp['bundle_fingerprint'] for fp in fps))>1
    if rerun_mismatch: errors.append('CROSS_FORMAT_NONDETERMINISTIC_RERUN');write_diff(models[0],models[1],root/'diffs',case['case_id'])
    status='passed' if not errors else 'failed'; result={'case_id':case['case_id'],'format':case['format'],'status':status,'reason_codes':sorted(set(errors)),'fixture_recipe_id':case['fixture'],'fixture_description':'programmatically generated regression source','generator_dependency':'repository test dependencies','generated_source_sha256':source_sha,'fingerprints':fps,'normalized_snapshot':models[0]}
    if status!='passed' or keep: result['bundles']=[str(p) for p in bundles]
    return result
def main(args):
    if args.update_baseline and not args.confirm_baseline_update: raise SystemExit('--update-baseline requires --confirm-baseline-update')
    cases=[c for c in load_cases() if c['profile']==args.profile and (not args.case or c['case_id']==args.case) and (not args.format or c['format']==args.format)]
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True);env=environment_manifest('pandoc-enabled' if args.profile=='optional-pandoc' else 'core-no-pandoc');(output/'environment-manifest.json').write_text(json.dumps(env,indent=2)+'\n')
    results=[run_case(c,output,args.reruns,args.keep_bundles) for c in cases]
    baseline_dir=Path(args.baseline_dir); baseline_path=baseline_dir/'fingerprints.json'; baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    baseline_mismatches=[]
    for result in results:
        current=result.get('fingerprints',[{}])[0].get('bundle_fingerprint')
        expected=baseline.get(result['case_id'])
        if result['status']=='passed' and expected and expected != current:
            result['reason_codes'].append('BASELINE_FINGERPRINT_MISMATCH'); baseline_mismatches.append(result['case_id'])
            if not args.update_baseline: result['status']='failed'
            snapshot=baseline_dir/(result['case_id']+'.normalized.json')
            if snapshot.exists(): write_diff(json.loads(snapshot.read_text()),result['normalized_snapshot'],output/'diffs',result['case_id']+'-baseline')
    if args.update_baseline:
        if any(r['status']!='passed' for r in results): raise SystemExit('baseline update refused: all selected cases must pass contract validation')
        updated={r['case_id']:r['fingerprints'][0]['bundle_fingerprint'] for r in results}
        merged=dict(baseline); merged.update(updated)
        baseline_path.parent.mkdir(parents=True,exist_ok=True)
        report={'old':baseline,'new':merged,'changed':[key for key in updated if baseline.get(key)!=updated[key]],'preserved':[key for key in baseline if key not in updated]}
        (output/'baseline-update-report.json').write_text(json.dumps(report,indent=2)+'\n'); baseline_path.write_text(json.dumps(merged,indent=2)+'\n')
        for result in results: (baseline_dir/(result['case_id']+'.normalized.json')).write_text(json.dumps(result['normalized_snapshot'],ensure_ascii=False,indent=2)+'\n')
    counts=Counter(r['status'] for r in results); formats=defaultdict(lambda:Counter())
    for r in results: formats[r['format']][r['status']]+=1
    summary={'schema_version':'1.0','task':'V1.7.0-DEV-PHASE-6-REPRODUCIBLE-CROSS-FORMAT-REGRESSION','profile':args.profile,'environment_profile':env['profile'],'case_count':len(results),'passed':counts['passed'],'failed':counts['failed'],'skipped':counts['skipped'],'formats':{k:dict(v) for k,v in formats.items()},'bundle_validation_failures':sum(any('BUNDLE_VALIDATION' in x for x in r.get('reason_codes',[])) for r in results),'unexpected_warning_cases':sum('UNEXPECTED_WARNING' in r.get('reason_codes',[]) for r in results),'chunk_limit_violations':sum('CHUNK_LIMIT' in r.get('reason_codes',[]) for r in results),'reference_errors':sum(any(x in r.get('reason_codes',[]) for x in ('REFERENCE_ERROR','ELEMENT_ID_INVALID','LOCATOR_MISSING','TABLE_INDEX_MALFORMED')) for r in results),'rerun_mismatches':sum('CROSS_FORMAT_NONDETERMINISTIC_RERUN' in r.get('reason_codes',[]) for r in results),'baseline_mismatches':len(baseline_mismatches),'normalized_determinism_status':'passed' if not any('CROSS_FORMAT_NONDETERMINISTIC_RERUN' in r.get('reason_codes',[]) for r in results) else 'failed','validation_status':'passed' if not counts['failed'] else 'failed','cases':results}
    public_results=[{k:v for k,v in result.items() if k!='normalized_snapshot'} for result in results]
    summary['cases']=public_results
    (output/'cross-format-regression-cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in public_results));(output/'artifact-fingerprints.json').write_text(json.dumps({r['case_id']:r.get('fingerprints',[]) for r in results},indent=2)+'\n');(output/'cross-format-regression-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));return 1 if counts['failed'] else 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--profile',default='core',choices=['core','optional-pandoc']);p.add_argument('--case');p.add_argument('--format');p.add_argument('--reruns',type=int,default=2);p.add_argument('--baseline-dir',default=str(ROOT/'tests/cross_format/baselines'));p.add_argument('--update-baseline',action='store_true');p.add_argument('--confirm-baseline-update',action='store_true');p.add_argument('--keep-bundles',action='store_true');a=p.parse_args();sys.exit(main(a))
