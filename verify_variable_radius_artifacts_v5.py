#!/usr/bin/env python3
"""Verify saved v5 profile, closed-mesh and radiance artifacts without rendering.

No experiment-driver or renderer implementation is imported. Independent raw
array calculations check frustum integrals, closed topology, signed volume,
float32 export, paired-seed statistics, and artifact bookkeeping. These checks
cannot establish an independent invocation history or real-material accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import numpy as np
from scipy.stats import t as student_t

from textile_sim.hierarchy import FiberCurve, audit_clearance, load_hierarchy
from textile_sim.material_transport import bind_material_reference, transport_material_reference
from textile_sim.variable_radius import (build_tapered_tube,
                                         load_variable_radius_profiles)

STATES = ("constant_reference", "incompressible_segments")
LIGHTS = ("R0", "R90", "T45")
INITIAL_NORMAL = (0., 0., 1.)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path):
    def reject(value):
        raise ValueError("nonfinite JSON constant: "+value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _npz(path):
    try:
        # Own the stream outside np.load so malformed ZIP construction also
        # closes its descriptor rather than relying on a partially built NpzFile.
        with Path(path).open("rb") as stream:
            with np.load(stream, allow_pickle=False) as stored:
                values = {key: stored[key] for key in stored.files}
    except (OSError, ValueError, EOFError, zipfile.BadZipFile) as exc:
        raise ValueError("invalid numeric archive: "+str(path)) from exc
    for key, value in values.items():
        _require(value.dtype.kind in "fiu" and np.isfinite(value).all(),
                 "nonfinite or nonnumeric array: "+key)
    return values


def _close(actual, expected, label, *, rtol=3e-11, atol=2e-15):
    a, b = np.asarray(actual), np.asarray(expected)
    _require(a.shape == b.shape and a.dtype.kind in "bfiu" and b.dtype.kind in "bfiu",
             "shape/type mismatch: "+label)
    _require(np.isfinite(a).all() and np.isfinite(b).all()
             and np.allclose(a, b, rtol=rtol, atol=atol), "numeric mismatch: "+label)


def _fields(actual, expected, label):
    _require(isinstance(actual, dict), "missing mapping: "+label)
    for key, value in expected.items():
        _require(key in actual, "missing field: "+label+"/"+key)
        name = label+"/"+key
        if isinstance(value, dict):
            _fields(actual[key], value, name)
        elif isinstance(value, (str, bool)) or value is None:
            _require(actual[key] == value, "metadata mismatch: "+name)
        elif isinstance(value, (list, tuple)) and any(isinstance(v, (str, dict)) for v in value):
            _require(actual[key] == list(value), "ordered metadata mismatch: "+name)
        else:
            _close(actual[key], value, name)


def _array_digest(array):
    a = np.ascontiguousarray(array)
    h = hashlib.sha256(_canonical([a.shape, a.dtype.str]).encode("ascii"))
    h.update(a.tobytes())
    return h.hexdigest()


def _arc(points):
    _require(points.ndim == 2 and points.shape[1] == 3 and len(points) >= 2,
             "invalid centerline shape")
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    _require(np.all(lengths > 0.) and np.isfinite(lengths).all(),
             "zero/nonfinite centerline segment")
    return np.r_[0., np.cumsum(lengths)]


def _profiles(root):
    profiles = {state: load_variable_radius_profiles(root/"profiles"/state) for state in STATES}
    a, b = (profiles[state] for state in STATES)
    _require(len(a) == len(b) and len(a) > 0, "radius states have unequal/empty fiber counts")
    summaries = {}
    for state in STATES:
        items, source_volume, frustum_volume = [], 0., 0.
        for p in profiles[state]:
            lengths = np.diff(_arc(p.points_mm))
            _close(p.segment_length_mm, lengths, "raw centerline lengths", rtol=0., atol=0.)
            q = p.segment_radius_mm**2
            source = np.pi*q*lengths
            r = p.node_radius_mm
            frustum = np.pi*lengths*(r[:-1]**2+r[:-1]*r[1:]+r[1:]**2)/3
            _close(p.segment_volume_proxy_mm3, source, "raw cylinder volume proxy")
            _close(p.segment_frustum_volume_mm3, frustum, "raw frustum volume integral")
            _close(p.segment_relative_volume_error, frustum/source-1, "local volume redistribution")
            _close(source.sum(), frustum.sum(), "per-fiber total frustum conservation")
            source_volume += float(source.sum())
            frustum_volume += float(frustum.sum())
            items.append({"fiber_id": p.fiber_id, "profile_sha256": p.sha256,
                          "node_radius_min_mm": float(r.min()), "node_radius_max_mm": float(r.max()),
                          "min_segment_relative_volume_error": float((frustum/source-1).min()),
                          "max_segment_relative_volume_error": float((frustum/source-1).max())})
        summaries[state] = {"fiber_count": len(items), "fibers": items,
                            "source_cylinder_volume_proxy_mm3": source_volume,
                            "linear_radius_frustum_integral_mm3": frustum_volume}
    identity = ("fiber_id", "yarn_id", "ply_id", "material_id", "family", "yarn_index",
                "ply_index", "fiber_index", "kind", "cross_section", "length_unit")
    for before, after in zip(a, b):
        _require(all(getattr(before, key) == getattr(after, key) for key in identity),
                 "radius states do not preserve ordered fiber/parent/material identities")
        for key in ("points_mm", "material_coordinates_mm", "parent_material_coordinates_mm"):
            _close(getattr(before, key), getattr(after, key), "same labeled pose: "+key, rtol=0., atol=0.)
        radius = before.segment_radius_mm
        _require(np.all(radius == radius[0]), "constant-reference state has nonconstant segment radii")
        actual_lengths = np.diff(_arc(before.points_mm))
        reference_lengths = np.diff(before.material_coordinates_mm)
        expected_radius = radius/np.sqrt(actual_lengths/reference_lengths)
        _close(after.segment_radius_mm, expected_radius, "declared inverse-square-root stretch radius law")
        x, y = _json_provenance(before), _json_provenance(after)
        _require(x.get("source_radius_mode") == STATES[0] and y.get("source_radius_mode") == STATES[1],
                 "source radius mode provenance mismatch")
        _require(x.get("source_reference_sha256") == y.get("source_reference_sha256"),
                 "radius states refer to different source material references")
    return profiles, summaries


def _json_provenance(profile):
    value = json.loads(profile.provenance_json)
    _require(isinstance(value, dict), "profile provenance is not an object")
    return value


def _mesh_buffer_audit(vertices, faces, mesh):
    """Raw topology/volume/export audit independent of volume_optics.py."""
    _require(vertices.dtype == np.dtype("float32") and faces.dtype == np.dtype("uint32"),
             "renderer buffers require float32 mm vertices and uint32 triangle indices")
    _require(vertices.shape == mesh.vertices_mm.shape and faces.shape == mesh.faces.shape,
             "renderer buffer/source mesh dimensions differ")
    _require(np.array_equal(vertices, mesh.vertices_mm.astype(np.float32)),
             "renderer vertices do not match the labeled source tube")
    _require(np.array_equal(faces, mesh.faces.astype(np.uint32)),
             "renderer face winding/connectivity does not match the labeled source tube")
    _require(np.all(faces < len(vertices)) and np.all(np.diff(np.sort(faces, axis=1), axis=1) > 0),
             "invalid or collapsed triangle indices")
    edges = np.concatenate((faces[:, (0, 1)], faces[:, (1, 2)], faces[:, (2, 0)]))
    edge_set, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0,
                                          return_inverse=True, return_counts=True)
    orientation = np.bincount(inverse, weights=np.where(edges[:, 0] < edges[:, 1], 1, -1))
    _require(np.all(counts == 2) and np.all(orientation == 0), "mesh is not closed with opposed winding")
    _require(len(np.unique(faces)) == len(vertices) and len(vertices)-len(edge_set)+len(faces) == 2,
             "tube mesh has unused vertices or non-sphere Euler characteristic")
    source, quantized = mesh.vertices_mm, vertices.astype(np.float64)
    original = source[faces]
    exported = quantized[faces]
    normals = np.cross(original[:, 1]-original[:, 0], original[:, 2]-original[:, 0])
    qnormals = np.cross(exported[:, 1]-exported[:, 0], exported[:, 2]-exported[:, 0])
    areas = np.linalg.norm(normals, axis=1)/2
    qareas = np.linalg.norm(qnormals, axis=1)/2
    _require(np.all(areas > 0) and np.all(qareas > 0)
             and np.all(np.einsum("ij,ij->i", normals, qnormals) > 0),
             "float32 export collapses or flips faces")
    def volume(v):
        q = v-v.mean(axis=0)
        return float(np.einsum("ij,ij->i", q[faces[:, 0]],
                               np.cross(q[faces[:, 1]], q[faces[:, 2]])).sum()/6)
    source_volume, quantized_volume = volume(source), volume(quantized)
    _require(source_volume > 0. and quantized_volume > 0., "nonpositive mesh signed volume")
    _close(source_volume, mesh.signed_volume_mm3, "independent mesh signed volume")
    return {"vertex_count": len(vertices), "face_count": len(faces),
            "closed_oriented_edge_incidence": True, "self_intersection_certified_absent": False,
            "max_float32_displacement_mm": float(np.max(np.linalg.norm(quantized-source, axis=1))),
            "source_signed_volume_mm3": source_volume, "float32_signed_volume_mm3": quantized_volume,
            "float32_relative_volume_change": quantized_volume/source_volume-1,
            "minimum_source_triangle_area_mm2": float(areas.min()),
            "minimum_float32_triangle_area_mm2": float(qareas.min()),
            "vertices_float32_sha256": _array_digest(vertices), "faces_uint32_sha256": _array_digest(faces)}


def _paired(before, after, confidence=.95):
    """Student-t interval over paired seeds, independently of optical_lod.py."""
    a, b = np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    _require(a.shape == b.shape and a.ndim >= 1 and len(a) >= 2,
             "paired data require at least two aligned seed replicates")
    delta = b-a
    mean = delta.mean(axis=0)
    variance = np.sum((delta-mean)**2, axis=0)/(len(delta)-1)
    standard_error = np.sqrt(variance/len(delta))
    _require(0 < confidence < 1, "confidence must be inside (0,1)")
    half = student_t.ppf((1+confidence)/2, len(delta)-1)*standard_error
    return {"paired_count": len(delta), "confidence": confidence,
            "mean_delta": mean.tolist(), "standard_error": standard_error.tolist(),
            "interval_low": (mean-half).tolist(), "interval_high": (mean+half).tolist(),
            "scope": "Monte Carlo repeatability only; Student-t finite-replicate approximation"}


def _relative_percent(before, after):
    return [None if x == 0 else float((y-x)/x*100) for x, y in zip(before, after)]


def _mixed_numbers(actual, expected, label):
    _require(isinstance(actual, list) and len(actual) == len(expected),
             "relative statistic length mismatch: "+label)
    for observed, target in zip(actual, expected):
        if target is None:
            _require(observed is None, "zero-baseline relative statistic must be null: "+label)
        else:
            _close(observed, target, label)


def _validate_axes(metrics, producer):
    _require(metrics.get("schema_version") == "variable_radius_optics_experiment_v5.0",
             "unsupported optical experiment schema")
    _require(metrics.get("status") in ("rendered", "skipped")
             and metrics.get("states") == list(STATES) and metrics.get("lights") == list(LIGHTS),
             "invalid optical status/state/light axes")
    radials = np.asarray(metrics["radial_segments"])
    wavelengths = np.asarray(metrics["wavelengths_nm"])
    seeds = np.asarray(metrics["seeds"])
    _require(radials.ndim == 1 and radials.dtype.kind in "iu" and len(radials) >= 1
             and np.all(radials >= 3) and np.all(np.diff(radials) > 0),
             "radial levels must be unique increasing integers >= 3")
    _require(wavelengths.ndim == 1 and wavelengths.dtype.kind in "fiu" and len(wavelengths) >= 1
             and np.all(wavelengths > 0) and np.all(np.diff(wavelengths) > 0),
             "wavelengths must be finite unique increasing positive values")
    _require(seeds.ndim == 1 and seeds.dtype.kind in "iu" and len(seeds) >= 2
             and np.all(seeds >= 0) and len(set(seeds.tolist())) == len(seeds),
             "seeds must identify at least two unique nonnegative integer replicates")
    _close(radials, producer["radial_segments"], "producer radial levels", atol=0., rtol=0.)
    _close(wavelengths, producer["wavelengths_nm"], "producer wavelengths", atol=0., rtol=0.)
    _require(len(seeds) == producer["replicates"], "producer replicate count mismatch")
    _require(isinstance(producer["resolution"], int) and not isinstance(producer["resolution"], bool)
             and producer["resolution"] > 0 and isinstance(producer["spp"], int)
             and not isinstance(producer["spp"], bool) and producer["spp"] > 0,
             "positive integer resolution and spp required")
    planned = len(radials)*len(STATES)*len(LIGHTS)*len(wavelengths)*len(seeds)
    _require(producer["planned_render_count"] == (planned if producer["requested_render"] else 0),
             "planned render count disagrees with requested mode and ordered axes")
    return radials.tolist(), wavelengths.tolist(), seeds.tolist()


def _comparison_statistics(row, before, after, confidence):
    # before/after arrays are seed by wavelength; the replicate unit is a seed.
    mean_before, mean_after = before.mean(axis=0), after.mean(axis=0)
    _close(row["mean_before"], mean_before, "paired before mean")
    _close(row["mean_after"], mean_after, "paired after mean")
    _mixed_numbers(row["relative_mean_change_percent"], _relative_percent(mean_before, mean_after),
                   "relative change percent")
    base = _paired(before, after)
    _fields(row["paired_95"], base, "paired seed 95% interval")
    if confidence is None:
        _require(row["paired_bonferroni"] is None, "unplanned multiplicity-adjusted interval")
    else:
        _fields(row["paired_bonferroni"], _paired(before, after, confidence),
                "paired Bonferroni interval")
    return base


def _comparisons(metrics, radiance, radials, wavelengths):
    # Input order: radial, state, light, wavelength, seed, row, column.
    means = radiance.astype(np.float64).mean(axis=(-2, -1))
    count_wave = len(wavelengths)
    seen, rows = set(), []
    expected = {("radius", ri, li) for ri in range(len(radials)) for li in range(len(LIGHTS))}
    expected |= {("radial_refinement", ri, si, li) for ri in range(len(radials)-1)
                 for si in range(len(STATES)) for li in range(len(LIGHTS))}
    for row in metrics["comparisons"]:
        kind = row["kind"]
        _require(row.get("light") in LIGHTS, "comparison light is outside ordered axes")
        li = LIGHTS.index(row["light"])
        if kind == "radius":
            _require(row.get("radial_segments") in radials
                     and row.get("reference_state") == STATES[0] and row.get("state") == STATES[1],
                     "invalid radius comparison association")
            ri = radials.index(row["radial_segments"])
            key = (kind, ri, li)
            before, after = means[ri, 0, li].T, means[ri, 1, li].T
            family_size = len(LIGHTS)*count_wave if ri == len(radials)-1 else None
            confidence = 1-.05/family_size if family_size else None
        elif kind == "radial_refinement":
            _require(row.get("coarse_radial_segments") in radials[:-1]
                     and row.get("state") in STATES, "invalid radial refinement association")
            ri = radials.index(row["coarse_radial_segments"])
            _require(row.get("fine_radial_segments") == radials[ri+1], "refinement must use neighboring ordered levels")
            si = STATES.index(row["state"])
            key = (kind, ri, si, li)
            before, after = means[ri, si, li].T, means[ri+1, si, li].T
            family_size = len(STATES)*len(LIGHTS)*count_wave*(len(radials)-1)
            confidence = 1-.05/family_size
        else:
            raise ValueError("unknown comparison kind: "+str(kind))
        _require(key in expected and key not in seen, "missing/duplicated comparison association")
        _require(row.get("bonferroni_family_size") == family_size, "comparison multiplicity family size mismatch")
        seen.add(key)
        interval = _comparison_statistics(row, before, after, confidence)
        rows.append({"kind": kind, "light": row["light"], "paired_95": interval})
    _require(seen == expected, "comparison family is incomplete")
    return rows


def _producer(root):
    manifest = _json(root/"experiment_manifest.json")
    _require(manifest.get("schema_version") == "variable_radius_experiment_v5.0"
             and manifest.get("status") == "passed", "producer experiment is incomplete or unsupported")
    _require(isinstance(manifest.get("requested_render"), bool), "explicit requested_render flag required")
    ledger = manifest.get("output_sha256")
    _require(isinstance(ledger, dict) and ledger, "producer output hash ledger is missing")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*")
              if path.is_file() and path != root/"experiment_manifest.json"}
    _require(actual == set(ledger), "producer output ledger has missing or extra files")
    for name, expected in ledger.items():
        path = (root/name).resolve()
        _require(root in path.parents and not Path(name).is_absolute(), "output ledger path leaves artifact directory")
        _require(_sha(path) == expected, "output file checksum mismatch: "+name)
    for key in ("source_sha256", "input_sha256"):
        values = manifest.get(key)
        _require(isinstance(values, dict) and values, "missing source/input provenance ledger: "+key)
        _require(all(isinstance(name, str) and isinstance(value, str) and len(value) == 64
                     and all(c in "0123456789abcdef" for c in value) for name, value in values.items()),
                 "invalid source/input SHA-256 provenance: "+key)
    _require(manifest.get("input_hashes_unchanged") is True and manifest.get("source_hashes_unchanged") is True,
             "producer reports source/input drift")
    return manifest


def _source_pose(producer, profiles, source_input):
    if source_input is None:
        return {"external_source_inputs_rechecked": False,
                "note": "Pass --source-input to compare the saved profiles with the original mechanics pair."}
    folder = Path(source_input).resolve()
    expected_names = {f"{pose}/hierarchy_geometry.{extension}" for pose in ("initial", "relaxed")
                      for extension in ("json", "npz")}
    _require(set(producer["input_sha256"]) == expected_names, "unexpected mechanics input ledger")
    for name, digest in producer["input_sha256"].items():
        _require(_sha(folder/name) == digest, "original mechanics input checksum mismatch: "+name)
    initial, target = load_hierarchy(folder/"initial"), load_hierarchy(folder/"relaxed")
    _require(set(initial.yarns) == set(target.yarns), "original mechanics parent IDs differ")
    for key in initial.yarns:
        _close(initial.yarns[key][:, :2], target.yarns[key][:, :2], "declared parent XY material-index correspondence",
               rtol=0., atol=0.)
    normals = {key: np.array(INITIAL_NORMAL) for key in initial.yarns}
    reference = bind_material_reference(initial, yarn_initial_normals=normals,
                                        correspondence="shared_vertex_indices")
    coordinates = {key: curve.material_coordinates_mm for key, curve in reference.yarns.items()}
    state_hashes = {}
    for mode in STATES:
        state = transport_material_reference(reference, target.yarns, yarn_initial_normals=normals,
                    deformed_parent_coordinates_mm=coordinates, radius_mode=mode)
        _require(len(state.fiber_records) == len(profiles[mode]), "original/saved fiber counts differ")
        state_hashes[mode] = state.sha256
        for p, f in zip(profiles[mode], state.fiber_records):
            _fields(p.metadata(), f.provenance(), "original source fiber identities")
            for key in ("points_mm", "material_coordinates_mm", "parent_material_coordinates_mm", "segment_radius_mm"):
                _close(getattr(p, key), getattr(f, key), "original material state: "+key, rtol=0., atol=0.)
            provenance = _json_provenance(p)
            _require(provenance.get("source_state_sha256") == state.sha256
                     and provenance.get("source_reference_sha256") == reference.sha256,
                     "original source state/reference digest mismatch")
    return {"external_source_inputs_rechecked": True, "input_files_hash_verified": len(expected_names),
            "reference_sha256": reference.sha256, "state_sha256": state_hashes,
            "scope": "Core v4 material map reapplied to explicitly supplied saved mechanics data; no experiment driver import."}


def _clearance(profiles):
    identity = ("fiber_id", "yarn_id", "ply_id", "material_id", "family", "yarn_index",
                "ply_index", "fiber_index", "kind", "cross_section")
    fibers = tuple(FiberCurve(points_mm=p.points_mm,
                    radii_mm=np.full(len(p.points_mm), float(p.node_radius_mm.max())),
                    **{key: getattr(p, key) for key in identity}) for p in profiles)
    # audit_clearance consumes only these validated capsule curves; no invented
    # yarn/ply geometry is added to make an artificial hierarchy container.
    result = audit_clearance(SimpleNamespace(fiber_records=fibers))
    _require(result["certified_separated"], "different-fiber max-node-radius capsules overlap")
    return result


def _profile_totals(profiles):
    error = np.concatenate([p.segment_relative_volume_error for p in profiles])
    volume = float(sum(np.pi*p.segment_radius_mm**2 @ p.segment_length_mm for p in profiles))
    frustum = float(sum(p.segment_frustum_volume_mm3.sum() for p in profiles))
    return {"fiber_count": len(profiles), "vertex_count": sum(len(p.points_mm) for p in profiles),
            "segment_count": sum(len(p.segment_length_mm) for p in profiles),
            "source_cylinder_volume_proxy_mm3": volume, "total_frustum_integral_mm3": frustum,
            "frustum_total_relative_error": frustum/volume-1,
            "node_radius_min_mm": float(min(p.node_radius_mm.min() for p in profiles)),
            "node_radius_max_mm": float(max(p.node_radius_mm.max() for p in profiles)),
            "local_segment_volume_relative_error_min": float(error.min()),
            "local_segment_volume_relative_error_max": float(error.max()),
            "local_absolute_error_percentile_99": float(np.percentile(np.abs(error), 99))}


def _meshes(root, profiles, radials):
    geometry = _json(root/"geometry_metrics.json")
    _require(geometry.get("schema_version") == "variable_radius_geometry_v5.0"
             and geometry.get("length_unit") == "mm" and geometry.get("same_centerlines_for_both_states") is True,
             "geometry schema/unit/same-centerline declaration mismatch")
    _require(set(geometry["states"]) == set(STATES)
             and set(geometry["mesh_levels"]) == {str(n) for n in radials},
             "geometry state/radial-level mapping is incomplete")
    clearances, totals = {}, {}
    for state in STATES:
        totals[state], clearances[state] = _profile_totals(profiles[state]), _clearance(profiles[state])
        row = geometry["states"][state]
        _fields(row, totals[state], "geometry profile totals")
        _fields(row["clearance"], clearances[state], "recomputed source capsule clearance")
        _require(len(row["profiles"]) == len(profiles[state]), "geometry profile summary count mismatch")
        for summary, p in zip(row["profiles"], profiles[state]):
            _fields(summary, p.summary(), "geometry profile summary")
            provenance = _json_provenance(p)
            _require(row["transport_state_sha256"] == provenance["source_state_sha256"]
                     and row["reference_sha256"] == provenance["source_reference_sha256"],
                     "geometry/source semantic state association mismatch")
    scene_rows, mesh_summaries = {}, {}
    for n in radials:
        _require(set(geometry["mesh_levels"][str(n)]) == set(STATES), "mesh level omits a radius state")
        for state in STATES:
            folder = root/"meshes"/f"radial_{n:03d}"/state
            manifest = _json(folder/"mesh_manifest.json")
            _require(manifest.get("schema_version") == "variable_radius_mesh_buffers_v5.0"
                     and manifest.get("length_unit") == "mm" and manifest.get("vertices_dtype") == "float32"
                     and manifest.get("faces_dtype") == "uint32"
                     and manifest.get("render_shading_normals") == "flat geometric triangle normals",
                     "mesh buffer schema/unit/normal contract mismatch")
            _close(manifest["initial_normal"], INITIAL_NORMAL, "mesh common initial direction", rtol=0., atol=0.)
            _require(_sha(folder/"renderer_buffers.npz") == manifest["arrays_sha256"], "renderer buffer NPZ checksum mismatch")
            arrays = _npz(folder/"renderer_buffers.npz")
            _require(len(manifest["fibers"]) == len(profiles[state]), "mesh fiber count mismatch")
            expected_keys, rows, audits = set(), [], []
            volume, count_vertex, count_face = 0., 0, 0
            for i, (row, p) in enumerate(zip(manifest["fibers"], profiles[state])):
                prefix = f"fiber_{i:04d}"
                _require(row.get("array_prefix") == prefix, "mesh fibers reordered or duplicated")
                mesh = build_tapered_tube(p, radial_segments=n, initial_normal=INITIAL_NORMAL)
                vertices_key, faces_key = prefix+"/vertices_mm", prefix+"/faces"
                expected_keys.update((vertices_key, faces_key))
                _require(vertices_key in arrays and faces_key in arrays, "missing mesh vertex/face array")
                audit = _mesh_buffer_audit(arrays[vertices_key], arrays[faces_key], mesh)
                _fields(row["buffer_audit"], {k: v for k, v in audit.items() if k != "float32_relative_volume_change"},
                        "raw renderer buffer audit")
                _close(row["buffer_audit"]["float32_relative_volume_change"], audit["float32_relative_volume_change"],
                       "float32 relative volume change", atol=2e-12)
                fields = {"fiber_id": p.fiber_id, "material_id": p.material_id, "profile_sha256": p.sha256,
                          "mesh_sha256": mesh.sha256, "radial_segments": n}
                _fields(row, fields, "renderer/source fiber identity")
                _fields(row["geometry_summary"], mesh.summary(), "source tube geometry summary")
                rows.append({**fields, "buffer_audit": row["buffer_audit"]})
                audits.append(audit)
                volume += mesh.signed_volume_mm3
                count_vertex += len(mesh.vertices_mm)
                count_face += len(mesh.faces)
            _require(set(arrays) == expected_keys, "unaccounted or missing mesh arrays")
            _fields(manifest["clearance_source"], clearances[state], "mesh max-radius enclosing capsule clearance")
            quantization = max(a["max_float32_displacement_mm"] for a in audits)
            remaining = clearances[state]["minimum_clearance_lower_bound_mm"]-2*quantization
            _require(remaining > 0., "float32 output exhausts different-fiber clearance")
            source, frustum = (totals[state][key] for key in
                               ("source_cylinder_volume_proxy_mm3", "total_frustum_integral_mm3"))
            factor = n*np.sin(2*np.pi/n)/(2*np.pi)
            summary = {"fiber_count": len(rows), "radial_segments": n, "vertex_count": count_vertex,
                       "face_count": count_face, "source_cylinder_volume_proxy_mm3": source,
                       "total_frustum_integral_mm3": frustum, "total_signed_volume_mm3": volume,
                       "float32_total_signed_volume_mm3": sum(a["float32_signed_volume_mm3"] for a in audits),
                       "mesh_to_source_proxy_relative_error": volume/source-1,
                       "mesh_to_frustum_relative_error": volume/frustum-1,
                       "straight_regular_polygon_volume_factor": factor,
                       "residual_after_polygon_factor": volume/(frustum*factor)-1,
                       "max_float32_displacement_mm": quantization,
                       "different_fiber_clearance_lower_bound_mm": remaining,
                       "same_fiber_self_intersection_certified_absent": False,
                       "smooth_circle_normal_half_bin_deg": 180./n}
            _fields(manifest["summary"], summary, "mesh level aggregate")
            g = geometry["mesh_levels"][str(n)][state]
            _fields(g, summary, "geometry mesh aggregate")
            _require(g["mesh_manifest"] == (folder/"mesh_manifest.json").relative_to(root).as_posix(),
                     "geometry mesh manifest association mismatch")
            scene_rows[(n, state)], mesh_summaries[(n, state)] = rows, summary
    return scene_rows, {str(n): {state: mesh_summaries[(n, state)] for state in STATES} for n in radials}


def _scene_metadata(path, expected_mesh_rows, wavelength, producer):
    metadata = _json(path)
    _require(metadata.get("schema_version") == "textile.closed_mesh_volume_optics/5.0"
             and metadata.get("scene_length_unit") == "mm"
             and metadata.get("wavelength_unit") == "vacuum_nm"
             and metadata.get("triangle_geometric_normals_only") is True,
             "closed-mesh scene schema/units/geometric-normal contract mismatch")
    semantic = {key: value for key, value in metadata.items()
                if key not in ("scene_sha256", "scene_build_seconds")}
    _require(hashlib.sha256(_canonical(semantic).encode("utf-8")).hexdigest() == metadata.get("scene_sha256"),
             "scene semantic metadata digest mismatch")
    _close(metadata["wavelength_nm"], wavelength, "scene wavelength", rtol=0., atol=0.)
    _require(len(metadata["meshes"]) == len(expected_mesh_rows), "scene has incorrect mesh count")
    for actual, expected in zip(metadata["meshes"], expected_mesh_rows):
        _fields(actual, expected, "scene mesh identity and buffer audit")
    materials = metadata["materials"]
    expected_material_ids = {row["material_id"] for row in expected_mesh_rows}
    _require(set(materials) == expected_material_ids, "scene material lookup differs from mesh labels")
    for key, entry in materials.items():
        table = entry["material"]
        _require(table.get("material_id") == key and table.get("data_status") == "synthetic"
                 and isinstance(table.get("source"), str) and table["source"].strip(),
                 "synthetic material identity/source status mismatch")
        w, nr, ki = [np.asarray(table[name], dtype=float) for name in ("wavelength_nm", "n_real", "kappa")]
        _require(w.ndim == 1 and len(w) >= 2 and nr.shape == w.shape and ki.shape == w.shape
                 and np.isfinite(w).all() and np.isfinite(nr).all() and np.isfinite(ki).all()
                 and np.all(np.diff(w) > 0) and w[0] > 0 and np.all(nr > 0) and np.all(ki >= 0)
                 and w[0] <= wavelength <= w[-1], "invalid bounded passive scalar spectrum")
        n, kappa = float(np.interp(wavelength, w, nr)), float(np.interp(wavelength, w, ki))
        absorption = 4*np.pi*kappa/(wavelength*1e-6)
        _fields(entry, {"wavelength_nm": wavelength, "n_real": n, "kappa": kappa,
                        "absorption_per_mm": absorption, "sigma_t_per_scene_unit": absorption,
                        "albedo": 0., "kappa_over_n": kappa/n,
                        "absorbing_medium_installed": absorption > 0}, "physical absorption units")
        _require(entry["background_n"] > 0 and 0 < entry["max_kappa_ratio"] <= .01
                 and kappa/n <= entry["max_kappa_ratio"], "real-index Fresnel approximation gate mismatch")
    config = metadata["render_config"]
    _require(config["resolution"] == producer["resolution"] and config["spp"] == producer["spp"],
             "scene/sample budget differs from experiment")
    bounds = np.asarray(metadata["rig"]["bounds_mm"], dtype=float)
    _require(bounds.shape == (2, 3) and np.isfinite(bounds).all() and np.all(bounds[1] > bounds[0]),
             "scene has invalid common rig bounds")
    return metadata


def _render_records(root, metrics, producer, arrays, mesh_rows, radials, wavelengths, seeds):
    folder = root/"optics"
    images = arrays["radiance"]
    expected_shape = (len(radials), len(STATES), len(LIGHTS), len(wavelengths), len(seeds),
                      producer["resolution"], producer["resolution"])
    _require(images.dtype == np.dtype("float32") and images.shape == expected_shape
             and float(images.min()) >= -1e-7, "invalid scalar radiance dtype/shape/sign")
    seen, scene_cache, common_rigs = set(), {}, {}
    _require(isinstance(metrics["records"], list), "missing per-render record list")
    for row in metrics["records"]:
        index = row["array_index"]
        _require(isinstance(index, list) and len(index) == 5
                 and all(isinstance(i, int) and not isinstance(i, bool) for i in index),
                 "render record index must be five explicit integers")
        ri, si, li, wi, ki = index
        _require(all(0 <= index[i] < expected_shape[i] for i in range(5)), "render index outside axes")
        key = tuple(index)
        _require(key not in seen and row["actual_render_count"] == 1, "duplicated render record or non-unit call count")
        seen.add(key)
        _fields(row, {"radial_segments": radials[ri], "state": STATES[si], "light": LIGHTS[li],
                      "wavelength_nm": wavelengths[wi], "seed": seeds[ki]}, "render axis association")
        image = images[key]
        _require(row["saved_scalar_sha256"] == _array_digest(image), "saved scalar image semantic digest mismatch")
        _close(row["saved_scalar_mean_radiance"], float(image.astype(np.float64).mean()),
               "saved scalar image mean")
        # raw_float32_sha256 records the original RGB backend buffer. Only the
        # explicitly saved scalar channel is independently reconstructible here.
        _require(isinstance(row.get("raw_float32_sha256"), str) and len(row["raw_float32_sha256"]) == 64,
                 "missing original RGB observational digest")
        name = row["scene_metadata_file"]
        path = (folder/name).resolve()
        _require(folder.resolve() in path.parents and not Path(name).is_absolute(),
                 "scene record path leaves optics directory")
        association = (ri, si, li, wi)
        if path not in scene_cache:
            meta = _scene_metadata(path, mesh_rows[(radials[ri], STATES[si])], wavelengths[wi], producer)
            scene_cache[path] = (association, meta)
        expected_association, metadata = scene_cache[path]
        _require(association == expected_association and row["scene_sha256"] == metadata["scene_sha256"],
                 "scene metadata reused for a different geometry/light/wavelength")
        _require(row.get("spp") == producer["spp"], "per-render spp differs from declared budget")
        config = metadata["render_config"]
        _require(config == metrics["lighting_configs"][LIGHTS[li]], "scene differs from declared lighting configuration")
        _close(metadata["rig"]["bounds_mm"], metrics["union_bounds_mm"], "scene common enclosing bounds", rtol=0., atol=0.)
        _require(config["mode"] == ("transmission" if LIGHTS[li] == "T45" else "reflection"),
                 "scene light/reflection/transmission mode mismatch")
        if li not in common_rigs:
            common_rigs[li] = metadata["rig"]
        else:
            _require(metadata["rig"] == common_rigs[li], "physical camera/light rig changes across compared geometry/wavelengths")
    _require(len(seen) == int(np.prod(expected_shape[:5])) == metrics["actual_render_count"],
             "raw scalar image channels and render count disagree")
    _require(len(scene_cache) == int(np.prod(expected_shape[:4])), "scene metadata count disagrees with ordered axes")
    return {"verified_saved_render_count": len(seen), "scene_metadata_files_verified": len(scene_cache),
            "radiance_shape": list(images.shape), "original_rgb_buffer_hash_independently_rechecked": False}


def _optics(root, metrics, producer, profiles, mesh_rows, radials, wavelengths, seeds):
    _require(metrics["radiance_axes"] == ["radial_segments", "state", "light", "wavelength_nm", "seed", "row", "column"],
             "saved scalar radiance axes are not explicit/correct")
    _require(metrics["radiance_channel"] == "RGB channel 0; channel agreement checked before saving",
             "scalar observation conversion rule mismatch")
    _require(metrics["resolution"] == producer["resolution"] and metrics["spp"] == producer["spp"],
             "optical sample budget differs from producer")
    _require(metrics["primary_radius_family_size"] == len(LIGHTS)*len(wavelengths)
             and metrics["primary_radius_radial_segments"] == radials[-1]
             and metrics["refinement_family_size"] == (len(radials)-1)*len(STATES)*len(LIGHTS)*len(wavelengths),
             "declared multiplicity family does not match comparison axes")
    _require(set(metrics["lighting_configs"]) == set(LIGHTS), "lighting configuration mapping incomplete")
    all_profiles = [p for state in STATES for p in profiles[state]]
    bounds = np.stack((np.min([np.min(p.points_mm-p.node_radius_mm[:, None], axis=0) for p in all_profiles], axis=0),
                       np.max([np.max(p.points_mm+p.node_radius_mm[:, None], axis=0) for p in all_profiles], axis=0)))
    _close(metrics["union_bounds_mm"], bounds, "common radius-envelope bounds", rtol=0., atol=0.)
    path = root/"optics"/"spectral_radiance.npz"
    if metrics["status"] == "skipped":
        _require(not producer["requested_render"] and producer["actual_render_count"] == 0
                 and metrics["actual_render_count"] == 0 and metrics["spectral_radiance_sha256"] is None
                 and metrics["records"] == [] and metrics["comparisons"] == [] and not path.exists()
                 and producer["completed_batches"] == [], "skipped run contains stale/fabricated render evidence")
        return {"status": "skipped", "verified_saved_render_count": 0, "paired_comparisons": []}
    _require(producer["requested_render"] and _sha(path) == metrics["spectral_radiance_sha256"],
             "saved radiance checksum or requested mode mismatch")
    arrays = _npz(path)
    _require(set(arrays) == {"radiance"}, "unexpected or missing saved scalar radiance arrays")
    result = _render_records(root, metrics, producer, arrays, mesh_rows, radials, wavelengths, seeds)
    intervals = _comparisons(metrics, arrays["radiance"], radials, wavelengths)
    _require(producer["actual_render_count"] == result["verified_saved_render_count"] == producer["planned_render_count"],
             "producer/records/raw-array counts disagree")
    expected_batches = {(n, state, light, wave) for n in radials for state in STATES for light in LIGHTS for wave in wavelengths}
    batches = set()
    for row in producer["completed_batches"]:
        key = (row["radial_segments"], row["state"], row["light"], row["wavelength_nm"])
        _require(key in expected_batches and key not in batches and row["actual_render_count"] == len(seeds),
                 "producer completed-batch association/count mismatch")
        batches.add(key)
    _require(batches == expected_batches, "producer completed-batch family incomplete")
    return {"status": "rendered", **result, "paired_comparisons": intervals}


def run(rootdir, source_input=None):
    root = Path(rootdir).resolve()
    _require(root.is_dir(), "experiment directory does not exist")
    producer = _producer(root)
    metrics = _json(root/"optics"/"optical_metrics.json")
    radials, wavelengths, seeds = _validate_axes(metrics, producer)
    profiles, profile_summary = _profiles(root)
    source = _source_pose(producer, profiles, source_input)
    mesh_rows, mesh_summary = _meshes(root, profiles, radials)
    optical_summary = _optics(root, metrics, producer, profiles, mesh_rows, radials, wavelengths, seeds)
    return {"schema_version": "variable_radius_artifact_verification_v5.0", "status": "passed",
            "producer": {"status": producer["status"], "output_files_hash_verified": len(producer["output_sha256"]),
                         "source_input_unchanged_during_production_declared": True,
                         "current_source_code_hashes_independently_rechecked": False},
            "source_input": source, "profiles": profile_summary, "meshes": mesh_summary, "optics": optical_summary,
            "checks": {"profile_hashes_and_derived_arrays": True, "independent_frustum_integrals": True,
                       "same_labeled_pose_and_declared_radius_law": True,
                       "closed_oriented_triangle_buffers_and_positive_signed_volume": True,
                       "exact_source_to_float32_renderer_buffer_identity": True,
                       "different_fiber_capsule_clearance_after_quantization": True,
                       "saved_scalar_means_hashes_and_paired_intervals": optical_summary["status"] == "rendered"},
            "scope": ["No new rendering is performed and no experiment-driver/renderer implementation is imported.",
                      "Core geometry construction is cross-checked by separate analytic/topological review tests.",
                      "Signed mesh volume, profile frustum integrals and source cylinder proxies have different meanings.",
                      "Different-fiber clearance excludes same-fiber self-intersection and physical contact response.",
                      "Scalar channel hashes and records do not independently prove original RGB buffers or execution history.",
                      "Seed intervals and Bonferroni families quantify conditional Monte Carlo noise, not real-material/model/perceptual uncertainty.",
                      "Current external code hashes are a separate runner gate; optional --source-input rechecks original data and its material map."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-input", type=Path, help="Optional original initial/relaxed mechanics hierarchy pair")
    args = parser.parse_args(argv)
    source, output = args.input.resolve(), args.output.resolve()
    if source == output or source in output.parents or output in source.parents:
        parser.error("verification input/output directories must not overlap")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("verification output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = run(source, args.source_input)
        code = 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, IndexError, EOFError, zipfile.BadZipFile) as exc:
        result = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
        code = 1
    (output/"verification_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "verified_saved_render_count": result.get("optics", {}).get("verified_saved_render_count")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
