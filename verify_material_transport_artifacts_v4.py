#!/usr/bin/env python3
"""Recompute v4 artifact consistency from saved numeric arrays, without rendering.

This verifies declared kinematics, bookkeeping, geometry/scene/export identity,
projection statistics and paired radiance intervals. It does not certify real
material deformation, renderer correctness, or that arrays prove an invocation
history. No experiment-driver code is imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from textile_sim.hierarchy import audit_clearance, load_hierarchy, rotation_minimizing_frames
from textile_sim.material_transport import SCHEMA_VERSION
from textile_sim.optical_lod import SGGXProjection, paired_mean_interval, projected_area_density
from textile_sim.optical_scene import OpticalScene, microstructure_statistics, polyline_bspline_controls

STATES = ("initial", "regenerated", "transported")
MODES = ("constant_reference", "incompressible_segments")
LIGHTS = ("R0", "R90", "T45")
PROVENANCE = ("fiber_id", "yarn_id", "ply_id", "material_id", "family", "yarn_index",
              "ply_index", "fiber_index", "kind", "cross_section")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path):
    def invalid(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _npz(path):
    with np.load(path, allow_pickle=False) as z:
        arrays = {key: z[key].copy() for key in z.files}
    for key, a in arrays.items():
        _require(a.dtype.kind in "fiu" and np.isfinite(a).all(), f"nonfinite/nonnumeric array: {key}")
    return arrays


def _close(actual, expected, label, *, atol=2e-12, rtol=2e-11):
    a, b = np.asarray(actual), np.asarray(expected)
    _require(a.shape == b.shape and a.dtype.kind in "bfiu" and b.dtype.kind in "bfiu",
             f"shape/type mismatch: {label}")
    _require(np.isfinite(a).all() and np.isfinite(b).all()
             and np.allclose(a, b, atol=atol, rtol=rtol), f"numeric mismatch: {label}")


def _arc(points):
    p = np.asarray(points)
    _require(p.ndim == 2 and p.shape[1] == 3 and len(p) >= 2, "invalid point array")
    length = np.linalg.norm(np.diff(p, axis=0), axis=1)
    _require(np.isfinite(length).all() and np.all(length > 0), "zero/nonfinite segment length")
    return np.r_[0., np.cumsum(length)]


def _coords(u, count, label):
    _require(u.shape == (count,) and u[0] == 0. and np.all(np.diff(u) > 0),
             f"invalid increasing material labels: {label}")


def _compare_fields(saved, computed, label):
    for key, value in computed.items():
        _require(key in saved, f"missing summary field: {label}/{key}")
        if isinstance(value, dict):
            _compare_fields(saved[key], value, label+"/"+key)
        elif isinstance(value, (str, bool)) or value is None:
            _require(saved[key] == value, f"metadata mismatch: {label}/{key}")
        else:
            _close(saved[key], value, label+"/"+key)


def _frame_sample(parent, u):
    knots, p, f = (parent[k] for k in ("material_coordinates_mm", "points_mm", "frames"))
    _require(np.all(u >= knots[0]) and np.all(u <= knots[-1]), "unsupported parent material labels")
    centers = np.column_stack([np.interp(u, knots, p[:, k]) for k in range(3)])
    frames = f if np.array_equal(u, knots) else Slerp(knots, Rotation.from_matrix(f))(u).as_matrix()
    return centers, frames


def _mapped(source, target, points, u):
    a, fa = _frame_sample(source, u); b, fb = _frame_sample(target, u)
    return b + np.einsum("nij,nkj,nk->ni", fb, fa, points-a)


def _group_summary(fibers):
    l0 = np.concatenate([f["reference_lengths"] for f in fibers])
    l1 = np.concatenate([f["lengths"] for f in fibers])
    v0 = np.concatenate([f["reference_volumes"] for f in fibers])
    v1 = np.concatenate([f["volumes"] for f in fibers])
    stretch = l1/l0; before, after = float(l0.sum()), float(l1.sum())
    return {"fiber_count": len(fibers), "vertex_count": sum(len(f["points_mm"]) for f in fibers),
        "segment_count": len(l0), "reference_fiber_length_mm": before,
        "deformed_fiber_length_mm": after, "relative_fiber_length_change": after/before-1,
        "min_segment_stretch": float(stretch.min()), "max_segment_stretch": float(stretch.max()),
        "reference_length_weighted_mean_engineering_strain": float(np.dot(l0, stretch-1)/before),
        "reference_length_weighted_rms_engineering_strain": float(np.sqrt(np.dot(l0, (stretch-1)**2)/before)),
        "reference_cylinder_segment_volume_mm3": float(v0.sum()),
        "deformed_cylinder_segment_volume_mm3": float(v1.sum()),
        "relative_cylinder_segment_volume_change": float(v1.sum()/v0.sum()-1),
        "max_absolute_relative_segment_volume_change": float(np.max(np.abs(v1/v0-1)))}


def _tracking(folder, mode):
    doc = _json(folder/"material_transport.json")
    _require(doc["schema_version"] == SCHEMA_VERSION and doc["array_file"] == "material_transport.npz",
             "unsupported tracking schema or array path")
    _require(_sha(folder/doc["array_file"]) == doc["array_file_sha256"], "tracking NPZ SHA-256 mismatch")
    arrays, used = _npz(folder/doc["array_file"]), set()
    def take(prefix, field):
        key = prefix+"/"+field
        _require(key in arrays and key not in used, f"missing/duplicate tracking array {key}")
        used.add(key); return arrays[key]
    parents, ply_parents = {"yarns": {}, "plies": {}}, {}
    for kind in parents:
        for row in doc["array_layout"]["parents"][kind]:
            key, prefix = row["id"], row["array_prefix"]
            _require(key not in parents[kind], "duplicate parent ID")
            poses = {}
            for pose in ("reference", "deformed"):
                values = {name: take(prefix, pose+"/"+name) for name in
                          ("points_mm", "material_coordinates_mm", "arclength_mm", "frames", "initial_normal")}
                arc = _arc(values["points_mm"])
                _coords(values["material_coordinates_mm"], len(arc), key)
                _close(values["arclength_mm"], arc, "parent arclength "+key)
                if pose == "reference":
                    _close(values["material_coordinates_mm"], arc, "reference parent labels "+key, atol=0., rtol=0.)
                frames = values["frames"]
                _require(frames.shape == (len(arc), 3, 3), "invalid frame shape")
                _close(np.einsum("nji,njk->nik", frames, frames),
                       np.broadcast_to(np.eye(3), frames.shape), "frame orthogonality")
                _close(np.linalg.det(frames), np.ones(len(arc)), "proper frame determinant")
                t, n, b = rotation_minimizing_frames(values["points_mm"], initial_normal=values["initial_normal"])
                _close(frames, np.stack((t, n, b), axis=-1), "stored RMF/director consistency", atol=2e-11)
                poses[pose] = values
            _close(poses["reference"]["material_coordinates_mm"][-1],
                   poses["deformed"]["material_coordinates_mm"][-1], "parent material endpoint", atol=0., rtol=0.)
            if kind == "plies":
                ply_parents[key] = row["parent_yarn_id"]
                poses["parent_coordinates"] = take(prefix, "parent_material_coordinates_mm")
            parents[kind][key] = poses
    for key, poses in parents["plies"].items():
        _require(ply_parents[key] in parents["yarns"], "missing ply parent yarn")
        yarn = parents["yarns"][ply_parents[key]]
        _close(poses["parent_coordinates"], yarn["reference"]["material_coordinates_mm"],
               "declared ply/yarn shared material labels", atol=0., rtol=0.)
        _close(poses["deformed"]["points_mm"],
               _mapped(yarn["reference"], yarn["deformed"], poses["reference"]["points_mm"], poses["parent_coordinates"]),
               "declared yarn-to-ply pose")
        rotation = yarn["deformed"]["frames"][0] @ yarn["reference"]["frames"][0].T
        a = rotation @ poses["reference"]["frames"][0, :, 0]
        b = poses["deformed"]["frames"][0, :, 0]
        cosine, v = float(np.clip(a@b, -1., 1.)), np.cross(a, b)
        _require(cosine > -1+1e-9, "ambiguous antiparallel child tangent alignment")
        skew = np.array([[0., -v[2], v[1]], [v[2], 0., -v[0]], [-v[1], v[0], 0.]])
        alignment = np.eye(3)+skew+skew@skew/(1+cosine)
        n = alignment @ rotation @ poses["reference"]["initial_normal"]
        n = n-(n@b)*b; n /= np.linalg.norm(n)
        _close(poses["deformed"]["initial_normal"], n, "declared child-director transport")
    fibers, families, seen = [], {}, set()
    fields = ("reference_points_mm", "points_mm", "material_coordinates_mm", "parent_material_coordinates_mm",
              "deformed_arclength_mm", "segment_stretch", "engineering_strain", "log_strain",
              "segment_radius_mm", "reference_segment_volume_mm3", "segment_volume_mm3")
    for row in doc["array_layout"]["fibers"]:
        fid = row["fiber_id"]
        _require(fid not in seen, "duplicate fiber ID"); seen.add(fid)
        f = {name: take(row["array_prefix"], name) for name in fields}
        f["provenance"] = {k: row[k] for k in PROVENANCE}; f["radius_mm"] = float(row["reference_radius_mm"])
        _require(np.isfinite(f["radius_mm"]) and f["radius_mm"] > 0, "invalid reference radius")
        _require(row["ply_id"] in parents["plies"] and ply_parents[row["ply_id"]] == row["yarn_id"], "fiber parent association mismatch")
        ply = parents["plies"][row["ply_id"]]
        a0, a1 = _arc(f["reference_points_mm"]), _arc(f["points_mm"])
        _close(f["material_coordinates_mm"], a0, "original fiber material labels", atol=0., rtol=0.)
        _close(f["parent_material_coordinates_mm"], ply["reference"]["material_coordinates_mm"],
               "fiber/ply shared material labels", atol=0., rtol=0.)
        _close(f["deformed_arclength_mm"], a1, "current fiber arclength")
        l0, l1 = np.diff(a0), np.diff(a1)
        stretch = l1/l0
        radius = np.full_like(stretch, f["radius_mm"]) if mode == MODES[0] else f["radius_mm"]/np.sqrt(stretch)
        v0, v1 = np.pi*f["radius_mm"]**2*l0, np.pi*radius**2*l1
        for field, expected in (("segment_stretch", stretch), ("engineering_strain", stretch-1),
             ("log_strain", np.log(stretch)), ("segment_radius_mm", radius),
             ("reference_segment_volume_mm3", v0), ("segment_volume_mm3", v1)):
            _close(f[field], expected, "fiber "+fid+"/"+field, atol=1e-16)
        _close(f["points_mm"], _mapped(ply["reference"], ply["deformed"],
                   f["reference_points_mm"], f["parent_material_coordinates_mm"]), "declared ply-to-fiber pose")
        f.update(reference_lengths=l0, lengths=l1, reference_volumes=v0, volumes=v1)
        fibers.append(f); families.setdefault(row["family"], []).append(f)
    _require(fibers and set(arrays) == used, "empty fibers or unaccounted tracking arrays")
    # Digest is recomputed from stored bytes. Re-normalizing saved frame seeds
    # and hashing a reconstructed float result would introduce artificial ULP changes.
    header = {"schema": SCHEMA_VERSION, "spec": doc["reference_spec"],
              "correspondence": doc["summary"]["material_correspondence"], "ply_yarn_ids": ply_parents}
    h = hashlib.sha256(_canonical(header).encode())
    def add(values):
        for a in values:
            h.update(np.asarray(a, dtype="<f8").tobytes())
    for kind in ("yarns", "plies"):
        for key, poses in sorted(parents[kind].items()):
            p = poses["reference"]
            h.update(_canonical(["yarn" if kind == "yarns" else "ply", key, p["points_mm"].shape]).encode())
            add(p[name] for name in ("points_mm", "material_coordinates_mm", "frames"))
            if kind == "plies": add([poses["parent_coordinates"]])
    for f in fibers:
        h.update(_canonical({**f["provenance"], "vertex_count": len(f["points_mm"])}).encode())
        add([f["reference_points_mm"], np.full(len(f["points_mm"]), f["radius_mm"]),
             f["material_coordinates_mm"], f["parent_material_coordinates_mm"]])
    ref_sha = h.hexdigest()
    _require(ref_sha == doc["summary"]["reference_sha256"], "reference semantic digest mismatch")
    h = hashlib.sha256((ref_sha+"|"+mode).encode("ascii"))
    for kind in ("yarns", "plies"):
        for key, poses in sorted(parents[kind].items()):
            p = poses["deformed"]
            h.update(_canonical([key, p["points_mm"].shape]).encode())
            add(p[name] for name in ("points_mm", "material_coordinates_mm", "frames"))
    for f in fibers:
        h.update(f["provenance"]["fiber_id"].encode()); add([f["points_mm"], f["segment_radius_mm"]])
    _require(h.hexdigest() == doc["summary"]["state_sha256"], "state semantic digest mismatch")
    summary = {"radius_mode": mode, "fiber_material_points_tracked": True,
        "physical_mass_conservation_certified": False, "contact_or_clearance_certified": False,
        "segment_cylinder_volume_conservation_enforced": mode == MODES[1],
        "all": _group_summary(fibers), "families": {k: _group_summary(v) for k, v in sorted(families.items())}}
    _compare_fields(doc["summary"], summary, "tracking summary")
    return {"summary": summary, "document": doc, "parents": parents, "fibers": fibers}


def _geometry(root, tracking):
    metrics = _json(root/"geometry_metrics.json")
    _require(metrics["length_unit"] == "mm" and set(metrics["states"]) == set(STATES), "geometry states/units mismatch")
    geometries, audits, summaries = {}, {}, {}
    fields = ("yarn_count", "ply_count", "fiber_count", "vertex_count", "fiber_counts_by_material",
              "total_fiber_length_mm", "cylinder_volume_proxy_mm3", "bounds_mm")
    for state in STATES:
        g = load_hierarchy(root/"geometry"/state)
        summaries[state] = {k: g.summary()[k] for k in fields}
        _compare_fields(metrics["states"][state], summaries[state], "geometry/"+state)
        audit = audit_clearance(g)
        _require(audit["certified_separated"], "different-fiber clearance not certified: "+state)
        audit_keys = ("certified_separated", "minimum_clearance_lower_bound_mm", "minimum_tested_clearance_mm",
                      "overlapping_capsule_pairs", "total_segments")
        _compare_fields(metrics["clearance_audits"][state], {k: audit[k] for k in audit_keys}, "clearance/"+state)
        geometries[state], audits[state] = g, audit
    for mode in MODES:
        _compare_fields(metrics["transport_states"][mode], tracking[mode]["summary"], "geometry transport summary")
    _require(metrics["incompressible_optical_export"]["blocked"] is True, "unsupported radius export was not blocked")
    for state, pose in (("initial", "reference"), ("transported", "deformed")):
        g, t = geometries[state], tracking[MODES[0]]
        _require(len(g.fiber_records) == len(t["fibers"]), "hierarchy/tracking fiber count mismatch")
        for record, raw in zip(g.fiber_records, t["fibers"]):
            _require(record.provenance() == raw["provenance"], "hierarchy/tracking fiber provenance mismatch")
            _close(record.points_mm, raw["reference_points_mm" if pose == "reference" else "points_mm"], "hierarchy/tracking pose")
            _close(record.radius_mm, raw["radius_mm"], "hierarchy/tracking radius", atol=0., rtol=0.)
        for kind in ("yarns", "plies"):
            _require(set(getattr(g, kind)) == set(t["parents"][kind]), "hierarchy/tracking parent IDs mismatch")
            for key, points in getattr(g, kind).items():
                _close(points, t["parents"][kind][key][pose]["points_mm"], "hierarchy/tracking parent pose")
    a, b = geometries["regenerated"], geometries["transported"]
    _require(a.provenance == b.provenance, "regenerated/tracked components differ")
    errors, angles = [], []
    for f, g in zip(a.fiber_records, b.fiber_records):
        errors.extend(np.linalg.norm(f.points_mm-g.points_mm, axis=1))
        u, v = np.diff(f.points_mm, axis=0), np.diff(g.points_mm, axis=0)
        cos = np.einsum("ij,ij->i", u, v)/(np.linalg.norm(u, axis=1)*np.linalg.norm(v, axis=1))
        angles.extend(np.rad2deg(np.arccos(np.clip(cos, -1., 1.))))
    comparison = {"rms_vertex_position_difference_mm": float(np.sqrt(np.mean(np.square(errors)))),
        "maximum_vertex_position_difference_mm": float(np.max(errors)),
        "rms_segment_tangent_angle_difference_deg": float(np.sqrt(np.mean(np.square(angles)))),
        "maximum_segment_tangent_angle_difference_deg": float(np.max(angles))}
    _compare_fields(metrics["regenerated_vs_transported"], comparison, "geometry comparison")
    _require(np.isfinite(metrics["identity_max_point_error_mm"]) and metrics["identity_max_point_error_mm"] <= 1e-11,
             "recorded identity residual exceeds gate")
    identity_error = max(float(np.max(np.linalg.norm(_mapped(
        tracking[MODES[0]]["parents"]["plies"][f["provenance"]["ply_id"]]["reference"],
        tracking[MODES[0]]["parents"]["plies"][f["provenance"]["ply_id"]]["reference"],
        f["reference_points_mm"], f["parent_material_coordinates_mm"])-f["reference_points_mm"], axis=1)))
        for f in tracking[MODES[0]]["fibers"])
    _require(identity_error <= 1e-11, "raw reference-frame identity residual exceeds gate")
    for key in a.yarns:
        _close(a.yarns[key], b.yarns[key], "shared regenerated/tracked parent pose")
    return geometries, audits, {"states": summaries, "regenerated_vs_transported": comparison,
                               "raw_reference_frame_identity_error_mm": identity_error,
                               "clearance_audits": audits}


def _export(folder, scene, audit, budget):
    doc = _json(folder/"manifest.json"); expected_hash = doc.pop("manifest_sha256")
    _require(hashlib.sha256(_canonical(doc).encode()).hexdigest() == expected_hash, "renderer manifest hash mismatch")
    _require(doc["scene_sha256"] == scene.sha256 and doc["scene_units"] == "mm", "renderer scene identity/units mismatch")
    fiber_map, used, displacement = {f.fiber_id: f for f in scene.fibers}, set(), 0.
    for group in doc["groups"]:
        name = group["filename"]
        _require(Path(name).name == name, "unexpected curve file path")
        path = folder/name
        _require(_sha(path) == group["file_sha256"], "renderer curve-file hash mismatch")
        blocks, current = [], []
        for line in path.read_text().splitlines()+[""]:
            if line.strip(): current.append([float(x) for x in line.split()])
            elif current: blocks.append(np.asarray(current)); current = []
        _require(len(blocks) == group["fiber_count"] == len(group["fiber_ids"]), "renderer curve/group count mismatch")
        smoothing, quantization, radius_quantization = 0., 0., 0.
        for fid, values in zip(group["fiber_ids"], blocks):
            _require(fid in fiber_map and fid not in used, "renderer fiber ID mismatch"); used.add(fid)
            f = fiber_map[fid]; controls, bound = polyline_bspline_controls(f.points_mm)
            _require(f.material_id == group["material_id"] and f.radius_mm == group["radius_mm"], "renderer material/radius association mismatch")
            _close(values, np.column_stack((controls, np.full(len(controls), f.radius_mm))), "renderer spline control export", atol=0., rtol=0.)
            smoothing = max(smoothing, bound)
            quantization = max(quantization, float(np.max(np.linalg.norm(controls.astype(np.float32).astype(float)-controls, axis=1))))
            radius_quantization = max(radius_quantization, abs(float(np.float32(f.radius_mm))-f.radius_mm))
        _compare_fields(group, {"max_centerline_smoothing_bound_mm": smoothing,
            "float32_centerline_quantization_bound_mm": quantization,
            "float32_radius_quantization_bound_mm": radius_quantization}, "renderer displacement bounds")
        optical = scene.material_map[group["material_id"]].at(doc["wavelength_nm_vacuum"])
        _compare_fields(group, {key: optical[key] for key in ("n_real", "kappa", "absorption_per_mm")}, "renderer optical constants")
        _close(group["bsdf"]["int_ior"], optical["n_real"], "renderer internal index")
        _close(group["bsdf"]["ext_ior"], scene.background_n, "renderer external index")
        _close(group["bsdf"]["sigma_a"]["value"], optical["absorption_per_mm"]*group["radius_mm"], "renderer radius-normalized absorption")
        displacement = max(displacement, smoothing+quantization+radius_quantization)
    _require(used == set(fiber_map), "renderer export lost fibers")
    lower = audit["minimum_clearance_lower_bound_mm"] - 2*displacement
    _require(lower > 0, "export displacement exhausted different-fiber clearance")
    computed = {"source_clearance_lower_bound_mm": audit["minimum_clearance_lower_bound_mm"],
        "maximum_tube_displacement_bound_mm": displacement, "exported_clearance_lower_bound_mm": lower}
    _compare_fields(budget, computed, "exported clearance budget")
    return computed


def _projection(folder, state, scene, volume, saved):
    z = _npz(folder/(state+"_projected_area_fits.npz"))
    train, hold = z["train_directions"], z["heldout_directions"]
    _require(len(train) == saved["training_direction_count"] and len(hold) == saved["heldout_direction_count"], "projection direction count mismatch")
    _require(saved["scene_sha256"] == scene.sha256, "projection scene identity mismatch")
    _close(saved["averaging_volume_mm3"], volume, "projection common averaging volume")
    truth = projected_area_density(scene, hold, volume)["all"]
    _close(z["heldout_truth_per_mm"], truth, "raw projected-area truth")
    rms = float(np.sqrt(np.mean(truth**2)))
    _close(saved["heldout_target_rms_per_mm"], rms, "projected-area target RMS")
    rows = {row["level"]: row for row in saved["levels"]}
    _require(set(rows) == {"all", "family", "yarn", "ply"} and len(rows) == len(saved["levels"]), "projection levels missing/duplicated")
    output = {}
    for level, row in rows.items():
        groups = projected_area_density(scene, train, volume, group_by=level)
        _require(set(groups) == set(row["fit_groups"]) and row["group_count"] == len(groups), "projection group association mismatch")
        _require(row["parameters"] == 6*len(groups), "projection parameter count mismatch")
        prediction = sum(SGGXProjection(np.asarray(value["matrix_per_mm2"])).projected_area(hold)
                         for value in row["fit_groups"].values())
        _close(z[level+"_heldout_prediction_per_mm"], prediction, "projection matrix/raw prediction")
        delta = prediction-truth
        result = {"heldout_relative_rmse": float(np.sqrt(np.mean(delta**2))/rms),
                  "heldout_max_error_over_rms_target": float(np.max(np.abs(delta))/rms)}
        _compare_fields(row, result, "heldout projection error"); output[level] = result
    return output


def _optics(root, geometries, audits):
    folder = root/"optics"; metrics = _json(folder/"optical_metrics.json")
    _require(metrics["status"] in ("rendered", "skipped") and metrics["states"] == list(STATES), "incomplete optical artifact status/states")
    _require(metrics["rendered_radius_mode"] == MODES[0], "unsupported optical radius mode")
    scenes, exports, fits = {}, {}, {}
    for state in STATES:
        scene = OpticalScene.load(folder/(state+"_scene.json")); scenes[state] = scene
        _require(scene.sha256 == metrics["scene_sha256"][state], "scene digest mismatch")
        _require(len(scene.fibers) == len(geometries[state].fiber_records), "scene geometry fiber count mismatch")
        for f, g in zip(scene.fibers, geometries[state].fiber_records):
            _require(all(getattr(f, k) == getattr(g, k) for k in ("fiber_id", "yarn_id", "ply_id", "material_id", "family")), "scene geometry identity mismatch")
            _close(f.points_mm, g.points_mm, "scene geometry positions", atol=0., rtol=0.)
            _close(f.radius_mm, g.radius_mm, "scene geometry radius", atol=0., rtol=0.)
        _compare_fields(metrics["microstructure"][state], microstructure_statistics(scene), "raw microstructure statistics")
        exports[state] = _export(folder/(state+"_curves"), scene, audits[state], metrics["exported_clearance_budgets"][state])
    union = np.stack((np.min([s.bounds_mm[0] for s in scenes.values()], axis=0),
                      np.max([s.bounds_mm[1] for s in scenes.values()], axis=0)))
    volume = float(np.prod(union[1]-union[0]))
    _close(metrics["union_bounds_mm"], union, "common scene bounds")
    _close(metrics["averaging_volume_mm3"], volume, "common scene averaging volume")
    for state, scene in scenes.items():
        fits[state] = _projection(folder, state, scene, volume, metrics["projection_fits"][state])
    output = {"status": metrics["status"], "verified_saved_render_count": 0,
              "projection_errors": fits, "exported_clearance_budgets": exports, "paired_comparisons": []}
    _close(metrics["wavelengths_nm"], [450., 550., 650.], "diagnostic wavelengths", atol=0., rtol=0.)
    seeds = np.asarray(metrics["seeds"])
    _require(seeds.ndim == 1 and seeds.dtype.kind in "iu" and len(seeds) >= 2
             and len(set(seeds.tolist())) == len(seeds) and np.all(seeds >= 0), "invalid independent seed IDs")
    if metrics["status"] == "skipped":
        _require(metrics["actual_render_count"] == 0 and not metrics["records"] and not metrics["comparisons"], "skipped optics contains fabricated render counts/results")
        _require(not (folder/"spectral_radiance.npz").exists(), "skipped optics contains stale radiance arrays")
        return output
    path = folder/"spectral_radiance.npz"
    _require(_sha(path) == metrics["spectral_radiance_sha256"], "radiance NPZ SHA-256 mismatch")
    arrays = _npz(path); expected_keys = {state+"__"+light for state in STATES for light in LIGHTS}
    _require(set(arrays) == expected_keys | {"seeds", "wavelengths_nm"}, "radiance stack keys/count mismatch")
    _close(arrays["seeds"], seeds, "raw radiance seed order", atol=0., rtol=0.)
    _close(arrays["wavelengths_nm"], metrics["wavelengths_nm"], "raw radiance wavelengths", atol=0., rtol=0.)
    records, shape, total = {}, None, 0
    for row in metrics["records"]:
        key = row["state"]+"__"+row["light"]
        _require(key in expected_keys and key not in records and row["array_key"] == key
                 and row["array_file"] == path.name, "render record association mismatch")
        a = arrays[key]
        _require(a.ndim == 4 and a.shape[0] == len(seeds) and a.shape[-1] == 3
                 and a.shape[1] > 0 and a.shape[2] > 0 and np.min(a) >= -1e-7, "invalid saved radiance shape/sign")
        if shape is None: shape = a.shape
        _require(a.shape == shape, "rendered states use different image/replicate dimensions")
        expected_count = len(seeds)*3
        _require(row["actual_render_count"] == expected_count, "render record count mismatch")
        _close(row["seeds"], seeds, "render record seed order", atol=0., rtol=0.)
        _close(row["wavelengths_nm"], metrics["wavelengths_nm"], "render record wavelengths", atol=0., rtol=0.)
        if "render_config" in row:
            _require(row["render_config"] == metrics["lighting_configs"][row["light"]], "per-state render configuration mismatch")
            _require(a.shape[1:3] == (row["render_config"]["resolution"],)*2, "radiance/config resolution mismatch")
        records[key] = row; total += expected_count
    _require(set(records) == expected_keys and total == metrics["actual_render_count"], "total render record count mismatch")
    comparisons = set()
    for row in metrics["comparisons"]:
        key = (row["light"], row["from_state"], row["to_state"])
        _require(key not in comparisons and key[0] in LIGHTS and key[1] in ("initial", "regenerated")
                 and key[2] == "transported", "unexpected/duplicate paired comparison")
        comparisons.add(key)
        a = arrays[key[1]+"__"+key[0]].astype(float).mean(axis=(1, 2))
        b = arrays[key[2]+"__"+key[0]].astype(float).mean(axis=(1, 2))
        interval = paired_mean_interval(a, b)
        _compare_fields(row["paired_interval"], interval, "paired seed interval")
        _compare_fields(row, {"from_mean_radiance": a.mean(axis=0).tolist(),
            "to_mean_radiance": b.mean(axis=0).tolist(),
            "relative_mean_radiance_change": ((b.mean(axis=0)-a.mean(axis=0))/a.mean(axis=0)).tolist()}, "paired radiance means")
        output["paired_comparisons"].append({"light": key[0], "from_state": key[1], "to_state": key[2], "paired_interval": interval})
    _require(comparisons == {(l, s, "transported") for l in LIGHTS for s in ("initial", "regenerated")}, "missing paired comparisons")
    output["verified_saved_render_count"] = total
    output["radiance_shape_per_state_light"] = list(shape)
    return output


def _producer(root):
    manifest = _json(root/"experiment_manifest.json")
    _require(manifest.get("status") == "passed", "producer experiment did not complete successfully")
    ledger = manifest.get("output_sha256")
    _require(isinstance(ledger, dict) and ledger, "producer output hash ledger is missing")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p != root/"experiment_manifest.json"}
    _require(set(ledger) == actual, "producer output ledger has missing or extra files")
    for name, expected in ledger.items():
        path = (root/name).resolve()
        _require(root in path.parents and not Path(name).is_absolute(), "producer ledger path leaves experiment directory")
        _require(_sha(path) == expected, "producer output hash mismatch: "+name)
    return manifest


def run(rootdir):
    root = Path(rootdir).resolve()
    _require(root.is_dir(), "experiment directory is missing")
    producer = _producer(root)
    tracked = {mode: _tracking(root/"tracking"/mode, mode) for mode in MODES}
    a, b = (tracked[mode] for mode in MODES)
    _require(a["document"]["summary"]["reference_sha256"] == b["document"]["summary"]["reference_sha256"], "radius modes use different material references")
    _require(len(a["fibers"]) == len(b["fibers"]), "radius modes use different fiber counts")
    for x, y in zip(a["fibers"], b["fibers"]):
        _require(x["provenance"] == y["provenance"], "radius modes use different fiber identities")
        for field in ("points_mm", "reference_points_mm", "material_coordinates_mm", "parent_material_coordinates_mm"):
            _close(x[field], y[field], "radius modes share the same labelled pose", atol=0., rtol=0.)
    for kind in ("yarns", "plies"):
        _require(set(a["parents"][kind]) == set(b["parents"][kind]), "radius modes have different parent IDs")
        for key in a["parents"][kind]:
            for pose in ("reference", "deformed"):
                for field in ("points_mm", "material_coordinates_mm", "frames", "initial_normal"):
                    _close(a["parents"][kind][key][pose][field], b["parents"][kind][key][pose][field],
                           "radius modes share the same framed parents", atol=0., rtol=0.)
    geometries, audits, geometry_result = _geometry(root, tracked)
    optical_result = _optics(root, geometries, audits)
    _require(producer["actual_render_count"] == optical_result["verified_saved_render_count"],
             "producer and raw-array render counts disagree")
    _require(producer["requested_render"] == (optical_result["status"] == "rendered"),
             "producer requested mode and optical status disagree")
    return {"schema_version": "material_transport_verification_v4.1", "status": "passed",
        "producer": {"status": producer["status"], "output_files_hash_verified": len(producer["output_sha256"]),
                     "current_external_input_or_source_files_rechecked": False},
        "tracking": {mode: values["summary"] for mode, values in tracked.items()},
        "geometry": geometry_result, "optics": optical_result,
        "checks": {"tracking_array_hashes": True, "reference_and_state_semantic_hashes": True,
            "raw_segment_lengths_strains_radii_and_volume_proxies": True,
            "material_labels_parentage_and_framed_poses": True, "proper_orthonormal_frames": True,
            "same_labelled_pose_across_radius_modes": True, "hierarchy_scene_renderer_curve_identity": True,
            "new_different_fiber_clearance_and_export_displacement": True,
            "raw_projected_area_errors": True, "saved_seed_arrays_and_paired_intervals": optical_result["status"] == "rendered"},
        "scope": ["No new rendering is executed by this verifier.",
            "Producer completion and output ledger are checked; the runner separately checks current external source/input hashes.",
            "Saved render count is consistency of records with array channels, not an independent proof of invocation history.",
            "Segment cylinder-volume proxies are not a proof of global material-volume or mass conservation.",
            "Different-fiber capsule clearance excludes self-contact and physical contact response.",
            "Statistical intervals describe rendering replicates, not model error, measured fabric variability or perceptual validity."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    source, output = args.input.resolve(), args.output.resolve()
    if output == source or output in source.parents or source in output.parents:
        parser.error("verification input and output directories must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("verification output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = run(source); code = 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}; code = 1
    (output/"verification_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(output),
        "verified_saved_render_count": result.get("optics", {}).get("verified_saved_render_count")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
