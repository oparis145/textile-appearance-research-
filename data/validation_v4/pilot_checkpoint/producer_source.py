#!/usr/bin/env python3
"""Compare regenerated and material-tracked fibers on one prescribed yarn pose.

The reference is the stored initial geometry, not a stress-free constituent
configuration.  Three monochromatic bands are numerical diagnostics, not a
color reconstruction.  The variable-radius volume-proxy state is NOT rendered.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from textile_sim.hierarchy import audit_clearance, load_hierarchy, save_hierarchy
from textile_sim.material_transport import (
    bind_material_reference, transport_material_reference, save_material_transport,
)
from textile_sim.optical_scene import from_hierarchy, export_mitsuba, microstructure_statistics
from textile_sim.optical_lod import paired_mean_interval
from textile_sim.render import RenderConfig
from run_multiscale_optics_v3 import synthetic_materials, render_stack, fit_hierarchy

ROOT = Path(__file__).resolve().parent
STATES = ("initial", "regenerated", "transported")
LIGHTS = ("R0", "R90", "T45")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def positive_int(value):
    result = int(value)
    if result <= 0 or str(result) != str(value):
        raise argparse.ArgumentTypeError("a positive integer is required")
    return result


def source_hashes():
    paths = sorted((ROOT/"textile_sim").glob("*.py"))
    paths += [Path(__file__).resolve(), ROOT/"run_multiscale_optics_v3.py"]
    return {str(p.relative_to(ROOT)): sha256(p) for p in paths}


def input_hashes(pair):
    paths = [pair/pose/name for pose in ("initial", "relaxed")
             for name in ("hierarchy_geometry.json", "hierarchy_geometry.npz")]
    return {str(p.relative_to(pair)): sha256(p) for p in paths}


def matched_parent_indices(initial, target):
    """Declare the stored height-only fixture correspondence; do not infer it.

    Exactly shared XY parent vertices establish the particular fixture's graph
    indexing.  Attaching material labels to those indices remains a prescribed
    no-slip kinematic assumption, not measured material motion.
    """
    if set(initial.yarns) != set(target.yarns):
        raise ValueError("the prescribed pose must retain every reference yarn ID")
    for key in initial.yarns:
        a, b = initial.yarns[key], target.yarns[key]
        if a.shape != b.shape or not np.array_equal(a[:, :2], b[:, :2]):
            raise ValueError("this experiment requires the same height-graph parent indices and XY coordinates")
    if initial.provenance != target.provenance:
        raise ValueError("initial and regenerated fixture provenance must match")
    for a, b in zip(initial.fiber_records, target.fiber_records):
        if a.points_mm.shape != b.points_mm.shape or a.radius_mm != b.radius_mm:
            raise ValueError("regenerated comparison needs matching fiber sampling and radii")
    return {"declaration": "original material labels attached to shared height-graph yarn vertex indices",
            "exact_parent_XY_match": True, "measured_material_correspondence": False,
            "stress_free_reference": False, "prescribed_endpoint_director": [0., 0., 1.],
            "physical_twist_equilibrium_solved": False}


def geometry_comparison(a, b):
    errors, tangents = [], []
    for before, after in zip(a.fiber_records, b.fiber_records):
        errors.extend(np.linalg.norm(before.points_mm-after.points_mm, axis=1))
        da, db = np.diff(before.points_mm, axis=0), np.diff(after.points_mm, axis=0)
        cosine = np.einsum("ij,ij->i", da, db)/(np.linalg.norm(da, axis=1)*np.linalg.norm(db, axis=1))
        tangents.extend(np.rad2deg(np.arccos(np.clip(cosine, -1., 1.))))
    return {"rms_vertex_position_difference_mm": float(np.sqrt(np.mean(np.square(errors)))),
            "maximum_vertex_position_difference_mm": float(np.max(errors)),
            "rms_segment_tangent_angle_difference_deg": float(np.sqrt(np.mean(np.square(tangents)))),
            "maximum_segment_tangent_angle_difference_deg": float(np.max(tangents)),
            "scope": "geometry at matched parent parameter indices; regenerated vertices have no independently tracked material identity"}


def geometry_figure(out, constant, incompressible):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), constrained_layout=True)
    for family, color in (("warp", "#137c8b"), ("weft", "#ce7440")):
        fibers = [f for f in constant.fiber_records if f.reference.record.family == family]
        strain = np.concatenate([f.engineering_strain for f in fibers])*100
        lengths = np.concatenate([np.diff(f.material_coordinates_mm) for f in fibers])
        axes[0].hist(strain, bins=np.linspace(-16, 16, 65), weights=lengths/lengths.sum(),
                     histtype="step", lw=1.7, label=family, color=color)
    axes[0].set(xlabel="Sampled segment engineering strain (%)", ylabel="Reference-length fraction",
                title="Local strain relative to the stored initial pose")
    axes[0].legend()
    summary = constant.summary()
    groups = [summary["all"], summary["families"]["warp"], summary["families"]["weft"]]
    axes[1].bar(["all", "warp", "weft"], [100*g["relative_fiber_length_change"] for g in groups],
                color=["#565c70", "#137c8b", "#ce7440"])
    axes[1].axhline(0, color="black", lw=.6)
    axes[1].set(ylabel="Total fiber length change (%)", title="Aggregate changes can cancel")
    ratios = np.concatenate([f.segment_radius_mm/f.reference.record.radius_mm
                             for f in incompressible.fiber_records])
    axes[2].hist(ratios, bins=45, color="#5c6faa")
    axes[2].set(xlabel="Segment radius / reference radius", ylabel="Segment count",
                title="Cylinder-volume proxy mode (not rendered)")
    fig.suptitle("Prescribed material-coordinate transport; constituent stresses are not solved", fontsize=12)
    fig.savefig(out/"figures"/"material_transport_diagnostics.png", dpi=190)
    plt.close(fig)


def optical_figures(out, arrays, metrics):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(10, 10), constrained_layout=True)
    for c, light in enumerate(LIGHTS):
        images = [arrays[state+"__"+light].astype(float).mean(axis=0)[..., 1] for state in STATES]
        vmax = max(float(np.max(x)) for x in images)
        for r, (state, img) in enumerate(zip(STATES, images)):
            axes[r, c].imshow(img, cmap="gray", vmin=0, vmax=vmax)
            axes[r, c].set_title(f"{state} / {light}", fontsize=10)
            axes[r, c].axis("off")
    fig.suptitle("550 nm radiance; shared rig and grayscale per light; 4 independent seed averages\n"
                 "Synthetic circular fibers. Display scale is not a calibrated product photograph.", fontsize=11)
    fig.savefig(out/"figures"/"material_transport_550nm.png", dpi=190)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for ax, light in zip(axes, LIGHTS):
        comparison = next(c for c in metrics["comparisons"]
                          if c["light"] == light and c["from_state"] == "regenerated")
        interval = comparison["paired_interval"]
        scale = np.asarray(comparison["from_mean_radiance"])
        y = 100*np.asarray(interval["mean_delta"])/scale
        lo = 100*np.asarray(interval["interval_low"])/scale
        hi = 100*np.asarray(interval["interval_high"])/scale
        ax.errorbar(metrics["wavelengths_nm"], y, yerr=np.stack((y-lo, hi-y)),
                    fmt="o-", capsize=4, color="#315f8a")
        ax.axhline(0, color="black", lw=.6)
        ax.set(title=light, xlabel="Vacuum wavelength (nm)", ylabel="Tracked − regenerated (% of baseline)")
    fig.suptitle("Pointwise paired 95% t intervals across seeds; rendering noise only", fontsize=12)
    fig.savefig(out/"figures"/"material_transport_paired_radiance.png", dpi=190)
    plt.close(fig)


def run_experiments(pair_directory, output, resolution=64, spp=32, replicates=4, render=True):
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (resolution, spp, replicates)):
        raise ValueError("resolution, spp and replicates must be positive integers")
    if replicates < 2:
        raise ValueError("at least two independent seeds are required for paired intervals")
    pair, out = Path(pair_directory).resolve(), Path(output).resolve()
    if pair == out or pair in out.parents or out in pair.parents:
        raise ValueError("input and output must not overlap")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError("output must be a new or empty directory")
    inputs, sources = input_hashes(pair), source_hashes()
    out.mkdir(parents=True, exist_ok=True)
    (out/"figures").mkdir()
    start = time.perf_counter()
    manifest = {"schema_version": "material_transport_experiment_v4.1", "status": "running",
                "started_utc": utc_now(), "input_pair_directory": str(pair),
                "input_sha256": inputs, "source_sha256": sources,
                "requested_render": bool(render), "actual_render_count": None if render else 0,
                "resolution": resolution, "spp": spp, "replicates": replicates,
                "completed_render_records": []}
    write_json(out/"experiment_manifest.json", manifest)
    try:
        initial, regenerated = load_hierarchy(pair/"initial"), load_hierarchy(pair/"relaxed")
        correspondence = matched_parent_indices(initial, regenerated)
        normals = {key: np.array([0., 0., 1.]) for key in initial.yarns}
        reference = bind_material_reference(initial, yarn_initial_normals=normals,
                                            correspondence="shared_vertex_indices")
        labels = {key: curve.material_coordinates_mm for key, curve in reference.yarns.items()}
        identity = transport_material_reference(reference, initial.yarns, yarn_initial_normals=normals,
                                                deformed_parent_coordinates_mm=labels)
        identity_error = max(float(np.max(np.linalg.norm(a.points_mm-b.points_mm, axis=1)))
                             for a, b in zip(initial.fiber_records, identity.fiber_records))
        if identity_error > 1e-11:
            raise RuntimeError("reference identity transport failed")
        transport_states = {}
        for mode in ("constant_reference", "incompressible_segments"):
            state = transport_material_reference(reference, regenerated.yarns,
                    yarn_initial_normals=normals, deformed_parent_coordinates_mm=labels, radius_mode=mode)
            save_material_transport(out/"tracking"/mode, state)
            transport_states[mode] = state
        constant, incompressible = (transport_states[m] for m in ("constant_reference", "incompressible_segments"))
        try:
            incompressible.to_hierarchy()
        except ValueError as exc:
            rejected = {"blocked": True, "reason": str(exc)}
        else:
            raise RuntimeError("variable-radius state escaped the constant-radius optical export gate")
        geometries = {"initial": initial, "regenerated": regenerated, "transported": constant.to_hierarchy()}
        audits = {}
        for name, geometry in geometries.items():
            audits[name] = audit_clearance(geometry)
            if not audits[name]["certified_separated"]:
                raise RuntimeError(f"new different-fiber capsule clearance audit failed: {name}")
            save_hierarchy(out/"geometry"/name, geometry)
        geometry_metrics = {"schema_version": "material_transport_geometry_v4.1",
            "length_unit": "mm", "correspondence": correspondence,
            "states": {key: value.summary() for key, value in geometries.items()},
            "clearance_audits": audits, "identity_max_point_error_mm": identity_error,
            "transport_states": {key: value.summary() for key, value in transport_states.items()},
            "incompressible_optical_export": rejected,
            "regenerated_vs_transported": geometry_comparison(regenerated, geometries["transported"])}
        write_json(out/"geometry_metrics.json", geometry_metrics)
        geometry_figure(out, constant, incompressible)

        optics = out/"optics"
        optics.mkdir()
        materials = synthetic_materials()
        scenes = {key: from_hierarchy(value, materials) for key, value in geometries.items()}
        union = np.stack((np.min([s.bounds_mm[0] for s in scenes.values()], axis=0),
                          np.max([s.bounds_mm[1] for s in scenes.values()], axis=0)))
        volume = float(np.prod(union[1]-union[0]))
        wavelengths = np.array([450., 550., 650.])
        seeds = 9203+13579*np.arange(replicates)
        configs = {
            "R0": RenderConfig(resolution=resolution, spp=spp, light_elevation_deg=40, light_azimuth_deg=0, width_fraction=.68),
            "R90": RenderConfig(resolution=resolution, spp=spp, light_elevation_deg=40, light_azimuth_deg=90, width_fraction=.68),
            "T45": RenderConfig(resolution=resolution, spp=spp, mode="transmission", light_elevation_deg=55, light_azimuth_deg=45, width_fraction=.68)}
        metrics = {"schema_version": "material_transport_optics_v4.1", "status": "running" if render else "skipped",
            "states": list(STATES), "wavelengths_nm": wavelengths.tolist(), "seeds": seeds.tolist(),
            "scene_sha256": {}, "union_bounds_mm": union.tolist(), "averaging_volume_mm3": volume,
            "lighting_configs": {k: asdict(v) for k, v in configs.items()},
            "projection_fits": {}, "microstructure": {}, "exported_clearance_budgets": {},
            "records": [], "comparisons": [], "actual_render_count": None if render else 0,
            "rendered_radius_mode": "constant_reference",
            "scope": "Three monochromatic radiance diagnostics for synthetic constituents; no CIE/color or real-fabric reconstruction",
            "uncertainty_scope": "paired independent rendering seeds; pointwise intervals, not simultaneous or model/measurement uncertainty"}
        write_json(optics/"synthetic_material_spectra.json", [m.to_dict() for m in materials])
        exports = {}
        for name, scene in scenes.items():
            scene.save(optics/f"{name}_scene.json")
            metrics["scene_sha256"][name] = scene.sha256
            metrics["microstructure"][name] = microstructure_statistics(scene)
            exports[name] = export_mitsuba(scene, optics/f"{name}_curves", wavelengths[0], max_smoothing_error_mm=.0004)
            displacement = max(g["max_centerline_smoothing_bound_mm"]+
                               g["float32_centerline_quantization_bound_mm"]+
                               g["float32_radius_quantization_bound_mm"] for g in exports[name]["groups"])
            remaining = audits[name]["minimum_clearance_lower_bound_mm"]-2*displacement
            if remaining <= 0:
                raise RuntimeError(f"spline and float32 bounds exhausted new clearance audit: {name}")
            metrics["exported_clearance_budgets"][name] = {
                "source_clearance_lower_bound_mm": audits[name]["minimum_clearance_lower_bound_mm"],
                "maximum_tube_displacement_bound_mm": displacement,
                "exported_clearance_lower_bound_mm": remaining,
                "scope": "different fibers only; subtract both tubes' spline and float32 storage displacement bounds"}
            metrics["projection_fits"][name] = fit_hierarchy(scene, volume, optics, name)
        write_json(optics/"optical_metrics.json", metrics)
        arrays = {}
        if render:
            for name, scene in scenes.items():
                for light, config in configs.items():
                    stack, info = render_stack(scene, optics/f"{name}_curves", exports[name], union,
                                              config, wavelengths, seeds)
                    key = name+"__"+light
                    arrays[key] = stack
                    metrics["records"].append({"state": name, "light": light,
                        "array_file": "spectral_radiance.npz", "array_key": key, **info})
                    # Checkpoint completed batches without claiming the unknown
                    # number of rays/renders inside an interrupted next batch.
                    np.savez_compressed(optics/"spectral_radiance.npz", wavelengths_nm=wavelengths, seeds=seeds, **arrays)
                    manifest["completed_render_records"] = [{k: r[k] for k in ("state", "light", "actual_render_count")}
                                                            for r in metrics["records"]]
                    write_json(out/"experiment_manifest.json", manifest)
                    write_json(optics/"optical_metrics.json", metrics)
                    print(json.dumps({"state": name, "light": light, "actual_renders": info["actual_render_count"],
                                      "seconds": info["seconds"]}), flush=True)
            for light in LIGHTS:
                for before, after in (("initial", "transported"), ("regenerated", "transported")):
                    a = arrays[before+"__"+light].astype(float).mean(axis=(1, 2))
                    b = arrays[after+"__"+light].astype(float).mean(axis=(1, 2))
                    interval = paired_mean_interval(a, b)
                    if np.any(a.mean(axis=0) <= 0):
                        raise RuntimeError("relative radiance comparison requires a positive baseline")
                    metrics["comparisons"].append({"light": light, "from_state": before, "to_state": after,
                        "from_mean_radiance": a.mean(axis=0).tolist(), "to_mean_radiance": b.mean(axis=0).tolist(),
                        "relative_mean_radiance_change": ((b.mean(axis=0)-a.mean(axis=0))/a.mean(axis=0)).tolist(),
                        "paired_interval": interval})
            metrics.update(status="rendered", actual_render_count=sum(r["actual_render_count"] for r in metrics["records"]),
                           spectral_radiance_sha256=sha256(optics/"spectral_radiance.npz"))
            optical_figures(out, arrays, metrics)
        write_json(optics/"optical_metrics.json", metrics)
        if inputs != input_hashes(pair) or sources != source_hashes():
            raise RuntimeError("input or numerical source changed during experiment; rerun after stabilizing")
        manifest.update(status="passed", finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
            actual_render_count=metrics["actual_render_count"], input_hashes_unchanged=True, source_hashes_unchanged=True,
            output_sha256={str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*"))
                           if p.is_file() and p.name != "experiment_manifest.json"})
        write_json(out/"experiment_manifest.json", manifest)
        print(json.dumps({"status": "passed", "output": str(out), "actual_render_count": metrics["actual_render_count"],
                          "elapsed_seconds": manifest["elapsed_seconds"]}), flush=True)
        return {"geometry": geometry_metrics, "optics": metrics, "manifest": manifest}
    except Exception as exc:
        manifest.update(status="failed", finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
                        error_type=type(exc).__name__, error=str(exc))
        write_json(out/"experiment_manifest.json", manifest)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-directory", default=str(ROOT/"data/mechanics_v3/optical_pair"))
    parser.add_argument("--output", default=str(ROOT/"data/material_transport_v4"))
    parser.add_argument("--resolution", type=positive_int, default=64)
    parser.add_argument("--spp", type=positive_int, default=32)
    parser.add_argument("--replicates", type=positive_int, default=4)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args(argv)
    run_experiments(args.pair_directory, args.output, args.resolution, args.spp, args.replicates, not args.no_render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
