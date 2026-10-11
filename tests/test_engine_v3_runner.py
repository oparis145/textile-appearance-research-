"""Runner contracts: preserve artifacts, wire the true data dependency, never invent renders."""
from contextlib import redirect_stdout, redirect_stderr
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import run_engine_v3 as runner


class EngineV3RunnerTests(unittest.TestCase):
    def test_dry_run_writes_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "must_not_exist"
            with redirect_stdout(io.StringIO()) as stream:
                code = runner.main(["--stages", "verify", "--output", str(out), "--dry-run"])
            plan = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertFalse(plan["writes"])
            self.assertFalse(out.exists())
            self.assertEqual(plan["plan"][0]["stage"], "verify")

    def test_canonical_dependency_wires_new_mechanics_to_new_optics(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "new"
            old = Path(temporary) / "old"
            plan = runner.make_plan(out, ["verify", "tests", "optics", "mechanics"], input_data=old)
            self.assertEqual([p.stage for p in plan], list(runner.STAGES))
            optics = plan[1].command
            self.assertEqual(optics[optics.index("--pair-directory")+1], str(out / "mechanics_v3/optical_pair"))
            self.assertNotIn("--skip-render", optics)
            self.assertEqual(plan[2].command[-1], "executed")

    def test_omitted_mechanics_is_read_from_explicit_input_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, old = Path(temporary)/"new", Path(temporary)/"old"
            plan = runner.make_plan(out, ["optics", "verify"], input_data=old, no_render=True)
            optics = plan[0].command
            self.assertEqual(optics[optics.index("--pair-directory")+1], str(old / "mechanics_v3/optical_pair"))
            self.assertIn("--skip-render", optics)
            verify = plan[1].command
            self.assertEqual(verify[verify.index("--_mechanics")+1], str(old / "mechanics_v3"))
            self.assertEqual(verify[verify.index("--_optics")+1], str(out / "optical_v3"))
            self.assertEqual(verify[-1], "not_requested")

    def test_ambiguous_or_unmatched_stage_requests_are_rejected(self):
        for stages, kwargs in ((["verify"], {"no_render": True}),
                               (["mechanics", "verify"], {}), (["optics", "optics"], {}),
                               (["optics"], {"replicates": 1}), (["optics"], {"resolution": 7})):
            with self.subTest(stages=stages, kwargs=kwargs), self.assertRaises(ValueError):
                runner.make_plan("unused", stages, **kwargs)
        with self.assertRaisesRegex(ValueError, "overlap"):
            runner.make_plan(runner.ROOT / "data/mechanics_v3/new_audit", ["verify"])

    def test_nonempty_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "existing.json"
            marker.write_bytes(b"{\"old_evidence\":true}\n")
            before = marker.read_bytes()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main(["--stages", "verify", "--output", temporary])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(marker.read_bytes(), before)
            self.assertFalse((Path(temporary)/"run_manifest.json").exists())

    def test_source_provenance_fails_on_mutation_and_outside_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"repo"
            root.mkdir()
            source = root/"model.py"
            source.write_text("model = 1\n")
            record = {"source_sha256": {"model.py": runner.sha256(source)}}
            runner.check_source_hashes(record, root)
            source.write_text("model = 2\n")
            with self.assertRaisesRegex(ValueError, "source provenance mismatch"):
                runner.check_source_hashes(record, root)
            outside = root.parent/"outside.py"
            outside.write_text("x = 1\n")
            with self.assertRaisesRegex(ValueError, "source provenance mismatch"):
                runner.check_source_hashes({"source_sha256": {"../outside.py": runner.sha256(outside)}}, root)

    def test_no_render_status_cannot_smuggle_observation_or_count(self):
        omitted = {"render_status": "not_requested", "actual_explicit_fiber_render_count": 0,
                   "render_runs": {}, "paired_observation_comparisons": []}
        self.assertEqual(runner.check_render_record(omitted)["recorded_explicit_fiber_render_count"], 0)
        for modification in ({"paired_observation_comparisons": [1]}, {"actual_explicit_fiber_render_count": 1},
                             {"render_status": "executed"}):
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                runner.check_render_record({**omitted, **modification})

    def test_recorded_render_total_and_stage_status_must_agree(self):
        metrics = runner.read_json(runner.ROOT / "data/optical_v3/optical_scale_metrics.json")
        record = runner.check_render_record(metrics, "executed")
        self.assertEqual(record["recorded_explicit_fiber_render_count"], 536)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            runner.check_render_record(metrics, "not_requested")
        changed = copy.deepcopy(metrics)
        changed["render_runs"]["initial"]["reflection_warp"]["actual_render_count"] += 1
        with self.assertRaisesRegex(ValueError, "per-run counts"):
            runner.check_render_record(changed)

    def test_failed_partial_render_is_unknown_instead_of_zero(self):
        # The optical subprocess can fail after some renders but before final
        # metrics exist. The caller must not invent a zero count in that case.
        for no_render, expected in ((False, None), (True, 0)):
            with self.subTest(no_render=no_render), tempfile.TemporaryDirectory() as temporary:
                plan = runner.make_plan(temporary, ["optics"], no_render=no_render)
                manifest = {"no_experiment_render": no_render,
                            "input_sha256": runner.source_inputs()}
                with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=7)), \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = runner.execute_plan(plan, temporary, {}, manifest)
                saved = runner.read_json(Path(temporary)/"run_manifest.json")
                self.assertEqual(code, 7)
                self.assertEqual(saved["status"], "failed")
                self.assertEqual(saved["explicit_fiber_renders_executed"], expected)
                self.assertEqual(saved["records"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
