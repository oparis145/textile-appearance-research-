"""Run the complete unittest suite and write the machine-readable evidence.

Expensive scene experiments are validated from their recorded data; they are
not silently rendered again here. Use run_all.py to generate missing data.
"""
from pathlib import Path
import hashlib
import json
import platform
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))


def main():
    output=ROOT/"data"
    output.mkdir(exist_ok=True)
    start=time.perf_counter()
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    with (output/"final_tests.log").open("w",encoding="utf-8") as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ("textile_sim","tests") for path in sorted((ROOT/folder).glob("*.py"))}
    record={"tests_run":result.testsRun,"failures":len(result.failures),
            "errors":len(result.errors),"skipped":len(result.skipped),
            "elapsed_seconds":time.perf_counter()-start,"python":platform.python_version(),
            "failure_details":[[str(test),detail] for test,detail in result.failures],
            "error_details":[[str(test),detail] for test,detail in result.errors],
            "skipped_details":[[str(test),reason] for test,reason in result.skipped],
            "source_sha256":hashes,
            "scope":"Independent analytical/numerical checks and recorded-scene gates; not real-material validation"}
    (output/"final_test_summary.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in record.items() if k!="source_sha256"},indent=2))
    if not result.wasSuccessful() or result.skipped:
        print((output/"final_tests.log").read_text()[-18000:])
        raise SystemExit(1 if not result.wasSuccessful() else 2)


if __name__=="__main__":main()
