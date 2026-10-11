"""Run the complete suite once with core + visualization source provenance.

This release gate adds visualization sources/configs to its hash scope without
changing the frozen v0.5 runner. It reports tests, not renderer-call counts.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source_ledger():
    files = set(ROOT.glob("*.py"))
    for folder in ("textile_sim", "tests", "visualization"):
        files.update((ROOT / folder).rglob("*.py"))
    files.update((ROOT / "examples").rglob("*.json"))
    files.add(ROOT / "requirements.txt")
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files) if p.is_file()}


def atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                     encoding="utf-8") as stream:
        tmp = Path(stream.name)
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be new or empty; existing results are preserved")
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    before = source_ledger()
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    with (output / "tests.log").open("w", encoding="utf-8", buffering=1) as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"),
                                                       pattern="test_*.py")
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    after = source_ledger()
    changed = sorted(p for p in set(before) | set(after)
                     if before.get(p) != after.get(p))
    summary = {
        "schema": "textile-research/full-suite-provenance/5.1",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - timer,
        "python": sys.version,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "source_files": len(before),
        "source_sha256_initial": before,
        "source_sha256_final": after,
        "changed_source_files": changed,
        "success": result.wasSuccessful() and not changed,
        "failure_details": [{"test": str(t), "traceback": msg}
                            for t, msg in result.failures],
        "error_details": [{"test": str(t), "traceback": msg}
                          for t, msg in result.errors],
        "skipped_details": [{"test": str(t), "reason": msg}
                            for t, msg in result.skipped],
        "scope": ("Complete tests/test_*.py unittest discovery. Core, visualization, "
                  "tests, root Python and example JSON source hashes are covered. "
                  "Small renderer checks may run inside tests. Test count is not "
                  "an image, independent sample, or measured-material count."),
        "log_sha256": hashlib.sha256((output / "tests.log").read_bytes()).hexdigest(),
    }
    atomic_json(output / "test_summary.json", summary)
    print(json.dumps({k: summary[k] for k in
                      ("tests_run", "failures", "errors", "skipped",
                       "source_files", "changed_source_files", "success",
                       "elapsed_seconds")}, ensure_ascii=False))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
