"""Create a portable, verified archive of code, report, final data and figures.

No downloaded papers, installed dependencies, private helpers, caches or pilot
geometries are included. Failed numerical settings remain documented in notes
and in the final experiments' convergence records.
"""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parent
DEST=ROOT.parent/"textile_optical_simulation_bundle.zip"


def include(path):
    relative=path.relative_to(ROOT)
    parts=relative.parts
    if not path.is_file() or "__pycache__" in parts or any(x.startswith(".") for x in parts):
        return False
    if len(parts)==1:
        return path.suffix in (".py",".md",".txt")
    if parts[0] in ("textile_sim","tests","notes"):
        return path.suffix in (".py",".md")
    if parts[0]=="report":
        return len(parts)==2 and path.suffix in (".py",".pdf")
    if parts[0]=="references":
        return path.name in ("Mitsuba_hair.cpp","Mitsuba_LICENSE.txt","NOTICE.md")
    if parts[0]=="figures":
        return not path.name.startswith(("pilot_","corrected_"))
    if parts[0]=="data":
        return (not any(x in ("render_pilot","render_corrected","reproduction_logs") for x in parts)
                and "pilot" not in path.name)
    return False


def main():
    files=sorted(p for p in ROOT.rglob("*") if include(p))
    manifest={"package":"textile_optical_simulation_bundle", "date":"2026-10-10",
              "source_root":"textile_lab", "files":[]}
    for path in files:
        data=path.read_bytes()
        manifest["files"].append({"path":str(path.relative_to(ROOT)),"bytes":len(data),
                                  "sha256":hashlib.sha256(data).hexdigest()})
    with zipfile.ZipFile(DEST,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            archive.write(path,"textile_lab/"+str(path.relative_to(ROOT)))
        archive.writestr("textile_lab/PACKAGE_MANIFEST.json",json.dumps(manifest,indent=2))
    # Verify both archive CRC and content hashes; this is a distribution check,
    # not another run of the numerical tests.
    with zipfile.ZipFile(DEST) as archive:
        bad=archive.testzip()
        if bad:raise RuntimeError("Archive CRC failure: "+bad)
        for item in manifest["files"]:
            data=archive.read("textile_lab/"+item["path"])
            if hashlib.sha256(data).hexdigest()!=item["sha256"]:
                raise RuntimeError("Archive content hash mismatch: "+item["path"])
    record={"archive":str(DEST),"file_count":len(files)+1,
            "uncompressed_bytes":sum(x["bytes"] for x in manifest["files"]),
            "archive_bytes":DEST.stat().st_size,
            "archive_sha256":hashlib.sha256(DEST.read_bytes()).hexdigest(),
            "CRC_and_all_file_hashes_verified":True}
    (ROOT.parent/"textile_package_validation.json").write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))


if __name__=="__main__":main()
