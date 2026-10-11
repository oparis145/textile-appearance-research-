"""Reproduce selected research stages with explicit subprocesses and logs.

Run from anywhere: python /path/to/textile_lab/run_all.py --stages tests wave
No third-party repository cloning or downloads are performed by this runner.
Install requirements.txt first. Results are written inside this project.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STAGES = {
    "tests": ["validate_all.py"],
    "wave": ["-m", "textile_sim.fiber_wave"],
    "ray": ["-m", "textile_sim.ply_ray", "--output-dir", "data"],
    "match": ["-m", "textile_sim.fiber_wave", "--textile-benchmark"],
    "beam": ["-m", "textile_sim.fiber_wave_beam"],
    "measurement": ["-m", "textile_sim.angular_measurement"],
    "surrogate": ["-m", "textile_sim.angular_surrogate"],
    "aperture": ["-m", "textile_sim.aperture_wave", "--output", "data"],
    "fabric": ["run_fabric_experiments.py"],
    "meta": ["-m", "textile_sim.meta_optics", "--output", "data"],
    "render-checks": ["validate_render.py", "--phase", "all"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="+", choices=tuple(STAGES),
                        default=list(STAGES))
    parser.add_argument("--quick-fabric", action="store_true",
                        help="Only lower the fabric render resolution/spp; not a reference result")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs = ROOT / "data" / "reproduction_logs" / stamp
    if not args.dry_run:
        logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MPLBACKEND", "Agg")
    records = []
    for name in args.stages:
        command = [sys.executable, "-u", *STAGES[name]]
        if name == "fabric" and args.quick_fabric:
            command.append("--quick")
        print(name + ": " + " ".join(command), flush=True)
        if args.dry_run:
            continue
        start = time.perf_counter()
        path = logs / (name + ".log")
        with path.open("w", encoding="utf-8") as stream:
            process = subprocess.run(command, cwd=ROOT, env=env,
                                     stdout=stream, stderr=subprocess.STDOUT)
        record = {"stage": name, "command": command,
                  "seconds": time.perf_counter() - start,
                  "exit_code": process.returncode,
                  "log": str(path.relative_to(ROOT))}
        records.append(record)
        (logs / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(json.dumps(record), flush=True)
        if process.returncode:
            print(path.read_text(encoding="utf-8")[-12000:], file=sys.stderr)
            raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
