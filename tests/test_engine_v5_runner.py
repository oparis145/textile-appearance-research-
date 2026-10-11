"""v5 orchestration tests: true dependencies, evidence preservation and honest counts."""
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

import run_engine_v5 as runner


def optical_record(rendered=True, radials=runner.RADIAL_SEGMENTS, wavelengths=runner.WAVELENGTHS_NM,
                   seeds=(2, 17, 71, 123)):
    base = {"schema_version": runner.OPTICS_SCHEMA, "states": list(runner.OPTICAL_STATES),
            "lights": list(runner.LIGHTS), "radial_segments": list(radials),
            "wavelengths_nm": list(wavelengths), "seeds": list(seeds)}
    if not rendered:
        return {**base, "status": "skipped", "actual_render_count": 0, "records": [], "comparisons": []}
    records = [{"radial_segments": radial, "state": state, "light": light,
                "wavelength_nm": wavelength, "seed": seed, "actual_render_count": 1,
                "array_index": [ri, si, li, wi, ki]}
               for ri, radial in enumerate(radials) for si, state in enumerate(runner.OPTICAL_STATES)
               for li, light in enumerate(runner.LIGHTS) for wi, wavelength in enumerate(wavelengths)
               for ki, seed in enumerate(seeds)]
    return {**base, "status": "rendered", "actual_render_count": len(records),
            "spectral_radiance_sha256": "f"*64, "records": records}


def manifest(no_render=False, paths=(), source=None):
    return {"no_experiment_render": no_render, "read_only_input_paths": [str(path) for path in paths],
            "source_sha256_initial": {} if source is None else source,
            "input_sha256_initial": runner.input_hashes(paths)}


def source_pair_fixture(path):
    """Four byte fixtures for runner path/hash tests, not physical hierarchies."""
    pair = Path(path)
    for pose in ("initial", "relaxed"):
        (pair/pose).mkdir(parents=True)
        for extension in ("json", "npz"):
            (pair/pose/("hierarchy_geometry."+extension)).write_bytes((pose+extension).encode())
    return pair


