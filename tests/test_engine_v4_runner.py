"""v4 orchestration tests: true dependencies, evidence preservation and honest counts."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_engine_v4 as runner


def optical_record(rendered=True):
    if not rendered:
        return {"status": "skipped", "actual_render_count": 0, "records": [], "comparisons": []}
    return {"status": "rendered", "actual_render_count": 108,
            "states": list(runner.OPTICAL_STATES), "wavelengths_nm": [450., 550., 650.],
            "seeds": [2, 17, 71, 123], "spectral_radiance_sha256": "f"*64,
            "records": [{"state": state, "light": light, "actual_render_count": 12}
                        for state in runner.OPTICAL_STATES for light in runner.LIGHTS]}


def manifest(no_render=False, paths=(), source=None):
    return {"no_experiment_render": no_render, "read_only_input_paths": [str(path) for path in paths],
            "source_sha256_initial": {} if source is None else source,
            "input_sha256_initial": runner.input_hashes(paths)}


class EngineV4RunnerTests(unittest.TestCase):
    def test_dry_run_requires_no_existing_inputs_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"uncreated"
            with redirect_stdout(io.StringIO()) as stream:
                code = runner.main(["--dry-run", "--output", str(out),
                                    "--input-data", str(Path(temporary)/"not_present")])
            value = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertFalse(value["writes"])
            self.assertEqual(value["planned_explicit_fiber_renders"], 108)
            self.assertEqual([item["stage"] for item in value["plan"]], list(runner.STAGES))

    def test_cold_dry_run_imports_no_numerical_or_renderer_packages(self):
        code = """import contextlib, io, json, sys
import run_engine_v4
with contextlib.redirect_stdout(io.StringIO()):
    status = run_engine_v4.main(['--dry-run', '--output', sys.argv[1]])
