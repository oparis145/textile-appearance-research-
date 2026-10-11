#!/usr/bin/env python3
"""Reproduce the v2 hierarchy and optical bridge with auditable stage records.

Examples (run from any working directory):
  python run_engine_v2.py --stages geometry refinement optics tests --dry-run
  python run_engine_v2.py --stages geometry refinement --output data/new_geometry_run
  python run_engine_v2.py --stages optics tests --no-render --output data/new_bridge_run

The five saved examples/hierarchy/*.json files are the geometry source. The
refinement stage calls compare_sampling_refinement() for genuine 1/2/4 meshes;
the optics stage invokes the existing bridge experiment driver. That driver
has its own explicitly configured 98-fiber specimen, not all five geometries.
The tests stage discovers the complete suite and fails on failures OR skips.
It checks legacy recorded experiment evidence without regenerating it.

Install requirements.txt first. No dependencies are installed or downloaded by
this runner. All new outputs/logs/manifests are written beneath --output; an
existing nonempty output is rejected. Dry-run prints JSON and writes nothing.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parent
STAGES = ("geometry", "refinement", "optics", "tests")
CASES = (
    "plain_single_ply", "twill_two_ply", "basket_rectangular_three_ply",
    "twill_migration_waviness", "twill_loop_excursions",
)
THREAD_VARIABLES = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)
RECORDED_TEST_INPUTS = (
    "data/render_validation_metrics.json",
    "data/fiber_wave_gaussian_beam.npz",
    "data/fiber_wave_gaussian_beam_metrics.json",
)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def positive_int(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


@dataclass(frozen=True)
class StageCommand:
    stage: str
    case: str
    command: tuple[str, ...]
    output_directory: str
    required_outputs: tuple[str, ...] = ()

    @property
    def label(self):
        return self.stage + ("_" + self.case if self.case else "")


def make_plan(output, selected, *, no_render=False, resolution=128, spp=64,
              max_candidate_pairs=8_000_000):
    """Return commands without importing numerical modules or creating files."""
    output = Path(output).resolve()
    selected = tuple(selected)
    if len(set(selected)) != len(selected) or any(s not in STAGES for s in selected):
        raise ValueError("stages must be distinct members of geometry/refinement/optics/tests")
    plan = []
    python = (sys.executable, "-u")
    for stage in STAGES:
        if stage not in selected:
            continue
        if stage in ("geometry", "refinement"):
            for case in CASES:
                config = ROOT / "examples" / "hierarchy" / (case + ".json")
                target = output / "hierarchy_v2" / case if stage == "geometry" else output / "refinement" / case
                if stage == "geometry":
                    command = python + ("-m", "textile_sim.hierarchy", "--config", str(config),
                                        "--out", str(target), "--max-candidate-pairs", str(max_candidate_pairs))
                    required = ("hierarchy_geometry.npz", "hierarchy_geometry.json", "hierarchy_metrics.json")
                else:
                    command = python + (str(ROOT / "run_engine_v2.py"), "--_worker", "refinement",
                                        "--_config", str(config), "--output", str(target))
                    required = ("sampling_refinement_metrics.json",)
                plan.append(StageCommand(stage, case, command, str(target), required))
        elif stage == "optics":
            target = output / "optical_bridge_v2"
            command = python + (str(ROOT / "run_optical_bridge_experiments.py"), "--output", str(target),
                                "--resolution", str(resolution), "--spp", str(spp))
            if no_render:
                command += ("--skip-render",)
            plan.append(StageCommand(stage, "", command, str(target), ("optical_bridge_metrics.json",)))
        else:
            target = output / "tests"
            command = python + (str(ROOT / "run_engine_v2.py"), "--_worker", "tests", "--output", str(target))
            plan.append(StageCommand(stage, "", command, str(target), ("test_summary.json", "tests.log")))
    return plan


def input_hashes(selected):
    files = set(ROOT.glob("*.py"))
    for folder in ("textile_sim", "tests"):
        files.update((ROOT / folder).glob("*.py"))
    files.update((ROOT / "examples" / "hierarchy").glob("*.json"))
    files.add(ROOT / "requirements.txt")
    if "tests" in selected:
        files.update(ROOT / name for name in RECORDED_TEST_INPUTS)
    return {str(p.relative_to(ROOT)): sha256(p) if p.is_file() else None
            for p in sorted(files)}


def environment_record(env):
    packages = {}
    for name in ("numpy", "scipy", "matplotlib", "pillow", "mitsuba", "drjit"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            # render.py may load a local .sim_deps directory. Do not mistake
            # missing distribution metadata for a failed numerical experiment.
            packages[name] = None
    return {"python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "packages_on_python_path": packages,
            "numeric_threads": {key: env[key] for key in THREAD_VARIABLES if key in env},
            "MPLBACKEND": env.get("MPLBACKEND"),
            "version_scope": "Distribution metadata; renderer also records its actually loaded version."}


def run_refinement(config, output):
    from textile_sim.hierarchy import FabricSpec, compare_sampling_refinement

    config = Path(config)
    started = time.perf_counter()
    spec = FabricSpec.from_dict(json.loads(config.read_text(encoding="utf-8")))
    result = compare_sampling_refinement(spec, factors=(1, 2, 4))
    samples = result["samples_per_crossing"]
    if any(b < 2 * a for a, b in zip(samples, samples[1:])):
        raise RuntimeError("refinement did not produce genuinely distinct 1/2/4 sampling levels")
    result.update(config_sha256=sha256(config), config=str(config.resolve()),
                  seconds=time.perf_counter() - started)
    write_json(Path(output) / "sampling_refinement_metrics.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return 0


def run_tests(output):
    """Use the same complete discovery and no-skips policy as validate_all.py."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (output / "tests.log").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = {"tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped),
              "elapsed_seconds": time.perf_counter() - started,
              "failure_details": [[str(t), detail] for t, detail in result.failures],
              "error_details": [[str(t), detail] for t, detail in result.errors],
              "skipped_details": [[str(t), reason] for t, reason in result.skipped],
              "scope": "Complete unittest discovery; recorded legacy scene gates are checked, not re-rendered."}
    write_json(output / "test_summary.json", record)
    print(json.dumps(record, indent=2), flush=True)
    if not result.wasSuccessful() or result.skipped:
        print((output / "tests.log").read_text(encoding="utf-8")[-16000:], file=sys.stderr)
    return 1 if not result.wasSuccessful() else (2 if result.skipped else 0)


