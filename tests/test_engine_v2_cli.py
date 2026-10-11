"""Regression checks for runner side effects and scientific failure propagation."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_engine_v2 as runner


class EngineV2RunnerTests(unittest.TestCase):
    def test_dry_run_from_another_directory_does_not_create_any_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            location = Path(temporary)
            target = location / "never_created"
            process = subprocess.run(
                [sys.executable, str(runner.ROOT / "run_engine_v2.py"), "--stages",
                 "geometry", "refinement", "optics", "tests", "--no-render", "--dry-run",
                 "--output", str(target)], cwd=location, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(list(location.iterdir()), [])
            plan = json.loads(process.stdout)
            self.assertFalse(plan["writes"])
            self.assertEqual(len(plan["plan"]), 12)
            self.assertEqual(sum(item["stage"] == "geometry" for item in plan["plan"]), 5)
            optics = next(item for item in plan["plan"] if item["stage"] == "optics")
            self.assertIn("--skip-render", optics["command"])

    def test_failed_clearance_or_subprocess_stops_and_preserves_hashed_evidence(self):
        # Even a child that exits zero must not bless its failed clearance audit.
        # A genuine nonzero child exit is also propagated rather than hidden.
        for child_exit in (0, 2):
            with self.subTest(child_exit=child_exit), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                case = output / "geometry"
                case.mkdir()
                metric = case / "hierarchy_metrics.json"
                metric.write_text(json.dumps({"clearance_audit": {"certified_separated": False}}))
                marker = output / "should_never_run"
                commands = [
                    runner.StageCommand("geometry", "failed_fixture",
                        (sys.executable, "-c", f"print('known failed clearance'); raise SystemExit({child_exit})"),
                        str(case), ("hierarchy_metrics.json",)),
                    runner.StageCommand("fixture", "must_not_execute",
                        (sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"),
                        str(output / "unused")),
                ]
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = runner.execute_plan(commands, output, os.environ.copy(), {"selected_stages": []})
                self.assertEqual(code, child_exit if child_exit else 1)
                self.assertFalse(marker.exists())
                evidence = json.loads((output / "run_manifest.json").read_text())
                self.assertEqual(evidence["status"], "failed")
                self.assertEqual(len(evidence["records"]), 1)
                self.assertEqual(len(evidence["unexecuted_commands"]), 1)
                log = output / evidence["records"][0]["log"]
                self.assertEqual(evidence["records"][0]["log_sha256"], runner.sha256(log))
                for path, digest in evidence["output_sha256"].items():
                    self.assertEqual(runner.sha256(output / path), digest)

    def test_existing_run_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / "old_evidence.json"
            sentinel.write_text('{"preserve":true}\n')
            process = subprocess.run(
                [sys.executable, str(runner.ROOT / "run_engine_v2.py"), "--stages", "geometry",
                 "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(sentinel.read_text(), '{"preserve":true}\n')
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_missing_recorded_evidence_cannot_pass_via_skip(self):
        class MissingEvidence(unittest.TestCase):
            def runTest(self):
                self.skipTest("controlled missing-evidence fixture")

        with tempfile.TemporaryDirectory() as temporary:
            suite = unittest.TestSuite([MissingEvidence()])
            with patch.object(unittest.defaultTestLoader, "discover", return_value=suite), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = runner.run_tests(temporary)
            evidence = json.loads((Path(temporary) / "test_summary.json").read_text())
            self.assertEqual(code, 2)
            self.assertEqual(evidence["tests_run"], 1)
            self.assertEqual(evidence["skipped"], 1)
            self.assertEqual(evidence["failures"], 0)


if __name__ == "__main__":
    unittest.main()
