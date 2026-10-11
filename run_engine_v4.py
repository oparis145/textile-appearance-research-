#!/usr/bin/env python3
"""Reproduce or audit material-coordinate textile transport in isolated outputs.

Stages execute in experiment -> verify -> tests order.  The experiment consumes
--input-data/mechanics_v3/optical_pair.  Verify consumes the new experiment when
selected, or --input-data/material_transport_v4 otherwise.  --no-render skips
only the experiment's optical renders; the complete tests may run small CPU
renderer checks.  A dry run imports only stdlib and writes nothing.

Examples (from any working directory):
  python run_engine_v4.py --dry-run
  python run_engine_v4.py --stages verify --output scratch_runs/v4_audit
  python run_engine_v4.py --stages experiment verify --no-render --output scratch_runs/v4_geometry
  python run_engine_v4.py --output scratch_runs/v4_full

No downloads, automatic installations, or overwriting of existing run evidence.
Hashes bind source files and read-only input artifacts at both ends of a run.
The render count includes explicit-fiber experiment renders, not rays or the
small renders inside tests.  Failed partial render batches retain an unknown
count (null), rather than an invented zero.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_engine_v2 import (RECORDED_TEST_INPUTS, StageCommand, THREAD_VARIABLES,
    environment_record, positive_int, run_tests, sha256, stage_hashes, utc_now, write_json)

ROOT = Path(__file__).resolve().parent
STAGES = ("experiment", "verify", "tests")
OPTICAL_STATES = ("initial", "regenerated", "transported")
LIGHTS = ("R0", "R90", "T45")
WAVELENGTHS_NM = (450., 550., 650.)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _integer(value, minimum, name):
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def reused_inputs(selected, input_data):
    """Explicit file/folder scope read by the selected stages and saved tests."""
    selected, data = tuple(selected), Path(input_data).resolve()
    paths = set()
    if "experiment" in selected:
        paths.add(data/"mechanics_v3/optical_pair")
    if "verify" in selected and "experiment" not in selected:
        paths.add(data/"material_transport_v4")
    if "tests" in selected:
        paths.update(ROOT/name for name in RECORDED_TEST_INPUTS)
        paths.add(ROOT/"data/optical_v3/optical_scale_metrics.json")
        paths.add(ROOT/"data/mechanics_v3/optical_pair")
    return tuple(sorted(path.resolve() for path in paths))


def _check_overlap(output, paths):
    output = Path(output).resolve()
    for raw in paths:
        path = Path(raw).resolve()
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError("output must not overlap read-only input paths: "+str(path))


def make_plan(output, selected, *, input_data=None, no_render=False,
              resolution=64, spp=32, replicates=4, max_render_count=108):
    """Wire the actual CLI dependency graph without reading data or importing science."""
    output = Path(output).resolve()
    data = (ROOT/"data" if input_data is None else Path(input_data)).resolve()
    selected = tuple(selected)
    if not selected or len(set(selected)) != len(selected) or any(stage not in STAGES for stage in selected):
        raise ValueError("select distinct stages from experiment, verify, tests")
    if no_render and "experiment" not in selected:
        raise ValueError("--no-render only applies when the experiment stage is selected")
    _integer(resolution, 8, "resolution"); _integer(spp, 1, "spp")
    _integer(replicates, 2, "replicates"); _integer(max_render_count, 1, "max_render_count")
    planned_count = len(OPTICAL_STATES)*len(LIGHTS)*len(WAVELENGTHS_NM)*replicates
    if "experiment" in selected and not no_render and planned_count > max_render_count:
        raise ValueError(f"requested experiment requires {planned_count} renders, exceeding --max-render-count {max_render_count}")
    _check_overlap(output, reused_inputs(selected, data))
    _check_overlap(output, (ROOT/"textile_sim", ROOT/"tests", ROOT/"examples"))
    experiment = output/"experiment" if "experiment" in selected else data/"material_transport_v4"
    python = (sys.executable, "-u")
    plan = []
    for stage in STAGES:
        if stage not in selected:
            continue
        if stage == "experiment":
            target = experiment
            command = python+(str(ROOT/"run_material_transport_experiments.py"),
                "--pair-directory", str(data/"mechanics_v3/optical_pair"), "--output", str(target),
                "--resolution", str(resolution), "--spp", str(spp), "--replicates", str(replicates))
            if no_render:
                command += ("--no-render",)
            required = ("experiment_manifest.json", "geometry_metrics.json", "optics/optical_metrics.json")
        elif stage == "verify":
            target = output/"verification"
            command = python+(str(ROOT/"verify_material_transport_artifacts_v4.py"),
                              "--input", str(experiment), "--output", str(target))
            required = ("verification_summary.json",)
        else:
            target = output/"tests"
            command = python+(str(ROOT/"run_engine_v4.py"), "--worker-tests", "--output", str(target))
            required = ("test_summary.json", "tests.log")
        plan.append(StageCommand(stage, "", command, str(target), required))
    return plan


def source_inputs():
    files = set(ROOT.glob("*.py"))
    for folder in ("textile_sim", "tests"):
        files.update((ROOT/folder).glob("*.py"))
    for folder in ("examples/hierarchy", "examples/mechanics"):
        files.update((ROOT/folder).glob("*.json"))
    files.add(ROOT/"requirements.txt")
    return {str(path.relative_to(ROOT)): sha256(path) if path.is_file() else None for path in sorted(files)}


def input_hashes(paths, *, require_present=True):
    """Hash the complete declared folders; additions and deletion change the map."""
    hashes = {}
    for raw in paths:
        path = Path(raw).resolve()
        if not path.exists():
            if require_present:
                raise FileNotFoundError("required read-only input does not exist: "+str(path))
            hashes[str(path)] = None
        elif path.is_file():
            hashes[str(path)] = sha256(path)
        elif path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file())
            if not files:
                if require_present:
                    raise FileNotFoundError("required read-only input directory is empty: "+str(path))
                hashes[str(path)] = None
            for file in files:
                hashes[str(file.resolve())] = sha256(file)
        else:
            raise ValueError("input must be a regular file or directory: "+str(path))
    return hashes


def check_source_record(record):
    expected = record.get("source_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("experiment lacks source_sha256 provenance")
    for name, digest in expected.items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha256(path) != digest:
            raise ValueError("experiment source provenance mismatch: "+name)


def check_render_record(metrics, *, expected=None):
    """Verify counts from individual completed batches, not from a success flag."""
    status = metrics.get("status")
    if status not in ("rendered", "skipped") or (expected is not None and status != expected):
        raise ValueError("optical status contradicts the completed/requested experiment")
    count = _integer(metrics.get("actual_render_count"), 0, "actual_render_count")
    records = metrics.get("records")
    if not isinstance(records, list):
        raise ValueError("optical metrics must contain a completed-record list")
    if status == "skipped":
        if count or records or metrics.get("comparisons") or metrics.get("spectral_radiance_sha256"):
            raise ValueError("skipped optics cannot contain newly computed renders or observation comparisons")
    else:
        if (len(metrics.get("states", [])) != len(OPTICAL_STATES)
                or set(metrics["states"]) != set(OPTICAL_STATES)
                or tuple(metrics.get("wavelengths_nm", [])) != WAVELENGTHS_NM):
            raise ValueError("rendered experiment must contain all three states and specified wavelength channels")
        seeds = metrics.get("seeds")
        if (not isinstance(seeds, list) or len(seeds) < 2 or len(set(seeds)) != len(seeds)
                or any(not isinstance(seed, int) or isinstance(seed, bool) or seed < 0 for seed in seeds)):
            raise ValueError("rendered experiment requires independent integer seeds")
        pairs, total = set(), 0
        for record in records:
            key = (record.get("state"), record.get("light"))
            if key in pairs or key[0] not in OPTICAL_STATES or key[1] not in LIGHTS:
                raise ValueError("duplicate or unknown state/light render batch")
            pairs.add(key)
            subtotal = _integer(record.get("actual_render_count"), 1, "batch render count")
            if subtotal != len(seeds)*len(WAVELENGTHS_NM):
                raise ValueError("render batch count disagrees with its seed/wavelength budget")
            total += subtotal
        if pairs != {(state, light) for state in OPTICAL_STATES for light in LIGHTS} or total != count:
            raise ValueError("render total disagrees with complete per-batch records")
        digest = metrics.get("spectral_radiance_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("rendered raw radiance needs a SHA-256 binding")
    return {"status": status, "recorded_render_count": count}


def _argument(command, name):
    return command[command.index(name)+1]


def check_stage_outputs(item, *, no_render=False):
    directory = Path(item.output_directory)
    for name in item.required_outputs:
        if not (directory/name).is_file():
            raise RuntimeError("required stage output missing: "+str(directory/name))
    if item.stage == "experiment":
        manifest = read_json(directory/"experiment_manifest.json")
        if (manifest.get("status") != "passed" or manifest.get("requested_render") is not (not no_render)
                or manifest.get("input_hashes_unchanged") is not True or manifest.get("source_hashes_unchanged") is not True):
            raise ValueError("experiment manifest did not pass its requested execution/provenance gates")
        check_source_record(manifest)
        metrics = read_json(directory/"optics/optical_metrics.json")
        count = check_render_record(metrics, expected="skipped" if no_render else "rendered")["recorded_render_count"]
        if manifest.get("actual_render_count") != count:
            raise ValueError("experiment and optical render counts disagree")
        for name in ("resolution", "spp", "replicates"):
            if manifest.get(name) != int(_argument(item.command, "--"+name)):
                raise ValueError("experiment changed its requested "+name)
        if not no_render:
            if len(metrics["seeds"]) != manifest["replicates"]:
                raise ValueError("optical seed count differs from requested replicates")
            raw = directory/"optics/spectral_radiance.npz"
            if not raw.is_file() or sha256(raw) != metrics["spectral_radiance_sha256"]:
                raise ValueError("optical raw radiance file hash mismatch")
        return count
    if item.stage == "verify":
        metrics = read_json(directory/"verification_summary.json")
        if metrics.get("status") != "passed":
            raise ValueError("independent artifact verification did not pass")
        producer = read_json(Path(_argument(item.command, "--input"))/"experiment_manifest.json")
        if producer.get("status") != "passed":
            raise ValueError("saved producer experiment did not complete successfully")
        check_source_record(producer)
        optics = metrics.get("optics", {})
        count = _integer(optics.get("verified_saved_render_count"), 0, "verified_saved_render_count")
        if optics.get("status") not in ("rendered", "skipped") or ((optics["status"] == "skipped") != (count == 0)):
            raise ValueError("verification render status and saved count disagree")
        return count
    metrics = read_json(directory/"test_summary.json")
    _integer(metrics.get("tests_run"), 1, "tests_run")
    if any(metrics.get(key) != 0 for key in ("failures", "errors", "skipped")):
        raise ValueError("complete tests require zero failures, errors and skips")
    return None


def _changed(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def execute_plan(plan, output, env, manifest):
    """Run serially and persist failed stages without claiming missing evidence."""
    output = Path(output)
    logs = output/"logs"; logs.mkdir(parents=True, exist_ok=True)
    path = output/"run_manifest.json"
    start = time.perf_counter()
    manifest.update(status="running", started_utc=utc_now(), records=[],
                    explicit_fiber_renders_executed=0, saved_explicit_fiber_renders_verified=0)
    write_json(path, manifest)
    final_code = 0
    for index, item in enumerate(plan):
        log = logs/f"{index+1:02d}_{item.stage}.log"
        entry = {**asdict(item), "cwd": str(ROOT), "started_utc": utc_now(), "status": "running",
                 "log": str(log.relative_to(output))}
        manifest["records"].append(entry)
        if item.stage == "experiment" and not manifest["no_experiment_render"]:
            manifest["explicit_fiber_renders_executed"] = None
        if item.stage == "verify":
            manifest["saved_explicit_fiber_renders_verified"] = None
        write_json(path, manifest)
        print(json.dumps({"stage": item.stage, "command": item.command, "log": str(log)}), flush=True)
        tick, error, count = time.perf_counter(), None, None
        try:
            with log.open("w", encoding="utf-8") as stream:
                code = subprocess.run(item.command, cwd=ROOT, env=env,
                                      stdout=stream, stderr=subprocess.STDOUT, check=False).returncode
            if code == 0:
                count = check_stage_outputs(item, no_render=manifest["no_experiment_render"])
        except KeyboardInterrupt:
            code, error = 130, "interrupted by user"
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            code, error = 1, f"{type(exc).__name__}: {exc}"
        if not log.exists():
            log.write_text((error or "subprocess did not create a log")+"\n", encoding="utf-8")
        entry.update(status="passed" if code == 0 else "failed", exit_code=code, finished_utc=utc_now(),
                     elapsed_seconds=time.perf_counter()-tick, log_sha256=sha256(log),
                     output_sha256=stage_hashes(item.output_directory, output))
        if error:
            entry["error"] = error
        if code == 0 and item.stage == "experiment":
            manifest["explicit_fiber_renders_executed"] = count
        if code == 0 and item.stage == "verify":
            manifest["saved_explicit_fiber_renders_verified"] = count
        write_json(path, manifest)
        print(json.dumps({key: entry[key] for key in ("stage", "status", "exit_code", "elapsed_seconds")}), flush=True)
        if code:
            final_code = code if code > 0 else 128-code
            print(log.read_text(encoding="utf-8", errors="replace")[-12000:], file=sys.stderr)
            if error:
                print(error, file=sys.stderr)
            break
    provenance_error = None
    try:
        sources_final = source_inputs()
        inputs_final = input_hashes(manifest["read_only_input_paths"], require_present=False)
        source_changes = _changed(manifest["source_sha256_initial"], sources_final)
        input_changes = _changed(manifest["input_sha256_initial"], inputs_final)
    except (OSError, ValueError) as exc:
        provenance_error = f"{type(exc).__name__}: {exc}"
        sources_final, inputs_final, source_changes, input_changes = None, None, None, None
    if source_changes or input_changes or provenance_error:
        final_code = final_code or 1
    manifest.update(status="passed" if final_code == 0 else "failed", exit_code=final_code,
        finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
        source_sha256_final=sources_final, input_sha256_final=inputs_final,
        changed_source_files_during_run=source_changes, changed_input_files_during_run=input_changes,
        provenance_error=provenance_error,
        unexecuted_commands=[asdict(item) for item in plan[len(manifest["records"]):]])
    manifest["output_sha256_final"] = {str(file.relative_to(output)): sha256(file)
        for file in sorted(output.rglob("*")) if file.is_file() and file != path and file.suffix != ".tmp"}
    manifest["hash_scope"] = "Sources and declared read-only inputs before/after; all produced artifacts except the self-referential run manifest and temporary writes."
    write_json(path, manifest)
    print(json.dumps({"status": manifest["status"], "exit_code": final_code,
        "explicit_fiber_renders_executed": manifest["explicit_fiber_renders_executed"],
        "saved_explicit_fiber_renders_verified": manifest["saved_explicit_fiber_renders_verified"],
        "changed_source_files_during_run": source_changes, "changed_input_files_during_run": input_changes,
        "manifest": str(path)}), flush=True)
    return final_code


def _fresh_output(output, parser):
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be new or empty; existing run evidence is preserved")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input-data", type=Path, default=ROOT/"data")
    parser.add_argument("--no-render", action="store_true", help="skip experiment renders; selected tests may still render")
    parser.add_argument("--dry-run", action="store_true", help="print the real plan without numerical imports, writes, or execution")
    parser.add_argument("--resolution", type=positive_int, default=64)
    parser.add_argument("--spp", type=positive_int, default=32)
    parser.add_argument("--replicates", type=positive_int, default=4)
    parser.add_argument("--max-render-count", type=positive_int, default=108,
                        help="cap explicit experiment renders; increase explicitly with replicate budget")
    parser.add_argument("--threads", type=positive_int, default=1)
    parser.add_argument("--worker-tests", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_tests:
        if args.output is None or args.dry_run:
            parser.error("internal test worker requires --output and cannot use --dry-run")
        _fresh_output(args.output, parser)
        return run_tests(args.output)
    output = (args.output or ROOT/"scratch_runs/engine_v4_runs"/
              dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")).resolve()
    try:
        plan = make_plan(output, args.stages, input_data=args.input_data,
            no_render=args.no_render, resolution=args.resolution, spp=args.spp,
            replicates=args.replicates, max_render_count=args.max_render_count)
    except ValueError as exc:
        parser.error(str(exc))
    readonly = reused_inputs(args.stages, args.input_data)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "writes": False, "cwd": str(ROOT), "output": str(output),
            "plan": [asdict(item) for item in plan], "read_only_input_paths": [str(p) for p in readonly],
            "planned_explicit_fiber_renders": (27*args.replicates if "experiment" in args.stages and not args.no_render else 0),
            "notes": ["The experiment carries original material labels; no fiber stress or mass claim.",
                "Verify reads saved results and never re-renders them.",
                "--no-render applies to the experiment; complete tests may execute small renderer checks.",
                "No dependency installs or downloads are performed."]}, indent=2))
        return 0
    _fresh_output(output, parser)
    try:
        source_hashes, data_hashes = source_inputs(), input_hashes(readonly)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    env = os.environ.copy()
    for key in THREAD_VARIABLES:
        env[key] = str(args.threads)
    env.update(MPLBACKEND="Agg", PYTHONUNBUFFERED="1")
    manifest = {"schema_version": "textile-engine-v4-run/1.0", "root": str(ROOT), "output": str(output),
        "input_data": str(args.input_data.resolve()), "requested_stages": args.stages,
        "selected_stages": [stage for stage in STAGES if stage in args.stages],
        "no_experiment_render": args.no_render, "tests_may_execute_small_renderer_checks": "tests" in args.stages,
        "render_budget": {"resolution": args.resolution, "spp": args.spp,
                          "replicates": args.replicates, "max_render_count": args.max_render_count},
        "verified_input_origin": "new_experiment" if "experiment" in args.stages else "existing_artifact",
        "historical_external_input_paths_reread_by_verify": False,
        "invocation": [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)],
        "environment": environment_record(env), "read_only_input_paths": [str(p) for p in readonly],
        "source_sha256_initial": source_hashes, "input_sha256_initial": data_hashes,
        "output_sha256_initial": {},
        "scope": "Prescribed material-coordinate transport, discrete segment-volume diagnostics and synthetic monochromatic optics; no measured textile calibration. Counts of saved verified renders are not additional renders."}
    return execute_plan(plan, output, env, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
