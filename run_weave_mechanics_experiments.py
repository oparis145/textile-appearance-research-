"""Reproduce v3 reduced yarn mechanics, calibrated only to synthetic fixtures.

Writes data/figures to an explicit output folder. Existing numerical files are
replaced only when --reuse-existing is supplied. All experiments check independent
KKT gates; optical embeddings additionally require actual fiber capsule clearance.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from textile_sim.hierarchy import YarnSpec, audit_clearance, hex_ply, save_hierarchy
from textile_sim.weave_draft import WeaveDraft
from textile_sim.weave_mechanics import (SCHEMA_VERSION, YarnElasticity, ReducedWeaveSpec,
    ReducedWeaveProblem, solve_equilibrium, build_relaxed_hierarchy, beam_energy_gradient_hessian)

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def solve_case(spec):
    start = time.perf_counter()
    p = ReducedWeaveProblem(spec)
    r = solve_equilibrium(p)
    return p, r, {"spec": spec.to_dict(), "elapsed_seconds": time.perf_counter()-start,
                  "diagnostics": r.diagnostics, "history": r.history}


def optical_pair(output, config):
    p, r, result = solve_case(ReducedWeaveSpec.from_dict(config["mechanics"]))
    w, f = (YarnSpec.from_dict(config[key]) for key in ("warp_yarn", "weft_yarn"))
    metrics = {"schema_version": SCHEMA_VERSION, "config": p.spec.to_dict(), "equilibrium": r.diagnostics,
        "history": r.history, "seconds": result["elapsed_seconds"],
        "comparison_scope": "same topology/material labels, regenerated hierarchy on before/after yarn tracks; not a mass-conserving fiber deformation"}
    for name, state in (("initial", r.initial_heights_mm), ("relaxed", r)):
        geometry = build_relaxed_hierarchy(p, state, w, f, subdivisions=config["subdivisions"], seed=config["seed"])
        clearance = audit_clearance(geometry)
        if not clearance["certified_separated"]:
            raise RuntimeError("actual fiber clearance failed: "+json.dumps(clearance))
        geometry.metadata["clearance_audit"] = clearance
        save_hierarchy(output/name, geometry)
        metrics[name] = geometry.summary(); metrics[name]["clearance_audit"] = clearance
    np.savez_compressed(output/"mechanical_heights.npz", initial_mm=r.initial_heights_mm, relaxed_mm=r.heights_mm)
    write_json(output/"pair_metrics.json", metrics)
    return p, r, metrics


def run_sweeps(output):
    base = ReducedWeaveSpec(WeaveDraft.plain(), .012, .012)
    sweeps = {}
    for label, values in (("warp_bending_ratio", (.2, 1., 5., 20.)),
                          ("warp_flat_pretension_strain", (0., .005, .02, .05))):
        entries = []
        for value in values:
            warp = replace(base.warp_elasticity,
                **({"bending_stiffness_N_mm2": base.weft_elasticity.bending_stiffness_N_mm2*value}
                   if label == "warp_bending_ratio" else {"rest_fraction": 1/(1+value)}))
            p, r, record = solve_case(replace(base, warp_elasticity=warp))
            record["parameter_value"] = value
            entries.append(record)
        sweeps[label] = entries
    write_json(output/"parameter_sweeps.json", sweeps)
    return sweeps


def run_refinement(output, base):
    records, curves, solutions = [], [], []
    for n in (4, 8, 16):
        p, r, record = solve_case(replace(base, segments_per_crossing=n))
        record["segments_per_crossing"] = n
        records.append(record); curves.append(p.centerlines(r.heights_mm)); solutions.append(r.heights_mm)
    comparisons = []
    for index in range(2):
        distances = []
        for key, fine in curves[index+1].items():
            coarse = curves[index][key]
            axis = 1 if key[0] == "warp" else 0
            difference = np.interp(fine[:, axis], coarse[:, axis], coarse[:, 2])-fine[:, 2]
            distances.extend(difference)
        a = records[index]["diagnostics"]["final_energy_excess_N_mm"]
        b = records[index+1]["diagnostics"]["final_energy_excess_N_mm"]
        comparisons.append({"coarse_segments_per_crossing": records[index]["segments_per_crossing"],
            "fine_segments_per_crossing": records[index+1]["segments_per_crossing"],
            "max_interpolated_height_difference_mm": float(np.max(np.abs(distances))),
            "rms_interpolated_height_difference_mm": float(np.sqrt(np.mean(np.square(distances)))),
            "relative_energy_difference": abs(a-b)/abs(b)})
    if not comparisons[1]["rms_interpolated_height_difference_mm"] < comparisons[0]["rms_interpolated_height_difference_mm"]:
        raise RuntimeError("observed height refinement did not improve")
    result = {"cases": records, "comparisons": comparisons,
        "scope": "observed discrete-model convergence; not absolute continuum or real-cloth error bounds"}
    write_json(output/"mesh_refinement.json", result)
    np.savez_compressed(output/"mesh_heights.npz", **{f"segments_{n}": z for n,z in zip((4,8,16),solutions)})
    return result


def beam_benchmark(output):
    length, bending, load = 1.2, 3e-6, 2e-7
    m = YarnElasticity(0., bending)
    curves, records = [], []
    for n in (12, 24, 48, 96):
        h = length/n; x = np.arange(1, n)*h
        stiffness = beam_energy_gradient_hessian(np.zeros(n-1), h, m)[2]
        numerical = np.linalg.solve(stiffness, np.full(n-1, load*h))
        exact = load*x*(length**3-2*length*x*x+x**3)/(24*bending)
        records.append({"segments": n, "max_deflection_error_mm": float(np.max(np.abs(numerical-exact))),
            "force_balance_inf_N": float(np.max(np.abs(stiffness@numerical-load*h)))})
        curves.append((x, numerical, exact))
    result = {"length_mm": length, "bending_N_mm2": bending, "uniform_load_N_per_mm": load,
              "boundary": "simply supported; height zero, rotation free", "cases": records}
    write_json(output/"beam_benchmark.json", result)
    return result, curves


def run_topologies(output):
    result = {}
    for name, draft in (("plain", WeaveDraft.plain()), ("twill_2_1", WeaveDraft.twill(2,1)),
                        ("basket_2_2", WeaveDraft.basket(2,2))):
        spec = ReducedWeaveSpec(draft, .012, .012, warp_count=4, weft_count=4, segments_per_crossing=4)
        p, r, record = solve_case(spec)
        result[name] = record
        centers = p.centerlines(r.heights_mm)
        np.savez_compressed(output/f"{name}_centerlines.npz", **{f"{f}_{i}":value for (f,i),value in centers.items()})
    write_json(output/"topology_cases.json", result)
    return result


def figure_pair(p, r, output):
    colors = {"warp": "#146d9b", "weft": "#d15f34"}
    initial, relaxed = p.centerlines(r.initial_heights_mm), p.centerlines(r.heights_mm)
    fig, axs = plt.subplots(2, 2, figsize=(11.8, 8.2), constrained_layout=True)
    for ax, family in zip(axs[0], ("warp", "weft")):
        for (f, i), points in initial.items():
            if f != family: continue
            axis = 1 if family == "warp" else 0
            ax.plot(points[:,axis], points[:,2]*1000, color="#8e9aa2", ls="--", alpha=.7,
                    label="Feasible C2 initialization" if i == 0 else None)
            ax.plot(relaxed[(f,i)][:,axis], relaxed[(f,i)][:,2]*1000, color=colors[family],
                    label="Reduced equilibrium" if i == 0 else None)
        ax.set_title(f"{family.capitalize()} tracks: height redistribution")
        ax.set_xlabel("Projected position (mm)"); ax.set_ylabel("Height (µm)"); ax.legend(fontsize=9)
        ax.grid(alpha=.2)
    vals = [r.diagnostics[state]["families"][family]["tangent_second_moment"][2][2]
            for state in ("initial","relaxed") for family in ("warp","weft")]
    x = np.arange(2)
    axs[1,0].bar(x-.16, vals[:2], .32, label="Initialization", color="#98a9b4")
    axs[1,0].bar(x+.16, vals[2:], .32, label="Equilibrium", color=[colors["warp"],colors["weft"]])
    axs[1,0].set_xticks(x,["Warp", "Weft"]); axs[1,0].set_ylabel("Length-weighted tangent moment Czz")
    axs[1,0].set_title("Orientation changes that feed optical models"); axs[1,0].legend(fontsize=9)
    hist = [r.diagnostics["initial_energy_excess_N_mm"]]+[h["energy_excess_N_mm"] for h in r.history]
    axs[1,1].plot(np.arange(len(hist)),np.array(hist)*1e6,color="#235f51")
    axs[1,1].set_xlabel("SLSQP callback iteration"); axs[1,1].set_ylabel("Excess elastic energy (µN mm)")
    axs[1,1].set_title("Actual optimizer trace; callbacks may be nonmonotone")
    axs[1,1].grid(alpha=.2)
    fig.suptitle("Reduced yarn mechanics → explicit optical geometry\nSynthetic stiffness; pinned tracks; no friction or mass-conserving fiber deformation", fontsize=13)
    fig.savefig(output/"mechanics_to_geometry.png", dpi=180); plt.close(fig)


def figures_diagnostics(sweeps, refinement, beam, output):
    fig, axs = plt.subplots(2, 2, figsize=(11.8, 8.2), constrained_layout=True)
    for ax, key in zip(axs[0], sweeps):
        cases = sweeps[key]
        x = [q["parameter_value"] for q in cases]
        for family, color in (("warp", "#146d9b"), ("weft", "#d15f34")):
            ax.plot(x, [q["diagnostics"]["relaxed"]["families"][family]["crimp_ratio"]*100 for q in cases], "o-", label=family, color=color)
        ax.set_ylabel("Yarn crimp (%)"); ax.grid(alpha=.2); ax.legend()
        ax.set_xlabel("Warp / weft bending stiffness" if key=="warp_bending_ratio" else "Warp flat-state engineering prestrain")
        if key == "warp_bending_ratio": ax.set_xscale("log")
    comparisons=refinement["comparisons"]
    axs[1,0].plot([c["fine_segments_per_crossing"] for c in comparisons],
        [c["rms_interpolated_height_difference_mm"]*1000 for c in comparisons],"o-",color="#235f51")
    axs[1,0].set_xlabel("Fine segments per crossing interval"); axs[1,0].set_ylabel("Adjacent-mesh RMS height change (µm)")
    axs[1,0].set_title("Actual 4→8→16 mechanical refinements"); axs[1,0].grid(alpha=.2)
    n=np.array([c["segments"] for c in beam["cases"]]); err=np.array([c["max_deflection_error_mm"] for c in beam["cases"]])
    axs[1,1].loglog(n,err,"o-",label="Numerical beam error",color="#642a80")
    axs[1,1].loglog(n,err[0]*(n[0]/n)**2,"--",label="Second-order reference",color="#8e9aa2")
    axs[1,1].set_xlabel("Beam elements"); axs[1,1].set_ylabel("Max deflection error (mm)")
    axs[1,1].set_title("Independent analytic simply-supported beam"); axs[1,1].legend(fontsize=9); axs[1,1].grid(alpha=.2)
    fig.suptitle("Constitutive effects and numerical validation — synthetic controlled experiments", fontsize=13)
    fig.savefig(output/"mechanics_validation.png", dpi=180); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--figures", type=Path)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--reuse-optical-pair", action="store_true", help="Load the frozen validated pair already under output/optical_pair")
    args=parser.parse_args()
    output=args.out.resolve(); figures=(args.figures or output/"figures").resolve()
    if output.exists() and any(output.iterdir()) and not args.reuse_existing:
        parser.error("output directory is nonempty; use a new folder or explicit --reuse-existing")
    output.mkdir(parents=True,exist_ok=True); figures.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    source_paths=[Path(__file__),ROOT/"textile_sim/weave_mechanics.py",ROOT/"tests/test_weave_mechanics.py",
                  ROOT/"examples/mechanics/optical_pair.json",ROOT/"examples/mechanics/two_ply_relaxation.json"]
    source_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    config=json.loads((ROOT/"examples/mechanics/optical_pair.json").read_text())
    if args.reuse_optical_pair:
        from textile_sim.weave_mechanics import WeaveEquilibrium, equilibrium_residual
        p=ReducedWeaveProblem(ReducedWeaveSpec.from_dict(config["mechanics"]))
        metrics=json.loads((output/"optical_pair/pair_metrics.json").read_text())
        if metrics["config"] != p.spec.to_dict(): raise ValueError("frozen optical pair config mismatch")
        with np.load(output/"optical_pair/mechanical_heights.npz",allow_pickle=False) as z:
            r=WeaveEquilibrium(z["initial_mm"].copy(),z["relaxed_mm"].copy(),metrics["equilibrium"],tuple(metrics["history"]),
                p.sha256,p.state_sha256(z["relaxed_mm"]))
        if equilibrium_residual(p,r.heights_mm)["stationarity_relative"]>1e-8:
            raise RuntimeError("frozen pair no longer passes KKT")
        write_json(output/"optical_pair/equilibrium_binding_audit.json", {
            "problem_sha256":p.sha256,"height_state_sha256":p.state_sha256(r.heights_mm),
            "independently_recomputed_kkt":equilibrium_residual(p,r.heights_mm),
            "recomputed_constraints":p.constraint_diagnostics(r.heights_mm),
            "module_sha256":source_hashes["textile_sim/weave_mechanics.py"],
            "geometry_files_sha256":{str(path.relative_to(output/"optical_pair")):hashlib.sha256(path.read_bytes()).hexdigest()
                 for folder in ("initial","relaxed") for path in sorted((output/"optical_pair"/folder).glob("hierarchy_geometry.*"))},
            "scope":"The frozen optical geometry files remain unchanged; their actual mechanical state is independently revalidated after the result-binding review fix."})
    else:
        p,r,metrics=optical_pair(output/"optical_pair",config)
    print("Optical pair ready",flush=True)
    two_ply_config=json.loads((ROOT/"examples/mechanics/two_ply_relaxation.json").read_text())
    optical_pair(output/"two_ply",two_ply_config)
    print("Two-ply embedding ready",flush=True)
    sweeps=run_sweeps(output); print("Stiffness/prestrain sweeps ready",flush=True)
    refinement=run_refinement(output,p.spec); print("Mesh refinements ready",flush=True)
    beam,beam_curves=beam_benchmark(output)
    topologies=run_topologies(output)
    figure_pair(p,r,figures); figures_diagnostics(sweeps,refinement,beam,figures)
    if source_hashes!={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}:
        raise RuntimeError("source/config changed during experiments; rerun with a stable code state")
    manifest={"schema_version":SCHEMA_VERSION,"elapsed_seconds":time.perf_counter()-start,
        "python":platform.python_version(),"numpy":np.__version__,"optical_pair_reused":args.reuse_optical_pair,
        "source_sha256":source_hashes,
        "cases":{"optical_pair":1,"two_ply_embedding":1,"parameter_sweeps":8,"mesh_levels":3,"beam_mesh_levels":4,"drafts":3},
        "all_experiments_synthetic":True,
        "scope":"reduced equilibrium and numerical evidence; no measured textile parameters, constituent-fiber mechanics, friction, or real material validation"}
    write_json(output/"experiment_manifest.json",manifest)
    print(json.dumps(manifest,indent=2))


if __name__ == "__main__":
    main()
