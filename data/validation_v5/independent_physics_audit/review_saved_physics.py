"""Recompute saved v5 analytic-oracle statistics without importing a renderer.

Run from the repository root; input files are read only. The optional installed
header directory is read for source evidence, without executing intersection
queries. No new Monte Carlo samples or renderer calls are made by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

import numpy as np
from scipy.stats import t as student_t


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(value):
    a = np.ascontiguousarray(value)
    header = json.dumps([a.shape, a.dtype.str], separators=(",", ":"))
    h = hashlib.sha256(header.encode("ascii"))
    h.update(a.tobytes())
    return h.hexdigest()


def close(actual, expected):
    np.testing.assert_allclose(actual, expected, rtol=2e-13, atol=2e-15)


def statistics(values):
    values = np.asarray(values, dtype=np.float64)
    mean = float(np.mean(values))
    se = float(np.sqrt(np.sum((values-mean)**2)/(len(values)*(len(values)-1))))
    half = float(student_t.ppf(.975, len(values)-1))*se
    return mean, se, [mean-half, mean+half]


def run(source, ray_audit, headers_root=None):
    manifest_path = source/"experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    metrics = json.loads((source/"validation_metrics.json").read_text())
    crc_files = 0
    for relative, row in manifest["output_files"].items():
        p = source/relative
        assert p.stat().st_size == row["bytes"]
        assert digest(p) == row["sha256"]
        if p.suffix == ".npz":
            with zipfile.ZipFile(p) as archive:
                assert archive.testzip() is None
            crc_files += 1
    with (source/"scalar_radiance.npz").open("rb") as stream:
        with np.load(stream, allow_pickle=False) as archive:
            assert set(archive.files) == {"images", "case_names", "seeds", "expected_radiance"}
            images = archive["images"]
            names = archive["case_names"].tolist()
            seeds = archive["seeds"].tolist()
            expected_array = archive["expected_radiance"]
    assert images.dtype == np.float32 and images.shape == (8, 4, 16, 16, 3)
    assert np.all(np.isfinite(images)) and np.all(images >= 0)
    assert np.array_equal(images[..., 0], images[..., 1])
    assert np.array_equal(images[..., 0], images[..., 2])
    assert len(names) == len(set(names)) == metrics["case_count"] == 8
    assert seeds == metrics["seeds"] == manifest["seeds"] and len(set(seeds)) == 4
    assert names == [row["case"] for row in metrics["cases"]]
    assert metrics["actual_render_calls"] == manifest["actual_render_calls"] == 32
    assert digest(source/"scalar_radiance.npz") == metrics["raw_file_sha256"]
    means = images[..., 0].astype(np.float64).mean(axis=(2, 3))
    count = len(seeds)*images.shape[2]*images.shape[3]*metrics["spp"]
    rows = []
    for i, row in enumerate(metrics["cases"]):
        expected = math.exp(-row["absorption_per_mm"]*row["axial_length_mm"])
        close(expected, math.exp(-row["optical_depth"]))
        close(expected, expected_array[i])
        close(expected, row["expected_radiance"])
        mean, se, interval = statistics(means[i])
        close(means[i], row["seed_means"])
        close([mean, se], [row["mean"], row["seed_standard_error"]])
        close(interval, row["pointwise_95pct_seed_mean_interval"])
        guard = 6*math.sqrt(expected*(1-expected)/count)+1e-4
        close(guard, row["oracle_guard_absolute_tolerance"])
        assert count == row["scalar_camera_path_count"]
        error = mean-expected
        close(error, row["error_from_analytic_mean"])
        close(error/expected, row["relative_error_from_analytic_mean"])
        guard_pass = abs(error) <= guard
        covered = interval[0] <= expected <= interval[1]
        assert guard_pass == row["oracle_guard_passed"]
        assert covered == row["pointwise_95pct_interval_contains_analytic"]
        assert len(row["renders"]) == len(seeds)
        for j, render in enumerate(row["renders"]):
            assert render["seed"] == seeds[j]
            assert array_digest(images[i, j]) == render["raw_float32_sha256"]
        material = row["scene"]["materials"]["oracle"]
        close(4*math.pi*material["kappa"]/(material["wavelength_nm"]*1e-6),
              row["absorption_per_mm"])
        close(material["sigma_t_per_scene_unit"], row["absorption_per_mm"])
        assert material["albedo"] == 0
        assert row["camera_max_radius_mm"] < row["minimum_cross_section_inradius_mm"]
        rows.append({"case": row["case"], "mean": mean, "expected": expected,
                     "pointwise_95_seed_interval": interval,
                     "analytic_covered_by_seed_interval": bool(covered),
                     "absolute_oracle_guard": guard, "guard_passed": bool(guard_pass)})
    paired = {}
    for key, row in metrics["paired_controls"].items():
        after, before = key.split("_minus_")
        delta = means[names.index(after)]-means[names.index(before)]
        mean, se, interval = statistics(delta)
        close(delta, row["seed_paired_differences"])
        close([mean, se], [row["mean"], row["seed_standard_error"]])
        close(interval, row["pointwise_95pct_seed_mean_interval"])
        paired[key] = {"mean_difference": mean, "pointwise_95_seed_interval": interval,
                       "zero_in_interval": bool(interval[0] <= 0 <= interval[1])}
    ray = json.loads(ray_audit.read_text())
    path_expectations = []
    for row in ray["rows"]:
        value = math.exp(-row["absorption_per_mm"]*row["measured_internal_path_mm"])
        close(value, row["expected_using_measured_path"])
        path_expectations.append(value)
    prediction = path_expectations[1]-path_expectations[0]
    close(prediction, ray["predicted_scaled_minus_baseline"])
    interval = paired["scaled_tau_075_minus_beer_tau_075"]["pointwise_95_seed_interval"]
    installed_headers = []
    if headers_root is not None:
        revision = "478e193a183c21723f4a8251afc3ad29a8da4c5e"
        specifications = [
            ("render/interaction.h", "77a5a8b50f586a388b940642046696ae012fc9606b8bb6bc5f308e817ebac60b"),
            ("core/math.h", "297f0ca1dbbdf21171de0eca978647d422fe9fc739e48c54aac757fb6e730cb0")]
        for relative, expected_sha in specifications:
            actual_sha = digest(headers_root/relative)
            assert actual_sha == expected_sha
            installed_headers.append({"relative_path": relative, "installed_file_sha256": actual_sha,
                "source_audit_declared_pinned_url": f"https://github.com/mitsuba-renderer/mitsuba3/blob/{revision}/include/mitsuba/{relative}",
                "remote_commit_independently_fetched_in_this_check": False})
    return {"schema": "textile.independent_saved_physics_review/5.0", "status": "passed",
        "review_script_sha256": digest(__file__),
        "input_manifest_sha256": digest(manifest_path),
        "raw_file_sha256": digest(source/"scalar_radiance.npz"),
        "input_output_files_hash_verified": len(manifest["output_files"]), "npz_crc_verified": crc_files,
        "raw_shape": list(images.shape), "saved_render_records_verified": 32,
        "actual_new_render_calls": 0, "independent_seeds_per_case": len(seeds),
        "cases": rows, "paired_controls": paired,
        "ray_offset": {"recorded_audit_sha256": digest(ray_audit),
            "predicted_scaled_minus_baseline_from_recorded_paths": prediction,
            "prediction_inside_paired_interval": bool(interval[0] <= prediction <= interval[1]),
            "scope": "Independent arithmetic on recorded path lengths; original intersection queries were not re-executed."},
        "installed_header_evidence": installed_headers,
        "limits": ["Hash and array consistency is not independent execution attestation.",
            "Scalar RGB channels are identical and are not independent samples.",
            "Pointwise t intervals use four seed means; they cover Monte Carlo noise only.",
            "The analytic six-SE plus 1e-4 guard is not a confidence interval.",
            "Both unit-scale cases pass their oracle guard, but their paired interval excludes zero: exact numerical unit invariance is not established.",
            "The recorded ray-offset prediction is consistent with the simple cap comparison; it does not attribute every textile-image discrepancy.",
            "Current producer source hashes and remote pinned source contents were not separately fetched or checked in this review."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ray-offset", type=Path, required=True)
    parser.add_argument("--headers-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to replace an existing audit result")
    result = run(args.input, args.ray_offset, args.headers_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"status": result["status"], "saved_render_records_verified": 32,
        "new_render_calls": 0, "paired_controls": result["paired_controls"]}, indent=2))
