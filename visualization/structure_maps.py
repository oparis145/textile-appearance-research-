"""Deterministic geometric maps of textile hierarchy surfaces.

This is a visualization adapter, not a scattering/material model. Ply envelopes
are explicitly identified presentation proxies. Frozen textile_sim modules are
consumed without changing their data or optical contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import MappingProxyType
import zipfile

import numpy as np

from textile_sim.hierarchy import HierarchyGeometry, arclength_mm
from textile_sim.variable_radius import sweep_tapered_tube
from textile_sim.render import get_mitsuba


SURFACE_SCHEMA = "textile.structure_surface/5.1"
MAP_SCHEMA = "textile.structure_maps/5.1"
VECTOR_FIELDS = ("world_normal", "world_smooth_normal", "world_tangent", "position_mm")
FLOAT_FIELDS = VECTOR_FIELDS + ("height_mm", "ray_parameter_mm", "ray_distance_mm")
INDEX_FIELDS = ("object_index", "fiber_index", "ply_index", "yarn_index",
                "material_index", "family_index", "primitive_index")
ID_KINDS = ("fiber", "ply", "yarn", "material", "family")


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=_json_default)


def _readonly(value, dtype=None):
    a = np.ascontiguousarray(value, dtype=dtype)
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


def _array_hash(value):
    a = np.ascontiguousarray(value)
    h = hashlib.sha256(_canonical({"shape": a.shape, "dtype": a.dtype.str}).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _unit_rows(value, name, count=None):
    a = np.asarray(value, dtype=np.float64)
    if a.shape == (3,) and count is not None:
        a = np.broadcast_to(a, (count, 3))
    if a.ndim != 2 or a.shape[1] != 3 or (count is not None and len(a) != count) or not np.isfinite(a).all():
        raise ValueError(f"{name} must contain finite three-vectors")
    norm = np.linalg.norm(a, axis=1)
    if np.any(norm <= 0):
        raise ValueError(f"{name} contains a zero vector")
    return a/norm[:, None]


def _source_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = (Path(__file__).resolve(), root/"textile_sim/hierarchy.py",
             root/"textile_sim/variable_radius.py", root/"textile_sim/render.py")
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def hierarchy_geometry_sha256(geometry):
    """Hash actual source arrays, all IDs, source spec and declared metadata."""
    if not isinstance(geometry, HierarchyGeometry):
        raise TypeError("HierarchyGeometry required")
    h = hashlib.sha256(_canonical({"spec": geometry.spec, "metadata": geometry.metadata,
                                  "curve_basis": geometry.curve_basis}).encode())
    for f in geometry.fiber_records:
        h.update(_canonical(f.provenance()).encode())
        h.update(_array_hash(f.points_mm).encode())
        h.update(_array_hash(f.radii_mm).encode())
    for name, curves in (("plies", geometry.plies), ("yarns", geometry.yarns)):
        h.update(name.encode())
        for key in sorted(curves):
            h.update(key.encode()); h.update(_array_hash(curves[key]).encode())
    return h.hexdigest()


def _vertex_normals(vertices, faces, side_count=None):
    """Area-weighted display normals; cap creases are not used to smooth sides."""
    result = np.zeros((len(vertices), 3), dtype=np.float64)
    f = faces if side_count is None else faces[:side_count]
    for start in range(0, len(f), 65536):
        indices = f[start:start+65536]
        triangles = np.asarray(vertices[indices], dtype=np.float64)
        cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        for corner in range(3):
            np.add.at(result, indices[:, corner], cross)
    good = np.linalg.norm(result, axis=1) > 0
    result[good] /= np.linalg.norm(result[good], axis=1)[:, None]
    return result, good


@dataclass(frozen=True, eq=False)
class StructureSurface:
    vertices_mm: np.ndarray
    faces: np.ndarray
    vertex_tangent: np.ndarray
    vertex_smooth_normal: np.ndarray
    face_object_index: np.ndarray
    face_is_cap: np.ndarray
    objects_json: str
    metadata_json: str
    _sha256: str = field(init=False, repr=False)
    _ray_scene: object = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self):
        original = np.asarray(self.vertices_mm, dtype=np.float64)
        if original.ndim != 2 or original.shape[1] != 3 or len(original) < 3 or not np.isfinite(original).all():
            raise ValueError("vertices_mm must be finite Nx3")
        raw_faces = np.asarray(self.faces)
        if raw_faces.ndim != 2 or raw_faces.shape[1] != 3 or not len(raw_faces) or raw_faces.dtype.kind not in "iu":
            raise ValueError("faces must be nonempty integer Mx3")
        if raw_faces.min() < 0 or raw_faces.max() >= len(original):
            raise ValueError("face vertex index out of range")
        v = np.asarray(original, dtype=np.float32)
        if not np.isfinite(v).all():
            raise ValueError("float32 vertices overflow")
        f = np.asarray(raw_faces, dtype=np.uint32)
        for start in range(0, len(f), 65536):
            tri = v[f[start:start+65536]].astype(np.float64)
            area2 = np.linalg.norm(np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]), axis=1)
            if np.any(area2 <= 0) or not np.isfinite(area2).all():
                raise ValueError("degenerate triangle after float32 conversion")
        objects = json.loads(self.objects_json)
        meta = json.loads(self.metadata_json)
        if not isinstance(objects, list) or not objects or not all(isinstance(o, dict) for o in objects):
            raise ValueError("nonempty object metadata required")
        keys = [o.get("object_id") for o in objects]
        if any(not isinstance(k, str) or not k for k in keys) or len(set(keys)) != len(keys):
            raise ValueError("object IDs must be unique nonempty strings")
        if not isinstance(meta, dict) or meta.get("length_unit", "mm") != "mm":
            raise ValueError("surface metadata requires mm units")
        owner = np.asarray(self.face_object_index)
        caps = np.asarray(self.face_is_cap)
        if owner.shape != (len(f),) or owner.dtype.kind not in "iu" or owner.min() < 0 or owner.max() >= len(objects):
            raise ValueError("one valid object index is required per face")
        if caps.shape != (len(f),) or caps.dtype.kind != "b":
            raise ValueError("face_is_cap must be a boolean per face")
        tangent = _unit_rows(self.vertex_tangent, "vertex_tangent", len(v))
        smooth = _unit_rows(self.vertex_smooth_normal, "vertex_smooth_normal", len(v))
        values = {"vertices_mm": (v, np.float32), "faces": (f, np.uint32),
                  "vertex_tangent": (tangent, np.float32), "vertex_smooth_normal": (smooth, np.float32),
                  "face_object_index": (owner, np.int32), "face_is_cap": (caps, bool)}
        for key, (value, dtype) in values.items():
            object.__setattr__(self, key, _readonly(value, dtype))
        meta.update({"schema_version": SURFACE_SCHEMA, "length_unit": "mm",
                     "vertex_count": len(v), "triangle_count": len(f),
                     "max_float32_vertex_displacement_mm": max(float(np.max(np.linalg.norm(v.astype(float)-original, axis=1))), float(meta.get("source_max_float32_vertex_displacement_mm", 0))),
                     "triangle_geometric_normals_are_primary": True,
                     "smooth_normals_are_display_interpolants": True,
                     "self_intersection_certified_absent": False})
        object.__setattr__(self, "objects_json", _canonical(objects))
        object.__setattr__(self, "metadata_json", _canonical(meta))
        h = hashlib.sha256((self.objects_json+self.metadata_json).encode())
        for key in values:
            h.update(key.encode()); h.update(_array_hash(getattr(self, key)).encode())
        object.__setattr__(self, "_sha256", h.hexdigest())

    @property
    def sha256(self):
        return self._sha256

    @property
    def objects(self):
        return json.loads(self.objects_json)

    @property
    def metadata(self):
        return json.loads(self.metadata_json)

    @property
    def bounds_mm(self):
        return np.stack((self.vertices_mm.min(axis=0), self.vertices_mm.max(axis=0))).astype(float)


def surface_from_arrays(vertices_mm, faces, *, vertex_tangent, vertex_smooth_normal=None,
                        face_object_index=None, objects=None, metadata=None, face_is_cap=None):
    """Generic open/closed triangle surface for analytical geometry oracles."""
    v = np.asarray(vertices_mm, dtype=float); f = np.asarray(faces)
    if vertex_smooth_normal is None:
        if f.dtype.kind not in "iu" or f.ndim != 2 or f.shape[1:] != (3,) or not len(f):
            raise ValueError("integer triangle faces required")
        if f.min() < 0 or f.max() >= len(v):
            raise ValueError("face vertex index out of range")
        vertex_smooth_normal, good = _vertex_normals(v, f)
        if not np.all(good):
            raise ValueError("unused vertices or cancelling display normals; supply explicit normals")
    objects = [{"object_id": "custom:0", "level": "custom"}] if objects is None else objects
    owner = np.zeros(len(f), dtype=np.int32) if face_object_index is None else face_object_index
    caps = np.zeros(len(f), dtype=bool) if face_is_cap is None else face_is_cap
    return StructureSurface(v, f, vertex_tangent, vertex_smooth_normal, owner, caps,
                            _canonical(objects), _canonical({} if metadata is None else metadata))


def _tube_arrays(points, radii, radial_segments, initial_normal):
    tube = sweep_tapered_tube(points, radii, radial_segments=radial_segments, initial_normal=initial_normal)
    m, count = radial_segments, len(points)
    tangent = np.vstack((np.repeat(tube["frames"][:, :, 0], m, axis=0),
                         tube["frames"][0, :, 0], tube["frames"][-1, :, 0]))
    side_count = 2*m*(count-1)
    smooth, good = _vertex_normals(tube["vertices_mm"], tube["faces"], side_count)
    if not np.all(good[:-2]):
        raise ValueError("tube has undefined side display normals")
    smooth[-2] = -tangent[-2]; smooth[-1] = tangent[-1]
    caps = np.arange(len(tube["faces"])) >= side_count
    return tube["vertices_mm"], tube["faces"], tangent, smooth, caps, tube["summary"]


def build_structure_surface(geometry, *, level="ply_envelope", radial_segments=64,
                            envelope_scale=1.0, initial_normal=None, max_triangles=20_000_000):
    """Build traceable ply presentation tubes or explicit circular fiber tubes.

    Parent ply correspondence must share the stored node indices. Radius is a
    node-ball envelope proxy, not a claim that the swept solid encloses every
    curved/oblique child surface or preserves its material volume.
    """
    if not isinstance(geometry, HierarchyGeometry) or geometry.curve_basis != "polyline":
        raise TypeError("explicit polyline HierarchyGeometry required")
    if geometry.metadata.get("length_unit", "mm") != "mm":
        raise ValueError("hierarchy length units must be mm")
    if level not in ("ply_envelope", "explicit_fiber"):
        raise ValueError("level must be ply_envelope or explicit_fiber")
    n = _integer(radial_segments, "radial_segments", 3)
    budget = _integer(max_triangles, "max_triangles")
    scale = float(envelope_scale)
    if not np.isfinite(scale) or scale <= 0 or isinstance(envelope_scale, (bool, np.bool_)):
        raise ValueError("positive finite envelope_scale required")
    if level == "explicit_fiber" and scale != 1:
        raise ValueError("envelope_scale cannot change explicit fiber geometry")
    source_hash = hierarchy_geometry_sha256(geometry)
    code_hash = _source_hashes()
    groups = {}
    for f in geometry.fiber_records:
        if f.cross_section != "circle":
            raise ValueError("only circular fiber sections supported")
        groups.setdefault(f.ply_id, []).append(f)
    records = []
    if level == "explicit_fiber":
        for f in geometry.fiber_records:
            objects = {"object_id": f.fiber_id, "level": level, **f.provenance(),
                       "child_fiber_ids": [f.fiber_id], "material_ids": [f.material_id],
                       "radius_rule": "source node radius; unchanged",
                       "presentation_proxy": False}
            records.append((f.points_mm, f.radii_mm, objects))
    else:
        for ply_id in sorted(geometry.plies):
            children = groups.get(ply_id, [])
            if not children:
                raise ValueError("cannot infer radius for an empty ply")
            points = np.asarray(geometry.plies[ply_id], dtype=float)
            arclength_mm(points)
            if any(len(f.points_mm) != len(points) for f in children):
                raise ValueError("ply envelopes require shared stored parent/fiber node indices")
            if len({f.yarn_id for f in children}) != 1 or len({f.family for f in children}) != 1:
                raise ValueError("ply children must have one yarn and one family")
            radii = np.max([np.linalg.norm(f.points_mm-points, axis=1)+f.radii_mm for f in children], axis=0)*scale
            materials = sorted({f.material_id for f in children})
            fractions = np.sum([f.radii_mm**2 for f in children], axis=0)/radii**2
            obj = {"object_id": ply_id, "level": level, "ply_id": ply_id,
                   "yarn_id": children[0].yarn_id, "family": children[0].family,
                   "fiber_id": None, "material_id": materials[0] if len(materials) == 1 else None,
                   "material_ids": materials, "child_fiber_ids": [f.fiber_id for f in children],
                   "child_fiber_provenance": [f.provenance() for f in children],
                   "presentation_proxy": True, "solid_proxy_fills_interfiber_voids": True,
                   "contains_all_child_surfaces_certified": False,
                   "radius_rule": "envelope_scale * max_child(node center distance + child radius)",
                   "radius_min_mm": float(radii.min()), "radius_max_mm": float(radii.max()),
                   "nominal_circle_area_fraction_min": float(fractions.min()),
                   "nominal_circle_area_fraction_max": float(fractions.max())}
            records.append((points, radii, obj))
    total_faces = sum(2*n*len(points) for points, _, _ in records)
    if total_faces > budget:
        raise ValueError(f"triangle budget exceeded: {total_faces} > {budget}")
    blocks = {key: [] for key in ("v", "f", "t", "s", "o", "c")}
    objects, summaries, offset = [], [], 0
    max_quantization = 0.
    for object_index, (points, radii, obj) in enumerate(records):
        v, f, tangent, smooth, caps, summary = _tube_arrays(points, radii, n, initial_normal)
        quantized = v.astype(np.float32)
        max_quantization = max(max_quantization, float(np.max(np.linalg.norm(quantized.astype(float)-v, axis=1))))
        blocks["v"].append(quantized)
        blocks["f"].append((f+offset).astype(np.uint32))
        blocks["t"].append(tangent.astype(np.float32)); blocks["s"].append(smooth.astype(np.float32))
        blocks["o"].append(np.full(len(f), object_index, dtype=np.int32)); blocks["c"].append(caps)
        offset += len(v); objects.append(obj)
        summaries.append({"object_id": obj["object_id"], "summary": summary})
    if source_hash != hierarchy_geometry_sha256(geometry) or code_hash != _source_hashes():
        raise RuntimeError("source geometry or source code changed during surface construction")
    tables = {"fiber": sorted(f.fiber_id for f in geometry.fiber_records),
              "ply": sorted(geometry.plies), "yarn": sorted(geometry.yarns),
              "material": sorted(geometry.material_ids),
              "family": sorted({f.family for f in geometry.fiber_records})}
    meta = {"level": level, "presentation_proxy": level == "ply_envelope",
            "source_geometry_sha256": source_hash, "source_spec": geometry.spec,
            "source_summary": geometry.summary(), "source_files_sha256": code_hash,
            "source_unchanged_during_construction": True, "id_tables": tables,
            "source_max_float32_vertex_displacement_mm": max_quantization,
            "radial_segments": n, "envelope_scale": scale,
            "initial_normal": None if initial_normal is None else np.asarray(initial_normal).tolist(),
            "centerline_orientation": "ply centerline" if level == "ply_envelope" else "fiber centerline",
            "orientation_is_surface_bsdf_tangent": False,
            "smooth_normal_rule": "area-weighted side vertex normals; cap hits retain geometric normal",
            "tube_summaries": summaries,
            "scope": "synthetic geometric surface visualization; no lighting, measured material, scattering or contact certification"}
    return surface_from_arrays(np.concatenate(blocks["v"]), np.concatenate(blocks["f"]),
        vertex_tangent=np.concatenate(blocks["t"]), vertex_smooth_normal=np.concatenate(blocks["s"]),
        face_object_index=np.concatenate(blocks["o"]), face_is_cap=np.concatenate(blocks["c"]),
        objects=objects, metadata=meta)


@dataclass(frozen=True)
class OrthographicCamera:
    origin_mm: np.ndarray
    right: np.ndarray
    up: np.ndarray
    view_direction: np.ndarray
    width_mm: float
    height_mm: float
    resolution_hw: tuple[int, int] = (512, 512)

    def __post_init__(self):
        origin = np.asarray(self.origin_mm, dtype=float)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError("camera origin must be finite xyz in mm")
        axes = _unit_rows(np.stack((self.right, self.up, self.view_direction)), "camera axes", 3)
        if not np.allclose(axes@axes.T, np.eye(3), atol=1e-10, rtol=0) or not np.allclose(np.cross(axes[0], axes[1]), -axes[2], atol=1e-10, rtol=0):
            raise ValueError("orthonormal right/up/view axes with cross(right,up)=-view required")
        sizes = np.asarray([self.width_mm, self.height_mm], dtype=float)
        if not np.isfinite(sizes).all() or np.any(sizes <= 0):
            raise ValueError("positive finite physical camera dimensions required")
        if len(self.resolution_hw) != 2:
            raise ValueError("resolution_hw is (height,width)")
        resolution = tuple(_integer(v, "resolution") for v in self.resolution_hw)
        object.__setattr__(self, "origin_mm", _readonly(origin))
        for key, axis in zip(("right", "up", "view_direction"), axes):
            object.__setattr__(self, key, _readonly(axis))
        object.__setattr__(self, "width_mm", float(sizes[0])); object.__setattr__(self, "height_mm", float(sizes[1]))
        object.__setattr__(self, "resolution_hw", resolution)

    def to_dict(self):
        return {"type": "orthographic", "origin_mm": self.origin_mm.tolist(), "right": self.right.tolist(),
                "up": self.up.tolist(), "view_direction": self.view_direction.tolist(),
                "width_mm": self.width_mm, "height_mm": self.height_mm,
                "resolution_hw": list(self.resolution_hw),
                "pixel_size_mm": [self.height_mm/self.resolution_hw[0], self.width_mm/self.resolution_hw[1]],
                "pixel_rule": "origin + ((col+.5)/W-.5)*width*right + (.5-(row+.5)/H)*height*up",
                "row_column_convention": "row 0 toward +up; column 0 toward -right",
                "backend_origin_rule": "float64 pixel formula cast to float32 before ray query",
                "backend_view_direction_float32": self.view_direction.astype(np.float32).tolist(),
                "world_height_definition": "z coordinate of nearest actual triangle hit; not ray distance"}

    @property
    def sha256(self):
        return hashlib.sha256(_canonical(self.to_dict()).encode()).hexdigest()


def make_topdown_camera(bounds_mm, *, resolution=512, extent_xy_mm=None, padding_fraction=.02):
    bounds = np.asarray(bounds_mm, dtype=float)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[1] < bounds[0]):
        raise ValueError("bounds_mm must be finite ordered 2x3")
    if isinstance(resolution, (int, np.integer)) and not isinstance(resolution, (bool, np.bool_)):
        resolution = (_integer(resolution, "resolution"),)*2
    else:
        resolution = tuple(resolution)
    padding = float(padding_fraction)
    if not np.isfinite(padding) or padding < 0:
        raise ValueError("padding_fraction must be finite nonnegative")
    if extent_xy_mm is None:
        lower, upper = bounds[0, :2], bounds[1, :2]
        margin = (upper-lower)*padding
        extent = (lower[0]-margin[0], upper[0]+margin[0], lower[1]-margin[1], upper[1]+margin[1])
    else:
        extent = np.asarray(extent_xy_mm, dtype=float)
        if extent.shape != (4,) or not np.isfinite(extent).all():
            raise ValueError("extent_xy_mm is (xmin,xmax,ymin,ymax)")
    xmin, xmax, ymin, ymax = extent
    width, height = xmax-xmin, ymax-ymin
    if width <= 0 or height <= 0:
        raise ValueError("positive camera extent required")
    origin = [(xmin+xmax)/2, (ymin+ymax)/2, bounds[1, 2]+max(width, height, 1e-3)]
    return OrthographicCamera(origin, [1, 0, 0], [0, 1, 0], [0, 0, -1], width, height, resolution)


def _prepare_scene(surface):
    if surface._ray_scene is not None:
        return surface._ray_scene
    mi = get_mitsuba()
    mesh = mi.Mesh("structure_surface", len(surface.vertices_mm), len(surface.faces), mi.Properties(),
                   has_vertex_normals=False, has_vertex_texcoords=False)
    params = mi.traverse(mesh)
    params["vertex_positions"] = mi.Float(surface.vertices_mm.ravel())
    params["faces"] = mi.UInt(surface.faces.ravel())
    params.update()
    scene = mi.load_dict({"type": "scene", "surface": mesh})
    object.__setattr__(surface, "_ray_scene", scene)
    return scene


def _id_tables(surface):
    objects = surface.objects
    declared = surface.metadata.get("id_tables", {})
    tables, object_maps = {}, {}
    for kind in ID_KINDS:
        key = kind if kind == "family" else kind+"_id"
        values = list(declared.get(kind, sorted({o[key] for o in objects if o.get(key) is not None})))
        if len(set(values)) != len(values) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError("ID lookup must contain unique nonempty strings")
        lookup = {name: i for i, name in enumerate(values)}
        ids = []
        for obj in objects:
            value = obj.get(key)
            if value is not None and value not in lookup:
                raise ValueError("object ID missing from declared lookup")
            ids.append(-1 if value is None else lookup[value])
        tables[kind] = values; object_maps[kind] = np.asarray(ids, dtype=np.int32)
    tables["object"] = [obj["object_id"] for obj in objects]
    return tables, object_maps


def _barycentric(point, triangles):
    e0 = triangles[:, 1]-triangles[:, 0]; e1 = triangles[:, 2]-triangles[:, 0]
    v = point-triangles[:, 0]
    d00 = np.einsum("ij,ij->i", e0, e0); d01 = np.einsum("ij,ij->i", e0, e1)
    d11 = np.einsum("ij,ij->i", e1, e1)
    d20 = np.einsum("ij,ij->i", v, e0); d21 = np.einsum("ij,ij->i", v, e1)
    denom = d00*d11-d01*d01
    if np.any(denom <= 0):
        raise RuntimeError("degenerate hit triangle")
    b1 = (d11*d20-d01*d21)/denom; b2 = (d00*d21-d01*d20)/denom
    b = np.column_stack((1-b1-b2, b1, b2))
    excursion = float(np.max(np.maximum(-b, b-1), initial=0))
    # Float32 p and triangle coordinates differ by a few ulp at edges. Never
    # use shading UVs as a silent substitute for actual triangle barycentrics.
    if excursion > .002:
        raise RuntimeError(f"hit barycentric excursion too large: {excursion}")
    b = np.clip(b, 0, 1); b /= b.sum(axis=1)[:, None]
    return b, excursion


def _sample_grid(surface, camera, height, width, chunk_size):
    mi = get_mitsuba(); scene = _prepare_scene(surface)
    count = height*width
    arrays = {key: np.full((count, 3) if key in VECTOR_FIELDS else count, np.nan, dtype=np.float32)
              for key in FLOAT_FIELDS}
    arrays.update({key: np.full(count, -1, dtype=np.int32) for key in INDEX_FIELDS})
    arrays["valid_mask"] = np.zeros(count, dtype=bool)
    _, mappings = _id_tables(surface)
    direction = camera.view_direction.astype(np.float32)
    direction_length = float(np.linalg.norm(direction.astype(float)))
    max_excursion = 0.
    for start in range(0, count, chunk_size):
        stop = min(count, start+chunk_size)
        index = np.arange(start, stop)
        x = ((index % width+.5)/width-.5)*camera.width_mm
        y = (.5-(index//width+.5)/height)*camera.height_mm
        origins = (camera.origin_mm+x[:, None]*camera.right+y[:, None]*camera.up).astype(np.float32)
        if not np.isfinite(origins).all():
            raise ValueError("camera ray origin overflows float32")
        ray = mi.Ray3f(mi.Point3f(origins.T), mi.Vector3f(direction))
        hit = scene.ray_intersect(ray)
        valid = np.asarray(hit.is_valid()).reshape(-1).astype(bool)
        if not valid.any():
            continue
        out = index[valid]
        prim = np.asarray(hit.prim_index).reshape(-1)[valid].astype(np.int64)
        if np.any(prim < 0) or np.any(prim >= len(surface.faces)):
            raise RuntimeError("renderer returned invalid primitive index")
        positions = np.asarray(hit.p).T[valid].astype(np.float64)
        normals = _unit_rows(np.asarray(hit.n).T[valid], "hit normal")
        parameter = np.asarray(hit.t).reshape(-1)[valid]
        faces = surface.faces[prim]
        triangles = surface.vertices_mm[faces].astype(np.float64)
        bary, excursion = _barycentric(positions, triangles)
        max_excursion = max(max_excursion, excursion)
        tangent = _unit_rows(np.sum(surface.vertex_tangent[faces]*bary[:, :, None], axis=1), "interpolated centerline tangent")
        smooth = _unit_rows(np.sum(surface.vertex_smooth_normal[faces]*bary[:, :, None], axis=1), "interpolated display normal")
        cap = surface.face_is_cap[prim]
        smooth[cap] = normals[cap]
        owners = surface.face_object_index[prim]
        arrays["valid_mask"][out] = True
        for key, value in (("world_normal", normals), ("world_smooth_normal", smooth),
                           ("world_tangent", tangent), ("position_mm", positions),
                           ("height_mm", positions[:, 2]), ("ray_parameter_mm", parameter),
                           ("ray_distance_mm", parameter*direction_length),
                           ("object_index", owners), ("primitive_index", prim)):
            arrays[key][out] = value
        for kind, mapping in mappings.items():
            arrays[kind+"_index"][out] = mapping[owners]
    return {key: value.reshape((height, width, 3) if key in VECTOR_FIELDS else (height, width))
            for key, value in arrays.items()}, max_excursion


@dataclass(frozen=True, init=False)
class StructureMapResult:
    arrays: object
    supersampled: object
    _metadata_json: str

    def __init__(self, arrays, supersampled, metadata):
        object.__setattr__(self, "arrays", MappingProxyType(dict(arrays)))
        object.__setattr__(self, "supersampled", MappingProxyType(dict(supersampled)))
        object.__setattr__(self, "_metadata_json", _canonical(metadata))

    @property
    def metadata(self):
        return json.loads(self._metadata_json)


def trace_structure_maps(surface, camera, *, supersample=2, chunk_size=131072):
    """Nearest geometric hit at pixel centers, plus separate deterministic AA.

    Supersampled colors may be box-filtered for display. Center hit normals,
    physical heights and categorical IDs must never be replaced by AA mixtures.
    """
    if not isinstance(surface, StructureSurface) or not isinstance(camera, OrthographicCamera):
        raise TypeError("StructureSurface and OrthographicCamera required")
    factor = _integer(supersample, "supersample")
    chunk = _integer(chunk_size, "chunk_size")
    h, w = camera.resolution_hw
    if h*w*factor*factor > 16_777_216:
        raise ValueError("supersampling ray grid exceeds 16,777,216 samples")
    code_hash = _source_hashes(); start = time.perf_counter()
    center, excursion = _sample_grid(surface, camera, h, w, chunk)
    if factor == 1:
        samples = center
    else:
        samples, high_excursion = _sample_grid(surface, camera, h*factor, w*factor, chunk)
        excursion = max(excursion, high_excursion)
    coverage = samples["valid_mask"].reshape(h, factor, w, factor).mean(axis=(1, 3)).astype(np.float32)
    center = {key: _readonly(value) for key, value in center.items()}
    samples = center if factor == 1 else {key: _readonly(value) for key, value in samples.items()}
    center = {**center, "coverage": _readonly(coverage)}
    if code_hash != _source_hashes():
        raise RuntimeError("source files changed during map tracing")
    tables, _ = _id_tables(surface)
    mi = get_mitsuba()
    metadata = {"schema_version": MAP_SCHEMA, "length_unit": "mm", "vector_frame": "world_xyz",
        "surface": {**surface.metadata, "surface_sha256": surface.sha256},
        "objects": surface.objects, "id_tables": tables,
        "camera": camera.to_dict(), "camera_sha256": camera.sha256,
        "runtime": {"mitsuba": mi.__version__, "variant": mi.variant(), "geometry_dtype": "float32"},
        "source_files_sha256": code_hash, "source_hashes_unchanged_during_trace": True,
        "actual_lighting_render_calls": 0,
        "actual_primary_ray_queries": h*w*(1 if factor == 1 else 1+factor*factor),
        "center_hit_count": int(center["valid_mask"].sum()),
        "supersampled_hit_count": int(samples["valid_mask"].sum()),
        "supersample": factor, "supersampled_resolution_hw": [h*factor, w*factor],
        "supersampling_rule": "deterministic uniform subpixel centers; no random seed or Monte Carlo replicates",
        "physical_map_rule": "one pixel-center nearest hit; floating misses NaN; missing or inapplicable IDs -1",
        "coverage_rule": "fraction of SxS subpixel centers that hit any surface; not alpha inferred from lighting",
        "world_normal_rule": "actual unflipped triangle geometric normal from ray_intersect, normalized",
        "world_smooth_normal_rule": surface.metadata.get("smooth_normal_rule", "normalized barycentric vertex normal; display field"),
        "world_tangent_rule": "normalized barycentric directed centerline tangent; NOT projected surface BSDF tangent",
        "height_rule": "world z in mm at same nearest triangle hit as normal and IDs",
        "max_barycentric_roundoff_excursion_before_clamp": excursion,
        "elapsed_seconds": time.perf_counter()-start,
        "scope": "geometric cartography; no lighting, scattering, actual material or paper-result replication"}
    return StructureMapResult(center, samples, metadata)


def _atomic_write(path, data):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix="."+path.name+".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_structure_maps(output_directory, result, *, include_supersampled=False):
    """Atomic nonpickle NPZ/JSON. Default stores physical center maps+coverage."""
    if not isinstance(result, StructureMapResult):
        raise TypeError("StructureMapResult required")
    output = Path(output_directory)
    raw = output/"structure_maps.npz"; manifest = output/"structure_maps.json"
    if raw.exists() or manifest.exists():
        raise FileExistsError("structure map output already exists")
    output.mkdir(parents=True, exist_ok=True)
    arrays = dict(result.arrays)
    if include_supersampled:
        arrays.update({"sample__"+key: value for key, value in result.supersampled.items()})
    if any(np.asarray(a).dtype.hasobject for a in arrays.values()):
        raise ValueError("object arrays are forbidden")
    buffer = io.BytesIO(); np.savez_compressed(buffer, **arrays); payload = buffer.getvalue()
    _atomic_write(raw, payload)
    with zipfile.ZipFile(raw) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("saved map NPZ CRC failed")
    with np.load(raw, allow_pickle=False) as restored:
        if set(restored.files) != set(arrays) or any(_array_hash(restored[k]) != _array_hash(arrays[k]) for k in arrays):
            raise RuntimeError("saved map NPZ array readback mismatch")
    metadata = {**result.metadata, "raw_file": raw.name,
                "raw_file_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "saved_supersamples": bool(include_supersampled), "npz_crc_verified": True,
                "arrays": {key: {"shape": list(value.shape), "dtype": value.dtype.str,
                                  "sha256": _array_hash(value)} for key, value in arrays.items()}}
    _atomic_write(manifest, (_canonical(metadata)+"\n").encode())
    return {"npz": raw, "json": manifest}


def load_structure_maps(input_directory):
    source = Path(input_directory)
    metadata = json.loads((source/"structure_maps.json").read_text())
    if metadata.get("schema_version") != MAP_SCHEMA or metadata.get("length_unit") != "mm":
        raise ValueError("unsupported structure-map schema/units")
    if metadata.get("raw_file") != "structure_maps.npz":
        raise ValueError("unexpected map NPZ filename")
    raw = source/"structure_maps.npz"
    if hashlib.sha256(raw.read_bytes()).hexdigest() != metadata.get("raw_file_sha256"):
        raise ValueError("map NPZ byte hash mismatch")
    with zipfile.ZipFile(raw) as archive:
        if archive.testzip() is not None:
            raise ValueError("map NPZ CRC failed")
    arrays, samples = {}, {}
    with np.load(raw, allow_pickle=False) as data:
        if set(data.files) != set(metadata["arrays"]):
            raise ValueError("map array key mismatch")
        for key in data.files:
            value = data[key]; spec = metadata["arrays"][key]
            if list(value.shape) != spec["shape"] or value.dtype.str != spec["dtype"] or _array_hash(value) != spec["sha256"]:
                raise ValueError("map array semantic hash mismatch")
            (samples if key.startswith("sample__") else arrays)[key.removeprefix("sample__")] = _readonly(value)
    return StructureMapResult(arrays, samples, metadata)
