#!/usr/bin/env python3
"""Analytical closed-volume attenuation oracles with raw render provenance.

One scalar wavelength is replicated into three RGB channels.  Seed means are
the statistical replicates; channels and pixels are not additional repeated
experiments.  The index-matched cases isolate Beer attenuation through flat
caps, independently of facet refraction or the v4 hair BSDF approximation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import __version__ as scipy_version
from scipy.stats import t as student_t

from textile_sim.optical_scene import MaterialSpectrum
from textile_sim.render import RenderConfig, get_mitsuba
from textile_sim.variable_radius import (
    VariableRadiusFiber, build_tapered_tube, save_tapered_tube,
)
from textile_sim.volume_optics import build_volume_scene, render_volume_scene

ROOT = Path(__file__).resolve().parent
SCHEMA = "textile.volume_optics_physics_validation/5.0"
DEFAULT_SEEDS = (1187, 9781, 23417, 45751)
CASES = (
    ("beer_tau_000", "cylinder", 1., 0., 1.),
    ("beer_tau_025", "cylinder", 1., .25, 1.),
    ("beer_tau_075", "cylinder", 1., .75, 1.),
    ("beer_tau_150", "cylinder", 1., 1.5, 1.),
    ("beer_tau_300", "cylinder", 1., 3., 1.),
    ("furnace_n155", "cylinder", 1., 0., 1.55),
    ("scaled_tau_075", "scaled_cylinder", 8., .75, 1.),
    ("tapered_tau_075", "tapered", 1., .75, 1.),
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False)+"\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    names = ("volume_optics", "variable_radius", "hierarchy", "weave_draft",
             "optical_scene", "render")
    files = [ROOT/"textile_sim"/(name+".py") for name in names]
    files.append(Path(__file__).resolve())
    return {str(path.relative_to(ROOT)): sha256(path) for path in files}


def positive_int(value):
    result = int(value)
    if result <= 0 or str(result) != str(value):
        raise argparse.ArgumentTypeError("positive integer required")
    return result


def build_fixture(name):
    scale = 8. if name == "scaled_cylinder" else 1.
    z = np.array((0., .2, .5, .8, 1.)) if name == "tapered" else np.array((0., 1.))
    radii = np.array((.2, .3, .15, .25)) if name == "tapered" else np.array((.2,))
    points = np.column_stack((z*0, z*0, z))*scale
    profile = VariableRadiusFiber(
        points_mm=points, material_coordinates_mm=z*scale,
        parent_material_coordinates_mm=z*scale, segment_radius_mm=radii*scale,
        fiber_id="analytic_"+name, yarn_id="analytic_yarn", ply_id="analytic_ply",
        material_id="oracle", provenance_json=json.dumps({
            "source": "synthetic analytic closed-volume physics fixture",
            "stress_free_or_measured": False, "length_scale": scale}))
    return build_tapered_tube(profile, radial_segments=32, initial_normal=(1., 0., 0.))


def seed_interval(values):
    data = np.asarray(values, dtype=np.float64)
    mean = float(data.mean())
    stderr = float(data.std(ddof=1)/np.sqrt(len(data)))
    halfwidth = float(student_t.ppf(.975, len(data)-1)*stderr)
    return {"mean": mean, "seed_count": len(data), "seed_standard_error": stderr,
            "pointwise_95pct_seed_mean_interval": [mean-halfwidth, mean+halfwidth],
            "interval_interpretation": "Student-t seed means, Monte Carlo noise only; no family correction"}


def make_figure(out, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), constrained_layout=True)
    beer = [row for row in rows if row["case"].startswith("beer_")]
    x = np.array([row["optical_depth"] for row in beer])
    y = np.array([row["mean"] for row in beer])
    ci = np.array([row["pointwise_95pct_seed_mean_interval"] for row in beer])
    dense = np.linspace(0., float(x.max()), 250)
    axes[0].plot(dense, np.exp(-dense), color="#3b3e48", label="Analytic exp(-optical depth)")
    axes[0].errorbar(x, y, yerr=np.vstack((y-ci[:, 0], ci[:, 1]-y)), fmt="o",
                     capsize=4, color="#007f90", label="Rendered seed means, pointwise 95%")
    axes[0].set(xlabel="Optical depth (mu_a times axial length)", ylabel="Mean scalar radiance",
                title="Index-matched closed-mesh Beer oracle")
    axes[0].legend(fontsize=8)
    selected = rows[-3:]
    error = np.array([r["mean"]-r["expected_radiance"] for r in selected])
    halfwidth = np.array([(r["pointwise_95pct_seed_mean_interval"][1]-r["pointwise_95pct_seed_mean_interval"][0])/2
                         for r in selected])
    axes[1].axhline(0., color="black", linewidth=.8)
    axes[1].errorbar(np.arange(3), error, yerr=halfwidth, fmt="o", capsize=4, color="#ba7040")
    axes[1].set(xticks=np.arange(3), xticklabels=["Clear dielectric", "8x scale", "Varying radius"],
                ylabel="Mean radiance minus analytic expectation",
                title="Independent boundary and geometry controls")
    for axis in axes:
        axis.grid(alpha=.18)
    fig.savefig(out/"physics_oracles.png", dpi=170)
    plt.close(fig)


def run(output, *, resolution=16, spp=2048, seeds=DEFAULT_SEEDS):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("existing validation outputs are never overwritten")
    if (len(seeds) < 2 or len(seeds) != len(set(seeds))
            or any(isinstance(seed, bool) or not isinstance(seed, (int, np.integer))
                   or seed < 0 for seed in seeds)):
        raise ValueError("at least two distinct nonnegative integer seeds are required")
    if (isinstance(resolution, bool) or not isinstance(resolution, (int, np.integer))
            or resolution < 1 or isinstance(spp, bool)
            or not isinstance(spp, (int, np.integer)) or spp < 1):
        raise ValueError("positive integer resolution and spp are required")
    output.mkdir(parents=True, exist_ok=True)
    before, started, start = source_hashes(), utc_now(), time.perf_counter()
    manifest = {"schema": SCHEMA, "status": "running", "started_utc": started,
                "producer_source_sha256": before, "requested_resolution": int(resolution),
                "requested_spp": int(spp), "seeds": list(map(int, seeds)),
                "planned_actual_render_calls": len(CASES)*len(seeds),
                "actual_render_calls": 0, "command": sys.argv}
    write_json(output/"experiment_manifest.json", manifest)
    try:
        fixtures = {name: build_fixture(name) for name in ("cylinder", "scaled_cylinder", "tapered")}
        for name, fixture in fixtures.items():
            save_tapered_tube(output/"geometry"/name, fixture)
        cfg = RenderConfig(mode="furnace", resolution=int(resolution), spp=int(spp),
                           width_fraction=.3, view_elevation_deg=90., max_depth=64, rr_depth=128)
        mi = get_mitsuba()
        raw_images, rows = [], []
        for case, fixture_name, scale, depth, index in CASES:
            fixture = fixtures[fixture_name]
            mu = depth/scale
            material = MaterialSpectrum.from_absorption("oracle", (450., 550., 650.),
                index, mu, source="synthetic known-coefficient analytic physics oracle",
                provenance_json=json.dumps({"optical_depth": depth, "axial_length_mm": scale}))
            scene, metadata = build_volume_scene([fixture], [material], 550., cfg)
            # Every orthographic pixel sample is within the inscribed polygon
            # at every ring. Thus all index-matched paths cross both flat caps.
            maximum_camera_radius = .5*metadata["rig"]["film_width_mm"]*np.sqrt(2)
            minimum_polygon_inradius = float(fixture.profile.node_radius_mm.min()*np.cos(np.pi/fixture.radial_segments))
            if maximum_camera_radius >= minimum_polygon_inradius:
                raise RuntimeError("analytic fixture camera footprint escapes a tube cross section")
            ray = mi.Ray3f(mi.Point3f(.03*scale, .02*scale, .5*scale), mi.Vector3f(0., 0., -1.))
            exit_hit = scene.ray_intersect(ray)
            point = np.asarray(exit_hit.p).ravel().astype(float)
            normal = np.asarray(exit_hit.n).ravel().astype(float)
            if (not bool(np.asarray(exit_hit.is_valid())[0]) or abs(point[2]) > 1e-6*scale
                    or not np.allclose(normal, (0., 0., -1.), atol=1e-6, rtol=0)):
                raise RuntimeError("closed boundary failed its internal axial exit oracle")
            images, renders = [], []
            for seed in seeds:
                image, render = render_volume_scene(scene, metadata, seed=int(seed), spp=int(spp))
                images.append(image); renders.append(render)
                manifest["actual_render_calls"] += 1
            images = np.asarray(images, dtype=np.float32)
            raw_images.append(images)
            seed_means = images[..., 0].astype(np.float64).mean(axis=(1, 2))
            expected = float(np.exp(-depth))
            stats = seed_interval(seed_means)
            ray_count = len(seeds)*int(resolution)**2*int(spp)
            # For the index-matched pure absorber each camera sample survives
            # with Beer probability. This six-SE guard catches implementation
            # errors without requiring every pointwise 95% interval to cover.
            guard = float(6*np.sqrt(expected*(1-expected)/ray_count)+1e-4)
            error = stats["mean"]-expected
            row = {"case": case, "fixture": fixture_name, "axial_length_mm": scale,
                   "optical_depth": depth, "n_real": index, "absorption_per_mm": mu,
                   "expected_radiance": expected, **stats, "seed_means": seed_means.tolist(),
                   "error_from_analytic_mean": error, "relative_error_from_analytic_mean": error/expected,
                   "pointwise_95pct_interval_contains_analytic":
                       stats["pointwise_95pct_seed_mean_interval"][0] <= expected <= stats["pointwise_95pct_seed_mean_interval"][1],
                   "oracle_guard_absolute_tolerance": guard, "oracle_guard_passed": abs(error) <= guard,
                   "guard_definition": "6 analytic Bernoulli standard errors of all camera paths plus 1e-4 numerical allowance; not a reported confidence interval",
                   "scalar_camera_path_count": ray_count,
                   "camera_max_radius_mm": maximum_camera_radius,
                   "minimum_cross_section_inradius_mm": minimum_polygon_inradius,
                   "internal_exit_position_mm": point.tolist(), "internal_exit_normal": normal.tolist(),
                   "scene": metadata, "renders": renders}
            rows.append(row)
            print(json.dumps({key: row[key] for key in ("case", "mean", "expected_radiance",
                "relative_error_from_analytic_mean", "oracle_guard_passed")}), flush=True)
        stacked = np.asarray(raw_images, dtype=np.float32)
        np.savez_compressed(output/"scalar_radiance.npz", images=stacked,
                            case_names=np.asarray([c[0] for c in CASES]),
                            seeds=np.asarray(seeds, dtype=np.int64),
                            expected_radiance=np.asarray([r["expected_radiance"] for r in rows]))
        by_name = {r["case"]: r for r in rows}
        baseline = np.asarray(by_name["beer_tau_075"]["seed_means"])
        comparisons = {}
        for name in ("scaled_tau_075", "tapered_tau_075"):
            difference = np.asarray(by_name[name]["seed_means"])-baseline
            comparisons[name+"_minus_beer_tau_075"] = {
                **seed_interval(difference), "seed_paired_differences": difference.tolist(),
                "expected_difference": 0.,
                "scope": "same optical depth in index-matched straight geometry; not general textile radius invariance"}
        metrics = {"schema": SCHEMA, "case_count": len(rows), "seeds": list(map(int, seeds)),
                   "actual_render_calls": manifest["actual_render_calls"],
                   "resolution": int(resolution), "spp": int(spp),
                   "image_axes": ["case", "seed", "y", "x", "replicated_scalar_channel"],
                   "spectral_mode": "550 nm scalar material parameters in gray RGB backend; not wavelength-integrated color",
                   "raw_file": "scalar_radiance.npz", "raw_file_sha256": sha256(output/"scalar_radiance.npz"),
                   "cases": rows, "paired_controls": comparisons,
                   "all_oracle_guards_passed": all(r["oracle_guard_passed"] for r in rows),
                   "all_internal_exit_checks_passed": True,
                   "geometry_scale_ratio": fixtures["scaled_cylinder"].signed_volume_mm3/fixtures["cylinder"].signed_volume_mm3,
                   "geometry_scale_ratio_expected": 8.**3,
                   "limitations": ["known synthetic coefficients, not real textile validation",
                        "camera footprint stays inside every straight cross-section",
                        "these Beer tests isolate medium units and boundary exit; they do not validate general refracting caustics",
                        "pointwise seed intervals cover only render noise and are not adjusted for multiple cases",
                        "closed manifold topology does not alone certify arbitrary mesh self-intersection absence"]}
        write_json(output/"validation_metrics.json", metrics)
        make_figure(output, rows)
        after = source_hashes()
        drift = [name for name in before if before[name] != after[name]]
        status = "passed" if metrics["all_oracle_guards_passed"] and not drift else "failed"
        files = {str(path.relative_to(output)): {"bytes": path.stat().st_size, "sha256": sha256(path)}
                 for path in sorted(output.rglob("*")) if path.is_file() and path.name != "experiment_manifest.json"}
        manifest.update(status=status, finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
                        producer_source_sha256_after=after, source_drift=drift,
                        runtime={"python": sys.version, "numpy": np.__version__, "scipy": scipy_version,
                                 "mitsuba": mi.__version__, "variant": mi.variant()}, output_files=files,
                        all_oracle_guards_passed=metrics["all_oracle_guards_passed"],
                        independent_seed_count=len(seeds), actual_case_count=len(CASES))
        write_json(output/"experiment_manifest.json", manifest)
        if status != "passed":
            raise RuntimeError("physics oracle guard or producer source stability failed")
        return manifest
    except Exception as exc:
        manifest.update(status="failed", finished_utc=utc_now(), elapsed_seconds=time.perf_counter()-start,
                        error_type=type(exc).__name__, error=str(exc))
        write_json(output/"experiment_manifest.json", manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"data/validation_v5/volume_physics")
    parser.add_argument("--resolution", type=positive_int, default=16)
    parser.add_argument("--spp", type=positive_int, default=2048)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    args = parser.parse_args()
    result = run(args.output, resolution=args.resolution, spp=args.spp, seeds=args.seeds)
    print(json.dumps({"status": result["status"], "actual_render_calls": result["actual_render_calls"],
                      "output": str(args.output.resolve()), "elapsed_seconds": result["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
