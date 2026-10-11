#!/usr/bin/env python3
"""Numerical scene-scale sensitivity of the existing scalar volume model.

This creates geometrically similar *numerical* scenes with lengths multiplied
by S and absorption divided by S. Original physical-mm profiles/materials are
preserved in inputs/. Derived kappa is a numerical proxy, not a different
measured textile. The original renderer and geometry producers are unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
from scipy.stats import t as student_t

from textile_sim.optical_scene import MaterialSpectrum
from textile_sim.render import RenderConfig, get_mitsuba
from textile_sim.variable_radius import load_variable_radius_profiles, build_tapered_tube
from textile_sim.volume_optics import build_volume_scene, render_volume_scene, triangle_buffer_audit

ROOT = Path(__file__).resolve().parent
STATES = ("constant_reference", "incompressible_segments")
LIGHTS = ("R0", "R90", "T45")
SCHEMA = "textile.volume_optics_scene_scale_sensitivity/5.0"
INPUTS = tuple("profiles/"+state+"/"+name for state in STATES
               for name in ("variable_radius_profiles.json", "variable_radius_profiles.npz")) + (
    "optics/synthetic_material_spectra.json", "optics/optical_metrics.json")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n").encode()
    temporary = path.with_name(path.name+".part")
    with temporary.open("wb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def save_npz_atomic(path, **arrays):
    """Complete ZIP in memory, verify CRC, publish, then verify stored bytes."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    payload = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("in-memory NPZ CRC mismatch")
    temporary = path.with_name(path.name+".part")
    with temporary.open("wb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    expected = hashlib.sha256(payload).hexdigest()
    if sha256(path) != expected:
        raise RuntimeError("stored NPZ byte checksum mismatch")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("stored NPZ CRC mismatch")
    return expected


def source_hashes():
    names = ("volume_optics", "variable_radius", "hierarchy", "weave_draft", "optical_scene", "render")
    paths = [ROOT/"textile_sim"/(name+".py") for name in names]+[Path(__file__).resolve()]
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def interval(values, *, family_size=None):
    data = np.asarray(values, dtype=np.float64)
    mean = float(data.mean()); se = float(data.std(ddof=1)/np.sqrt(len(data)))
    confidence = .95 if family_size is None else 1-.05/family_size
    halfwidth = float(student_t.ppf((1+confidence)/2, len(data)-1)*se)
    return {"mean_delta": mean, "interval_low": mean-halfwidth, "interval_high": mean+halfwidth,
            "standard_error": se, "confidence": confidence, "seed_count": len(data),
            "family_size": family_size, "interval_excludes_zero": abs(mean) > halfwidth}


def summarize(raw, scales):
    means = np.asarray(raw, dtype=np.float64).mean(axis=(-1, -2))
    comparisons = []
    pairs = [(a, b) for a in range(len(scales)) for b in range(a+1, len(scales))]
    family = len(pairs)*len(STATES)*len(LIGHTS)
    for a, b in pairs:
        for si, state in enumerate(STATES):
            for li, light in enumerate(LIGHTS):
                x, y = means[a, si, li], means[b, si, li]
                delta = y-x
                comparisons.append({"kind": "numerical_scale", "before_scale": scales[a],
                    "after_scale": scales[b], "state": state, "light": light,
                    "mean_before": float(x.mean()), "mean_after": float(y.mean()),
                    "relative_mean_change_percent": float(100*delta.mean()/x.mean()) if x.mean() else None,
                    "paired_seed_differences": delta.tolist(), "pointwise_95": interval(delta),
                    "family_adjusted": interval(delta, family_size=family)})
    for qi, scale in enumerate(scales):
        for li, light in enumerate(LIGHTS):
            x, y = means[qi, 0, li], means[qi, 1, li]
            delta = y-x
            comparisons.append({"kind": "radius_effect", "scale": scale, "light": light,
                "mean_constant": float(x.mean()), "mean_variable": float(y.mean()),
                "relative_mean_change_percent": float(100*delta.mean()/x.mean()) if x.mean() else None,
                "paired_seed_differences": delta.tolist(), "pointwise_95": interval(delta),
                "family_adjusted": interval(delta, family_size=len(LIGHTS)) if qi == len(scales)-1 else None,
                "primary_family": qi == len(scales)-1})
    for a, b in pairs:
        for li, light in enumerate(LIGHTS):
            x = means[a, 1, li]-means[a, 0, li]
            y = means[b, 1, li]-means[b, 0, li]
            delta = y-x
            comparisons.append({"kind": "radius_effect_scale_interaction", "before_scale": scales[a],
                "after_scale": scales[b], "light": light,
                "paired_seed_differences": delta.tolist(), "pointwise_95": interval(delta),
                "family_adjusted": interval(delta, family_size=len(pairs)*len(LIGHTS)),
                "scope": "change of the variable-minus-constant effect under numerical scene rescaling"})
    return means, comparisons


def make_figure(output, raw, scales):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    means = np.asarray(raw, dtype=np.float64).mean(axis=(-1, -2))
    fig, axes = plt.subplots(1, 3, figsize=(13., 4.2), constrained_layout=True)
    for li, light in enumerate(LIGHTS):
        for si, state in enumerate(STATES):
            center = means[:, si, li].mean(axis=-1)
            se = means[:, si, li].std(axis=-1, ddof=1)/np.sqrt(means.shape[-1])
            ci = student_t.ppf(.975, means.shape[-1]-1)*se
            axes[li].errorbar(scales, center, yerr=ci, fmt="o-", capsize=4, label=state)
        axes[li].set(xscale="log", xlabel="Numerical scene length scale S", ylabel="Mean scalar radiance",
                     title=light, xticks=scales, xticklabels=[str(s) for s in scales])
        axes[li].grid(alpha=.2); axes[li].legend(fontsize=8)
    fig.suptitle("Physical geometry fixed by similarity mapping; 550 nm, 64 radial sides\n"
                 "Pointwise 95% seed intervals; no claim of convergence from overlapping intervals", fontsize=11)
    fig.savefig(output/"scene_scale_sensitivity.png", dpi=160); plt.close(fig)


def run(input_run, output, *, scales=(1., 10., 100.), resolution=64, spp=64):
    source, output = Path(input_run).resolve(), Path(output).resolve()
    scales = tuple(float(s) for s in scales)
    if (len(scales) < 2 or list(scales) != sorted(set(scales))
            or not np.isfinite(scales).all() or min(scales) <= 0):
        raise ValueError("at least two strictly increasing positive numerical scales required")
    if any(isinstance(x, bool) or not isinstance(x, (int, np.integer)) or x <= 0 for x in (resolution, spp)):
        raise ValueError("positive integer resolution and spp required")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("input and output directories must not overlap")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    snapshot = output/"inputs"
    for name in INPUTS:
        target = snapshot/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source/name, target)
        if sha256(source/name) != sha256(target):
            raise RuntimeError("input snapshot copy checksum mismatch")
    input_hash = {name: sha256(snapshot/name) for name in INPUTS}
    profiles = {state: load_variable_radius_profiles(snapshot/"profiles"/state) for state in STATES}
    materials = tuple(MaterialSpectrum(**d) for d in json.loads((snapshot/"optics/synthetic_material_spectra.json").read_text()))
    original = json.loads((snapshot/"optics/optical_metrics.json").read_text())
    bounds = np.asarray(original["union_bounds_mm"], dtype=float)
    configs = {light: replace(RenderConfig(**original["lighting_configs"][light]), resolution=int(resolution), spp=int(spp))
               for light in LIGHTS}
    seeds = tuple(int(s) for s in original["seeds"])
    if len(seeds) != 4 or len(set(seeds)) != 4:
        raise ValueError("the declared sensitivity study requires four independent seeds")
    expected_count = len(scales)*len(STATES)*len(LIGHTS)*len(seeds)
    if expected_count > 144:
        raise ValueError("explicit small sensitivity budget exceeded")
    sources = source_hashes(); started = utc_now(); start = time.perf_counter()
    manifest = {"schema": SCHEMA, "status": "running", "started_utc": started,
                "producer_source_sha256": sources, "input_snapshot_sha256": input_hash,
                "input_source_directory": str(source), "actual_render_calls": 0,
                "planned_actual_render_calls": expected_count, "scales": list(scales),
                "resolution": int(resolution), "spp": int(spp), "seeds": list(seeds), "command": sys.argv}
    json_write(output/"experiment_manifest.json", manifest)
    rows, geometry = [], []
    raw = np.empty((len(scales), len(STATES), len(LIGHTS), len(seeds), resolution, resolution), dtype=np.float32)
    try:
        for qi, scale in enumerate(scales):
            scaled_mats = tuple(replace(material,
                kappa=tuple(k/scale for k in material.kappa),
                source="numerical similarity proxy for "+material.material_id,
                data_status="synthetic", provenance_json=json.dumps({
                    "numerical_scale": scale, "physical_material": material.to_dict(),
                    "physical_wavelength_nm": 550., "kappa_is_scaled_numerical_proxy": True,
                    "real_index_unchanged": True, "numerical_mu_equals_physical_mu_divided_by_scale": True}))
                for material in materials)
            json_write(output/"materials"/f"scale_{scale:g}.json", [m.to_dict() for m in scaled_mats])
            for si, state in enumerate(STATES):
                original_profiles = profiles[state]
                scaled_profiles = tuple(replace(p, points_mm=p.points_mm*scale,
                    material_coordinates_mm=p.material_coordinates_mm*scale,
                    parent_material_coordinates_mm=p.parent_material_coordinates_mm*scale,
                    segment_radius_mm=p.segment_radius_mm*scale,
                    provenance_json=json.dumps({"physical_profile_sha256": p.sha256,
                        "physical_provenance": json.loads(p.provenance_json), "numerical_scale": scale,
                        "original_physical_length_unit": "mm", "numerical_coordinate_divided_by_scale_gives_physical_mm": True}))
                    for p in original_profiles)
                meshes = tuple(build_tapered_tube(p, radial_segments=64, initial_normal=(0., 0., 1.)) for p in scaled_profiles)
                buffers, identities = {}, []
                for fi, (old, mesh) in enumerate(zip(original_profiles, meshes)):
                    v, f, audit = triangle_buffer_audit(mesh.vertices_mm, mesh.faces)
                    prefix = f"fiber_{fi:04d}"
                    buffers[prefix+"/vertices_numerical"] = v; buffers[prefix+"/faces"] = f
                    identities.append({"fiber_id": old.fiber_id, "physical_profile_sha256": old.sha256,
                        "numerical_profile_sha256": mesh.profile.sha256, "numerical_mesh_sha256": mesh.sha256,
                        "maximum_physical_centerline_error_mm": float(np.max(np.abs(mesh.profile.points_mm/scale-old.points_mm))),
                        "maximum_physical_radius_error_mm": float(np.max(np.abs(mesh.profile.node_radius_mm/scale-old.node_radius_mm))),
                        "buffer_audit_numerical_units": audit})
                folder = output/"geometry"/f"scale_{scale:g}"/state
                checksum = save_npz_atomic(folder/"renderer_buffers.npz", **buffers)
                record = {"scale": scale, "state": state, "radial_segments": 64,
                          "length_mapping": "physical_mm = numerical_coordinate / scale; backend metadata keeps its nominal mm label",
                          "array_file": "renderer_buffers.npz", "array_file_sha256": checksum, "fibers": identities}
                json_write(folder/"geometry_mapping.json", record); geometry.append(record)
                for li, light in enumerate(LIGHTS):
                    scene, metadata = build_volume_scene(meshes, scaled_mats, 550., configs[light], bounds_mm=bounds*scale)
                    json_write(output/"scenes"/f"scale_{scale:g}__{state}__{light}.json", metadata)
                    for ki, seed in enumerate(seeds):
                        image, row = render_volume_scene(scene, metadata, seed=seed, spp=int(spp))
                        raw[qi, si, li, ki] = image[..., 0]
                        row.update(scale=scale, state=state, light=light, array_index=[qi, si, li, ki])
                        rows.append(row); manifest["actual_render_calls"] += 1
                    json_write(output/"experiment_manifest.json", manifest)
                    print(json.dumps({"scale": scale, "state": state, "light": light,
                                      "actual_render_calls": manifest["actual_render_calls"]}), flush=True)
                del buffers, meshes
        checksum = save_npz_atomic(output/"scalar_radiance.npz", radiance=raw,
            scales=np.asarray(scales), seeds=np.asarray(seeds, dtype=np.int64))
        means, comparisons = summarize(raw, scales)
        metrics = {"schema": SCHEMA, "status": "rendered", "physical_wavelength_nm": 550.,
                   "physical_model": "same real-index Fresnel plus pure absorption; numerical similarity test only",
                   "physical_geometry_mapping": "original physical-mm profiles and materials retained in inputs/",
                   "backend_metadata_unit_caveat": "derived scenes use nominal mm fields with lengths*S and kappa/S; numerical proxies are not measurements or a physical material change",
                   "scales": list(scales), "states": list(STATES), "lights": list(LIGHTS), "seeds": list(seeds),
                   "radial_segments": 64, "resolution": int(resolution), "spp": int(spp),
                   "radiance_axes": ["scale", "state", "light", "seed", "y", "x"],
                   "actual_render_calls": manifest["actual_render_calls"], "raw_file_sha256": checksum,
                   "records": rows, "mean_radiance_per_seed": means.tolist(), "comparisons": comparisons,
                   "all_scale_pair_family_size": len(scales)*(len(scales)-1)//2*2*3,
                   "primary_radius_family": "three lights at largest numerical scale",
                   "uncertainty_scope": "paired seed means; conditional Monte Carlo noise; no physical-data or model-error uncertainty",
                   "interpretation": "unresolved scale changes do not prove convergence; significant changes diagnose numerical sensitivity"}
        json_write(output/"sensitivity_metrics.json", metrics)
        make_figure(output, raw, scales)
        after = source_hashes()
        if after != sources or {name: sha256(snapshot/name) for name in INPUTS} != input_hash:
            raise RuntimeError("source or input snapshot changed during sensitivity run")
        for path in output.rglob("*.npz"):
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("final NPZ CRC scan failed")
        files = {str(path.relative_to(output)): {"sha256": sha256(path), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file() and path.name != "experiment_manifest.json"}
        manifest.update(status="passed", finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
                        producer_source_sha256_after=after, source_drift=[], input_hashes_unchanged=True,
                        all_saved_npz_crc_passed=True, output_files=files,
                        runtime={"mitsuba": get_mitsuba().__version__, "variant": get_mitsuba().variant(),
                                 "numpy": np.__version__, "python": sys.version})
        json_write(output/"experiment_manifest.json", manifest)
        return manifest
    except Exception as exc:
        manifest.update(status="failed", finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
                        error_type=type(exc).__name__, error=str(exc))
        json_write(output/"experiment_manifest.json", manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-run", type=Path, default=ROOT/"data/variable_radius_v5")
    parser.add_argument("--output", type=Path, default=ROOT/"data/validation_v5/volume_scale_sensitivity")
    parser.add_argument("--scales", nargs="+", type=float, default=(1., 10., 100.))
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--spp", type=int, default=64)
    args = parser.parse_args()
    result = run(args.input_run, args.output, scales=args.scales, resolution=args.resolution, spp=args.spp)
    print(json.dumps({"status": result["status"], "actual_render_calls": result["actual_render_calls"],
                      "elapsed_seconds": result["elapsed_seconds"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
