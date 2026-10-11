#!/usr/bin/env python3
"""Run or audit the v3 mechanics-to-optics experiments without overwriting evidence.

Examples, from any working directory:
  python run_engine_v3.py --dry-run
  python run_engine_v3.py --stages verify --output data/engine_v3_runs/audit_001
  python run_engine_v3.py --stages optics verify --no-render --output data/engine_v3_runs/projection_001
  python run_engine_v3.py --output data/engine_v3_runs/full_001

Stages execute in mechanics, optics, verify, tests order. Omitted upstream stages
read --input-data/mechanics_v3 or --input-data/optical_v3, defaulting to the
committed data directory. --no-render applies only to the optical experiment;
the complete tests stage includes small CPU renderer checks. Verify reads saved
arrays and recomputes numerical summaries; it never re-renders a saved image.
No dependencies are installed, no files are downloaded, and existing nonempty
output directories are rejected. The pinned CIE source remains a repository
input. A dry run imports no numerical modules and creates no output directory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_engine_v2 import (StageCommand, THREAD_VARIABLES, environment_record,
                           positive_int, run_tests, sha256, stage_hashes,
                           utc_now, write_json)

ROOT = Path(__file__).resolve().parent
STAGES = ("mechanics", "optics", "verify", "tests")
STATES = ("initial", "relaxed")
LIGHTS = ("reflection_warp", "reflection_weft", "transmission_diag")


def make_plan(output, selected, *, input_data=None, no_render=False,
              resolution=64, spp=32, replicates=4):
    """Build real CLI commands without accessing scientific inputs or writing."""
    output = Path(output).resolve()
    input_data = (ROOT / "data" if input_data is None else Path(input_data)).resolve()
    selected = tuple(selected)
    if not selected or len(set(selected)) != len(selected) or any(s not in STAGES for s in selected):
        raise ValueError("select distinct stages from mechanics, optics, verify, tests")
    if no_render and "optics" not in selected:
        raise ValueError("--no-render only applies when the optics stage is selected")
    if "mechanics" in selected and "verify" in selected and "optics" not in selected:
        raise ValueError("verifying regenerated mechanics requires regenerating its matching optics stage")
    if resolution < 8 or spp < 1 or replicates < 2:
        raise ValueError("resolution >= 8, spp >= 1, and replicates >= 2 are required")
    mechanics = (output if "mechanics" in selected else input_data) / "mechanics_v3"
    optics = (output if "optics" in selected else input_data) / "optical_v3"
    reused = []
    if "mechanics" not in selected and any(s in selected for s in ("optics", "verify")):
        reused.append(mechanics)
    if "optics" not in selected and "verify" in selected:
        reused.append(optics)
    if any(output.is_relative_to(folder) or folder.is_relative_to(output) for folder in reused):
        raise ValueError("output must not overlap the reused upstream experiment directories")
    py = (sys.executable, "-u")
    plan = []
    for stage in STAGES:
        if stage not in selected:
            continue
        if stage == "mechanics":
            command = py + (str(ROOT / "run_weave_mechanics_experiments.py"), "--out", str(mechanics),
                            "--figures", str(mechanics / "figures"))
            target, required = mechanics, ("experiment_manifest.json", "optical_pair/pair_metrics.json",
                                          "two_ply/pair_metrics.json", "mesh_refinement.json", "beam_benchmark.json")
        elif stage == "optics":
            command = py + (str(ROOT / "run_multiscale_optics_v3.py"), "--pair-directory", str(mechanics / "optical_pair"),
                            "--output", str(optics), "--figures", str(optics / "figures"),
                            "--resolution", str(resolution), "--spp", str(spp), "--replicates", str(replicates))
            if no_render:
                command += ("--skip-render",)
            target, required = optics, ("optical_scale_metrics.json", "initial_optical_scene.json",
                                        "relaxed_optical_scene.json", "initial_projected_area_fits.npz",
                                        "relaxed_projected_area_fits.npz")
        elif stage == "verify":
            target = output / "verification"
            expected = "any" if "optics" not in selected else ("not_requested" if no_render else "executed")
            command = py + (str(ROOT / "run_engine_v3.py"), "--_worker", "verify", "--output", str(target),
                            "--_mechanics", str(mechanics), "--_optics", str(optics), "--_expected-render", expected)
            required = ("artifact_verification.json",)
        else:
            target = output / "tests"
            command = py + (str(ROOT / "run_engine_v3.py"), "--_worker", "tests", "--output", str(target))
            required = ("test_summary.json", "tests.log")
        plan.append(StageCommand(stage, "", command, str(target), required))
    return plan


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_source_hashes(record, root=ROOT):
    """Fail on absent, changed or out-of-tree source evidence, not only on a bad status flag."""
    root = Path(root).resolve()
    hashes = record.get("source_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("missing source_sha256 provenance")
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256(path) != expected:
            raise ValueError("source provenance mismatch: " + name)
    return dict(hashes)


def check_render_record(metrics, expected="any"):
    """Separate verified past renders, newly requested renders and an omitted renderer."""
    status = metrics.get("render_status")
    if status not in ("executed", "not_requested") or (expected != "any" and status != expected):
        raise ValueError("optical render status contradicts the requested stage")
    count = metrics.get("actual_explicit_fiber_render_count")
    runs = metrics.get("render_runs", {})
    fine = metrics.get("spectral_fine_grid_render_runs", {})
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("invalid explicit-fiber render count")
    actual = sum(r["actual_render_count"] for lights in runs.values() for r in lights.values())
    actual += sum(r["actual_render_count"] for r in fine.values())
    if count != actual:
        raise ValueError("render total disagrees with the per-run counts")
    if status == "not_requested":
        if count or runs or fine or metrics.get("paired_observation_comparisons"):
            raise ValueError("an omitted renderer cannot supply newly computed observation results")
    elif count == 0 or set(runs) != set(STATES) or set(fine) != set(STATES):
        raise ValueError("executed optics requires both states and the actual spectral refinement")
    return {"recorded_render_status": status, "recorded_explicit_fiber_render_count": count}


def verify_artifacts(mechanics_directory, optical_directory, output, expected_render="any"):
    """Audit saved v3 data; recompute geometry/KKT/projection/observation checks, never render.

    The detailed mechanical audit covers the optical pair, not every parameter
    sweep. Source hashes bind the companion mechanics experiments. This checks
    implementation and artifact consistency, not measured physical correctness.
    """
    import numpy as np
    from textile_sim.hierarchy import YarnSpec, audit_clearance, load_hierarchy
    from textile_sim.weave_mechanics import (ReducedWeaveSpec, ReducedWeaveProblem,
        WeaveEquilibrium, build_relaxed_hierarchy, equilibrium_residual)
    from textile_sim.optical_scene import OpticalScene, from_hierarchy
    from textile_sim.optical_lod import (projected_area_density, load_cie1931,
        spectral_xyz_weights, planck_relative, integrate_xyz, paired_mean_interval)

    mechanics, optics = Path(mechanics_directory), Path(optical_directory)
    input_artifacts = {str(path.resolve()): sha256(path) for folder in (mechanics, optics)
                       for path in sorted(folder.rglob("*")) if path.is_file()}
    pair = mechanics / "optical_pair"
    mm, om = read_json(mechanics / "experiment_manifest.json"), read_json(optics / "optical_scale_metrics.json")
    sources = {"mechanics": check_source_hashes(mm), "optics": check_source_hashes(om)}
    render_record = check_render_record(om, expected_render)
    if sha256(pair / "pair_metrics.json") != om["input_pair_metrics_sha256"]:
        raise ValueError("optics does not refer to the supplied mechanical pair metrics")
    pm = read_json(pair / "pair_metrics.json")
    config = read_json(ROOT / "examples/mechanics/optical_pair.json")
    p = ReducedWeaveProblem(ReducedWeaveSpec.from_dict(config["mechanics"]))
    if pm["config"] != p.spec.to_dict():
        raise ValueError("mechanical pair differs from the recorded source fixture")
    with np.load(pair / "mechanical_heights.npz", allow_pickle=False) as z:
        initial, relaxed = z["initial_mm"].copy(), z["relaxed_mm"].copy()
    kkt = equilibrium_residual(p, relaxed)
    if kkt["stationarity_relative"] > 1e-8 or kkt["complementarity_relative"] > 1e-8:
        raise ValueError("saved relaxed state failed recomputed KKT stationarity/complementarity")
    constraints = p.constraint_diagnostics(relaxed)
    if constraints["max_violation_mm"] > 1e-10:
        raise ValueError("saved relaxed state failed feasibility")
    energies = [float(p.energy_gradient_hessian(z)[0]) for z in (initial, relaxed)]
    if energies[1] > energies[0] + 1e-12:
        raise ValueError("relaxed state increased the modeled energy")
    np.testing.assert_allclose(energies, [pm["equilibrium"]["initial_energy_excess_N_mm"],
                                        pm["equilibrium"]["final_energy_excess_N_mm"]], rtol=1e-10, atol=1e-14)
    result = WeaveEquilibrium(initial, relaxed, pm["equilibrium"], tuple(pm["history"]),
                             p.sha256, p.state_sha256(relaxed))
    yarns = [YarnSpec.from_dict(config[k]) for k in ("warp_yarn", "weft_yarn")]
    scenes, geometry_checks, projections = {}, {}, {}
    for state, heights in (("initial", initial), ("relaxed", result)):
        saved = load_hierarchy(pair / state)
        rebuilt = build_relaxed_hierarchy(p, heights, *yarns, subdivisions=config["subdivisions"], seed=config["seed"])
        if len(saved.fiber_records) != len(rebuilt.fiber_records):
            raise ValueError("saved hierarchy fiber count differs from the mechanical reconstruction")
        for a, b in zip(saved.fiber_records, rebuilt.fiber_records):
            if (a.fiber_id, a.yarn_id, a.ply_id, a.material_id) != (b.fiber_id, b.yarn_id, b.ply_id, b.material_id):
                raise ValueError("saved hierarchy parent/material identities changed")
            np.testing.assert_allclose(a.points_mm, b.points_mm, rtol=0, atol=2e-13)
            np.testing.assert_array_equal(a.radii_mm, b.radii_mm)
        clearance = audit_clearance(saved)
        if not clearance["certified_separated"]:
            raise ValueError("saved hierarchy failed freshly recomputed different-fiber clearance")
        scene = OpticalScene.load(optics / f"{state}_optical_scene.json")
        if from_hierarchy(saved, scene.materials, scene.background_n).sha256 != scene.sha256:
            raise ValueError("optical scene differs from the supplied saved hierarchy")
        scenes[state] = scene
        geometry_checks[state] = {"fiber_count": len(saved.fiber_records), "scene_sha256": scene.sha256,
                                 "recomputed_clearance": clearance}
        manifest = read_json(optics / f"{state}_curves/manifest.json")
        digest = manifest.pop("manifest_sha256", None)
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if hashlib.sha256(canonical.encode()).hexdigest() != digest or manifest["scene_sha256"] != scene.sha256:
            raise ValueError("export manifest is not bound to the saved optical scene")
        for group in manifest["groups"]:
            curve_path = (optics / f"{state}_curves" / group["filename"]).resolve()
            if not curve_path.is_relative_to((optics / f"{state}_curves").resolve()) or sha256(curve_path) != group["file_sha256"]:
                raise ValueError("exported curve file hash mismatch")
        volume = om["common_averaging_volume_mm3"]
        with np.load(optics / f"{state}_projected_area_fits.npz", allow_pickle=False) as z:
            directions, truth = z["heldout_directions"], z["heldout_truth_per_mm"]
            recomputed = projected_area_density(scene, directions, volume)["all"]
            np.testing.assert_allclose(recomputed, truth, rtol=2e-12, atol=2e-12)
            rms = float(np.sqrt(np.mean(truth**2)))
            rows = []
            for level in om["projection_fits"][state]["levels"]:
                prediction = z[level["level"] + "_heldout_prediction_per_mm"]
                fitted = np.zeros_like(prediction)
                for group in level["fit_groups"].values():
                    s = np.asarray(group["matrix_per_mm2"])
                    if np.linalg.eigvalsh(s)[0] <= 0:
                        raise ValueError("saved SGGX matrix is not positive definite")
                    fitted += np.sqrt(np.einsum("ij,jk,ik->i", directions, s, directions))
                np.testing.assert_allclose(prediction, fitted, rtol=2e-12, atol=2e-12)
                error = float(np.sqrt(np.mean((prediction-truth)**2)) / rms)
                np.testing.assert_allclose(error, level["heldout_relative_rmse"], rtol=1e-10, atol=1e-12)
                rows.append({"level": level["level"], "recomputed_relative_rmse": error})
            projections[state] = rows
    cie_nm, cie_xyz = load_cie1931()
    union = np.array([np.minimum.reduce([scene.bounds_mm[0] for scene in scenes.values()]),
                      np.maximum.reduce([scene.bounds_mm[1] for scene in scenes.values()])])
    np.testing.assert_allclose(union, om["common_union_bounds_mm"], rtol=0, atol=2e-13)
    np.testing.assert_allclose(np.prod(union[1]-union[0]), om["common_averaging_volume_mm3"], rtol=1e-12)
    observations, raw_counts = [], 0
    if om["render_status"] == "executed":
        stacks = {}
        for state in STATES:
            if set(om["render_runs"][state]) != set(LIGHTS):
                raise ValueError("missing or extra lighting runs")
            for light in LIGHTS:
                info = om["render_runs"][state][light]
                with np.load(optics / f"{state}_{light}_radiance.npz", allow_pickle=False) as z:
                    stack, nm, seeds = z["radiance"], z["wavelengths_nm"], z["seeds"]
                    size = info["render_config"]["resolution"]
                    if stack.shape != (len(seeds), size, size, len(nm)) or not np.isfinite(stack).all() or stack.min() < -1e-7:
                        raise ValueError("invalid raw radiance array")
                    np.testing.assert_array_equal(nm, info["wavelengths_nm"])
                    np.testing.assert_array_equal(seeds, info["seeds"])
                    if len(seeds)*len(nm) != info["actual_render_count"] or len(set(map(int, seeds))) != len(seeds):
                        raise ValueError("raw render counts or independent seeds disagree")
                    stacks[state, light] = (stack.copy(), nm.copy(), seeds.copy())
                    raw_counts += len(seeds)*len(nm)
            with np.load(optics / f"{state}_reflection_warp_fine_radiance.npz", allow_pickle=False) as z:
                fine, fine_nm, seeds = z["radiance"], z["wavelengths_nm"], z["seeds"]
                coarse, coarse_nm, coarse_seeds = stacks[state, "reflection_warp"]
                if fine.shape != coarse.shape[:-1] + (2*len(coarse_nm)-1,) or not np.isfinite(fine).all() or fine.min() < -1e-7:
                    raise ValueError("invalid nested fine spectral array")
                np.testing.assert_array_equal(fine[..., ::2], coarse)
                np.testing.assert_array_equal(fine_nm[::2], coarse_nm)
                np.testing.assert_array_equal(seeds, coarse_seeds)
                info = om["spectral_fine_grid_render_runs"][state]
                np.testing.assert_array_equal(fine_nm[1::2], info["wavelengths_nm"])
                np.testing.assert_array_equal(seeds, info["seeds"])
                count = len(seeds)*len(fine_nm[1::2])
                if count != info["actual_render_count"]:
                    raise ValueError("nested refinement count disagrees with raw samples")
                raw_counts += count
        for record in om["paired_observation_comparisons"]:
            light, temperature = record["light"], record["temperature_kelvin"]
            a, nm, seeds = stacks["initial", light]
            b, nm_b, seeds_b = stacks["relaxed", light]
            np.testing.assert_array_equal(nm, nm_b)
            np.testing.assert_array_equal(seeds, seeds_b)
            weights, _ = spectral_xyz_weights(nm, cie_nm, cie_xyz, planck_relative(cie_nm, temperature))
            before, after = [integrate_xyz(x.mean(axis=(1, 2)), weights) for x in (a, b)]
            interval = paired_mean_interval(before, after)
            for key in ("mean_delta", "standard_error", "interval_low", "interval_high"):
                np.testing.assert_allclose(interval[key], record["xyz_interval"][key], rtol=1e-10, atol=1e-12)
            np.testing.assert_allclose(before.mean(axis=0), record["initial_mean_xyz"], rtol=1e-10, atol=1e-12)
            np.testing.assert_allclose(after.mean(axis=0), record["relaxed_mean_xyz"], rtol=1e-10, atol=1e-12)
            relative = float((after[:, 1].mean()-before[:, 1].mean())/before[:, 1].mean())
            np.testing.assert_allclose(relative, record["relative_mean_Y_change"], rtol=1e-10, atol=1e-12)
            observations.append({"light": light, "temperature_kelvin": temperature, "relative_mean_Y_change": relative,
                                 "paired_replicates": len(seeds), "recomputed_Y_interval": [interval["interval_low"][1], interval["interval_high"][1]]})
        if {(x["light"], x["temperature_kelvin"]) for x in observations} != {(l, t) for l in LIGHTS for t in (3000, 6500)} or len(observations) != 6:
            raise ValueError("paired observations must contain all six distinct lighting/source combinations")
        if raw_counts != om["actual_explicit_fiber_render_count"]:
            raise ValueError("recorded explicit-fiber render total disagrees with saved raw sample counts")
    current_artifacts = {str(path.resolve()): sha256(path) for folder in (mechanics, optics)
                         for path in sorted(folder.rglob("*")) if path.is_file()}
    if input_artifacts != current_artifacts:
        raise ValueError("input experiment artifacts changed during verification")
    record = {"schema": "textile-engine-v3-artifact-verification/1.0", "status": "passed",
              "created_utc": utc_now(), "mechanics_directory": str(mechanics.resolve()),
              "optical_directory": str(optics.resolve()), "source_sha256": sources,
              "input_artifact_sha256": input_artifacts,
              "mechanical_problem_sha256": p.sha256, "mechanical_state_sha256": p.state_sha256(relaxed),
              "energy_excess_N_mm": {"initial": energies[0], "relaxed": energies[1]},
              "recomputed_kkt": kkt, "geometry": geometry_checks, "projection": projections,
              "observations": observations, **render_record,
              "renders_executed_by_this_verification": 0, "raw_explicit_fiber_samples_verified": raw_counts,
              "scope": ["Source and artifact consistency with fresh optical-pair KKT, geometry reconstruction and different-fiber clearance checks.",
                        "SGGX projected-area predictions and paired CIE/Planck means/intervals recomputed from saved arrays.",
                        "Saved radiance is checked, not re-rendered; this does not validate a measured textile or every mechanics sweep.",
                        "No aggregate fabric BSDF, coherent-wave transport, fiber mass conservation or metasurface superiority is established."]}
    write_json(Path(output) / "artifact_verification.json", record)
    print(json.dumps({"status": "passed", "verified_saved_renders": raw_counts, "renders_executed": 0,
                      "output": str(Path(output) / "artifact_verification.json")}), flush=True)
    return 0


def check_stage_outputs(item, no_render):
    directory = Path(item.output_directory)
    for name in item.required_outputs:
        if not (directory / name).is_file():
            raise RuntimeError("required stage output missing: " + str(directory / name))
    if item.stage == "mechanics":
        record = read_json(directory / "experiment_manifest.json")
        check_source_hashes(record)
        if record["optical_pair_reused"]:
            raise RuntimeError("a new mechanics stage unexpectedly reused a frozen pair")
    elif item.stage == "optics":
        record = read_json(directory / "optical_scale_metrics.json")
        check_source_hashes(record)
        check_render_record(record, "not_requested" if no_render else "executed")
    elif item.stage == "tests":
        record = read_json(directory / "test_summary.json")
        if not record["tests_run"] or record["failures"] or record["errors"] or record["skipped"]:
            raise RuntimeError("complete tests require zero failures, errors and skips")
    elif read_json(directory / "artifact_verification.json")["status"] != "passed":
        raise RuntimeError("artifact verification did not pass")


def source_inputs():
    files = {ROOT / "run_engine_v3.py", ROOT / "run_engine_v2.py", ROOT / "run_weave_mechanics_experiments.py",
             ROOT / "run_multiscale_optics_v3.py", ROOT / "requirements.txt",
             ROOT / "data/optical_v3/cie/CIE_xyz_1931_2deg.csv"}
    files.update((ROOT / "textile_sim").glob("*.py"))
    files.update((ROOT / "tests").glob("*.py"))
    files.update((ROOT / "examples/mechanics").glob("*.json"))
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(files)}


def execute_plan(plan, output, env, manifest):
    output = Path(output)
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    target = output / "run_manifest.json"
    started = time.perf_counter()
    manifest.update(status="running", started_utc=utc_now(), records=[], explicit_fiber_renders_executed=0,
                    past_explicit_fiber_renders_verified=0)
    write_json(target, manifest)
    final_code = 0
    for index, item in enumerate(plan):
        log = logs / f"{index+1:02d}_{item.stage}.log"
        record = {**asdict(item), "cwd": str(ROOT), "started_utc": utc_now(), "status": "running", "log": str(log.relative_to(output))}
        manifest["records"].append(record)
        if item.stage == "optics" and not manifest["no_experiment_render"]:
            # A driver may fail after producing some wavelength images, before
            # it writes its final metrics. Zero would incorrectly assert that
            # no renders occurred. Only a successful, checked stage knows the
            # exact total; interrupted/failed partial runs retain null.
            manifest["explicit_fiber_renders_executed"] = None
        write_json(target, manifest)
        print(json.dumps({"stage": item.stage, "command": item.command, "log": str(log)}), flush=True)
        tick, error = time.perf_counter(), None
        try:
            with log.open("w", encoding="utf-8") as stream:
                code = subprocess.run(item.command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False).returncode
            if code == 0:
                check_stage_outputs(item, manifest["no_experiment_render"])
        except KeyboardInterrupt:
            code, error = 130, "interrupted by user"
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            code, error = 1, str(exc)
        if not log.is_file():
            log.write_text((error or "subprocess did not create a log") + "\n", encoding="utf-8")
        record.update(status="passed" if code == 0 else "failed", exit_code=code, finished_utc=utc_now(),
                      elapsed_seconds=time.perf_counter()-tick, log_sha256=sha256(log),
                      output_sha256=stage_hashes(item.output_directory, output))
        if error:
            record["error"] = error
        if code == 0 and item.stage == "optics":
            manifest["explicit_fiber_renders_executed"] = read_json(Path(item.output_directory)/"optical_scale_metrics.json")["actual_explicit_fiber_render_count"]
        if code == 0 and item.stage == "verify":
            manifest["past_explicit_fiber_renders_verified"] = read_json(Path(item.output_directory)/"artifact_verification.json")["raw_explicit_fiber_samples_verified"]
        write_json(target, manifest)
        print(json.dumps({key: record[key] for key in ("stage", "status", "exit_code", "elapsed_seconds")}), flush=True)
        if code:
            final_code = code if code > 0 else 128-code
            print(log.read_text(encoding="utf-8", errors="replace")[-12000:], file=sys.stderr)
            if error:
                print(error, file=sys.stderr)
            break
    final_hashes = source_inputs()
    changed = sorted(k for k in manifest["input_sha256"].keys() | final_hashes.keys()
                     if manifest["input_sha256"].get(k) != final_hashes.get(k))
    if changed:
        final_code = final_code or 1
    manifest.update(status="passed" if final_code == 0 else "failed", exit_code=final_code,
                    elapsed_seconds=time.perf_counter()-started, finished_utc=utc_now(),
                    changed_source_files_during_run=changed,
                    unexecuted_commands=[asdict(x) for x in plan[len(manifest["records"]):]])
    manifest["output_sha256"] = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*"))
                                 if p.is_file() and p != target and p.suffix != ".tmp"}
    manifest["hash_scope"] = "All produced artifacts except the self-referential run manifest; input sources are hashed separately."
    write_json(target, manifest)
    print(json.dumps({"status": manifest["status"], "exit_code": final_code,
                      "explicit_fiber_renders_executed": manifest["explicit_fiber_renders_executed"],
                      "past_explicit_fiber_renders_verified": manifest["past_explicit_fiber_renders_verified"],
                      "changed_source_files_during_run": changed, "manifest": str(target)}), flush=True)
    return final_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--output", type=Path, help="new or empty output directory")
    parser.add_argument("--input-data", type=Path, default=ROOT / "data", help="source data root for omitted upstream stages")
    parser.add_argument("--no-render", action="store_true", help="skip the optical experiment renders; selected tests may still render")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing and run no subprocess")
    parser.add_argument("--threads", type=positive_int, default=1)
    parser.add_argument("--resolution", type=positive_int, default=64)
    parser.add_argument("--spp", type=positive_int, default=32)
    parser.add_argument("--replicates", type=positive_int, default=4)
    parser.add_argument("--_worker", choices=("verify", "tests"), help=argparse.SUPPRESS)
    parser.add_argument("--_mechanics", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--_optics", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--_expected-render", choices=("any", "executed", "not_requested"), default="any", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._worker:
        if args.output is None or args.dry_run:
            parser.error("internal worker needs --output and cannot use --dry-run")
        if args._worker == "tests":
            return run_tests(args.output)
        if args._mechanics is None or args._optics is None:
            parser.error("verification worker requires both input directories")
        return verify_artifacts(args._mechanics, args._optics, args.output, args._expected_render)
    output = (args.output or ROOT / "data/engine_v3_runs" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")).resolve()
    try:
        plan = make_plan(output, args.stages, input_data=args.input_data, no_render=args.no_render,
                         resolution=args.resolution, spp=args.spp, replicates=args.replicates)
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps({"dry_run": True, "writes": False, "cwd": str(ROOT), "output": str(output),
                          "plan": [asdict(x) for x in plan], "notes": [
                              "Omitted upstream stages use --input-data; regenerated mechanics and optics use this output.",
                              "Verify recomputes saved evidence and executes zero renders.",
                              "--no-render applies to the optical experiment, not the complete tests stage.",
                              "Pinned official CIE data is read from the repository, with its published checksum."]}, indent=2))
        return 0
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be new or empty; existing run evidence is preserved")
    env = os.environ.copy()
    for key in THREAD_VARIABLES:
        env[key] = str(args.threads)
    env.update(MPLBACKEND="Agg", PYTHONUNBUFFERED="1")
    manifest = {"schema": "textile-engine-v3-run/1.0", "root": str(ROOT), "output": str(output),
                "input_data": str(args.input_data.resolve()), "selected_stages": [s for s in STAGES if s in args.stages],
                "requested_stages": args.stages, "no_experiment_render": args.no_render,
                "tests_may_execute_small_renderer_checks": "tests" in args.stages,
                "invocation": [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)],
                "environment": environment_record(env), "input_sha256": source_inputs(),
                "scope": "Synthetic reduced mechanics, geometric optical reduction and explicit-fiber spectral ray experiments; no real textile calibration."}
    return execute_plan(plan, output, env, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