print(json.dumps({'status': status, 'heavy': sorted(set(sys.modules) & {'numpy','scipy','matplotlib','mitsuba','drjit'})}))
"""
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/"no_output"
            process = subprocess.run([sys.executable, "-c", code, str(target)], cwd=runner.ROOT,
                                     capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(process.stdout), {"status": 0, "heavy": []})
            self.assertFalse(target.exists())

    def test_new_experiment_is_the_verifier_input_regardless_request_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, old = Path(temporary)/"new", Path(temporary)/"old"
            plan = runner.make_plan(out, ["tests", "verify", "experiment"], input_data=old)
            self.assertEqual([item.stage for item in plan], list(runner.STAGES))
            experiment, verify, tests = (item.command for item in plan)
            self.assertEqual(experiment[experiment.index("--pair-directory")+1], str(old/"mechanics_v3/optical_pair"))
            self.assertEqual(verify[verify.index("--input")+1], str(out/"experiment"))
            self.assertIn("--worker-tests", tests)
            self.assertNotIn("--no-render", experiment)

    def test_verify_only_consumes_selected_existing_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, old = Path(temporary)/"new", Path(temporary)/"old"
            plan = runner.make_plan(out, ["verify"], input_data=old)
            self.assertEqual(plan[0].command[plan[0].command.index("--input")+1], str(old/"material_transport_v4"))
            self.assertEqual(runner.reused_inputs(["verify"], old), (old/"material_transport_v4",))

    def test_no_render_budget_is_distinct_from_requested_sampling(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"new"
            plan = runner.make_plan(out, ["experiment", "verify"], no_render=True, replicates=8, max_render_count=1)
            self.assertIn("--no-render", plan[0].command)
            self.assertNotIn("--no-render", plan[1].command)
            with self.assertRaisesRegex(ValueError, "216 renders"):
                runner.make_plan(out, ["experiment"], replicates=8)
            runner.make_plan(out, ["experiment"], replicates=8, max_render_count=216)
        invalid = (([], {}), (["experiment", "experiment"], {}), (["verify"], {"no_render": True}),
                   (["experiment"], {"resolution": 7}), (["experiment"], {"replicates": 1}),
                   (["experiment"], {"spp": True}), (["unknown"], {}))
        for selected, values in invalid:
            with self.subTest(selected=selected, values=values), self.assertRaises(ValueError):
                runner.make_plan("unused", selected, **values)

    def test_output_cannot_overlap_reused_input_or_source_directories(self):
        for target, stages in ((runner.ROOT/"data/mechanics_v3/optical_pair/new", ["experiment"]),
                               (runner.ROOT/"data/material_transport_v4/new", ["verify"]),
                               (runner.ROOT/"textile_sim/new", ["experiment"]),
                               (runner.ROOT/"tests/new", ["verify"])):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "overlap"):
                runner.make_plan(target, stages)

    def test_existing_output_and_internal_worker_evidence_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary)/"keep.json"
            marker.write_bytes(b'{"preserve": true}\n')
            for arguments in (["--stages", "verify"], ["--worker-tests"]):
                with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                    runner.main([*arguments, "--output", temporary])
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(marker.read_bytes(), b'{"preserve": true}\n')
                self.assertFalse((Path(temporary)/"run_manifest.json").exists())

    def test_missing_input_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"fresh"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                runner.main(["--stages", "verify", "--input-data", str(Path(temporary)/"missing"), "--output", str(out)])
            self.assertEqual(exc.exception.code, 2)
            self.assertFalse(out.exists())

    def test_render_counts_require_complete_unique_batches(self):
        valid = optical_record()
        self.assertEqual(runner.check_render_record(valid)["recorded_render_count"], 108)
        changed = []
        missing = copy.deepcopy(valid); missing["records"].pop(); changed.append(missing)
        duplicate = copy.deepcopy(valid); duplicate["records"][-1] = duplicate["records"][0]; changed.append(duplicate)
        bad_total = copy.deepcopy(valid); bad_total["actual_render_count"] += 1; changed.append(bad_total)
        bad_batch = copy.deepcopy(valid); bad_batch["records"][0]["actual_render_count"] = 9; changed.append(bad_batch)
        bad_seeds = copy.deepcopy(valid); bad_seeds["seeds"][-1] = bad_seeds["seeds"][0]; changed.append(bad_seeds)
        fake_hash = copy.deepcopy(valid); fake_hash["spectral_radiance_sha256"] = "no hash"; changed.append(fake_hash)
        for value in changed:
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.check_render_record(value)
        with self.assertRaises(ValueError):
            runner.check_render_record(valid, expected="skipped")

    def test_skipped_optics_cannot_contain_fabricated_observations(self):
        skipped = optical_record(False)
        self.assertEqual(runner.check_render_record(skipped)["recorded_render_count"], 0)
        for change in ({"actual_render_count": 1}, {"records": [1]}, {"comparisons": [1]},
                       {"spectral_radiance_sha256": "f"*64}, {"actual_render_count": False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.check_render_record({**skipped, **change})

    def test_source_records_reject_changed_or_outside_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"repo"; root.mkdir()
            file = root/"model.py"; file.write_text("value = 1\n")
            with patch.object(runner, "ROOT", root):
                entry = {"source_sha256": {"model.py": runner.sha256(file)}}
                runner.check_source_record(entry)
                file.write_text("value = 2\n")
                with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    runner.check_source_record(entry)
                outside = root.parent/"external.py"; outside.write_text("value = 1\n")
                with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    runner.check_source_record({"source_sha256": {"../external.py": runner.sha256(outside)}})

    def test_failed_partial_render_count_is_unknown_and_stops_later_stages(self):
        for no_render, expected_count in ((False, None), (True, 0)):
            with self.subTest(no_render=no_render), tempfile.TemporaryDirectory() as temporary:
                plan = runner.make_plan(temporary, ["experiment", "verify"], no_render=no_render)
                evidence = manifest(no_render)
                with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as call, \
                     patch.object(runner, "source_inputs", return_value={}), \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = runner.execute_plan(plan, temporary, {}, evidence)
                saved = runner.read_json(Path(temporary)/"run_manifest.json")
                self.assertEqual(code, 7)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(saved["explicit_fiber_renders_executed"], expected_count)
                self.assertEqual(saved["records"][0]["status"], "failed")
                self.assertEqual(len(saved["unexecuted_commands"]), 1)

    def test_verify_stage_requires_saved_producer_sources_to_match_current_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"model.py"; source.write_text("value = 1\n")
            producer, verification = root/"producer", root/"verification"
            producer.mkdir(); verification.mkdir()
            (producer/"experiment_manifest.json").write_text(json.dumps({"status": "passed",
                "source_sha256": {"model.py": runner.sha256(source)}}))
            (verification/"verification_summary.json").write_text(json.dumps({"status": "passed",
                "optics": {"status": "rendered", "verified_saved_render_count": 108}}))
            item = runner.StageCommand("verify", "", ("verifier", "--input", str(producer)),
                                       str(verification), ("verification_summary.json",))
            with patch.object(runner, "ROOT", root):
                self.assertEqual(runner.check_stage_outputs(item), 108)
                source.write_text("value = 2\n")
                with self.assertRaisesRegex(ValueError, "source provenance mismatch"):
                    runner.check_stage_outputs(item)

    def test_verifying_saved_renders_does_not_claim_new_renders(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = runner.make_plan(temporary, ["verify"])
            with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                 patch.object(runner, "check_stage_outputs", return_value=108), \
                 patch.object(runner, "source_inputs", return_value={}), redirect_stdout(io.StringIO()):
                code = runner.execute_plan(plan, temporary, {}, manifest())
            saved = runner.read_json(Path(temporary)/"run_manifest.json")
            self.assertEqual(code, 0)
            self.assertEqual(saved["explicit_fiber_renders_executed"], 0)
            self.assertEqual(saved["saved_explicit_fiber_renders_verified"], 108)
            self.assertNotIn("run_manifest.json", saved["output_sha256_final"])
            for name, digest in saved["output_sha256_final"].items():
                self.assertEqual(runner.sha256(Path(temporary)/name), digest)

    def test_source_or_readonly_input_drift_fails_successful_subprocess(self):
        with tempfile.TemporaryDirectory() as temporary:
            input_dir, out = Path(temporary)/"input", Path(temporary)/"output"
            input_dir.mkdir(); original = input_dir/"data.json"; original.write_text('{"value": 1}\n')
            evidence = manifest(paths=(input_dir,))
            def change_input(*args, **kwargs):
                original.write_text('{"value": 2}\n')
                (input_dir/"added.json").write_text('{}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(runner.subprocess, "run", side_effect=change_input), \
                 patch.object(runner, "check_stage_outputs", return_value=0), \
                 patch.object(runner, "source_inputs", return_value={"changed_source.py": "new"}), \
                 redirect_stdout(io.StringIO()):
                code = runner.execute_plan(runner.make_plan(out, ["verify"]), out, {}, evidence)
            saved = runner.read_json(out/"run_manifest.json")
            self.assertEqual(code, 1)
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["changed_source_files_during_run"], ["changed_source.py"])
            self.assertEqual(set(saved["changed_input_files_during_run"]), {str(original), str(input_dir/"added.json")})

    def test_test_worker_delegates_to_full_discovery_without_recursive_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"fresh"
            with patch.object(runner, "run_tests", return_value=0) as worker:
                self.assertEqual(runner.main(["--worker-tests", "--output", str(out)]), 0)
            worker.assert_called_once_with(out)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.main(["--worker-tests", "--output", str(out), "--dry-run"])


if __name__ == "__main__":
    unittest.main()
