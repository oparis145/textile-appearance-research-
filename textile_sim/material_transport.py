"""Lagrangian, framed kinematic transport of a sampled textile hierarchy.

All lengths are mm.  The reference fiber vertices are labelled once and then
carried through a prescribed yarn -> ply -> fiber map.  Material labels are NOT
new relaxed arclengths.  This is a no-slip kinematic *assumption*, not a solution
of fiber stress, contact, incompressibility, or material twist.  Explicit initial
yarn directors are essential: a centerline cannot determine rotation about its
own tangent.  See notes/material_transport_v4.md for equations and limitations.

The optional incompressible_segments mode conserves the sum of the disjoint
straight-cylinder segment volume proxies by storing one radius per segment.
It cannot be silently exported through the current constant-radius optical API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .hierarchy import (FiberCurve, HierarchyGeometry, arclength_mm,
                        rotation_minimizing_frames)

SCHEMA_VERSION = "textile.material_transport/4.0"
RADIUS_MODES = ("constant_reference", "incompressible_segments")


def _readonly(value):
    a = np.ascontiguousarray(value, dtype=np.float64)
    return np.frombuffer(a.tobytes(), dtype=np.float64).reshape(a.shape)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _points(value, name):
    p = np.asarray(value, dtype=float)
    try:
        s = arclength_mm(p)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: {exc}") from exc
    if not np.isfinite(s).all() or not np.isfinite(s[-1]):
        raise ValueError(f"{name}: nonfinite arclength")
    if np.linalg.norm(p[-1]-p[0]) <= 1e-12*s[-1]:
        raise ValueError(f"{name}: closed or near-closed parents require a holonomy convention")
    return _readonly(p), _readonly(s)


def _coordinates(value, count, name):
    s = np.asarray(value, dtype=float)
    if (s.shape != (count,) or not np.isfinite(s).all() or s[0] != 0
            or np.any(np.diff(s) <= 0)):
        raise ValueError(f"{name} must start at zero and increase strictly at every vertex")
    return _readonly(s)


def _unit(v, name):
    v = np.asarray(v, dtype=float)
    if v.shape != (3,) or not np.isfinite(v).all():
        raise ValueError(f"{name} must be a finite 3-vector")
    norm = float(np.linalg.norm(v))
    if not np.isfinite(norm) or norm <= 1e-14:
        raise ValueError(f"{name} has zero/ill-conditioned magnitude")
    return v/norm


def _exact_keys(mapping, expected, name):
    if not isinstance(mapping, Mapping) or set(mapping) != set(expected):
        raise ValueError(f"{name} must contain exactly the reference yarn IDs; no implicit family/index matching")


@dataclass(frozen=True)
class FramedCurve:
    """Open polyline sampled at explicit material-coordinate knots.

    Position interpolation is linear; orientation interpolation follows the
    shortest SO(3) geodesic between double-reflection RMF samples.  Tangents are
    sampled arclength derivatives, not an assertion that a polyline corner has
    a unique differential tangent.  Refinement therefore needs its own check.
    """
    points_mm: np.ndarray
    material_coordinates_mm: np.ndarray
    initial_normal: np.ndarray
    arclength_mm: np.ndarray = field(init=False)
    frames: np.ndarray = field(init=False)

    def __post_init__(self):
        p, arc = _points(self.points_mm, "framed parent")
        u = _coordinates(self.material_coordinates_mm, len(p), "parent material coordinates")
        director = _unit(self.initial_normal, "initial_normal")
        tangent, n1, n2 = rotation_minimizing_frames(p, initial_normal=director)
        matrices = np.stack((tangent, n1, n2), axis=-1)
        relative = np.einsum("nji,njk->nik", matrices[:-1], matrices[1:])
        angles = Rotation.from_matrix(relative).magnitude()
        if np.any(angles >= np.pi-1e-8):
            raise ValueError("adjacent frames have ambiguous half-turn interpolation; refine the parent")
        object.__setattr__(self, "points_mm", p)
        object.__setattr__(self, "material_coordinates_mm", u)
        object.__setattr__(self, "initial_normal", _readonly(n1[0]))
        object.__setattr__(self, "arclength_mm", arc)
        object.__setattr__(self, "frames", _readonly(matrices))

    def evaluate(self, coordinates_mm):
        q = np.asarray(coordinates_mm, dtype=float)
        if q.ndim != 1 or len(q) < 1 or not np.isfinite(q).all():
            raise ValueError("query material coordinates must be a finite vector")
        if np.any(q < self.material_coordinates_mm[0]) or np.any(q > self.material_coordinates_mm[-1]):
            raise ValueError("material-coordinate extrapolation is not permitted")
        p = np.column_stack([np.interp(q, self.material_coordinates_mm, self.points_mm[:, k])
                             for k in range(3)])
        if np.array_equal(q, self.material_coordinates_mm):
            return p, self.frames.copy()
        frames = Slerp(self.material_coordinates_mm, Rotation.from_matrix(self.frames.copy()))(q).as_matrix()
        return p, frames


def transport_framed_points(reference_parent: FramedCurve, deformed_parent: FramedCurve,
                            reference_points_mm, parent_material_coordinates_mm):
    """Carry fixed 3-component local offsets, including their axial component.

    x_d(u) = p_d(u) + B_d(u) B_r(u)^T [x_r(u)-p_r(u)].
    Keeping all components, rather than projecting into a new normal plane,
    makes the map invertible at the labelled samples and avoids erasing offsets.
    It does not establish global injectivity or exclude fiber intersections.
    """
    if not isinstance(reference_parent, FramedCurve) or not isinstance(deformed_parent, FramedCurve):
        raise TypeError("both parents must be FramedCurve")
    if reference_parent.material_coordinates_mm[-1] != deformed_parent.material_coordinates_mm[-1]:
        raise ValueError("parent endpoints must carry the same reference material labels")
    points = np.asarray(reference_points_mm, dtype=float)
    u = np.asarray(parent_material_coordinates_mm, dtype=float)
    if points.shape != (len(u), 3) or not np.isfinite(points).all():
        raise ValueError("one finite point is required for every parent material label")
    reference_centers, reference_frames = reference_parent.evaluate(u)
    deformed_centers, deformed_frames = deformed_parent.evaluate(u)
    local = np.einsum("nji,nj->ni", reference_frames, points-reference_centers)
    result = deformed_centers+np.einsum("nij,nj->ni", deformed_frames, local)
    if not np.isfinite(result).all():
        raise ValueError("transport generated nonfinite points")
    return result


def _minimal_alignment(a, b):
    """Proper rotation carrying two unit tangents without additional spin."""
    a, b = _unit(a, "source tangent"), _unit(b, "target tangent")
    cosine = float(np.clip(np.dot(a, b), -1., 1.))
    if cosine <= -1+1e-9:
        raise ValueError("antiparallel ply tangent alignment has no unique minimal rotation")
    v = np.cross(a, b)
    skew = np.array(((0., -v[2], v[1]), (v[2], 0., -v[0]), (-v[1], v[0], 0.)))
    return np.eye(3)+skew+(skew@skew)/(1+cosine)


@dataclass(frozen=True)
class MaterialFiberReference:
    record: FiberCurve
    material_coordinates_mm: np.ndarray
    parent_material_coordinates_mm: np.ndarray

    def __post_init__(self):
        if not isinstance(self.record, FiberCurve):
            raise TypeError("record must be FiberCurve")
        count = len(self.record.points_mm)
        u = _coordinates(self.material_coordinates_mm, count, "fiber reference arclength labels")
        if not np.array_equal(u, arclength_mm(self.record.points_mm)):
            raise ValueError("fiber material coordinates must be the immutable original fiber arclength")
        parent = _coordinates(self.parent_material_coordinates_mm, count, "fiber parent labels")
        object.__setattr__(self, "material_coordinates_mm", u)
        object.__setattr__(self, "parent_material_coordinates_mm", parent)

    @property
    def fiber_id(self):
        return self.record.fiber_id


@dataclass(frozen=True)
class MaterialReference:
    yarns: Mapping[str, FramedCurve]
    plies: Mapping[str, FramedCurve]
    ply_yarn_ids: Mapping[str, str]
    ply_parent_material_coordinates_mm: Mapping[str, np.ndarray]
    fiber_records: tuple[MaterialFiberReference, ...]
    spec_json: str
    source_metadata_json: str
    correspondence: str = "declared_shared_vertex_indices"

    def __post_init__(self):
        if self.correspondence != "declared_shared_vertex_indices":
            raise ValueError("unsupported reference correspondence declaration")
        for key in ("yarns", "plies", "ply_yarn_ids"):
            object.__setattr__(self, key, MappingProxyType(dict(getattr(self, key))))
        object.__setattr__(self, "ply_parent_material_coordinates_mm", MappingProxyType({
            key: _readonly(value) for key, value in self.ply_parent_material_coordinates_mm.items()}))
        object.__setattr__(self, "fiber_records", tuple(self.fiber_records))
        # Freeze caller-owned metadata via serialization rather than a shallow
        # dict copy whose nested fields could invalidate reproducibility later.
        for key in ("spec_json", "source_metadata_json"):
            object.__setattr__(self, key, _canonical(json.loads(getattr(self, key))))
        for kind in ("yarns", "plies"):
            mapping = getattr(self, kind)
            if not mapping or any(not isinstance(key, str) or not key or not isinstance(value, FramedCurve)
                                  for key, value in mapping.items()):
                raise ValueError("nonempty named FramedCurve reference parents are required")
            if any(not np.array_equal(curve.material_coordinates_mm, curve.arclength_mm)
                   for curve in mapping.values()):
                raise ValueError("reference parent coordinates must be original parent arclengths")
        if set(self.ply_yarn_ids) != set(self.plies) or set(self.ply_parent_material_coordinates_mm) != set(self.plies):
            raise ValueError("reference ply correspondence maps must contain exactly the ply IDs")
        for key, curve in self.plies.items():
            parent_id = self.ply_yarn_ids[key]
            if parent_id not in self.yarns:
                raise ValueError("reference ply parent yarn is missing")
            parent = self.yarns[parent_id]
            if (len(curve.points_mm) != len(parent.points_mm)
                    or not np.array_equal(self.ply_parent_material_coordinates_mm[key], parent.material_coordinates_mm)):
                raise ValueError("reference ply knots disagree with declared shared vertex correspondence")
        if (not self.fiber_records or any(not isinstance(f, MaterialFiberReference) for f in self.fiber_records)
                or len({f.fiber_id for f in self.fiber_records}) != len(self.fiber_records)):
            raise ValueError("nonempty unique bound fiber reference records required")
        used_yarns, used_plies, yarn_labels, physical_yarns, ply_labels, physical_fibers = set(), set(), {}, {}, {}, set()
        for item in self.fiber_records:
            record = item.record
            if (record.ply_id not in self.plies or record.yarn_id not in self.yarns
                    or self.ply_yarn_ids[record.ply_id] != record.yarn_id):
                raise ValueError("reference fiber/ply/yarn parent association is inconsistent")
            parent = self.plies[record.ply_id]
            if not np.array_equal(item.parent_material_coordinates_mm, parent.material_coordinates_mm):
                raise ValueError("reference fiber knots disagree with declared shared vertex correspondence")
            used_yarns.add(record.yarn_id); used_plies.add(record.ply_id)
            label = (record.family, record.yarn_index)
            if ((record.yarn_id in yarn_labels and yarn_labels[record.yarn_id] != label)
                    or (label in physical_yarns and physical_yarns[label] != record.yarn_id)):
                raise ValueError("inconsistent reference family/index labels")
            yarn_labels[record.yarn_id] = label; physical_yarns[label] = record.yarn_id
            plabel = (record.yarn_id, record.ply_index)
            if record.ply_id in ply_labels and ply_labels[record.ply_id] != plabel:
                raise ValueError("inconsistent reference ply index labels")
            ply_labels[record.ply_id] = plabel
            fid = (record.yarn_id, record.ply_index, record.fiber_index)
            if fid in physical_fibers:
                raise ValueError("duplicate reference fiber index")
            physical_fibers.add(fid)
        if used_yarns != set(self.yarns) or used_plies != set(self.plies):
            raise ValueError("reference contains orphan parent curves")
        if len(set(ply_labels.values())) != len(ply_labels):
            raise ValueError("duplicate reference parent/ply index")

    @property
    def sha256(self):
        h = hashlib.sha256()
        h.update(_canonical({"schema": SCHEMA_VERSION, "spec": json.loads(self.spec_json),
                             "correspondence": self.correspondence,
                             "ply_yarn_ids": dict(self.ply_yarn_ids)}).encode("utf-8"))
        for kind, mapping in (("yarn", self.yarns), ("ply", self.plies)):
            for key in sorted(mapping):
                curve = mapping[key]
                h.update(_canonical([kind, key, curve.points_mm.shape]).encode("utf-8"))
                for a in (curve.points_mm, curve.material_coordinates_mm, curve.frames):
                    h.update(np.asarray(a, dtype="<f8").tobytes())
                if kind == "ply":
                    h.update(np.asarray(self.ply_parent_material_coordinates_mm[key], dtype="<f8").tobytes())
        for fiber in self.fiber_records:
            h.update(_canonical({**fiber.record.provenance(),
                                 "vertex_count": len(fiber.record.points_mm)}).encode("utf-8"))
            for a in (fiber.record.points_mm, fiber.record.radii_mm,
                      fiber.material_coordinates_mm, fiber.parent_material_coordinates_mm):
                h.update(np.asarray(a, dtype="<f8").tobytes())
        return h.hexdigest()


def bind_material_reference(geometry: HierarchyGeometry, *, yarn_initial_normals,
                            correspondence):
    """Declare the original builder's shared vertex indices as parent labels.

    This declaration must be explicit and can only be made for a hierarchy whose
    children and parents use the same ordered samples.  Coincident counts do NOT
    prove physical correspondence; unknown scans or independently resampled
    centerlines require an externally established correspondence, not this API.
    """
    if not isinstance(geometry, HierarchyGeometry):
        raise TypeError("geometry must be HierarchyGeometry")
    if correspondence != "shared_vertex_indices":
        raise ValueError("explicit correspondence='shared_vertex_indices' declaration is required")
    _exact_keys(yarn_initial_normals, geometry.yarns, "yarn_initial_normals")
    used_yarns, used_plies = set(), set()
    ply_yarn, yarn_labels, ply_labels = {}, {}, {}
    yarn_indices, fiber_indices = {}, set()
    for record in geometry.fiber_records:
        used_yarns.add(record.yarn_id); used_plies.add(record.ply_id)
        if record.ply_id in ply_yarn and ply_yarn[record.ply_id] != record.yarn_id:
            raise ValueError("one ply cannot have multiple parent yarns")
        ply_yarn[record.ply_id] = record.yarn_id
        label = (record.family, record.yarn_index)
        if record.yarn_id in yarn_labels and yarn_labels[record.yarn_id] != label:
            raise ValueError("inconsistent family/index records for one yarn")
        if label in yarn_indices and yarn_indices[label] != record.yarn_id:
            raise ValueError("different yarn IDs cannot share one family/index label")
        yarn_labels[record.yarn_id] = label; yarn_indices[label] = record.yarn_id
        plabel = (record.yarn_id, record.ply_index)
        if record.ply_id in ply_labels and ply_labels[record.ply_id] != plabel:
            raise ValueError("inconsistent ply index records")
        ply_labels[record.ply_id] = plabel
        fid = (record.yarn_id, record.ply_index, record.fiber_index)
        if fid in fiber_indices:
            raise ValueError("duplicate physical fiber family/ply/index")
        fiber_indices.add(fid)
    if used_yarns != set(geometry.yarns) or used_plies != set(geometry.plies):
        raise ValueError("orphan or missing parent curves cannot be material-bound")
    if len(set(ply_labels.values())) != len(ply_labels):
        raise ValueError("different ply IDs cannot share one parent/ply-index label")
    yarns = {key: FramedCurve(points, arclength_mm(points), yarn_initial_normals[key])
             for key, points in geometry.yarns.items()}
    plies, ply_coordinates = {}, {}
    for key, points in geometry.plies.items():
        parent = yarns[ply_yarn[key]]
        if len(points) != len(parent.points_mm):
            raise ValueError("shared vertex correspondence requires equal ply/yarn sample counts")
        ply_coordinates[key] = parent.material_coordinates_mm
        plies[key] = FramedCurve(points, arclength_mm(points), parent.initial_normal)
    fibers = []
    for record in geometry.fiber_records:
        parent = plies[record.ply_id]
        if len(record.points_mm) != len(parent.points_mm):
            raise ValueError("shared vertex correspondence requires equal fiber/ply sample counts")
        # FiberCurve already owns immutable byte-backed arrays, but copying the
        # record also guards against a caller replacing a mutable outer record.
        copied = FiberCurve(record.points_mm, record.radii_mm, **record.provenance())
        fibers.append(MaterialFiberReference(copied, arclength_mm(copied.points_mm),
                                             parent.material_coordinates_mm))
    return MaterialReference(yarns, plies, ply_yarn, ply_coordinates, tuple(fibers),
                             _canonical(geometry.spec), _canonical(geometry.metadata))


@dataclass(frozen=True)
class TransportedFiber:
    reference: MaterialFiberReference
    points_mm: np.ndarray
    radius_mode: str
    deformed_arclength_mm: np.ndarray = field(init=False)
    segment_stretch: np.ndarray = field(init=False)
    engineering_strain: np.ndarray = field(init=False)
    log_strain: np.ndarray = field(init=False)
    segment_radius_mm: np.ndarray = field(init=False)
    reference_segment_volume_mm3: np.ndarray = field(init=False)
    segment_volume_mm3: np.ndarray = field(init=False)

    def __post_init__(self):
        if not isinstance(self.reference, MaterialFiberReference) or self.radius_mode not in RADIUS_MODES:
            raise ValueError("a material reference and supported radius_mode are required")
        p, arc = _points(self.points_mm, "transported fiber")
        if p.shape != self.reference.record.points_mm.shape:
            raise ValueError("material transport cannot add, delete, or reorder fiber vertices")
        reference_length = np.diff(self.reference.material_coordinates_mm)
        length = np.diff(arc)
        stretch = length/reference_length
        if not np.isfinite(stretch).all() or np.any(stretch <= 0):
            raise ValueError("positive finite segment stretches required")
        r0 = self.reference.record.radius_mm
        radius = (np.full_like(stretch, r0) if self.radius_mode == "constant_reference"
                  else r0/np.sqrt(stretch))
        values = {"points_mm": p, "deformed_arclength_mm": arc,
                  "segment_stretch": stretch, "engineering_strain": stretch-1,
                  "log_strain": np.log(stretch), "segment_radius_mm": radius,
                  "reference_segment_volume_mm3": np.pi*r0*r0*reference_length,
                  "segment_volume_mm3": np.pi*radius*radius*length}
        for key, value in values.items():
            if not np.isfinite(value).all():
                raise ValueError("nonfinite radius/strain/segment-volume calculation")
            object.__setattr__(self, key, _readonly(value))

    @property
    def reference_points_mm(self):
        return self.reference.record.points_mm

    @property
    def material_coordinates_mm(self):
        return self.reference.material_coordinates_mm

    @property
    def reference_arclength_mm(self):
        return self.material_coordinates_mm

    @property
    def parent_material_coordinates_mm(self):
        return self.reference.parent_material_coordinates_mm

    @property
    def fiber_id(self):
        return self.reference.record.fiber_id

    def provenance(self):
        return self.reference.record.provenance()


@dataclass(frozen=True)
class MaterialTransportState:
    reference: MaterialReference
    yarns: Mapping[str, FramedCurve]
    plies: Mapping[str, FramedCurve]
    fiber_records: tuple[TransportedFiber, ...]
    radius_mode: str

    def __post_init__(self):
        if not isinstance(self.reference, MaterialReference) or self.radius_mode not in RADIUS_MODES:
            raise ValueError("unsupported radius mode")
        for key in ("yarns", "plies"):
            object.__setattr__(self, key, MappingProxyType(dict(getattr(self, key))))
        object.__setattr__(self, "fiber_records", tuple(self.fiber_records))
        for kind in ("yarns", "plies"):
            mapping = getattr(self, kind)
            expected = getattr(self.reference, kind)
            if set(mapping) != set(expected) or any(not isinstance(value, FramedCurve) for value in mapping.values()):
                raise ValueError("transported parents must match the bound reference IDs and types")
            for key, curve in mapping.items():
                if curve.material_coordinates_mm[-1] != expected[key].material_coordinates_mm[-1]:
                    raise ValueError("transported parents changed reference material-coordinate domains")
                if kind == "plies" and not np.array_equal(curve.material_coordinates_mm, expected[key].material_coordinates_mm):
                    raise ValueError("transported ply sample material labels cannot change")
        if len(self.fiber_records) != len(self.reference.fiber_records):
            raise ValueError("transported fiber records must preserve the reference count")
        for expected, actual in zip(self.reference.fiber_records, self.fiber_records):
            if (not isinstance(actual, TransportedFiber) or actual.reference is not expected
                    or actual.radius_mode != self.radius_mode):
                raise ValueError("transported fiber order, reference associations and radius modes must agree")
        # These public dataclasses must not accept a substituted geometry and
        # continue to claim it was produced by the declared kinematic map.
        for key, source in self.reference.plies.items():
            yid = self.reference.ply_yarn_ids[key]
            parent_coordinates = self.reference.ply_parent_material_coordinates_mm[key]
            expected_points = transport_framed_points(self.reference.yarns[yid], self.yarns[yid],
                                                       source.points_mm, parent_coordinates)
            _require_same_pose(self.plies[key].points_mm, expected_points, "ply")
            expected_normal = _transported_ply_normal(self.reference.yarns[yid], self.yarns[yid],
                                                       source, expected_points, parent_coordinates)
            _require_same_pose(self.plies[key].initial_normal, expected_normal, "ply director")
        for fiber in self.fiber_records:
            key = fiber.reference.record.ply_id
            expected_points = transport_framed_points(self.reference.plies[key], self.plies[key],
                fiber.reference_points_mm, fiber.parent_material_coordinates_mm)
            _require_same_pose(fiber.points_mm, expected_points, "fiber")

    @property
    def sha256(self):
        h = hashlib.sha256((self.reference.sha256+"|"+self.radius_mode).encode("ascii"))
        for mapping in (self.yarns, self.plies):
            for key in sorted(mapping):
                curve = mapping[key]
                h.update(_canonical([key, curve.points_mm.shape]).encode("utf-8"))
                for a in (curve.points_mm, curve.material_coordinates_mm, curve.frames):
                    h.update(np.asarray(a, dtype="<f8").tobytes())
        for f in self.fiber_records:
            h.update(f.fiber_id.encode("utf-8"))
            for a in (f.points_mm, f.segment_radius_mm):
                h.update(np.asarray(a, dtype="<f8").tobytes())
        return h.hexdigest()

    def summary(self):
        def group_summary(fibers):
            reference_length = np.concatenate([np.diff(f.material_coordinates_mm) for f in fibers])
            stretch = np.concatenate([f.segment_stretch for f in fibers])
            volume0 = np.concatenate([f.reference_segment_volume_mm3 for f in fibers])
            volume = np.concatenate([f.segment_volume_mm3 for f in fibers])
            before, after = float(reference_length.sum()), float(np.dot(reference_length, stretch))
            return {"fiber_count": len(fibers),
                    "vertex_count": sum(len(f.points_mm) for f in fibers),
                    "segment_count": len(stretch),
                    "reference_fiber_length_mm": before, "deformed_fiber_length_mm": after,
                    "relative_fiber_length_change": after/before-1,
                    "min_segment_stretch": float(stretch.min()),
                    "max_segment_stretch": float(stretch.max()),
                    "reference_length_weighted_mean_engineering_strain": float(np.dot(reference_length, stretch-1)/before),
                    "reference_length_weighted_rms_engineering_strain": float(np.sqrt(np.dot(reference_length, (stretch-1)**2)/before)),
                    "reference_cylinder_segment_volume_mm3": float(volume0.sum()),
                    "deformed_cylinder_segment_volume_mm3": float(volume.sum()),
                    "relative_cylinder_segment_volume_change": float(volume.sum()/volume0.sum()-1),
                    "max_absolute_relative_segment_volume_change": float(np.max(np.abs(volume/volume0-1)))}
        groups = {}
        for f in self.fiber_records:
            groups.setdefault(f.reference.record.family, []).append(f)
        return {"schema_version": SCHEMA_VERSION, "length_unit": "mm",
                "reference_sha256": self.reference.sha256, "state_sha256": self.sha256,
                "radius_mode": self.radius_mode,
                "fiber_material_points_tracked": True,
                "material_correspondence": self.reference.correspondence,
                "fiber_vertices_added_or_removed": 0,
                "fiber_stress_solved": False, "inextensibility_enforced": False,
                "contact_or_clearance_certified": False,
                "segment_cylinder_volume_conservation_enforced": self.radius_mode == "incompressible_segments",
                "physical_mass_conservation_certified": False,
                "constant_radius_optical_export_allowed": self.radius_mode == "constant_reference",
                "frame_rule": "explicit yarn endpoint directors; double-reflection RMF; SO(3) shortest-geodesic interpolation; child director carried by parent and minimally tangent-aligned",
                "scope": "prescribed framed no-slip kinematic correspondence; no solved fiber stress/twist/slip, contact, global injectivity, or full tube volume",
                "all": group_summary(self.fiber_records),
                "families": {name: group_summary(fibers) for name, fibers in sorted(groups.items())},
                "parents": {kind: {key: {
                    "reference_arclength_mm": float(getattr(self.reference, kind)[key].arclength_mm[-1]),
                    "deformed_arclength_mm": float(curve.arclength_mm[-1]),
                    "material_coordinate_end_mm": float(curve.material_coordinates_mm[-1]),
                    "target_vertex_count": len(curve.points_mm)} for key, curve in sorted(mapping.items())}
                    for kind, mapping in (("yarns", self.yarns), ("plies", self.plies))}}

    def to_hierarchy(self):
        """Create constant-radius optical geometry without stale source audits.

        Incompressible-segment mode is rejected even if its current example
        accidentally has uniform stretch: no uncalibrated radius conversion is
        performed and no unsupported variable-radius state can slip through.
        """
        if self.radius_mode != "constant_reference":
            raise ValueError("incompressible segment radii require a variable-radius optical adapter; export is blocked")
        records = tuple(FiberCurve(f.points_mm, np.full(len(f.points_mm), f.reference.record.radius_mm),
                                    **f.provenance()) for f in self.fiber_records)
        return HierarchyGeometry(records,
            {key: curve.points_mm.copy() for key, curve in self.yarns.items()},
            {key: curve.points_mm.copy() for key, curve in self.plies.items()},
            {"kind": "material_coordinate_transported_hierarchy", "schema_version": SCHEMA_VERSION,
             "reference_spec": json.loads(self.reference.spec_json),
             "reference_sha256": self.reference.sha256, "transport_state_sha256": self.sha256},
            {"length_unit": "mm", "geometry_tileable": False,
             "physical_mechanics_solved": False, "parent_centerlines_prescribed": True,
             "fiber_material_points_conserved": True,
             "fiber_material_points_conservation_meaning": "fixed original vertex labels/order retained; kinematic correspondence declared, not independently measured material motion",
             "fiber_inextensibility_enforced": False, "mass_conservation_certified": False,
             "clearance_audit_required": True, "reference_audits_inherited": False,
             "material_transport": self.summary()})


def transport_material_reference(reference: MaterialReference, deformed_yarns, *,
                                 yarn_initial_normals,
                                 deformed_parent_coordinates_mm,
                                 radius_mode="constant_reference"):
    """Evaluate a new pose from the original reference, never from regenerated fibers.

    ``deformed_parent_coordinates_mm[yarn_id]`` labels each target yarn vertex
    by ORIGINAL parent material coordinate.  Equal sampling uses
    ``reference.yarns[yarn_id].material_coordinates_mm``.  Refined target knots
    are allowed only with explicit increasing labels and identical endpoints.
    Passing relaxed arclengths changes the labels and is rejected at the endpoint
    whenever the yarn length changes; callers still own the interior mapping.
    """
    if not isinstance(reference, MaterialReference):
        raise TypeError("reference must be MaterialReference")
    if radius_mode not in RADIUS_MODES:
        raise ValueError(f"radius_mode must be one of {RADIUS_MODES}")
    for value, name in ((deformed_yarns, "deformed_yarns"),
                         (yarn_initial_normals, "yarn_initial_normals"),
                         (deformed_parent_coordinates_mm, "deformed_parent_coordinates_mm")):
        _exact_keys(value, reference.yarns, name)
    yarns = {}
    for key in reference.yarns:
        curve = FramedCurve(deformed_yarns[key], deformed_parent_coordinates_mm[key], yarn_initial_normals[key])
        if curve.material_coordinates_mm[-1] != reference.yarns[key].material_coordinates_mm[-1]:
            raise ValueError("target yarn endpoint must retain the original material coordinate, not relaxed arclength")
        yarns[key] = curve
    plies = {}
    for key, source in reference.plies.items():
        yid = reference.ply_yarn_ids[key]
        parent_coordinates = reference.ply_parent_material_coordinates_mm[key]
        points = transport_framed_points(reference.yarns[yid], yarns[yid],
                                          source.points_mm, parent_coordinates)
        target_normal = _transported_ply_normal(reference.yarns[yid], yarns[yid],
                                                 source, points, parent_coordinates)
        plies[key] = FramedCurve(points, source.material_coordinates_mm, target_normal)
    fibers = []
    for item in reference.fiber_records:
        key = item.record.ply_id
        points = transport_framed_points(reference.plies[key], plies[key],
                                          item.record.points_mm, item.parent_material_coordinates_mm)
        fibers.append(TransportedFiber(item, points, radius_mode))
    return MaterialTransportState(reference, yarns, plies, tuple(fibers), radius_mode)


def _require_same_pose(actual, expected, name):
    actual, expected = np.asarray(actual), np.asarray(expected)
    scale = max(float(np.max(np.abs(expected))), float(np.ptp(expected)), np.finfo(float).tiny)
    if actual.shape != expected.shape or not np.allclose(actual, expected, atol=256*np.finfo(float).eps*scale, rtol=0):
        raise ValueError(f"transported {name} does not match the declared reference map")


def _transported_ply_normal(reference_yarn, target_yarn, source_ply, points, parent_coordinates):
    _, source_frames = reference_yarn.evaluate(parent_coordinates[:1])
    _, target_frames = target_yarn.evaluate(parent_coordinates[:1])
    parent_rotation = target_frames[0]@source_frames[0].T
    # Carry the reference ply gauge with the parent, then tangent-align it.
    # Independent projection in the two poses would introduce gauge-dependent
    # spin when the ply tangent changes.
    target_arc = arclength_mm(points)
    target_t0 = np.gradient(points, target_arc, axis=0,
                            edge_order=2 if len(points) > 2 else 1)[0]
    alignment = _minimal_alignment(parent_rotation@source_ply.frames[0, :, 0], target_t0)
    target_normal = alignment@parent_rotation@source_ply.initial_normal
    tangent = _unit(target_t0, "target ply tangent")
    return _unit(target_normal-np.dot(target_normal, tangent)*tangent, "target ply director")


def save_material_transport(output_directory, state: MaterialTransportState):
    """Save reference labels, both poses, frames, strains and segment volumes.

    This is a raw, non-pickle NPZ plus a schema/array-layout JSON manifest.
    Existing artifacts are never overwritten.  The reference/state hashes bind
    numerical inputs and explicit director choices; NPZ SHA-256 binds file bytes.
    """
    if not isinstance(state, MaterialTransportState):
        raise TypeError("state must be MaterialTransportState")
    output = Path(output_directory)
    npz_path, json_path = output/"material_transport.npz", output/"material_transport.json"
    if npz_path.exists() or json_path.exists():
        raise FileExistsError("material transport artifacts already exist")
    arrays, layout = {}, {"fibers": [], "parents": {}}
    for index, fiber in enumerate(state.fiber_records):
        prefix = f"fiber_{index:05d}"
        for name in ("reference_points_mm", "points_mm", "material_coordinates_mm",
                     "parent_material_coordinates_mm", "deformed_arclength_mm", "segment_stretch",
                     "engineering_strain", "log_strain", "segment_radius_mm",
                     "reference_segment_volume_mm3", "segment_volume_mm3"):
            arrays[prefix+"/"+name] = getattr(fiber, name)
        layout["fibers"].append({"array_prefix": prefix, **fiber.provenance(),
                                  "reference_radius_mm": fiber.reference.record.radius_mm})
    for kind in ("yarns", "plies"):
        entries = []
        for index, key in enumerate(sorted(getattr(state, kind))):
            prefix = f"{kind}_{index:05d}"
            for pose, container in (("reference", state.reference), ("deformed", state)):
                curve = getattr(container, kind)[key]
                for name in ("points_mm", "material_coordinates_mm", "arclength_mm", "frames", "initial_normal"):
                    arrays[prefix+"/"+pose+"/"+name] = getattr(curve, name)
            entries.append({"id": key, "array_prefix": prefix,
                            **({"parent_yarn_id": state.reference.ply_yarn_ids[key]} if kind == "plies" else {})})
            if kind == "plies":
                arrays[prefix+"/parent_material_coordinates_mm"] = state.reference.ply_parent_material_coordinates_mm[key]
        layout["parents"][kind] = entries
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, **arrays)
    payload = {"schema_version": SCHEMA_VERSION, "summary": state.summary(),
               "reference_spec": json.loads(state.reference.spec_json),
               "reference_geometry_metadata": json.loads(state.reference.source_metadata_json),
               "array_file": npz_path.name, "array_file_sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
               "array_layout": layout}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    return {"json": json_path, "npz": npz_path}
