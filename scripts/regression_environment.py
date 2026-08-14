"""Sanitized environment evidence for regression runs."""
import importlib, importlib.metadata, platform, shutil
from pathlib import Path
from cross_format_regression import stable_bytes
import hashlib
from packaging.specifiers import SpecifierSet

DECLARED={"pymupdf":">=1.26.4,<1.27", "rapidocr-onnxruntime":">=1.4,<2", "openpyxl":">=3.1,<3.2", "python-docx":">=1.2,<1.3", "python-pptx":">=1.0,<1.1"}
def environment_manifest(profile="core-no-pandoc"):
    dependencies={}
    for name, declared in DECLARED.items():
        module={"pymupdf":"fitz", "python-docx":"docx", "python-pptx":"pptx", "rapidocr-onnxruntime":"rapidocr_onnxruntime"}.get(name,name.replace("-","_"))
        try:
            installed=importlib.metadata.version(name); satisfied=installed in SpecifierSet(declared)
            try: importlib.import_module(module); imported="passed"
            except Exception as exc: imported="failed:"+type(exc).__name__
        except importlib.metadata.PackageNotFoundError: installed=None; imported="failed"; satisfied=False
        status="declared" if satisfied else "unavailable"
        dependencies[name]={"declared":declared,"installed":installed,"requirement_satisfied":satisfied,"import_status":imported,"status":status}
    tools={name:{"available":bool(shutil.which(name))} for name in ("pandoc","tesseract")}
    result={"schema_version":"1.0","python":{"version":platform.python_version(),"implementation":platform.python_implementation()},"platform":{"system":platform.system(),"machine":platform.machine()},"profile":profile,"dependencies":dependencies,"system_tools":tools,
            "ocr_engine_profile":"rapidocr+tesseract-fallback" if tools["tesseract"]["available"] else "rapidocr-only"}
    result["system_tools"]["libGL.so.1"]={"available":bool(shutil.which("ldconfig")) and "libGL.so.1" in __import__("subprocess").run(["ldconfig","-p"],capture_output=True,text=True).stdout}
    result["environment_fingerprint"]=hashlib.sha256(stable_bytes(result)).hexdigest(); return result
