"""Explicit segment-radius to continuous-profile and triangle-tube conversion.

Lengths are millimeters. The v4 ``incompressible_segments`` state conserves a
sum of straight-cylinder segment proxies. This module exposes the additional
approximation needed by an optical surface: length-weighted node *area*
averaging followed by one positive scale per fiber. That scale preserves the
sum of exact straight frustum integrals, not each material segment's volume.
The actual closed triangle-mesh signed volume is measured separately, without
renormalization. Neither a positive signed volume nor closed edge incidence
certifies absence of self-intersections, mechanical equilibrium, or mass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import numbers
from pathlib import Path

import numpy as np

from .hierarchy import arclength_mm, rotation_minimizing_frames

PROFILE_SCHEMA = "textile.variable_radius_profile/5.0"
MESH_SCHEMA = "textile.tapered_tube_mesh/5.0"
PROFILE_RULE = "length_weighted_node_area_then_per_fiber_frustum_volume_scale"


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _json_object(value, name="provenance_json"):
    try:
        item = json.loads(value) if isinstance(value, str) else value
        if not isinstance(item, dict):
            raise ValueError(f"{name} must encode a JSON object")
        return _canonical(item)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} must encode a finite JSON object") from exc


def _readonly(value, dtype=np.float64):
    a = np.ascontiguousarray(value, dtype=dtype)
    if not np.isfinite(a).all():
        raise ValueError("numeric arrays must be finite")
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


def _identifier(value, name):
    if (not isinstance(value, str) or not value.strip()
            or any(ord(c) < 32 for c in value)):
        raise ValueError(f"{name} must be a nonempty identifier without control characters")
    return value


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _points(value):
    p = np.asarray(value, dtype=float)
    arc = arclength_mm(p)
    if not np.isfinite(arc).all():
        raise ValueError("centerline arclength must be finite")
    if np.linalg.norm(p[-1]-p[0]) <= 1e-12*arc[-1]:
        raise ValueError("closed/near-closed centerlines need a separate seam convention")
    return _readonly(p), np.diff(arc)


def _positive_vector(value, count, name):
    a = np.asarray(value, dtype=float)
    if a.shape != (count,) or not np.isfinite(a).all() or np.any(a <= 0):
        raise ValueError(f"{name} must contain one finite positive value per sample")
    return _readonly(a)


def _labels(value, count, name):
    a = np.asarray(value, dtype=float)
    if (a.shape != (count,) or not np.isfinite(a).all() or a[0] != 0
            or np.any(np.diff(a) <= 0)):
        raise ValueError(f"{name} must start at zero and increase strictly")
    return _readonly(a)


def _digest(metadata, arrays):
    h = hashlib.sha256(_canonical(metadata).encode("utf-8"))
    for name, value in sorted(arrays.items()):
        raw = np.asarray(value)
        dtype = "<i8" if raw.dtype.kind in "iu" else "<f8"
        a = np.ascontiguousarray(raw, dtype=dtype)
        h.update(_canonical([name, list(a.shape), dtype]).encode("utf-8"))
        h.update(a.tobytes())
    return h.hexdigest()


def frustum_segment_volumes_mm3(segment_length_mm, node_radius_mm):
    """Exact integral for a radius linear along each STRAIGHT segment.

    pi * length * (r_left^2 + r_left*r_right + r_right^2) / 3.
    Node ring planes on a bent centerline generally are not perpendicular to
    their connecting chord; this is therefore a reference integral, not the
    volume of the swept triangle mesh.
    """
    length = np.asarray(segment_length_mm, dtype=float)
    if length.ndim != 1 or len(length) < 1:
        raise ValueError("segment lengths must be a nonempty vector")
    length = _positive_vector(length, len(length), "segment_length_mm")
    r = _positive_vector(node_radius_mm, len(length)+1, "node_radius_mm")
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        result = np.pi*length*(r[:-1]*r[:-1]+r[:-1]*r[1:]+r[1:]*r[1:])/3
    if not np.isfinite(result).all() or np.any(result <= 0):
        raise ValueError("frustum volume overflow/underflow")
    return _readonly(result)


@dataclass(frozen=True, eq=False)
class VariableRadiusFiber:
    """A labeled fiber and an explicitly reconstructed linear-radius profile.

    Source radii refer to segments, node radii to vertices. No material label,
    centerline position, parent identity or constituent material is relabeled.
    The rule is deliberately fixed and recorded rather than exposing an opaque
    smoothing parameter. It is an optical geometry approximation, not a fiber
    constitutive or local incompressibility law.
    """
    points_mm: np.ndarray
    material_coordinates_mm: np.ndarray
    parent_material_coordinates_mm: np.ndarray
    segment_radius_mm: np.ndarray
    fiber_id: str
    yarn_id: str
    ply_id: str
    material_id: str
    family: str = "unspecified"
    yarn_index: int = 0
    ply_index: int = 0
    fiber_index: int = 0
    kind: str = "core"
    cross_section: str = "circle"
    length_unit: str = "mm"
    provenance_json: str = "{}"
    segment_length_mm: np.ndarray = field(init=False)
    raw_node_radius_mm: np.ndarray = field(init=False)
    node_radius_mm: np.ndarray = field(init=False)
    radius_scale: float = field(init=False)
    segment_volume_proxy_mm3: np.ndarray = field(init=False)
    segment_frustum_volume_mm3: np.ndarray = field(init=False)
    segment_relative_volume_error: np.ndarray = field(init=False)

    def __post_init__(self):
        if self.length_unit != "mm" or self.cross_section != "circle":
            raise ValueError("explicit mm units and circular cross section are required")
        for name in ("fiber_id", "yarn_id", "ply_id", "material_id", "family", "kind"):
            _identifier(getattr(self, name), name)
        for name in ("yarn_index", "ply_index", "fiber_index"):
            object.__setattr__(self, name, _integer(getattr(self, name), name))
        p, length = _points(self.points_mm)
        material = _labels(self.material_coordinates_mm, len(p), "material_coordinates_mm")
        parent = _labels(self.parent_material_coordinates_mm, len(p), "parent_material_coordinates_mm")
        r = _positive_vector(self.segment_radius_mm, len(p)-1, "segment_radius_mm")
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            area = r*r
            proxy = np.pi*area*length
        if not np.isfinite(proxy).all() or np.any(proxy <= 0):
            raise ValueError("cylinder volume overflow/underflow")
        nodal_area = np.empty(len(p))
        nodal_area[0], nodal_area[-1] = area[0], area[-1]
        # Use normalized weights to avoid forming length*area twice at extreme
        # scales. Endpoints retain the adjacent segment's radius before scale.
        w = length[:-1]/(length[:-1]+length[1:])
        nodal_area[1:-1] = w*area[:-1]+(1-w)*area[1:]
        raw = np.sqrt(nodal_area)
        initial_volume = frustum_segment_volumes_mm3(length, raw)
        target, initial = float(np.sum(proxy)), float(np.sum(initial_volume))
        if not np.isfinite([target, initial]).all() or target <= 0 or initial <= 0:
            raise ValueError("finite positive total volume proxies are required")
        scale = float(np.sqrt(target/initial))
        nodes = _positive_vector(raw*scale, len(p), "reconstructed node radius")
        frustum = frustum_segment_volumes_mm3(length, nodes)
        values = {"points_mm": p, "material_coordinates_mm": material,
                  "parent_material_coordinates_mm": parent, "segment_radius_mm": r,
                  "segment_length_mm": length, "raw_node_radius_mm": raw,
                  "node_radius_mm": nodes, "segment_volume_proxy_mm3": proxy,
                  "segment_frustum_volume_mm3": frustum,
                  "segment_relative_volume_error": frustum/proxy-1}
        for key, value in values.items():
            object.__setattr__(self, key, _readonly(value))
        object.__setattr__(self, "radius_scale", scale)
        object.__setattr__(self, "provenance_json", _json_object(self.provenance_json))

    def metadata(self):
        return {"schema": PROFILE_SCHEMA, "reconstruction_rule": PROFILE_RULE,
                **{name: getattr(self, name) for name in (
                    "fiber_id", "yarn_id", "ply_id", "material_id", "family", "yarn_index",
                    "ply_index", "fiber_index", "kind", "cross_section", "length_unit")},
                "provenance_json": self.provenance_json}

    def source_arrays(self):
        return {name: getattr(self, name) for name in (
            "points_mm", "material_coordinates_mm", "parent_material_coordinates_mm", "segment_radius_mm")}

    def arrays(self):
        return {**self.source_arrays(), **{name: getattr(self, name) for name in (
            "segment_length_mm", "raw_node_radius_mm", "node_radius_mm", "segment_volume_proxy_mm3",
            "segment_frustum_volume_mm3", "segment_relative_volume_error")}}

    @property
    def sha256(self):
        return _digest(self.metadata(), self.source_arrays())

    def summary(self):
        target = float(self.segment_volume_proxy_mm3.sum())
        current = float(self.segment_frustum_volume_mm3.sum())
        return {**self.metadata(), "profile_sha256": self.sha256,
                "vertex_count": len(self.points_mm), "segment_count": len(self.segment_length_mm),
                "node_radius_min_mm": float(self.node_radius_mm.min()),
                "node_radius_max_mm": float(self.node_radius_mm.max()),
                "source_segment_radius_min_mm": float(self.segment_radius_mm.min()),
                "source_segment_radius_max_mm": float(self.segment_radius_mm.max()),
                "global_radius_scale": self.radius_scale,
                "source_cylinder_volume_proxy_mm3": target,
                "linear_radius_frustum_integral_mm3": current,
                "total_frustum_relative_volume_error": current/target-1,
                "max_absolute_segment_relative_volume_error": float(np.max(np.abs(self.segment_relative_volume_error))),
                "volume_weighted_mean_absolute_segment_relative_error": float(
                    np.sum(np.abs(self.segment_frustum_volume_mm3-self.segment_volume_proxy_mm3))/target),
                "segment_volume_conservation_enforced": False,
                "total_frustum_integral_conservation_enforced": True,
                "physical_mass_or_curved_tube_volume_conservation_certified": False,
                "material_labels_preserved": True,
                "physical_mechanics_solved": False}


def profiles_from_transport(state):
    """Adapt a validated v4 state, preserving every fiber/parent/material label."""
    from .material_transport import MaterialTransportState
    if not isinstance(state, MaterialTransportState):
        raise TypeError("state must be MaterialTransportState")
    # Evaluate shared digests once instead of hashing every parent for every fiber.
    provenance = _canonical({"source_schema": "textile.material_transport/4.0",
                             "source_state_sha256": state.sha256,
                             "source_reference_sha256": state.reference.sha256,
                             "source_radius_mode": state.radius_mode,
                             "material_correspondence": state.reference.correspondence,
                             "radius_conversion_is_a_geometric_approximation": True})
    return tuple(VariableRadiusFiber(
        points_mm=f.points_mm, material_coordinates_mm=f.material_coordinates_mm,
        parent_material_coordinates_mm=f.parent_material_coordinates_mm,
        segment_radius_mm=f.segment_radius_mm, provenance_json=provenance,
        **f.provenance()) for f in state.fiber_records)


def _face_arrays(vertices, faces):
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    cross = np.cross(b-a, c-a)
    twice_area = np.linalg.norm(cross, axis=1)
    if not np.isfinite(twice_area).all() or np.any(twice_area <= 0):
        raise ValueError("triangle mesh contains degenerate/nonfinite faces")
    normals = cross/twice_area[:, None]
    vertex_sums = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(vertex_sums, faces[:, k], cross)
    norms = np.linalg.norm(vertex_sums, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ValueError("undefined area-weighted vertex normals")
    # Closed-surface divergence formula about a centered numerical origin.
    # Centering removes catastrophic cancellation under world translation;
    # it does not prove this arithmetic centroid lies inside a curved solid.
    origin = np.mean(vertices, axis=0)
    signed_volume = float(np.sum(np.einsum("ij,ij->i", a-origin,
                                         np.cross(b-origin, c-origin)))/6)
    if not np.isfinite(signed_volume) or signed_volume <= 0:
        raise ValueError("mesh requires positive finite signed volume")
    return normals, vertex_sums/norms[:, None], signed_volume, float(.5*twice_area.sum())


def mesh_edge_audit(faces, vertex_count):
    """Check oriented edge incidence and Euler characteristic, not intersections."""
    n = _integer(vertex_count, "vertex_count", 4)
    f = np.asarray(faces)
    if (f.ndim != 2 or f.shape[1] != 3 or len(f) < 4 or f.dtype.kind not in "iu"
            or np.any(f < 0) or np.any(f >= n) or np.any(np.diff(np.sort(f, axis=1), axis=1) == 0)):
        raise ValueError("faces must contain three distinct valid integer vertex indices")
    oriented = np.concatenate((f[:, (0, 1)], f[:, (1, 2)], f[:, (2, 0)]))
    undirected = np.sort(oriented, axis=1)
    unique, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    direction = np.where(oriented[:, 0] < oriented[:, 1], 1, -1)
    oriented_sum = np.bincount(inverse, weights=direction)
    used_count = len(np.unique(f))
    return {"vertex_count": n, "used_vertex_count": used_count, "face_count": len(f),
            "edge_count": len(unique), "euler_characteristic": n-len(unique)+len(f),
            "all_vertices_used": used_count == n,
            "every_edge_has_two_faces": bool(np.all(counts == 2)),
            "edge_orientations_opposed": bool(np.all(oriented_sum == 0)),
            "self_intersection_tested": False}


def sweep_tapered_tube(points_mm, node_radius_mm, *, radial_segments=16,
                        initial_normal=None, tangents=None):
    """Geometry-only closed, capped RMF tube; no material identity is attached.

    Exposes a low-level numerical oracle API. Optical adapters should consume
    ``build_tapered_tube(profile)`` so the source identities cannot be discarded.
    Analytic tangents may be supplied explicitly for convergence studies. The
    actual triangle normals include taper; radial ring vectors alone are not
    the physical normals of a tapered surface.
    """
    m = _integer(radial_segments, "radial_segments", 3)
    p, length = _points(points_mm)
    radius = _positive_vector(node_radius_mm, len(p), "node_radius_mm")
    tangent, normal1, normal2 = rotation_minimizing_frames(p, tangents=tangents,
                                                         initial_normal=initial_normal)
    frames = np.stack((tangent, normal1, normal2), axis=-1)
    theta = 2*np.pi*np.arange(m)/m
    direction = normal1[:, None, :]*np.cos(theta)[None, :, None]+normal2[:, None, :]*np.sin(theta)[None, :, None]
    rings = p[:, None, :]+radius[:, None, None]*direction
    vertices = np.vstack((rings.reshape(-1, 3), p[0], p[-1]))
    current = np.arange(m)
    nxt = (current+1) % m
    side = []
    for i in range(len(p)-1):
        a, b, c, d = i*m+current, i*m+nxt, (i+1)*m+current, (i+1)*m+nxt
        side.append(np.column_stack((a, b, c)))
        side.append(np.column_stack((b, d, c)))
    side_faces = np.vstack(side)
    first_cap = np.column_stack((np.full(m, len(p)*m), nxt, current))
    last_cap = np.column_stack((np.full(m, len(p)*m+1), (len(p)-1)*m+current, (len(p)-1)*m+nxt))
    faces = np.vstack((side_faces, first_cap, last_cap)).astype(np.int64)
    face_normals, vertex_normals, volume, area = _face_arrays(vertices, faces)
    topology = mesh_edge_audit(faces, len(vertices))
    if (not topology["all_vertices_used"] or not topology["every_edge_has_two_faces"]
            or not topology["edge_orientations_opposed"] or topology["euler_characteristic"] != 2):
        raise ValueError("tube mesh failed closed oriented sphere-topology checks")
    # Each side face carries its endpoint ring indices. This local orientation
    # check catches obvious folded quads, but cannot certify global injectivity.
    ring_of_vertex = side_faces//m
    face_radial = np.mean(vertices[side_faces]-p[ring_of_vertex], axis=1)
    orient = np.einsum("ij,ij->i", face_normals[:len(side_faces)], face_radial)
    if np.any(orient <= 0):
        raise ValueError("locally folded tube side faces; refine or reduce radius/curvature")
    if (np.any(face_normals[len(side_faces):len(side_faces)+m]@tangent[0] >= 0)
            or np.any(face_normals[-m:]@tangent[-1] <= 0)):
        raise ValueError("cap orientation does not agree with endpoint frames")
    integral = frustum_segment_volumes_mm3(length, radius)
    bend = np.arccos(np.clip(np.sum(tangent[:-1]*tangent[1:], axis=1), -1., 1.))
    polygon_factor = float(m*np.sin(2*np.pi/m)/(2*np.pi))
    summary = {"schema": MESH_SCHEMA, "length_unit": "mm", "radial_segments": m,
               "ring_count": len(p), **topology,
               "signed_volume_mm3": volume, "surface_area_mm2": area,
               "straight_frustum_integral_mm3": float(integral.sum()),
               "mesh_to_frustum_relative_volume_difference": volume/float(integral.sum())-1,
               "straight_polygon_volume_factor": polygon_factor,
               "relative_volume_residual_after_factoring_straight_polygon_formula":
                   volume/(float(integral.sum())*polygon_factor)-1,
               "max_ring_polygon_sagitta_mm": float(radius.max()*(1-np.cos(np.pi/m))),
               "max_adjacent_frame_tangent_angle_rad": float(bend.max()),
               "max_discrete_radius_curvature_indicator": float(np.max(
                   .5*(radius[:-1]+radius[1:])*bend/length)),
               "max_radius_slope_per_chord_length": float(np.max(np.abs(np.diff(radius))/length)),
               "side_faces_locally_outward": True, "closed_caps_included": True,
               "full_surface_error_bound_available": False,
               "inter_fiber_clearance_tested": False,
               "mesh_volume_renormalized": False,
               "physical_mass_conservation_certified": False,
               "frame_rule": "double-reflection RMF with explicit or deterministic initial normal",
               "normal_rule": "triangle geometric normals; area-weighted vertex normals are optional shading data"}
    arrays = {"vertices_mm": vertices, "faces": faces, "face_normals": face_normals,
              "vertex_normals": vertex_normals, "frames": frames,
              "ring_segment_length_mm": length, "node_radius_mm": radius,
              "side_face_ring_indices": ring_of_vertex}
    return {**{key: _readonly(value, np.int64 if key in ("faces", "side_face_ring_indices") else np.float64)
               for key, value in arrays.items()},
            "signed_volume_mm3": volume, "surface_area_mm2": area, "summary": summary}


@dataclass(frozen=True, eq=False)
class TaperedTubeMesh:
    profile: VariableRadiusFiber
    radial_segments: int = 16
    initial_normal: np.ndarray | None = None
    vertices_mm: np.ndarray = field(init=False)
    faces: np.ndarray = field(init=False)
    face_normals: np.ndarray = field(init=False)
    vertex_normals: np.ndarray = field(init=False)
    frames: np.ndarray = field(init=False)
    ring_segment_length_mm: np.ndarray = field(init=False)
    side_face_ring_indices: np.ndarray = field(init=False)
    signed_volume_mm3: float = field(init=False)
    surface_area_mm2: float = field(init=False)
    _audit_json: str = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.profile, VariableRadiusFiber):
            raise TypeError("profile must be VariableRadiusFiber")
        m = _integer(self.radial_segments, "radial_segments", 3)
        result = sweep_tapered_tube(self.profile.points_mm, self.profile.node_radius_mm,
                                    radial_segments=m, initial_normal=self.initial_normal)
        for name in ("vertices_mm", "faces", "face_normals", "vertex_normals", "frames",
                     "ring_segment_length_mm", "side_face_ring_indices", "signed_volume_mm3", "surface_area_mm2"):
            object.__setattr__(self, name, result[name])
        object.__setattr__(self, "radial_segments", m)
        # Preserve the exact seed used by RMF. Re-projecting an already projected
        # normal can change a few floating-point bits on artifact round-trip.
        # An implicit deterministic axis is made explicit for reproducibility.
        seed = (np.eye(3)[np.argmin(np.abs(self.frames[0, :, 0]))]
                if self.initial_normal is None else self.initial_normal)
        object.__setattr__(self, "initial_normal", _readonly(seed))
        object.__setattr__(self, "_audit_json", _canonical(result["summary"]))

    @property
    def fiber_id(self):
        return self.profile.fiber_id

    @property
    def material_id(self):
        return self.profile.material_id

    def arrays(self):
        return {name: getattr(self, name) for name in (
            "vertices_mm", "faces", "face_normals", "vertex_normals", "frames",
            "ring_segment_length_mm", "side_face_ring_indices", "initial_normal")}

    @property
    def sha256(self):
        return _digest({"schema": MESH_SCHEMA, "profile_sha256": self.profile.sha256,
                        "radial_segments": self.radial_segments}, self.arrays())

    def summary(self):
        source_volume = float(self.profile.segment_volume_proxy_mm3.sum())
        return {**json.loads(self._audit_json), "mesh_sha256": self.sha256,
                "profile_sha256": self.profile.sha256, "fiber_id": self.fiber_id,
                "yarn_id": self.profile.yarn_id, "ply_id": self.profile.ply_id,
                "material_id": self.material_id, "family": self.profile.family,
                "source_cylinder_volume_proxy_mm3": source_volume,
                "mesh_to_source_proxy_relative_volume_difference": self.signed_volume_mm3/source_volume-1,
                "profile_reconstruction": self.profile.summary()}


def build_tapered_tube(profile, *, radial_segments=16, initial_normal=None):
    return TaperedTubeMesh(profile, radial_segments, initial_normal)


def _profile_from_arrays(metadata, arrays):
    d = dict(metadata)
    if d.pop("schema", None) != PROFILE_SCHEMA or d.pop("reconstruction_rule", None) != PROFILE_RULE:
        raise ValueError("unsupported profile schema or reconstruction rule")
    sources = {key: arrays[key] for key in ("points_mm", "material_coordinates_mm",
               "parent_material_coordinates_mm", "segment_radius_mm")}
    return VariableRadiusFiber(**sources, **d)


def _same_arrays(actual, expected, context):
    if set(actual) != set(expected):
        raise ValueError(f"{context}: array keys disagree with schema")
    for key, value in expected.items():
        a = np.asarray(actual[key])
        if a.dtype.kind == "O" or a.shape != value.shape or not np.array_equal(a, value):
            raise ValueError(f"{context}: saved {key} disagrees with recomputed geometry")


def _save_pair(directory, stem, arrays, payload):
    output = Path(directory)
    npz_path, json_path = output/(stem+".npz"), output/(stem+".json")
    if npz_path.exists() or json_path.exists():
        raise FileExistsError("existing geometry artifacts are never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, **arrays)
    final = {**payload, "array_file": npz_path.name,
             "array_file_sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest()}
    json_path.write_text(json.dumps(final, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return {"json": json_path, "npz": npz_path}


def _read_pair(directory, stem):
    folder = Path(directory)
    manifest = json.loads((folder/(stem+".json")).read_text(encoding="utf-8"))
    if manifest.get("array_file") != stem+".npz":
        raise ValueError("unexpected array file; path redirection is not permitted")
    raw = folder/(stem+".npz")
    if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest.get("array_file_sha256"):
        raise ValueError("NPZ byte checksum mismatch")
    with np.load(raw, allow_pickle=False) as stored:
        arrays = {key: stored[key] for key in stored.files}
    return manifest, arrays


def save_variable_radius_profiles(output_directory, profiles):
    profiles = tuple(profiles)
    if (not profiles or any(not isinstance(p, VariableRadiusFiber) for p in profiles)
            or len({p.fiber_id for p in profiles}) != len(profiles)):
        raise ValueError("a nonempty collection of uniquely identified profiles is required")
    arrays, entries = {}, []
    for i, profile in enumerate(profiles):
        prefix = f"fiber_{i:05d}"
        arrays.update({prefix+"/"+key: value for key, value in profile.arrays().items()})
        entries.append({"array_prefix": prefix, "metadata": profile.metadata(),
                        "profile_sha256": profile.sha256, "summary": profile.summary()})
    return _save_pair(output_directory, "variable_radius_profiles", arrays,
                       {"schema": PROFILE_SCHEMA, "length_unit": "mm", "fibers": entries})


def load_variable_radius_profiles(input_directory):
    payload, arrays = _read_pair(input_directory, "variable_radius_profiles")
    if payload.get("schema") != PROFILE_SCHEMA or payload.get("length_unit") != "mm":
        raise ValueError("unsupported profile collection schema/units")
    profiles, expected = [], {}
    for i, entry in enumerate(payload["fibers"]):
        prefix = f"fiber_{i:05d}"
        if entry.get("array_prefix") != prefix:
            raise ValueError("array layout must retain the original ordered fiber prefixes")
        local = {key[len(prefix)+1:]: value for key, value in arrays.items() if key.startswith(prefix+"/")}
        profile = _profile_from_arrays(entry["metadata"], local)
        if entry.get("profile_sha256") != profile.sha256 or entry.get("summary") != profile.summary():
            raise ValueError("profile semantic digest or derived summary mismatch")
        _same_arrays(local, profile.arrays(), "profile")
        expected.update({prefix+"/"+key: value for key, value in profile.arrays().items()})
        profiles.append(profile)
    if not profiles or len({p.fiber_id for p in profiles}) != len(profiles):
        raise ValueError("empty/duplicate profile collection")
    _same_arrays(arrays, expected, "profile collection")
    return tuple(profiles)


def save_tapered_tube(output_directory, mesh):
    if not isinstance(mesh, TaperedTubeMesh):
        raise TypeError("mesh must be TaperedTubeMesh")
    arrays = {"profile/"+key: value for key, value in mesh.profile.arrays().items()}
    arrays.update({"mesh/"+key: value for key, value in mesh.arrays().items()})
    return _save_pair(output_directory, "tapered_tube", arrays,
                       {"schema": MESH_SCHEMA, "length_unit": "mm", "radial_segments": mesh.radial_segments,
                        "profile_metadata": mesh.profile.metadata(), "profile_sha256": mesh.profile.sha256,
                        "mesh_sha256": mesh.sha256, "summary": mesh.summary()})


def load_tapered_tube(input_directory):
    payload, arrays = _read_pair(input_directory, "tapered_tube")
    if payload.get("schema") != MESH_SCHEMA or payload.get("length_unit") != "mm":
        raise ValueError("unsupported tube schema/units")
    profile_arrays = {key[8:]: value for key, value in arrays.items() if key.startswith("profile/")}
    profile = _profile_from_arrays(payload["profile_metadata"], profile_arrays)
    _same_arrays(profile_arrays, profile.arrays(), "mesh source profile")
    mesh = build_tapered_tube(profile, radial_segments=payload["radial_segments"],
                              initial_normal=arrays["mesh/initial_normal"])
    expected = {"profile/"+key: value for key, value in profile.arrays().items()}
    expected.update({"mesh/"+key: value for key, value in mesh.arrays().items()})
    _same_arrays(arrays, expected, "tube mesh")
    if (payload.get("profile_sha256") != profile.sha256 or payload.get("mesh_sha256") != mesh.sha256
            or payload.get("summary") != mesh.summary()):
        raise ValueError("tube semantic digest or derived summary mismatch")
    return mesh
