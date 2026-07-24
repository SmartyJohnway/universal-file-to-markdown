#!/usr/bin/env python3
"""Run a clean-venv smoke qualification using only an extracted skill package."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile, venv, zipfile
from pathlib import Path

def run(command, cwd, results, name, env=None):
    completed=subprocess.run(command, cwd=cwd, text=True, capture_output=True, env=env)
    results[name]={"status":"passed" if completed.returncode==0 else "failed", "command":command, "stdout":completed.stdout[-2000:], "stderr":completed.stderr[-2000:]}
    if completed.returncode: raise RuntimeError(f"{name} failed")

def make_fixtures(directory: Path, python: Path):
    script='''from pathlib import Path
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from reportlab.pdfgen.canvas import Canvas
from PIL import Image, ImageDraw
p=Path(".")
d=Document(); d.add_paragraph("Package DOCX"); d.save(p/"sample.docx")
w=Workbook(); w.active["A1"]="Package XLSX"; w.save(p/"sample.xlsx")
r=Presentation(); r.slides.add_slide(r.slide_layouts[1]).shapes.title.text="Package PPTX"; r.save(p/"sample.pptx")
c=Canvas(str(p/"sample.pdf")); c.drawString(72,720,"Package PDF"); c.save()
(p/"sample.csv").write_bytes("name,city\\n中文,台北\\n".encode("big5"))
(p/"sample.json").write_text('{"message":"你好，package"}', encoding="utf-8")
(p/"sample.html").write_text('<h1>Package HTML</h1><p>ready</p>', encoding="utf-8")
image=Image.new("RGB",(300,100),"white"); ImageDraw.Draw(image).text((20,30),"PACKAGE OCR",fill="black"); image.save(p/"sample.png")
'''
    subprocess.run([str(python),"-c",script],cwd=directory,check=True)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--archive",type=Path,required=True); parser.add_argument("--output",type=Path,default=Path('.qualification/package-smoke')); parser.add_argument("--python",default=sys.executable); args=parser.parse_args()
    archive=args.archive.resolve(); output=args.output.resolve(); shutil.rmtree(output,ignore_errors=True); output.mkdir(parents=True)
    results={"archive":archive.name,"status":"failed","steps":{}}
    try:
        # Validate before extraction, using copied source manifest inside the archive after extraction.
        with zipfile.ZipFile(archive) as z:z.extractall(output/'extract')
        package=next((output/'extract').iterdir()); source_manifest=package/'package-manifest.json'
        run([sys.executable,str(package/'scripts/validate_skill_package.py'),str(archive),'--source-manifest',str(source_manifest)],package,results['steps'],'archive_validation')
        env_dir=output/'venv'; venv.EnvBuilder(with_pip=True,clear=True).create(env_dir); python=env_dir/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        run([str(python),'-m','pip','install','--upgrade','pip','setuptools','wheel'],package,results['steps'],'pip_bootstrap')
        run([str(python),'-m','pip','install','-r','requirements.txt'],package,results['steps'],'requirements_install')
        run([str(python),'scripts/capability_probe.py','--json'],package,results['steps'],'capability_probe')
        fixtures=output/'fixtures';fixtures.mkdir();make_fixtures(fixtures,python)
        extensions=['docx','xlsx','pptx','pdf','csv','json','html','png']
        for extension in extensions:
            bundle=output/'bundles'/extension
            run([str(python),str(package/'scripts/router.py'),str(fixtures/f'sample.{extension}'),'--output',str(bundle)],package,results['steps'],f'convert_{extension}')
            run([str(python),str(package/'scripts/validate_bundle.py'),str(bundle)],package,results['steps'],f'bundle_{extension}')
        results['status']='passed'
    except Exception as exc: results['error']=str(exc)
    print(json.dumps(results,ensure_ascii=False,indent=2)); return 0 if results['status']=='passed' else 1
if __name__=='__main__': raise SystemExit(main())