class EngineV5RunnerTests(unittest.TestCase):
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
            self.assertEqual(value["planned_explicit_fiber_renders"], 216)
            self.assertEqual([item["stage"] for item in value["plan"]], list(runner.STAGES))

    def test_cold_dry_run_imports_no_numerical_or_renderer_packages(self):
        code = """import contextlib, io, json, sys
import run_engine_v5
with contextlib.redirect_stdout(io.StringIO()):
    status = run_engine_v5.main(['--dry-run', '--output', sys.argv[1]])
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
            self.assertEqual(experiment[experiment.index("--input-pair")+1], str(old/"mechanics_v3/optical_pair"))
            self.assertEqual(verify[verify.index("--input")+1], str(out/"experiment"))
            self.assertEqual(runner._argument(verify, "--source-input"), str(old/"mechanics_v3/optical_pair"))
            self.assertIn("--worker-tests", tests)
            self.assertNotIn("--no-render", experiment)

    def test_verify_only_consumes_selected_existing_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, old = Path(temporary)/"new", Path(temporary)/"old"
            plan = runner.make_plan(out, ["verify"], input_data=old)
            self.assertEqual(plan[0].command[plan[0].command.index("--input")+1], str(old/"variable_radius_v5"))
            self.assertEqual(runner.reused_inputs(["verify"], old), (old/"variable_radius_v5",))

    def test_verify_auto_forwards_available_mechanics_pair_and_hashes_all_raw_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)/"archive"
            pair = source_pair_fixture(data/"mechanics_v3/optical_pair")
            saved = data/"variable_radius_v5"; saved.mkdir()
            (saved/"evidence.json").write_text("{}")
            plan = runner.make_plan(Path(temporary)/"out", ["verify"], input_data=data)
            self.assertEqual(runner._argument(plan[0].command, "--source-input"), str(pair))
            self.assertEqual(runner._argument(plan[0].command, "--input"), str(saved))
            paths = runner.reused_inputs(["verify"], data)
            self.assertEqual(set(paths), {pair, saved})
            hashes = runner.input_hashes(paths)
            for pose in ("initial", "relaxed"):
                for extension in ("json", "npz"):
                    source = pair/pose/("hierarchy_geometry."+extension)
                    self.assertEqual(hashes[str(source)], runner.sha256(source))
            with self.assertRaisesRegex(ValueError, "overlap"):
                runner.make_plan(pair/"forbidden_output", ["verify"], input_data=data)

    def test_verify_only_missing_default_source_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            data, out = Path(temporary)/"archive", Path(temporary)/"out"
            with redirect_stdout(io.StringIO()) as stream:
                code = runner.main(["--stages", "verify", "--input-data", str(data),
                                    "--output", str(out), "--dry-run"])
            record = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(record["source_input_verification"]["mode"], "unavailable_default")
            self.assertIsNone(record["source_input_verification"]["requested_path"])
            self.assertNotIn("--source-input", record["plan"][0]["command"])
            self.assertEqual(record["read_only_input_paths"], [str(data/"variable_radius_v5")])
            self.assertFalse(out.exists())

    def test_explicit_source_override_is_forwarded_hashed_and_cannot_be_silently_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)/"archive"
            saved = data/"variable_radius_v5"; saved.mkdir(parents=True)
            (saved/"evidence.json").write_text("{}")
            default = source_pair_fixture(data/"mechanics_v3/optical_pair")
            original = source_pair_fixture(Path(temporary)/"original")
            out = Path(temporary)/"out"
            plan = runner.make_plan(out, ["verify"], input_data=data, source_input=original)
            self.assertEqual(runner._argument(plan[0].command, "--source-input"), str(original))
            self.assertEqual(set(runner.reused_inputs(["verify"], data, source_input=original)), {original, saved})
            self.assertNotIn(str(default), [str(p) for p in runner.reused_inputs(["verify"], data, source_input=original)])
            with self.assertRaisesRegex(ValueError, "overlap"):
                runner.make_plan(original/"forbidden", ["verify"], input_data=data, source_input=original)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main(["--stages", "verify", "--input-data", str(data), "--output", str(out),
                             "--source-input", str(Path(temporary)/"explicit_missing")])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(out.exists())
            with self.assertRaisesRegex(ValueError, "verify stage"):
                runner.make_plan(out, ["experiment"], input_data=data, source_input=original)

    def test_custom_channels_propagate_to_actual_commands_and_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"fresh"
            plan = runner.make_plan(out, ["experiment"], radial_segments=(8, 24),
                                    wavelengths_nm=(500., 610.), replicates=3, max_render_count=72)
            cmd = plan[0].command
            self.assertEqual(runner._arguments(cmd, "--radial-segments"), ("8", "24"))
            self.assertEqual(runner._arguments(cmd, "--wavelengths"), ("500.0", "610.0"))
            self.assertEqual(runner._argument(cmd, "--max-render-count"), "72")
            with redirect_stdout(io.StringIO()) as output:
                runner.main(["--dry-run", "--output", str(out), "--stages", "experiment", "verify",
                             "--radial-segments", "8", "24", "--wavelengths", "500", "610",
                             "--replicates", "3", "--max-render-count", "72"])
            self.assertEqual(json.loads(output.getvalue())["planned_explicit_fiber_renders"], 72)
            self.assertFalse(out.exists())
            custom = optical_record(radials=(8, 24), wavelengths=(500., 610.), seeds=(3, 41, 59))
            self.assertEqual(runner.check_render_record(custom)["recorded_render_count"], 72)

    def test_no_render_budget_is_distinct_from_requested_sampling(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/"new"
            plan = runner.make_plan(out, ["experiment", "verify"], no_render=True, replicates=8, max_render_count=1)
            self.assertIn("--no-render", plan[0].command)
            self.assertNotIn("--no-render", plan[1].command)
            with self.assertRaisesRegex(ValueError, "432 renders"):
                runner.make_plan(out, ["experiment"], replicates=8)
            runner.make_plan(out, ["experiment"], replicates=8, max_render_count=432)
        invalid = (([], {}), (["experiment", "experiment"], {}), (["verify"], {"no_render": True}),
                   (["experiment"], {"resolution": 7}), (["experiment"], {"replicates": 1}),
                   (["experiment"], {"spp": True}), (["unknown"], {}),
                   (["experiment"], {"radial_segments": []}),
                   (["experiment"], {"radial_segments": (32, 16)}),
                   (["experiment"], {"radial_segments": (16, 16)}),
                   (["experiment"], {"radial_segments": (3, 8)}),
                   (["experiment"], {"radial_segments": (8, True)}),
                   (["experiment"], {"wavelengths_nm": (550, 450)}),
                   (["experiment"], {"wavelengths_nm": (450, 450)}),
                   (["experiment"], {"wavelengths_nm": (float("nan"),)}),
                   (["experiment"], {"wavelengths_nm": (True,)}))
        for selected, values in invalid:
            with self.subTest(selected=selected, values=values), self.assertRaises(ValueError):
                runner.make_plan("unused", selected, **values)

    def test_output_cannot_overlap_reused_input_or_source_directories(self):
        for target, stages in ((runner.ROOT/"data/mechanics_v3/optical_pair/new", ["experiment"]),
                               (runner.ROOT/"data/variable_radius_v5/new", ["verify"]),
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
        self.assertEqual(runner.check_render_record(valid)["recorded_render_count"], 216)
        changed = []
        missing = copy.deepcopy(valid); missing["records"].pop(); changed.append(missing)
        duplicate = copy.deepcopy(valid); duplicate["records"][-1] = duplicate["records"][0]; changed.append(duplicate)
        bad_total = copy.deepcopy(valid); bad_total["actual_render_count"] += 1; changed.append(bad_total)
        bad_batch = copy.deepcopy(valid); bad_batch["records"][0]["actual_render_count"] = 9; changed.append(bad_batch)
        bad_seeds = copy.deepcopy(valid); bad_seeds["seeds"][-1] = bad_seeds["seeds"][0]; changed.append(bad_seeds)
        fake_hash = copy.deepcopy(valid); fake_hash["spectral_radiance_sha256"] = "no hash"; changed.append(fake_hash)
        bad_index = copy.deepcopy(valid); bad_index["records"][0]["array_index"][0] = 2; changed.append(bad_index)
        boolean_index = copy.deepcopy(valid); boolean_index["records"][0]["array_index"][0] = False; changed.append(boolean_index)
        wrong_wavelength = copy.deepcopy(valid); wrong_wavelength["records"][0]["wavelength_nm"] = 555.; changed.append(wrong_wavelength)
        wrong_radial = copy.deepcopy(valid); wrong_radial["records"][0]["radial_segments"] = 24; changed.append(wrong_radial)
        bad_schema = copy.deepcopy(valid); bad_schema["schema_version"] = "unknown"; changed.append(bad_schema)
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

    def test_experiment_stage_checks_actual_cli_budget_and_raw_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"repo"; root.mkdir()
            source = root/"model.py"; source.write_text("value = 1\n")
            with patch.object(runner, "ROOT", root):
                item = runner.make_plan(root/"fresh", ["experiment"], radial_segments=(8, 16),
                    wavelengths_nm=(500., 610.), replicates=2, max_render_count=48)[0]
                target = Path(item.output_directory); (target/"optics").mkdir(parents=True)
                raw = target/"optics/spectral_radiance.npz"
                raw.write_bytes(b"unit fixture: hash validation only, not physical radiance")
                metrics = optical_record(radials=(8, 16), wavelengths=(500., 610.), seeds=(7, 23))
                metrics["spectral_radiance_sha256"] = runner.sha256(raw)
                evidence = {"schema_version": runner.EXPERIMENT_SCHEMA, "status": "passed", "requested_render": True,
                    "input_hashes_unchanged": True, "source_hashes_unchanged": True,
                    "source_sha256": {"model.py": runner.sha256(source)}, "actual_render_count": 48,
                    "planned_render_count": 48, "resolution": 64, "spp": 64, "replicates": 2,
                    "radial_segments": [8, 16], "wavelengths_nm": [500., 610.]}
                runner.write_json(target/"experiment_manifest.json", evidence)
                runner.write_json(target/"geometry_metrics.json", {})
                runner.write_json(target/"optics/optical_metrics.json", metrics)
                self.assertEqual(runner.check_stage_outputs(item), 48)
                runner.write_json(target/"experiment_manifest.json", {**evidence, "radial_segments": [8, 32]})
                with self.assertRaisesRegex(ValueError, "radial_segments"):
                    runner.check_stage_outputs(item)
                runner.write_json(target/"experiment_manifest.json", evidence)
                raw.write_bytes(b"changed radiance")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    runner.check_stage_outputs(item)

    def test_no_render_stage_requires_zero_observations_and_no_stale_raw_array(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"repo"; root.mkdir()
            source = root/"model.py"; source.write_text("value = 1\n")
            with patch.object(runner, "ROOT", root):
                item = runner.make_plan(root/"fresh", ["experiment"], no_render=True)[0]
                target = Path(item.output_directory); (target/"optics").mkdir(parents=True)
                evidence = {"schema_version": runner.EXPERIMENT_SCHEMA, "status": "passed", "requested_render": False,
                    "input_hashes_unchanged": True, "source_hashes_unchanged": True,
                    "source_sha256": {"model.py": runner.sha256(source)}, "actual_render_count": 0,
                    "planned_render_count": 0, "resolution": 64, "spp": 64, "replicates": 4,
                    "radial_segments": [16, 32, 64], "wavelengths_nm": [450., 550., 650.]}
                runner.write_json(target/"experiment_manifest.json", evidence)
                runner.write_json(target/"geometry_metrics.json", {})
                runner.write_json(target/"optics/optical_metrics.json", optical_record(False))
                self.assertEqual(runner.check_stage_outputs(item, no_render=True), 0)
                (target/"optics/spectral_radiance.npz").write_bytes(b"stale")
                with self.assertRaisesRegex(ValueError, "raw radiance"):
                    runner.check_stage_outputs(item, no_render=True)

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
            (producer/"optics").mkdir()
            (producer/"optics/optical_metrics.json").write_text(json.dumps(optical_record()))
            (producer/"experiment_manifest.json").write_text(json.dumps({"schema_version": runner.EXPERIMENT_SCHEMA,
                "status": "passed", "actual_render_count": 216,
                "source_sha256": {"model.py": runner.sha256(source)}}))
            (verification/"verification_summary.json").write_text(json.dumps({"status": "passed",
                "source_input": {"external_source_inputs_rechecked": False},
                "optics": {"status": "rendered", "verified_saved_render_count": 216}}))
            item = runner.StageCommand("verify", "", ("verifier", "--input", str(producer)),
                                       str(verification), ("verification_summary.json",))
            with patch.object(runner, "ROOT", root):
                self.assertEqual(runner.check_stage_outputs(item), 216)
                source.write_text("value = 2\n")
                with self.assertRaisesRegex(ValueError, "source provenance mismatch"):
                    runner.check_stage_outputs(item)

    def test_requested_original_source_reconstruction_must_return_all_source_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"model.py"; source.write_text("value = 1\n")
            producer, verification = root/"producer", root/"verification"
            (producer/"optics").mkdir(parents=True); verification.mkdir()
            (producer/"optics/optical_metrics.json").write_text(json.dumps(optical_record()))
            runner.write_json(producer/"experiment_manifest.json", {"schema_version": runner.EXPERIMENT_SCHEMA,
                "status": "passed", "actual_render_count": 216,
                "source_sha256": {"model.py": runner.sha256(source)}})
            original = {"external_source_inputs_rechecked": True, "input_files_hash_verified": 4,
                        "reference_sha256": "a"*64,
                        "state_sha256": {state: "b"*64 for state in runner.OPTICAL_STATES}}
            evidence = {"status": "passed", "source_input": original,
                        "optics": {"status": "rendered", "verified_saved_render_count": 216}}
            item = runner.StageCommand("verify", "", ("verifier", "--input", str(producer),
                "--source-input", str(root/"original")), str(verification), ("verification_summary.json",))
            with patch.object(runner, "ROOT", root):
                runner.write_json(verification/"verification_summary.json", evidence)
                self.assertEqual(runner.check_stage_outputs(item), 216)
                for change in ({"external_source_inputs_rechecked": False}, {"input_files_hash_verified": 3},
                               {"state_sha256": {}}, {"reference_sha256": "missing digest"}):
                    runner.write_json(verification/"verification_summary.json",
                                      {**evidence, "source_input": {**original, **change}})
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        runner.check_stage_outputs(item)

    def test_unavailable_source_choice_is_frozen_into_readonly_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)/"archive"
            selected = runner.resolve_source_input(["verify"], data)
            self.assertIsNone(selected)
            # A later directory appearance cannot silently change a prepared
            # command or its before/after hash scope.
            source_pair_fixture(data/"mechanics_v3/optical_pair")
            plan = runner.make_plan(Path(temporary)/"out", ["verify"], input_data=data, source_input=selected)
            self.assertNotIn("--source-input", plan[0].command)
            self.assertEqual(runner.reused_inputs(["verify"], data, source_input=selected), (data/"variable_radius_v5",))

    def test_verifying_saved_renders_does_not_claim_new_renders(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = runner.make_plan(temporary, ["verify"])
            with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                 patch.object(runner, "check_stage_outputs", return_value=216), \
                 patch.object(runner, "source_inputs", return_value={}), redirect_stdout(io.StringIO()):
                code = runner.execute_plan(plan, temporary, {}, manifest())
            saved = runner.read_json(Path(temporary)/"run_manifest.json")
            self.assertEqual(code, 0)
            self.assertEqual(saved["explicit_fiber_renders_executed"], 0)
            self.assertEqual(saved["saved_explicit_fiber_renders_verified"], 216)
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

    def test_isolated_worker_adds_source_hashes_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"fresh"
            def mock_full_discovery(target):
                runner.write_json(Path(target)/"test_summary.json", {"tests_run": 3, "failures": 0,
                    "errors": 0, "skipped": 0})
                (Path(target)/"tests.log").write_text("Synthetic worker test fixture\n")
                return 0
            with patch.object(runner, "_base_run_tests", side_effect=mock_full_discovery), \
                 patch.object(runner, "source_inputs", side_effect=({"model.py": "old"}, {"model.py": "new"})):
                self.assertEqual(runner.run_tests(output), 1)
            saved = runner.read_json(output/"test_summary.json")
            self.assertFalse(saved["source_hashes_unchanged"])
            self.assertEqual(saved["changed_source_files_during_tests"], ["model.py"])
            self.assertEqual(saved["source_sha256"], {"model.py": "new"})


if __name__ == "__main__":
    unittest.main()