def check_stage_outputs(item):
    directory = Path(item.output_directory)
    for name in item.required_outputs:
        if not (directory / name).is_file():
            raise RuntimeError("required stage output missing: " + str(directory / name))
    if item.stage == "geometry":
        record = json.loads((directory / "hierarchy_metrics.json").read_text(encoding="utf-8"))
        if record["clearance_audit"]["certified_separated"] is not True:
            raise RuntimeError("generated geometry lacks a positive different-fiber clearance certificate")
    elif item.stage == "optics":
        record = json.loads((directory / "optical_bridge_metrics.json").read_text(encoding="utf-8"))
        if record["fabric_polyline_clearance"]["certified_separated"] is not True:
            raise RuntimeError("optical specimen failed its clearance certificate")
    elif item.stage == "tests":
        record = json.loads((directory / "test_summary.json").read_text(encoding="utf-8"))
        if record["failures"] or record["errors"] or record["skipped"] or not record["tests_run"]:
            raise RuntimeError("complete tests must run at least once with zero failures, errors, and skips")


def stage_hashes(directory, output):
    directory, output = Path(directory), Path(output)
    if not directory.exists():
        return {}
    return {str(path.relative_to(output)): sha256(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def execute_plan(plan, output, env, manifest):
    """Execute serially, persist each result, and stop on the first failed gate."""
    output = Path(output)
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "run_manifest.json"
    manifest.update(status="running", started_utc=utc_now(), records=[])
    write_json(manifest_path, manifest)
    started = time.perf_counter()
    final_code = 0
    for i, item in enumerate(plan):
        log = logs / f"{i + 1:02d}_{item.label}.log"
        record = {**asdict(item), "cwd": str(ROOT), "started_utc": utc_now(),
                  "status": "running", "log": str(log.relative_to(output))}
        manifest["records"].append(record)
        write_json(manifest_path, manifest)
        print(json.dumps({"stage": item.stage, "case": item.case,
                          "command": item.command, "log": str(log)}), flush=True)
        tick = time.perf_counter()
        error = None
        try:
            with log.open("w", encoding="utf-8") as stream:
                process = subprocess.run(item.command, cwd=ROOT, env=env,
                                         stdout=stream, stderr=subprocess.STDOUT, check=False)
            code = process.returncode
            if code == 0:
                check_stage_outputs(item)
        except KeyboardInterrupt:
            code, error = 130, "interrupted by user"
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            code, error = 1, str(exc)
        if not log.exists():
            log.write_text((error or "subprocess did not create a log") + "\n", encoding="utf-8")
        record.update(finished_utc=utc_now(), elapsed_seconds=time.perf_counter() - tick,
                      exit_code=code, status="passed" if code == 0 else "failed",
                      log_sha256=sha256(log), output_sha256=stage_hashes(item.output_directory, output))
        if error:
            record["error"] = error
        write_json(manifest_path, manifest)
        print(json.dumps({key: record[key] for key in
                          ("stage", "case", "status", "exit_code", "elapsed_seconds")}), flush=True)
        if code:
            final_code = code if code > 0 else 128 - code
            print(log.read_text(encoding="utf-8", errors="replace")[-12000:], file=sys.stderr)
            if error:
                print(error, file=sys.stderr)
            break
    manifest.update(status="passed" if final_code == 0 else "failed", exit_code=final_code,
                    elapsed_seconds=time.perf_counter() - started, finished_utc=utc_now(),
                    unexecuted_commands=[asdict(item) for item in plan[len(manifest["records"]):]])
    if "refinement" in manifest.get("selected_stages", ()):
        combined = {}
        for case in CASES:
            path = output / "refinement" / case / "sampling_refinement_metrics.json"
            if path.is_file():
                combined[case] = json.loads(path.read_text(encoding="utf-8"))
        if combined:
            write_json(output / "refinement" / "sampling_refinement_metrics.json", combined)
    manifest["output_sha256"] = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path != manifest_path and path.suffix != ".tmp"
    }
    manifest["hash_scope"] = "All run artifacts except this self-referential manifest; source hashes are recorded separately."
    write_json(manifest_path, manifest)
    print(json.dumps({"status": manifest["status"], "exit_code": final_code,
                      "manifest": str(manifest_path)}), flush=True)
    return final_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=["geometry", "optics", "tests"],
                        help="selected stages; canonical execution order is geometry, refinement, optics, tests")
    parser.add_argument("--output", type=Path,
                        help="new or empty output directory; relative paths resolve from current working directory")
    parser.add_argument("--no-render", action="store_true",
                        help="skip four optical experiment renders; requested tests still include small CPU render checks")
    parser.add_argument("--dry-run", action="store_true", help="print JSON plan; do not create directories or run subprocesses")
    parser.add_argument("--threads", type=positive_int, default=1)
    parser.add_argument("--resolution", type=positive_int, default=128)
    parser.add_argument("--spp", type=positive_int, default=64)
    parser.add_argument("--max-candidate-pairs", type=positive_int, default=8_000_000)
    parser.add_argument("--_worker", choices=("refinement", "tests"), help=argparse.SUPPRESS)
    parser.add_argument("--_config", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._worker:
        if args.dry_run:
            parser.error("internal workers cannot be combined with --dry-run")
        if args.output is None:
            parser.error("internal workers require --output")
        if args._worker == "refinement":
            if args._config is None:
                parser.error("refinement worker requires --_config")
            return run_refinement(args._config, args.output)
        return run_tests(args.output)
    if len(set(args.stages)) != len(args.stages):
        parser.error("duplicate stages are not allowed")
    output = (args.output if args.output is not None else
              ROOT / "data" / "engine_v2_runs" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")).resolve()
    plan = make_plan(output, args.stages, no_render=args.no_render, resolution=args.resolution,
                     spp=args.spp, max_candidate_pairs=args.max_candidate_pairs)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "output": str(output), "cwd": str(ROOT),
                          "writes": False, "plan": [asdict(item) for item in plan],
                          "notes": ["All five source configs are loaded when their stages execute.",
                                    "Optics uses the bridge driver's own mixed-material 98-fiber case.",
                                    "Tests require committed legacy recorded inputs and include small CPU renderer checks."]}, indent=2))
        return 0
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be a new or empty directory; existing run evidence is preserved")
    env = os.environ.copy()
    for key in THREAD_VARIABLES:
        env[key] = str(args.threads)
    env["MPLBACKEND"] = "Agg"
    env["PYTHONUNBUFFERED"] = "1"
    selected = [stage for stage in STAGES if stage in args.stages]
    manifest = {"schema": "textile-engine-v2-run/1.0", "root": str(ROOT), "output": str(output),
                "selected_stages": selected, "requested_stages": args.stages,
                "no_experiment_render": args.no_render, "invocation": [sys.executable, str(Path(__file__).resolve()),
                                                                         *(sys.argv[1:] if argv is None else argv)],
                "environment": environment_record(env), "input_sha256": input_hashes(selected),
                "scope": "Reproduces synthetic geometric/numerical experiments; does not establish measured fabric fidelity."}
    return execute_plan(plan, output, env, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
