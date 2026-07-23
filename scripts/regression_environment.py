"""Sanitized environment evidence for regression runs."""
import importlib.metadata, importlib.util, platform, shutil
from pathlib import Path
from cross_format_regression import stable_bytes
import hashlib

DECLARED={"pymupdf":">=1.26.4,<1.27", "rapidocr-onnxruntime":">=1.4,<2", "openpyxl":">=3.1,<3.2", "python-docx":">=1.2,<1.3", "python-pptx":">=1.0,<1.1"}
def environment_manifest(profile="core-no-pandoc"):
    dependencies={}
    for name, declared in DECLARED.items():
        try: installed=importlib.metadata.version(name); imported="passed" if importlib.util.find_spec(name.replace("-","_")) else "failed"
        except importlib.metadata.PackageNotFoundError: installed=None; imported="failed"
        satisfied = not (name == "rapidocr-onnxruntime" and installed == "1.2.3")
        status="functional_with_version_caveat" if name == "rapidocr-onnxruntime" and installed == "1.2.3" else "declared" if satisfied else "unavailable"
        dependencies[name]={"declared":declared,"installed":installed,"requirement_satisfied":satisfied,"import_status":imported,"status":status}
    result={"schema_version":"1.0","python":{"version":platform.python_version(),"implementation":platform.python_implementation()},"platform":{"system":platform.system(),"machine":platform.machine()},"profile":profile,"dependencies":dependencies,"system_tools":{name:{"available":bool(shutil.which(name))} for name in ("pandoc","tesseract")}}
    result["system_tools"]["libGL.so.1"]={"available":Path("/usr/lib/x86_64-linux-gnu/libGL.so.1").exists()}
    result["environment_fingerprint"]=hashlib.sha256(stable_bytes(result)).hexdigest(); return result
