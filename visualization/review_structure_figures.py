"""Independent saved-array and analytic-oracle review of structure figures.

Geometry-map tests concern first-hit surface attributes, not radiance rendering,
material identification, or validation of a measured fabric. This module does
not import the figure producer's color/statistical helpers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _check(condition, reason):
    if not bool(condition):
        raise ValueError(reason)


def _load_npz(path):
    with zipfile.ZipFile(path) as archive:
        _check(archive.testzip() is None, f"ZIP CRC failed: {path}")
    with Path(path).open("rb") as stream:
        with np.load(stream, allow_pickle=False) as archive:
            return {key: archive[key] for key in archive.files}


def check_physical_arrays(arrays, camera, *, label):
    """Check coordinates without relying on the map producer's camera helper.

    For orthographic rays, camera origin is the center of the image plane;
    right/up offsets and physical ray distance determine each world position.
    Sample count may differ from camera resolution for supersampled raw maps.
    """
    valid = np.asarray(arrays["valid_mask"])
    _check(valid.ndim == 2 and valid.dtype == np.bool_, f"{label}: boolean 2D valid mask")
    h, w = valid.shape
    _check(h > 0 and w > 0 and valid.any(), f"{label}: nonempty visible domain")
    vectors = ("world_normal", "world_tangent", "position_mm")
    if "world_smooth_normal" in arrays:
        vectors += ("world_smooth_normal",)
    for key in vectors:
        a = arrays[key]
        _check(a.shape == (h, w, 3) and np.issubdtype(a.dtype, np.floating),
               f"{label}: {key} shape/dtype")
        _check(np.isfinite(a[valid]).all(), f"{label}: {key} finite valid values")
        _check(np.isnan(a[~valid]).all(), f"{label}: {key} NaN miss values")
    scalars = ("height_mm", "ray_distance_mm")+(("ray_parameter_mm",) if "ray_parameter_mm" in arrays else ())
    for key in scalars:
        a = arrays[key]
        _check(a.shape == (h, w) and np.issubdtype(a.dtype, np.floating),
               f"{label}: {key} shape/dtype")
        _check(np.isfinite(a[valid]).all(), f"{label}: {key} finite hits")
        _check(np.isnan(a[~valid]).all(), f"{label}: {key} NaN misses")
    unit_errors = {}
    for key in ("world_normal", "world_tangent", "world_smooth_normal"):
        if key not in arrays:
            continue
        values = np.asarray(arrays[key][valid], dtype=np.float64)
        error = float(np.max(np.abs(np.sqrt(np.sum(values**2, axis=-1))-1)))
        _check(error < 3e-6, f"{label}: {key} unit-length error {error}")
        unit_errors[key] = error
    origin = np.asarray(camera["origin_mm"], dtype=np.float64)
    right = np.asarray(camera["right"], dtype=np.float64)
    up = np.asarray(camera["up"], dtype=np.float64)
    view = np.asarray(camera["view_direction"], dtype=np.float64)
    basis = np.array([right, up, view])
    _check(origin.shape == (3,) and basis.shape == (3, 3), f"{label}: camera basis dimensions")
    _check(np.isfinite(origin).all() and np.isfinite(basis).all(), f"{label}: finite camera")
    _check(np.max(np.abs(basis@basis.T-np.eye(3))) < 2e-12,
           f"{label}: orthonormal camera basis")
    _check(np.dot(np.cross(right, up), view) < -.999999999,
           f"{label}: camera right/up/view convention")
    row, col = np.nonzero(valid)
    horizontal = ((col+.5)/w-.5)*float(camera["width_mm"])
    vertical = (.5-(row+.5)/h)*float(camera["height_mm"])
    ray_origins = origin+horizontal[:, None]*right+vertical[:, None]*up
    distance = np.asarray(arrays["ray_distance_mm"][valid], dtype=np.float64)
    _check(np.all(distance > 0), f"{label}: strictly positive first-hit ray distances")
    if "ray_parameter_mm" in arrays:
        parameter = arrays["ray_parameter_mm"][valid].astype(float)
        backend_direction = np.asarray(camera.get("backend_view_direction_float32", view.astype(np.float32)), dtype=float)
        _check(np.all(parameter > 0) and np.allclose(distance, parameter*np.linalg.norm(backend_direction),
               rtol=2e-7, atol=2e-9), f"{label}: physical distance differs from ray parameter times direction length")
    actual = np.asarray(arrays["position_mm"][valid], dtype=np.float64)
    expected = ray_origins+distance[:, None]*view
    position_error = float(np.max(np.linalg.norm(actual-expected, axis=-1)))
    allowance = 5e-6*(1+float(np.max(np.abs(expected))))
    _check(position_error < allowance,
           f"{label}: world position/ray mismatch {position_error} mm")
    height_error = float(np.max(np.abs(arrays["height_mm"][valid]-actual[:, 2])))
    _check(height_error < 2e-12, f"{label}: height is not actual world Z")
    ids = {}
    for key, a in arrays.items():
        if not key.endswith("_index"):
            continue
        _check(a.shape == (h, w) and np.issubdtype(a.dtype, np.integer),
               f"{label}: {key} must stay categorical integer")
        _check(np.all(a[~valid] == -1), f"{label}: {key} miss sentinel")
        _check(np.all(a[valid] >= -1), f"{label}: {key} invalid negative ID")
        # A valid ply proxy can have mixed material and no single fiber ID.
        if key in ("object_index", "primitive_index"):
            _check(np.all(a[valid] >= 0), f"{label}: {key} required on valid hit")
        ids[key] = np.unique(a[valid]).tolist()
    tangent = np.asarray(arrays["world_tangent"][valid], dtype=np.float64)
    normals = np.asarray(arrays["world_normal"][valid], dtype=np.float64)
    front_cosine = normals@(-view)
    normal_tangent_dot = np.sum(normals*tangent, axis=-1)
    projected = np.linalg.norm(tangent[:, :2], axis=-1)
    defined = projected >= 1e-8
    theta = np.mod(np.arctan2(tangent[defined, 1], tangent[defined, 0]), np.pi)
    reverse = np.mod(np.arctan2(-tangent[defined, 1], -tangent[defined, 0]), np.pi)
    # A doubled-angle director avoids the branch cut at theta=0=pi.
    director_error = float(np.max(np.abs(np.column_stack((np.cos(2*theta), np.sin(2*theta)))-
        np.column_stack((np.cos(2*reverse), np.sin(2*reverse)))))) if len(theta) else 0.
    _check(director_error < 3e-14, f"{label}: projected orientation is not headless")
    return {"label": label, "shape": [h, w], "valid_count": int(valid.sum()),
        "miss_count": int((~valid).sum()), "unit_length_max_errors": unit_errors,
        "position_ray_max_error_mm": position_error, "world_height_max_error_mm": height_error,
        "height_range_mm": [float(actual[:, 2].min()), float(actual[:, 2].max())],
        "min_front_facing_normal_cosine": float(front_cosine.min()),
        "backfacing_geometric_hit_count": int((front_cosine < -3e-6).sum()),
        "max_abs_normal_centerline_tangent_dot": float(np.max(np.abs(normal_tangent_dot))),
        "normal_tangent_orthogonality_is_a_gate": False,
        "projected_orientation_undefined_count": int((~defined).sum()),
        "headless_director_invariance_error": director_error, "categorical_visible_ids": ids}


def geometric_oracles():
    """Use analytic planes, not hierarchy regeneration, as ray-hit truth."""
    from visualization.structure_maps import (surface_from_arrays,
        make_topdown_camera, trace_structure_maps)

    def rectangle(xhalf, yhalf, a, b, c):
        xy = np.array([[-xhalf, -yhalf], [xhalf, -yhalf],
                       [xhalf, yhalf], [-xhalf, yhalf]], dtype=np.float64)
        return np.column_stack((xy, a*xy[:, 0]+b*xy[:, 1]+c))

    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    h, w = 9, 11
    x = ((np.arange(w)+.5)/w-.5)*2.
    y = (.5-(np.arange(h)+.5)/h)*1.6
    xx, yy = np.meshgrid(x, y)
    vertices = rectangle(.8, .55, .2, -.3, .4)
    surface = surface_from_arrays(vertices, faces, vertex_tangent=(1., 0., .2))
    camera = make_topdown_camera(surface.bounds_mm, resolution=(h, w),
                                extent_xy_mm=(-1., 1., -.8, .8))
    result = trace_structure_maps(surface, camera, supersample=2)
    expected_valid = (np.abs(xx) < .8) & (np.abs(yy) < .55)
    _check(np.array_equal(result.arrays["valid_mask"], expected_valid),
           "analytic plane coverage and image-row convention")
    actual_height = result.arrays["height_mm"][expected_valid]
    height_error = float(np.max(np.abs(actual_height-(.2*xx-.3*yy+.4)[expected_valid])))
    normal = np.array([-.2, .3, 1.]); normal /= np.linalg.norm(normal)
    normal_error = float(np.max(np.linalg.norm(result.arrays["world_normal"][expected_valid]-normal, axis=-1)))
    _check(height_error < 2e-6, "tilted-plane analytic world height")
    _check(normal_error < 2e-6, "tilted-plane analytic geometric normal")
    center = check_physical_arrays(result.arrays, camera.to_dict(), label="analytic_tilted_plane")
    subpixel = check_physical_arrays(result.supersampled, camera.to_dict(), label="analytic_tilted_plane_SS2")
    expected_coverage = result.supersampled["valid_mask"].reshape(h, 2, w, 2).mean(axis=(1, 3))
    _check(np.array_equal(result.arrays["coverage"], expected_coverage), "analytic plane exact coverage")
    rows = [{"oracle": "tilted_plane_with_silhouette", "height_error_mm": height_error,
             "normal_vector_error": normal_error, "center": center, "subpixel": subpixel,
             "executed_geometry_sources_sha256": result.metadata["source_files_sha256"],
             "actual_primary_ray_queries": result.metadata["actual_primary_ray_queries"]}]
    lower = rectangle(1.2, .9, 0., 0., .05)
    upper = rectangle(.45, .35, 0., 0., .6)
    stacked = surface_from_arrays(np.vstack((lower, upper)), np.vstack((faces, faces+4)),
        vertex_tangent=(1., 0., 0.), face_object_index=np.array([0, 0, 1, 1]),
        objects=[{"object_id": "lower", "level": "custom"},
                 {"object_id": "upper", "level": "custom"}])
    camera = make_topdown_camera(stacked.bounds_mm, resolution=(h, w),
                                extent_xy_mm=(-1., 1., -.8, .8))
    result = trace_structure_maps(stacked, camera, supersample=1)
    top = (np.abs(xx) < .45) & (np.abs(yy) < .35)
    _check(np.all(result.arrays["valid_mask"]), "background plane covers all oracle pixels")
    _check(np.array_equal(result.arrays["object_index"], top.astype(np.int32)),
           "two-layer visibility must select nearest surface, not first object")
    _check(np.array_equal(result.arrays["primitive_index"] >= 2, top),
           "two-layer visible primitive agrees with analytic rectangle")
    height_error = float(np.max(np.abs(result.arrays["height_mm"]-np.where(top, .6, .05))))
    _check(height_error < 2e-6, "two-layer analytic front/back heights")
    rows.append({"oracle": "two_layer_occlusion", "height_error_mm": height_error,
                 "visible_front_pixel_count": int(top.sum()),
                 "visible_back_pixel_count": int((~top).sum()),
                 "center": check_physical_arrays(result.arrays, camera.to_dict(), label="analytic_occlusion"),
                 "executed_geometry_sources_sha256": result.metadata["source_files_sha256"],
                 "actual_primary_ray_queries": result.metadata["actual_primary_ray_queries"]})
    return {"status": "passed", "oracles": rows,
            "actual_primary_ray_queries": sum(r["actual_primary_ray_queries"] for r in rows),
            "actual_lighting_render_calls": 0}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _path(value):
    value = Path(value)
    return value.resolve() if value.is_absolute() else (ROOT/value).resolve()


def _label(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _descriptor_file(descriptor, ledger, *, label):
    path = _path(descriptor["path"])
    _check(path.is_file(), f"{label}: missing file {path}")
    digest = _sha(path)
    _check(digest == descriptor["sha256"], f"{label}: byte SHA-256 mismatch")
    if "size_bytes" in descriptor:
        _check(path.stat().st_size == descriptor["size_bytes"], f"{label}: byte length mismatch")
    ledger[_label(path)] = digest
    return path


def _array_descriptors(arrays, descriptions, *, semantic, label):
    _check(set(arrays) == set(descriptions), f"{label}: array names differ")
    for name, value in arrays.items():
        spec = descriptions[name]
        _check(list(value.shape) == spec["shape"] and value.dtype.str == spec["dtype"],
               f"{label}/{name}: array shape or dtype mismatch")
        payload = np.ascontiguousarray(value).tobytes()
        if semantic:
            payload = _canonical({"shape": list(value.shape), "dtype": value.dtype.str})+payload
        key = "sha256" if semantic else "sha256_c_order_bytes"
        _check(hashlib.sha256(payload).hexdigest() == spec[key], f"{label}/{name}: array digest mismatch")


def _id_meaning(arrays, metadata, *, label):
    valid = arrays["valid_mask"]
    owner = arrays["object_index"][valid]
    objects, tables = metadata["objects"], metadata["id_tables"]
    _check(len(objects) == len({obj["object_id"] for obj in objects}), f"{label}: duplicate object identity")
    _check(owner.max() < len(objects), f"{label}: object lookup out of range")
    _check(np.max(arrays["primitive_index"][valid]) < metadata["surface"]["triangle_count"],
           f"{label}: primitive index exceeds surface triangle count")
    blocks = metadata["surface"]["tube_summaries"]
    _check([b["object_id"] for b in blocks] == [o["object_id"] for o in objects],
           f"{label}: primitive-block object order")
    lengths = np.array([b["summary"]["face_count"] for b in blocks], dtype=np.int64)
    _check(np.all(lengths > 0) and int(lengths.sum()) == metadata["surface"]["triangle_count"],
           f"{label}: primitive-block face accounting")
    expected_owner = np.searchsorted(np.cumsum(lengths), arrays["primitive_index"][valid], side="right")
    _check(np.array_equal(owner, expected_owner), f"{label}: actual hit primitive belongs to a different object")
    for kind in ("fiber", "ply", "yarn", "material", "family"):
        table = tables[kind]
        _check(len(table) == len(set(table)), f"{label}: duplicate {kind} lookup value")
        field = kind if kind == "family" else kind+"_id"
        expected = []
        for obj in objects:
            identity = obj.get(field)
            _check(identity is None or identity in table, f"{label}: object {field} not in lookup")
            expected.append(-1 if identity is None else table.index(identity))
        _check(np.array_equal(arrays[kind+"_index"][valid], np.asarray(expected)[owner]),
               f"{label}: {kind} category disagrees with hit object's identity")
    level = metadata["surface"]["level"]
    if level == "ply_envelope":
        for obj in objects:
            _check(obj["presentation_proxy"] is True and obj["solid_proxy_fills_interfiber_voids"] is True,
                   f"{label}: ply envelope must be marked as a filled proxy")
            _check(obj["fiber_id"] is None, f"{label}: envelope assigned a single fiber identity")
            if len(obj["material_ids"]) > 1:
                _check(obj["material_id"] is None, f"{label}: mixed ply assigned a single material")
    else:
        _check(level == "explicit_fiber", f"{label}: unsupported hierarchy level")
        _check(all(obj["presentation_proxy"] is False and obj["object_id"] == obj["fiber_id"]
                   for obj in objects), f"{label}: explicit fiber identity/proxy status")
    return {"object_count": len(objects), "visible_object_count": len(np.unique(owner)),
            "lookup_sizes": {kind: len(table) for kind, table in tables.items()}}


def _source_identity_assignments(metadata, spec, *, label):
    """Cross-check parent/material assignments against the original JSON design."""
    _check(metadata["surface"]["source_spec"] == spec, label+": source specification mismatch")
    expected = {}
    for family in ("warp", "weft"):
        template = spec[family+"_yarn"]
        for yarn in range(spec[family+"_count"]):
            for ply, p in enumerate(template["plies"]):
                for fiber, f in enumerate(p["fibers"]):
                    expected[(family, yarn, ply, fiber)] = f["material_id"]
    if metadata["surface"]["level"] == "explicit_fiber":
        fibers = metadata["objects"]
    else:
        fibers = [f for ply in metadata["objects"] for f in ply["child_fiber_provenance"]]
    observed = {}
    for f in fibers:
        key = (f["family"], f["yarn_index"], f["ply_index"], f["fiber_index"])
        _check(key not in observed, label+": duplicate source fiber index tuple")
        observed[key] = f["material_id"]
    _check(observed == expected, label+": material or hierarchy assignment differs from input design")
    return {"source_fiber_assignments_checked": len(observed),
            "source_material_names": sorted(set(observed.values()))}


def check_display_arrays(center, samples, display, encoding, supersample, *, label):
    """Independently sum color contributions over each sample lattice offset.

    No compositor functions are imported. Expected sample colors follow the
    declared map equations; the final background composite is checked directly,
    so accidentally storing premultiplied RGB as straight RGB is detectable.
    """
    import matplotlib
    from matplotlib.colors import ListedColormap, to_rgb

    valid = samples["valid_mask"]
    _check(valid.dtype == np.bool_ and valid.ndim == 2, f"{label}: SS boolean mask")
    h, w = center["valid_mask"].shape
    s = int(supersample)
    _check(s > 0 and valid.shape == (h*s, w*s), f"{label}: supersample grid dimensions")
    ss_unit_errors = {}
    for key in ("world_normal", "world_tangent", "height_mm"):
        a = samples[key]
        _check(a.shape == valid.shape+(() if key == "height_mm" else (3,)), f"{label}: SS {key} shape")
        _check(np.isfinite(a[valid]).all() and np.isnan(a[~valid]).all(),
               f"{label}: SS {key} finite-hit/NaN-miss contract")
        if key != "height_mm":
            error = float(np.max(np.abs(np.linalg.norm(a[valid].astype(np.float64), axis=-1)-1)))
            _check(error < 3e-6, f"{label}: SS {key} unit vectors")
            ss_unit_errors[key] = error
    hits = np.zeros((h, w), dtype=np.float64)
    for iy in range(s):
        for ix in range(s):
            hits += valid[iy::s, ix::s]
    coverage = hits/(s*s)
    _check(np.array_equal(center["coverage"], coverage.astype(center["coverage"].dtype)),
           f"{label}: coverage does not match saved hit samples")
    limits = np.asarray(encoding["height"]["shared_limits_um"], dtype=float)
    _check(limits.shape == (2,) and np.isfinite(limits).all() and limits[0] < limits[1],
           f"{label}: invalid shared height limits")
    height_um = samples["height_mm"]*1000
    center_height_um = center["height_mm"]*1000
    _check(np.all((height_um[valid] >= limits[0]) & (height_um[valid] <= limits[1])) and
           np.all((center_height_um[center["valid_mask"]] >= limits[0]) &
                  (center_height_um[center["valid_mask"]] <= limits[1])),
           f"{label}: shared height legend clips physical values")
    normal_rgb = np.clip((samples["world_normal"]+1)/2, 0, 1)
    tangent = samples["world_tangent"]
    threshold = float(encoding["orientation"]["projection_threshold"])
    defined = valid & (np.hypot(tangent[..., 0], tangent[..., 1]) >= threshold)
    theta = np.full(valid.shape, np.nan, dtype=np.float64)
    # Preserve declared stored-float32 arithmetic at a discrete LUT boundary.
    theta[defined] = np.remainder(np.arctan2(tangent[..., 1][defined], tangent[..., 0][defined]), np.pi)
    orientation_spec = encoding["orientation"]
    lut_size = int(orientation_spec["colormap_lut_size"])
    phase = float(orientation_spec["colormap_phase_fraction"])
    _check(lut_size > 1 and np.isfinite(phase), f"{label}: orientation LUT definition")
    base = matplotlib.colormaps[orientation_spec["colormap"]]
    lut = base(np.mod(np.arange(lut_size, dtype=float)/lut_size+phase, 1.))
    orientation_rgb = ListedColormap(lut)(np.nan_to_num(theta)/np.pi)[..., :3]
    orientation_rgb[valid & ~defined] = encoding["orientation"]["undefined_rgb"]
    lo, hi = map(float, limits)
    height_rgb = matplotlib.colormaps[encoding["height"]["colormap"]](
        np.nan_to_num((height_um-lo)/(hi-lo)))[..., :3]
    background = np.asarray(encoding["background_rgb"], dtype=float)
    _check(background.shape == (3,) and np.isfinite(background).all() and
           np.all((background >= 0) & (background <= 1)), f"{label}: background color")
    errors = {}
    for name, sample_color in (("normal", normal_rgb), ("orientation", orientation_rgb), ("height", height_rgb)):
        actual = display[name+"_rgba"]
        _check(actual.shape == (h, w, 4) and actual.dtype == np.float32 and
               np.isfinite(actual).all() and np.all((actual >= 0) & (actual <= 1)),
               f"{label}: {name} RGBA validity")
        _check(np.array_equal(actual[..., 3], coverage.astype(np.float32)), f"{label}: {name} coverage alpha")
        _check(np.all(actual[..., :3][hits == 0] == 0), f"{label}: {name} transparent RGB must be zero")
        contribution = np.zeros((h, w, 3), dtype=np.float64)
        for iy in range(s):
            for ix in range(s):
                mask = valid[iy::s, ix::s]
                rgb = sample_color[iy::s, ix::s]
                contribution += np.where(mask[..., None], rgb, background)
        expected_composite = contribution/(s*s)
        actual_composite = actual[..., :3].astype(float)*actual[..., 3:4]+background*(1-actual[..., 3:4])
        error = float(np.max(np.abs(actual_composite-expected_composite)))
        _check(error < 2e-7, f"{label}: {name} color equation or straight-alpha error {error}")
        errors[name] = error
    cv = center["valid_mask"]
    ct = center["world_tangent"]
    cd = cv & (np.hypot(ct[..., 0], ct[..., 1]) >= threshold)
    _check(np.array_equal(display["orientation_defined_mask"], cd), f"{label}: center orientation mask")
    stored_theta = display["orientation_angle_rad"]
    _check(stored_theta.shape == cv.shape and np.isfinite(stored_theta[cd]).all() and
           np.isnan(stored_theta[~cd]).all(), f"{label}: center orientation finite/undefined values")
    expected_theta = np.arctan2(ct[..., 1][cd].astype(float), ct[..., 0][cd].astype(float))
    angle_error = float(np.max(np.abs(np.exp(2j*stored_theta[cd].astype(float))-np.exp(2j*expected_theta)))) if cd.any() else 0.
    _check(angle_error < 8e-7, f"{label}: saved line orientation differs from physical tangent")
    material = display["material_rgba"]
    _check(material.shape == (h, w, 4) and material.dtype == np.float32 and
           np.isfinite(material).all(), f"{label}: material RGBA")
    _check(np.array_equal(material[..., 3], cv.astype(np.float32)),
           f"{label}: categorical map must use center hit, not SS coverage")
    _check(np.all(material[~cv] == 0), f"{label}: material background transparency")
    palette = encoding["material"]["palette_hex"]
    colors_seen = {}
    for category in np.unique(center["material_index"][cv]):
        mask = cv & (center["material_index"] == category)
        rgb = encoding["material"]["mixed_proxy_rgb"] if category < 0 else to_rgb(palette[int(category) % len(palette)])
        _check(np.allclose(material[..., :3][mask], rgb, rtol=0, atol=6e-8),
               f"{label}: material category {category} color was averaged or reassigned")
        colors_seen[str(int(category))] = list(map(float, rgb))
    return {"supersampled_shape": list(valid.shape), "supersampled_valid_count": int(valid.sum()),
        "sample_coverage_fraction": float(valid.mean()), "center_coverage_fraction": float(cv.mean()),
        "partial_coverage_pixel_count": int(((hits > 0) & (hits < s*s)).sum()),
        "supersampled_unit_length_max_errors": ss_unit_errors,
        "background_composite_max_errors": errors, "orientation_director_max_error": angle_error,
        "height_observed_um": [float(height_um[valid].min()), float(height_um[valid].max())],
        "center_orientation_undefined_hits": int((cv & ~cd).sum()),
        "sample_orientation_undefined_hits": int((valid & ~defined).sum()),
        "height_clipped_samples": 0, "categorical_colors": colors_seen}


def verify_saved_figures(manifest_path):
    """Read-only audit of every saved map, display array, figure and source link."""
    manifest_path = _path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    _check(manifest.get("schema") == "textile.structure_figures/5.1" and
           manifest.get("status") == "completed", "complete structure figure schema required")
    _check(manifest["not_a_radiance_render"] is True, "structure maps must not be declared radiance")
    ledger = {_label(manifest_path): _sha(manifest_path)}
    for relative, expected in manifest["producer_sources_sha256"].items():
        _check(_sha(_path(relative)) == expected, f"producer source changed: {relative}")
        ledger[relative] = expected
    spec_path = _descriptor_file(manifest["input_spec"], ledger, label="copied input spec")
    original = {"path": manifest["input_spec"]["original_path"],
                "sha256": manifest["input_spec"]["original_sha256"]}
    original_path = _descriptor_file(original, ledger, label="original input spec")
    spec = json.loads(spec_path.read_text())
    _check(spec == json.loads(original_path.read_text()), "saved and original hierarchy specifications differ")
    enc = manifest["encoding"]
    _check(enc["normal"]["source"] == "world_normal" and enc["normal"]["mapping"] == "RGB=(n+1)/2" and
           enc["normal"]["world_components_rgb"] == ["X", "Y", "Z"] and
           enc["normal"]["gamma_or_light_transport"].startswith("none"), "normal color/world-coordinate contract")
    _check(enc["orientation"]["source"] == "world_tangent" and enc["orientation"]["projection"] == "world XY" and
           enc["orientation"]["period_deg"] == 180 and enc["orientation"]["angle_formula"] == "atan2(ty,tx) mod pi",
           "headless orientation contract")
    _check(enc["height"]["source"] == "height_mm" and enc["height"]["units"] == "um" and
           enc["height"]["clipped_samples_allowed"] == 0, "physical height contract")
    _check(enc["material"]["antialias_categories"] is False and
           enc["antialias"]["normal_average_is_unit_vector"] is False, "AA/category semantics")
    _check(enc["camera"]["matplotlib_origin"] == "upper", "image Y convention")
    expected_keys = {f"{role}/{level}" for role in ("overview", "zoom") for level in ("ply_envelope", "explicit_fiber")}
    actual_keys = set(manifest["input_maps"])
    single_proxy = actual_keys == {"compact/ply_envelope"}
    compact = manifest.get("demonstration_variant") == "separate compact specification"
    _check(actual_keys == expected_keys or (single_proxy and compact),
           "expected four maps or one explicitly separated compact proxy")
    rows, geometry_hashes, saved_query_count = {}, set(), 0
    for key, record in manifest["input_maps"].items():
        raw_path = _descriptor_file(record["raw_arrays"], ledger, label=key+"/raw")
        meta_path = _descriptor_file(record["raw_metadata"], ledger, label=key+"/metadata")
        meta = json.loads(meta_path.read_text())
        _check(meta["schema_version"] == "textile.structure_maps/5.1" and
               meta["length_unit"] == "mm" and meta["vector_frame"] == "world_xyz", key+": raw schema/units/frame")
        _check(meta["raw_file"] == raw_path.name and meta["raw_file_sha256"] == _sha(raw_path),
               key+": nested raw hash")
        arrays = _load_npz(raw_path)
        _array_descriptors(arrays, meta["arrays"], semantic=True, label=key+"/physical")
        _check(meta["saved_supersamples"] is False and all(not k.startswith("sample__") for k in arrays),
               key+": physical arrays must be separate from display supersamples")
        _check(meta["camera"] == record["camera"] and
               hashlib.sha256(_canonical(meta["camera"])).hexdigest() == meta["camera_sha256"], key+": camera digest")
        _check(list(arrays["valid_mask"].shape) == record["resolution_hw"] == meta["camera"]["resolution_hw"],
               key+": image dimensions")
        _check(meta["supersample"] == record["supersample"], key+": sample factor")
        for relative, digest in meta["source_files_sha256"].items():
            _check(_sha(_path(relative)) == digest, key+": raw source hash changed: "+relative)
            ledger[relative] = digest
        _check(meta["source_hashes_unchanged_during_trace"] is True and
               meta["surface"]["source_unchanged_during_construction"] is True, key+": declared source mutation")
        _check(meta["surface"]["level"] == record["level"] and
               meta["surface"]["radial_segments"] == record["radial_segments"], key+": surface identity/resolution")
        _check(meta["surface"]["orientation_is_surface_bsdf_tangent"] is False,
               key+": centerline tangent must not be presented as a BSDF tangent")
        geometry_hashes.add(meta["surface"]["source_geometry_sha256"])
        physical = check_physical_arrays(arrays, meta["camera"], label=key)
        identities = _id_meaning(arrays, meta, label=key)
        identities.update(_source_identity_assignments(meta, spec, label=key))
        sources_path = _descriptor_file(record["display_sources"], ledger, label=key+"/SS")
        display_path = _descriptor_file(record["display_arrays"], ledger, label=key+"/display")
        samples, display = _load_npz(sources_path), _load_npz(display_path)
        _array_descriptors(samples, record["display_sources"]["arrays"], semantic=False, label=key+"/SS")
        _array_descriptors(display, record["display_arrays"]["arrays"], semantic=False, label=key+"/display")
        color = check_display_arrays(arrays, samples, display, enc, record["supersample"], label=key)
        stats = record["statistics"]
        expected_stats = {"center_valid_pixels": physical["valid_count"],
            "center_total_pixels": arrays["valid_mask"].size, "supersample_valid_pixels": color["supersampled_valid_count"],
            "supersample_total_pixels": samples["valid_mask"].size,
            "material_indices_on_valid_centers": physical["categorical_visible_ids"]["material_index"]}
        for name in ("center_coverage_fraction", "sample_coverage_fraction", "center_orientation_undefined_hits",
                     "sample_orientation_undefined_hits", "height_observed_um", "height_clipped_samples"):
            expected_stats[name] = color[name]
        for name, expected in expected_stats.items():
            _check(np.allclose(stats[name], expected, rtol=0, atol=1e-7), key+": incorrect statistic "+name)
        _check(meta["center_hit_count"] == physical["valid_count"] and
               meta["supersampled_hit_count"] == color["supersampled_valid_count"], key+": metadata hit counts")
        s = record["supersample"]
        queries = arrays["valid_mask"].size*(1 if s == 1 else 1+s*s)
        _check(queries == meta["actual_primary_ray_queries"] and meta["actual_lighting_render_calls"] == 0,
               key+": query count/radiance scope")
        saved_query_count += int(queries)
        camera, extent = meta["camera"], record["extent_xy_mm"]
        _check(np.array_equal(camera["right"], [1, 0, 0]) and np.array_equal(camera["up"], [0, 1, 0]) and
               np.array_equal(camera["view_direction"], [0, 0, -1]), key+": top-down projection")
        expected_extent = [camera["origin_mm"][0]-camera["width_mm"]/2, camera["origin_mm"][0]+camera["width_mm"]/2,
                           camera["origin_mm"][1]-camera["height_mm"]/2, camera["origin_mm"][1]+camera["height_mm"]/2]
        _check(np.allclose(extent, expected_extent, rtol=0, atol=2e-15), key+": extent differs from camera projection")
        rows[key] = {"physical": physical, "display": color, "identity": identities,
                     "extent_xy_mm": extent, "recorded_primary_ray_queries": int(queries),
                     "saved_array_count": len(arrays)+len(samples)+len(display)}
        del arrays, samples, display
    _check(len(geometry_hashes) == 1, "map layers do not share recorded source geometry")
    for role in (() if single_proxy else ("overview", "zoom")):
        one, two = (manifest["input_maps"][f"{role}/{level}"] for level in ("ply_envelope", "explicit_fiber"))
        _check(one["extent_xy_mm"] == two["extent_xy_mm"] and one["resolution_hw"] == two["resolution_hw"],
               role+": hierarchy views do not share projection/crop")
    figure_files, glyph_count, scalebar_count = [], 0, 0
    for fig in manifest["figures"]:
        extents = []
        for panel in fig["panels"]:
            _check(panel["map"] in rows and panel["field"] in ("normal", "orientation", "height", "material"),
                   "unknown figure panel data")
            _check(panel["extent_xy_mm"] == rows[panel["map"]]["extent_xy_mm"], "panel crop drift")
            extents.append(panel["extent_xy_mm"])
        for bar in fig["scale_bars"]:
            start, end, length = np.array(bar["start_xy_mm"]), np.array(bar["end_xy_mm"]), float(bar["length_mm"])
            _check(length > 0 and np.allclose(end-start, [length, 0], rtol=0, atol=1e-14), "metric scalebar length")
            _check(any(e[0] <= start[0] < end[0] <= e[1] and e[2] <= start[1] <= e[3] for e in extents),
                   "metric scalebar outside every panel")
            scalebar_count += 1
        for glyphs in fig.get("orientation_glyphs", []):
            _check(glyphs["arrowheads"] is False, "unoriented glyph must have no arrowhead")
            record = manifest["input_maps"][glyphs["map"]]
            d = _load_npz(_path(record["display_arrays"]["path"]))
            h, w = d["orientation_angle_rad"].shape
            x0, x1, y0, y1 = record["extent_xy_mm"]
            for glyph in glyphs["samples"]:
                r, c = glyph["pixel_row_col"]
                _check(0 <= r < h and 0 <= c < w and d["orientation_defined_mask"][r, c], "glyph on absent/undefined tangent")
                _check(abs(glyph["theta_rad"]-float(d["orientation_angle_rad"][r, c])) < 1e-12, "glyph angle differs from saved tangent")
                _check(np.allclose(glyph["center_xy_mm"], [x0+(c+.5)/w*(x1-x0), y1-(r+.5)/h*(y1-y0)],
                                   rtol=0, atol=1e-14), "glyph pixel/world coordinate mismatch")
                _check(glyph["half_length_mm"] > 0, "nonpositive glyph size")
                glyph_count += 1
        extensions = set()
        for descriptor in fig["files"]:
            path = _descriptor_file(descriptor, ledger, label=fig["name"])
            extensions.add(path.suffix)
            if path.suffix == ".png":
                from PIL import Image
                with Image.open(path) as im:
                    dimensions = list(im.size); im.verify()
                _check(min(dimensions) >= 600, "publication PNG unexpectedly small")
            elif path.suffix == ".pdf":
                content = path.read_bytes()
                _check(content.startswith(b"%PDF-") and b"%%EOF" in content[-100:], "invalid/truncated figure PDF")
            elif path.suffix == ".svg":
                from xml.etree import ElementTree
                _check(ElementTree.parse(path).getroot().tag.endswith("svg"), "invalid SVG document")
            figure_files.append(_label(path))
        _check(extensions == {".png", ".pdf", ".svg"}, "each figure requires PNG/PDF/SVG")
    for relative, expected in ledger.items():
        _check(_sha(_path(relative)) == expected, "audited input changed during review: "+relative)
    return {"schema_version": "textile.independent_structure_review/5.1", "status": "passed",
        "dataset_role": "separate_compact_demonstration" if compact else "main_hierarchy_comparison",
        "saved_map_count": len(rows), "saved_array_count": sum(row["saved_array_count"] for row in rows.values()),
        "unique_npz_crc_checks": 3*len(rows), "figure_count": len(manifest["figures"]),
        "figure_file_count": len(figure_files), "verified_scalebars": scalebar_count,
        "verified_headless_glyphs": glyph_count, "maps": rows,
        "recorded_source_geometry_sha256": next(iter(geometry_hashes)),
        "recorded_source_geometry_hash_was_regenerated": False,
        "recorded_saved_map_primary_ray_queries": saved_query_count,
        "new_primary_ray_queries_for_saved_array_review": 0, "new_lighting_render_calls": 0,
        "shared_height_limits_um": enc["height"]["shared_limits_um"],
        "audited_files_sha256": ledger, "inputs_unchanged_during_review": True,
        "scope": ["Independent coordinate, category, color/coverage and archive checks of saved maps.",
                  "Source geometry hashes are cross-checked declarations; source fiber arrays are not regenerated by this reader.",
                  "Figure files pass hash/container checks; human visual review is recorded separately.",
                  "No material inference, radiance computation, physical-fabric validation or optical convergence claim."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT/"figures/structure_v5_1/figure_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT/"data/validation_v5_1/independent_review")
    parser.add_argument("--initial-oracle", type=Path,
                        help="Copy a prior development oracle unchanged; do not count it as a new execution")
    parser.add_argument("--skip-oracles", action="store_true", help="Read saved arrays only; no new ray queries")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    _check(not output.exists(), "independent audit output must be a new directory")
    started = time.perf_counter()
    review_source_hash = _sha(__file__)
    summary = verify_saved_figures(args.manifest)
    oracle = None if args.skip_oracles else geometric_oracles()
    _check(_sha(__file__) == review_source_hash, "review source changed during execution")
    summary.update({"execution_workflow": "python -m visualization.review_structure_figures",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.perf_counter()-started,
        "review_source_sha256": review_source_hash, "review_source_unchanged": True,
        "analytic_oracles": {"status": "skipped"} if oracle is None else {
            "status": oracle["status"], "actual_primary_ray_queries": oracle["actual_primary_ray_queries"],
            "actual_lighting_render_calls": oracle["actual_lighting_render_calls"], "file": "analytic_oracles.json"}})
    output.mkdir(parents=True)
    if oracle is not None:
        oracle["review_source_sha256"] = review_source_hash
        oracle["execution_workflow"] = summary["execution_workflow"]
        oracle_path = output/"analytic_oracles.json"
        oracle_path.write_text(json.dumps(oracle, indent=2, allow_nan=False)+"\n")
        summary["analytic_oracles"]["sha256"] = _sha(oracle_path)
    if args.initial_oracle:
        previous = args.initial_oracle.resolve()
        copied = output/"initial_development_oracles.json"
        shutil.copyfile(previous, copied)
        summary["prior_development_oracle"] = {"copied_from": _label(previous), "file": copied.name,
            "sha256": _sha(copied), "copy_triggered_new_queries": False,
            "source_hash_recorded_at_original_execution": False,
            "reason_retained": "Initial draft result is retained as history, without retroactively assigning a source hash."}
    (output/"verification_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    print(json.dumps({key: summary[key] for key in ("status", "saved_map_count", "saved_array_count",
        "figure_file_count", "recorded_saved_map_primary_ray_queries", "analytic_oracles")}))


if __name__ == "__main__":
    main()
