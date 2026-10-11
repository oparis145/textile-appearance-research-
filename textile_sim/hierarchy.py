"""Explicit, validated fiber -> ply -> yarn -> planar woven-fabric geometry.

All lengths are millimeters. Twists are signed turns per millimeter of the
*parent's measured arclength*. Generated curves are interpolating polylines,
not cubic B-spline control polygons. Manufacturing mechanics, contact forces,
staple statistics, and full 3-D weave-block topology are outside this module.

The old :mod:`textile_sim.geometry` API is intentionally left unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
import numbers
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from .weave_draft import WeaveDraft, periodic_crossing_height

SCHEMA_VERSION = "textile-hierarchy/2.0"


def _json_value(value):
    """Canonical JSON-native values, including numpy scalar configuration inputs."""
    if isinstance(value, dict):
        return {key: _json_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(val) for val in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _finite(value, name, *, positive=False, nonnegative=False):
    if not np.isscalar(value) or isinstance(value, (bool, str)) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f"{name} has invalid sign")
    return float(value)


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _identifier(value, name):
    if (not isinstance(value, str) or not value or "/" in value or "\\" in value
            or any(ord(c) < 32 for c in value)):
        raise ValueError(f"{name} must be a nonempty local identifier without path separators")
    return value


def _offset(value, name):
    a = np.asarray(value, dtype=float)
    if a.shape != (2,) or not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must contain two finite coordinates")
    return tuple(map(float, a))


def _stable_phase(seed, key):
    # Independent of construction order, Python hash randomization, and count.
    h = hashlib.sha256(f"{int(seed)}|{key}".encode("utf-8")).digest()
    return 2*np.pi*int.from_bytes(h[:8], "little")/2**64


def arclength_mm(points_mm):
    p = np.asarray(points_mm, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2 or not np.all(np.isfinite(p)):
        raise ValueError("centerline must be a finite N x 3 array with N>=2")
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    if np.any(d <= 0):
        raise ValueError("consecutive centerline vertices must be distinct")
    return np.r_[0., np.cumsum(d)]


def _unit(a):
    a = np.asarray(a, dtype=float)
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    if np.any(n < 1e-14) or not np.all(np.isfinite(n)):
        raise ValueError("a tangent/normal is zero or nonfinite")
    return a/n


def rotation_minimizing_frames(points_mm, tangents=None, initial_normal=None):
    """Double-reflection transport with arclength-based sampled tangents.

    Returns unit tangent, first normal, second normal with t x n1 = n2.
    Supplying analytic tangents improves convergence for analytic centerlines.
    A cusp or reversing zero tangent is rejected; no arbitrary Frenet flip is
    silently introduced. This does not impose a closed-loop holonomy condition.
    """
    p = np.asarray(points_mm, dtype=float)
    s = arclength_mm(p)
    if tangents is None:
        t = _unit(np.gradient(p, s, axis=0, edge_order=2 if len(p) > 2 else 1))
    else:
        if np.shape(tangents) != p.shape:
            raise ValueError("tangents must have the same shape as points")
        t = _unit(tangents)
    if np.any(np.sum(t[1:]*t[:-1], axis=1) < -1+1e-9):
        raise ValueError("opposite consecutive tangents require refining/removing a cusp")
    if initial_normal is None:
        initial = np.eye(3)[np.argmin(np.abs(t[0]))]
    else:
        initial = np.asarray(initial_normal, dtype=float)
        if initial.shape != (3,) or not np.all(np.isfinite(initial)):
            raise ValueError("initial_normal must contain three finite values")
    n = np.empty_like(t)
    n[0] = _unit(initial-np.dot(initial, t[0])*t[0])
    for i in range(len(p)-1):
        v1 = p[i+1]-p[i]
        c1 = np.dot(v1, v1)
        reflected_n = n[i]-2*np.dot(v1, n[i])/c1*v1
        reflected_t = t[i]-2*np.dot(v1, t[i])/c1*v1
        v2 = t[i+1]-reflected_t
        c2 = np.dot(v2, v2)
        nxt = reflected_n if c2 < 1e-28 else reflected_n-2*np.dot(v2, reflected_n)/c2*v2
        n[i+1] = _unit(nxt-np.dot(nxt, t[i+1])*t[i+1])
    return t, n, _unit(np.cross(t, n))


def swept_offset(points_mm, offset_mm, twist_per_mm=0., phase_rad=0., *,
                 radial_displacement_mm=None, initial_normal=None, tangents=None):
    """Sweep one local 2D offset in an RMF, rotating by signed parent arclength.

    Positive twist is a right-handed rotation about the parent's forward
    tangent, because n2 = t x n1. Optional displacement changes radial distance
    while retaining the local polar direction; a central offset cannot migrate.
    """
    p = np.asarray(points_mm, dtype=float)
    q = np.asarray(_offset(offset_mm, "offset_mm"))
    rate = _finite(twist_per_mm, "twist_per_mm")
    phase = _finite(phase_rad, "phase_rad")
    s = arclength_mm(p)
    _, n1, n2 = rotation_minimizing_frames(p, tangents, initial_normal)
    return _sweep_from_frame(p, q, rate, phase, s, n1, n2, radial_displacement_mm)


def _sweep_from_frame(p, q, rate, phase, s, n1, n2, radial_displacement_mm=None):
    q = np.asarray(q, dtype=float)
    if radial_displacement_mm is not None:
        dr = np.asarray(radial_displacement_mm, dtype=float)
        if dr.shape != s.shape or not np.all(np.isfinite(dr)):
            raise ValueError("radial displacement must be finite at every vertex")
        radius = np.linalg.norm(q)
        if radius == 0 and np.any(dr != 0):
            raise ValueError("radial displacement of a central offset has no defined direction")
        if radius and np.any(radius+dr < 0):
            raise ValueError("radial displacement would pass through the ply axis")
        local = np.broadcast_to(q, (len(s), 2)).copy()
        if radius:
            local *= (1+dr/radius)[:, None]
    else:
        local = np.broadcast_to(q, (len(s), 2))
    angle = 2*np.pi*rate*s+phase
    c, sn = np.cos(angle), np.sin(angle)
    x = local[:, 0]*c-local[:, 1]*sn
    y = local[:, 0]*sn+local[:, 1]*c
    return p+x[:, None]*n1+y[:, None]*n2


@dataclass(frozen=True)
class FiberSpec:
    id: str
    material_id: str
    radius_mm: float
    offset_mm: tuple[float, float] = (0., 0.)
    migration_amplitude_mm: float = 0.
    migration_period_mm: float = 1.
    migration_phase_rad: float | None = None
    loop_amplitude_mm: float = 0.
    loop_length_mm: float = .1
    loop_center_fraction: float = .5

    def __post_init__(self):
        _identifier(self.id, "fiber id")
        _identifier(self.material_id, "material_id")
        _finite(self.radius_mm, "radius_mm", positive=True)
        object.__setattr__(self, "offset_mm", _offset(self.offset_mm, "fiber offset_mm"))
        _finite(self.migration_amplitude_mm, "migration_amplitude_mm", nonnegative=True)
        _finite(self.migration_period_mm, "migration_period_mm", positive=True)
        if self.migration_phase_rad is not None:
            _finite(self.migration_phase_rad, "migration_phase_rad")
        _finite(self.loop_amplitude_mm, "loop_amplitude_mm", nonnegative=True)
        _finite(self.loop_length_mm, "loop_length_mm", positive=True)
        _finite(self.loop_center_fraction, "loop_center_fraction")
        if not 0 < self.loop_center_fraction < 1:
            raise ValueError("loop center must lie strictly within the parent curve")
        r = np.linalg.norm(self.offset_mm)
        if self.migration_amplitude_mm > 0 and self.migration_amplitude_mm >= r:
            raise ValueError("migration must not reach/pass through the ply axis")
        if self.loop_amplitude_mm > 0 and r == 0:
            raise ValueError("loop excursion requires a noncentral fiber")

    @property
    def excursion_bound_mm(self):
        return self.migration_amplitude_mm+self.loop_amplitude_mm


@dataclass(frozen=True)
class PlySpec:
    id: str
    fibers: tuple[FiberSpec, ...]
    offset_mm: tuple[float, float] = (0., 0.)
    fiber_twist_per_mm: float = 0.
    fiber_phase_rad: float = 0.

    def __post_init__(self):
        _identifier(self.id, "ply id")
        object.__setattr__(self, "fibers", tuple(self.fibers))
        if not self.fibers or any(not isinstance(f, FiberSpec) for f in self.fibers):
            raise ValueError("ply must contain FiberSpec records")
        if len({f.id for f in self.fibers}) != len(self.fibers):
            raise ValueError("fiber IDs within a ply must be unique")
        object.__setattr__(self, "offset_mm", _offset(self.offset_mm, "ply offset_mm"))
        _finite(self.fiber_twist_per_mm, "fiber_twist_per_mm")
        _finite(self.fiber_phase_rad, "fiber_phase_rad")
        for i, f in enumerate(self.fibers):
            for g in self.fibers[i+1:]:
                d = np.linalg.norm(np.asarray(f.offset_mm)-g.offset_mm)
                bound = d-f.excursion_bound_mm-g.excursion_bound_mm-f.radius_mm-g.radius_mm
                if bound <= 0:
                    raise ValueError("fiber packing/migration cannot certify equal-section separation")

    @property
    def envelope_radius_mm(self):
        return max(np.linalg.norm(f.offset_mm)+f.excursion_bound_mm+f.radius_mm for f in self.fibers)


@dataclass(frozen=True)
class YarnSpec:
    id: str
    plies: tuple[PlySpec, ...]
    ply_twist_per_mm: float = 0.
    ply_phase_rad: float = 0.

    def __post_init__(self):
        _identifier(self.id, "yarn id")
        object.__setattr__(self, "plies", tuple(self.plies))
        if not self.plies or any(not isinstance(p, PlySpec) for p in self.plies):
            raise ValueError("yarn must contain PlySpec records")
        if len({p.id for p in self.plies}) != len(self.plies):
            raise ValueError("ply IDs within a yarn must be unique")
        _finite(self.ply_twist_per_mm, "ply_twist_per_mm")
        _finite(self.ply_phase_rad, "ply_phase_rad")
        for i, p in enumerate(self.plies):
            for q in self.plies[i+1:]:
                d = np.linalg.norm(np.asarray(p.offset_mm)-q.offset_mm)
                if d <= p.envelope_radius_mm+q.envelope_radius_mm:
                    raise ValueError("ply envelopes overlap in the yarn reference cross-section")

    @property
    def envelope_radius_mm(self):
        return max(np.linalg.norm(p.offset_mm)+p.envelope_radius_mm for p in self.plies)

    @property
    def fiber_count(self):
        return sum(len(p.fibers) for p in self.plies)

    def to_dict(self):
        return _json_value(asdict(self))

    @classmethod
    def from_dict(cls, value):
        obj = dict(value)
        plies = []
        for raw in obj.pop("plies"):
            p = dict(raw)
            fibers = tuple(FiberSpec(**f) for f in p.pop("fibers"))
            plies.append(PlySpec(fibers=fibers, **p))
        return cls(plies=tuple(plies), **obj)


def hex_ply(*, id="ply", rings=1, spacing_mm=.01, radius_mm=.003,
            material_ids=("synthetic_dielectric",), offset_mm=(0., 0.),
            fiber_twist_per_mm=1., migration_amplitude_mm=0., migration_period_mm=.3):
    """Construct a hexagonal core; material IDs cycle deterministically.

    Migration is omitted for the central fiber, whose radial direction is
    undefined. Geometry is independent of optical/material numerical values.
    """
    rings = _integer(rings, "rings")
    _finite(spacing_mm, "spacing_mm", positive=True)
    if not material_ids:
        raise ValueError("at least one material ID is required")
    centers = []
    for a in range(-rings, rings+1):
        for b in range(-rings, rings+1):
            if max(abs(a), abs(b), abs(a+b)) <= rings:
                centers.append((spacing_mm*(a+b/2), spacing_mm*np.sqrt(3)*b/2))
    fibers = tuple(FiberSpec(f"f{i:04d}", material_ids[i % len(material_ids)], radius_mm,
                            q, migration_amplitude_mm if np.linalg.norm(q) else 0.,
                            migration_period_mm)
                   for i, q in enumerate(centers))
    return PlySpec(id, fibers, offset_mm, fiber_twist_per_mm)


@dataclass(frozen=True)
class FabricSpec:
    draft: WeaveDraft
    warp_yarn: YarnSpec
    weft_yarn: YarnSpec
    warp_count: int = 4
    weft_count: int = 4
    warp_pitch_mm: float = .18
    weft_pitch_mm: float = .18
    crossing_gap_mm: float = .008
    warp_crimp_share: float = .5
    yarn_waviness_mm: float = 0.
    samples_per_crossing: int = 24
    max_segment_mm: float = .008
    max_turn_radians: float = .20
    padding_crossings: int = 1
    seed: int = 20261011
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported hierarchy schema version")
        if not isinstance(self.draft, WeaveDraft):
            raise TypeError("draft must be WeaveDraft")
        if not isinstance(self.warp_yarn, YarnSpec) or not isinstance(self.weft_yarn, YarnSpec):
            raise TypeError("warp_yarn/weft_yarn must be YarnSpec")
        _integer(self.warp_count, "warp_count", 1)
        _integer(self.weft_count, "weft_count", 1)
        _integer(self.samples_per_crossing, "samples_per_crossing", 4)
        _integer(self.padding_crossings, "padding_crossings", 1)
        _integer(self.seed, "seed", 0)
        for key in ("warp_pitch_mm", "weft_pitch_mm", "max_segment_mm", "max_turn_radians"):
            _finite(getattr(self, key), key, positive=True)
        _finite(self.crossing_gap_mm, "crossing_gap_mm", nonnegative=True)
        _finite(self.yarn_waviness_mm, "yarn_waviness_mm", nonnegative=True)
        _finite(self.warp_crimp_share, "warp_crimp_share")
        if not 0 <= self.warp_crimp_share <= 1:
            raise ValueError("warp_crimp_share must lie in [0,1]")
        if self.max_turn_radians > .5:
            raise ValueError("max_turn_radians must be <= 0.5 for meaningful sampling")
        for name, pitch, yarn in (("warp", self.warp_pitch_mm, self.warp_yarn),
                                  ("weft", self.weft_pitch_mm, self.weft_yarn)):
            if pitch <= 2*(yarn.envelope_radius_mm+self.yarn_waviness_mm):
                raise ValueError(f"neighboring {name} yarn reference envelopes overlap")

    @property
    def crossing_center_distance_mm(self):
        return self.warp_yarn.envelope_radius_mm+self.weft_yarn.envelope_radius_mm+self.crossing_gap_mm

    def to_dict(self):
        d = asdict(self)
        d["draft"] = self.draft.to_dict()
        d["units"] = {"length": "mm", "twist": "signed_turns_per_parent_arclength_mm"}
        return _json_value(d)

    @classmethod
    def from_dict(cls, value):
        d = dict(value)
        units = d.pop("units", {"length": "mm", "twist": "signed_turns_per_parent_arclength_mm"})
        if units != {"length": "mm", "twist": "signed_turns_per_parent_arclength_mm"}:
            raise ValueError("unsupported units; conversion must be explicit")
        d["draft"] = WeaveDraft.from_dict(d["draft"])
        d["warp_yarn"] = YarnSpec.from_dict(d["warp_yarn"])
        d["weft_yarn"] = YarnSpec.from_dict(d["weft_yarn"])
        return cls(**d)


@dataclass(frozen=True)
class FiberCurve:
    points_mm: np.ndarray
    radii_mm: np.ndarray
    fiber_id: str
    yarn_id: str
    ply_id: str
    material_id: str
    family: str
    yarn_index: int
    ply_index: int
    fiber_index: int
    kind: str = "core"
    cross_section: str = "circle"

    def __post_init__(self):
        p = np.array(self.points_mm, dtype=float, copy=True)
        arclength_mm(p)
        r = np.array(self.radii_mm, dtype=float, copy=True)
        if r.shape != (len(p),) or not np.all(np.isfinite(r)) or np.any(r <= 0):
            raise ValueError("positive finite radius required at each vertex")
        if np.ptp(r) > 1e-14:
            raise ValueError("v2 initially supports constant circular radius per fiber")
        if self.cross_section != "circle":
            raise ValueError("v2 geometry initially represents circular fibers")
        for key in ("fiber_id", "yarn_id", "ply_id", "material_id", "family"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key):
                raise ValueError(f"{key} must be nonempty")
        for key in ("yarn_index", "ply_index", "fiber_index"):
            _integer(getattr(self, key), key, 0)
        # Immutable bytes backing prevents callers from re-enabling the numpy
        # WRITEABLE flag on a supposedly frozen geometry reference.
        p = np.frombuffer(p.tobytes(), dtype=np.float64).reshape(p.shape)
        r = np.frombuffer(r.tobytes(), dtype=np.float64)
        object.__setattr__(self, "points_mm", p)
        object.__setattr__(self, "radii_mm", r)

    @property
    def radius_mm(self):
        return float(self.radii_mm[0])

    @property
    def xyzw_mm(self):
        return np.column_stack((self.points_mm, self.radii_mm))

    def provenance(self):
        return {k: getattr(self, k) for k in (
            "fiber_id", "yarn_id", "ply_id", "material_id", "family", "yarn_index",
            "ply_index", "fiber_index", "kind", "cross_section")}


@dataclass
class HierarchyGeometry:
    fiber_records: tuple[FiberCurve, ...]
    yarns: dict[str, np.ndarray]
    plies: dict[str, np.ndarray]
    spec: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    curve_basis: str = "polyline"

    def __post_init__(self):
        self.fiber_records = tuple(self.fiber_records)
        if not self.fiber_records or self.curve_basis != "polyline":
            raise ValueError("nonempty explicit polyline geometry required")
        if len({r.fiber_id for r in self.fiber_records}) != len(self.fiber_records):
            raise ValueError("fiber IDs must be globally unique")
        for kind, parents in (("yarn", self.yarns), ("ply", self.plies)):
            for key, value in parents.items():
                arclength_mm(value)
        for r in self.fiber_records:
            if r.yarn_id not in self.yarns or r.ply_id not in self.plies:
                raise ValueError("each fiber must reference an existing yarn and ply")
        self.metadata.setdefault("schema_version", SCHEMA_VERSION)
        self.metadata.setdefault("length_unit", "mm")

    @property
    def fibers(self):
        return tuple(r.xyzw_mm for r in self.fiber_records)

    @property
    def provenance(self):
        return [r.provenance() for r in self.fiber_records]

    @property
    def bounds_mm(self):
        lower = np.min([np.min(r.points_mm-r.radius_mm, axis=0) for r in self.fiber_records], axis=0)
        upper = np.max([np.max(r.points_mm+r.radius_mm, axis=0) for r in self.fiber_records], axis=0)
        return np.stack((lower, upper))

    @property
    def material_ids(self):
        return tuple(sorted({r.material_id for r in self.fiber_records}))

    def summary(self):
        counts = {}
        for r in self.fiber_records:
            counts[r.material_id] = counts.get(r.material_id, 0)+1
        lengths = [float(arclength_mm(r.points_mm)[-1]) for r in self.fiber_records]
        return {"schema_version": SCHEMA_VERSION, "curve_basis": self.curve_basis,
                "yarn_count": len(self.yarns), "ply_count": len(self.plies),
                "fiber_count": len(self.fiber_records),
                "vertex_count": sum(len(r.points_mm) for r in self.fiber_records),
                "fiber_counts_by_material": counts,
                "total_fiber_length_mm": float(sum(lengths)),
                "cylinder_volume_proxy_mm3": float(sum(np.pi*r.radius_mm**2*l
                                                      for r, l in zip(self.fiber_records, lengths))),
                "bounds_mm": self.bounds_mm.tolist(), "metadata": self.metadata}


def _radial_excursion(fiber, s, seed, key):
    phase = (fiber.migration_phase_rad if fiber.migration_phase_rad is not None
             else _stable_phase(seed, key+"/migration"))
    dr = fiber.migration_amplitude_mm*np.cos(2*np.pi*s/fiber.migration_period_mm+phase)
    if fiber.loop_amplitude_mm:
        center = fiber.loop_center_fraction*s[-1]
        half = .5*fiber.loop_length_mm
        if center-half < 0 or center+half > s[-1]:
            raise ValueError("loop interval must lie entirely inside the parent ply")
        u = (s-(center-half))/fiber.loop_length_mm
        mask = (u >= 0) & (u <= 1)
        bump = np.zeros_like(s)
        bump[mask] = 64*u[mask]**3*(1-u[mask])**3
        dr = dr+fiber.loop_amplitude_mm*bump
    return dr


def _yarn_records(yarn, centerline, *, family, yarn_index, seed, initial_normal=None):
    yarn_id = f"{family}:{yarn_index:04d}:{yarn.id}"
    plies, records = {}, []
    ys = arclength_mm(centerline)
    _, yn, yb = rotation_minimizing_frames(centerline, initial_normal=initial_normal)
    for pidx, ply in enumerate(yarn.plies):
        ply_id = f"{yarn_id}/{ply.id}"
        pc = _sweep_from_frame(centerline, ply.offset_mm, yarn.ply_twist_per_mm,
                               yarn.ply_phase_rad, ys, yn, yb)
        plies[ply_id] = pc
        s = arclength_mm(pc)
        # Align the first ply normal with the transported yarn cross-section.
        # This removes coordinate-axis changes between hierarchy levels.
        _, pn, pb = rotation_minimizing_frames(pc, initial_normal=yn[0])
        for fidx, fiber in enumerate(ply.fibers):
            fid = f"{ply_id}/{fiber.id}"
            dr = _radial_excursion(fiber, s, seed, fid)
            fc = _sweep_from_frame(pc, fiber.offset_mm, ply.fiber_twist_per_mm,
                                   ply.fiber_phase_rad, s, pn, pb, dr)
            records.append(FiberCurve(fc, np.full(len(fc), fiber.radius_mm), fid,
                                      yarn_id, ply_id, fiber.material_id, family,
                                      yarn_index, pidx, fidx,
                                      "loop_excursion" if fiber.loop_amplitude_mm else "core"))
    return yarn_id, plies, records


def build_yarn(yarn: YarnSpec, centerline_mm, *, family="standalone", yarn_index=0,
               seed=20261011, initial_normal=None):
    """Build one explicit nested yarn on a caller-supplied centerline.

    This calibration entry point does not refine the supplied centerline.
    Sampling/clearance diagnostics remain the caller's responsibility.
    """
    if not isinstance(yarn, YarnSpec):
        raise TypeError("yarn must be YarnSpec")
    _integer(yarn_index, "yarn_index")
    _integer(seed, "seed")
    p = np.array(centerline_mm, dtype=float, copy=True)
    arclength_mm(p)
    yid, plies, fibers = _yarn_records(yarn, p, family=family, yarn_index=yarn_index,
                                     seed=seed, initial_normal=initial_normal)
    return HierarchyGeometry(tuple(fibers), {yid: p}, plies,
                             {"kind": "standalone_yarn", "yarn": yarn.to_dict(), "seed": int(seed)},
                             {"centerline_sampling": "caller_supplied", "geometry_tileable": False,
                              "physical_mechanics_solved": False})


def _centerline(spec, family, yarn_index, samples_per_crossing):
    is_warp = family == "warp"
    pitch = spec.weft_pitch_mm if is_warp else spec.warp_pitch_mm
    cross_count = spec.weft_count if is_warp else spec.warp_count
    q = np.linspace(-spec.padding_crossings, cross_count-1+spec.padding_crossings,
                    (cross_count-1+2*spec.padding_crossings)*samples_per_crossing+1)
    s = q*pitch
    amplitude = spec.crossing_center_distance_mm*(spec.warp_crimp_share if is_warp else 1-spec.warp_crimp_share)
    z = periodic_crossing_height(s, draft=spec.draft, family=family, yarn_index=yarn_index,
                                crossing_pitch_mm=pitch, amplitude_mm=amplitude)
    k = np.floor(q).astype(int)
    u = q-k
    period = spec.draft.weft_repeat if is_warp else spec.draft.warp_repeat
    transverse_period = spec.draft.warp_repeat if is_warp else spec.draft.weft_repeat
    coeff = np.array([np.sin(_stable_phase(spec.seed,
                      f"waviness/{family}/{yarn_index % transverse_period}/{j % period}")) for j in k])
    lateral = spec.yarn_waviness_mm*coeff*64*u**3*(1-u)**3
    xoff = .5*(spec.warp_count-1)*spec.warp_pitch_mm
    yoff = .5*(spec.weft_count-1)*spec.weft_pitch_mm
    if is_warp:
        return np.column_stack((yarn_index*spec.warp_pitch_mm-xoff+lateral, s-yoff, z))
    return np.column_stack((s-xoff, yarn_index*spec.weft_pitch_mm-yoff+lateral, z))


def _sampling_stats(records, plies, yarns, spec):
    max_length, max_turn = 0., 0.
    for record in records:
        d = np.diff(record.points_mm, axis=0)
        norm = np.linalg.norm(d, axis=1)
        max_length = max(max_length, float(norm.max()))
        t = d/norm[:, None]
        if len(t) > 1:
            max_turn = max(max_turn, float(np.max(np.arccos(np.clip(np.sum(t[:-1]*t[1:], axis=1), -1., 1.)))))
    max_phase = 0.
    for family, template in (("warp", spec.warp_yarn), ("weft", spec.weft_yarn)):
        for yid, yc in yarns.items():
            if not yid.startswith(family+":"):
                continue
            max_phase = max(max_phase, float(np.max(np.diff(arclength_mm(yc))))*abs(template.ply_twist_per_mm)*2*np.pi)
            for ply in template.plies:
                pc = plies[yid+"/"+ply.id]
                ds = float(np.max(np.diff(arclength_mm(pc))))
                max_phase = max(max_phase, ds*abs(ply.fiber_twist_per_mm)*2*np.pi)
                for f in ply.fibers:
                    if f.migration_amplitude_mm:
                        max_phase = max(max_phase, ds/f.migration_period_mm*2*np.pi)
                    if f.loop_amplitude_mm:
                        # At least 24 samples along the nonperiodic loop interval.
                        max_phase = max(max_phase, ds/f.loop_length_mm*2*np.pi)
    return {"max_fiber_segment_mm": max_length, "max_polyline_turn_radians": max_turn,
            "max_parent_twist_or_migration_phase_step_rad": max_phase}


def build_hierarchy(spec: FabricSpec):
    """Generate a finite patch, refining until explicit sampling gates pass.

    Draft crossing order is prescribed with C2 interpolation. Envelope checks
    in the reference sections do not guarantee global separation after sweep;
    call :func:`audit_clearance` on the actual generated curves.
    """
    if not isinstance(spec, FabricSpec):
        raise TypeError("spec must be FabricSpec")
    n = spec.samples_per_crossing
    for refinement in range(9):
        records, yarns, plies = [], {}, {}
        for family, count, template in (("warp", spec.warp_count, spec.warp_yarn),
                                         ("weft", spec.weft_count, spec.weft_yarn)):
            for index in range(count):
                centerline = _centerline(spec, family, index, n)
                yid, p, r = _yarn_records(template, centerline, family=family,
                                         yarn_index=index, seed=spec.seed,
                                         initial_normal=(0., 0., 1.))
                yarns[yid] = centerline
                plies.update(p)
                records.extend(r)
        stats = _sampling_stats(records, plies, yarns, spec)
        if (stats["max_fiber_segment_mm"] <= spec.max_segment_mm
                and stats["max_polyline_turn_radians"] <= spec.max_turn_radians
                and stats["max_parent_twist_or_migration_phase_step_rad"] <= np.pi/12):
            break
        if sum(len(r.points_mm) for r in records) > 2_000_000:
            raise RuntimeError("sampling refinement would exceed practical geometry budget")
        n *= 2
    else:
        raise RuntimeError("hierarchy sampling gates did not converge after eight refinements")
    metadata = {
        "length_unit": "mm", "schema_version": SCHEMA_VERSION,
        "draft_diagnostics": spec.draft.diagnostics(),
        "visible_size_mm": [spec.warp_count*spec.warp_pitch_mm, spec.weft_count*spec.weft_pitch_mm],
        "crossing_center_distance_mm": spec.crossing_center_distance_mm,
        "nominal_crossing_envelope_gap_mm": spec.crossing_gap_mm,
        "sampling_refinements": refinement, "samples_per_crossing_used": n, **stats,
        "geometry_tileable": False,
        "periodicity_scope": "Draft and unperturbed/wavy yarn centerlines repeat; nested twist/migration phases are not forced to close.",
        "physical_mechanics_solved": False,
        "clearance_scope": "Reference-section bounds only; run actual polyline capsule audit for global separation.",
        "flyaway_scope": "Optional C2 outward loop excursion of an existing fiber; no duplicated fiber objects, but length/volume can change. No mass conservation or fitted staple statistics.",
    }
    return HierarchyGeometry(tuple(records), yarns, plies, spec.to_dict(), metadata)


def orientation_statistics(geometry: HierarchyGeometry):
    """Length-weighted tangent statistics for assessing optical correspondence.

    The tensor is the second moment of *unoriented* fiber tangents. It is not
    a BSDF: cross-section, material, spatial correlations, and masking are
    deliberately not integrated out into an appearance claim.
    """
    groups = {"all": list(geometry.fiber_records)}
    for family in sorted({f.family for f in geometry.fiber_records}):
        groups["family:"+family] = [f for f in geometry.fiber_records if f.family == family]
    for material in geometry.material_ids:
        groups["material:"+material] = [f for f in geometry.fiber_records if f.material_id == material]
    out = {}
    for key, fibers in groups.items():
        second, total, tilt2 = np.zeros((3, 3)), 0., 0.
        for f in fibers:
            d = np.diff(f.points_mm, axis=0)
            ds = np.linalg.norm(d, axis=1)
            t = d/ds[:, None]
            second += np.einsum("n,ni,nj->ij", ds, t, t)
            total += float(ds.sum())
            tilt2 += float(np.sum(ds*np.arcsin(np.clip(np.abs(t[:, 2]), 0, 1))**2))
        out[key] = {"total_fiber_length_mm": total,
                    "tangent_second_moment": (second/total).tolist(),
                    "tensor_eigenvalues": np.linalg.eigvalsh(second/total).tolist(),
                    "rms_out_of_plane_tilt_deg": float(np.sqrt(tilt2/total)*180/np.pi)}
    return out


def compare_sampling_refinement(spec: FabricSpec, factors=(1, 2, 4)):
    """Compare complete nested geometry at successively tighter sampling.

    This is an observed discretization study, not an a priori error bound to
    a continuum yarn model. For two generated polylines, interpolation on the
    union of their parameter knots bounds their pointwise difference and hence
    their mutual Hausdorff distance. Constant fiber radii are identical.
    """
    factors = tuple(_integer(v, "refinement factor", 1) for v in factors)
    if len(factors) < 2 or factors[0] != 1 or any(b <= a for a, b in zip(factors[:-1], factors[1:])):
        raise ValueError("refinement factors must increase strictly from one")
    baseline = build_hierarchy(spec)
    geometries = [baseline]
    baseline_samples = baseline.metadata["samples_per_crossing_used"]
    for factor in factors[1:]:
        # Scale the actual accepted baseline mesh, not its input request. The
        # latter can otherwise round two requested levels to the same mesh.
        refined = replace(spec, samples_per_crossing=baseline_samples*factor,
                          max_segment_mm=spec.max_segment_mm/factor,
                          max_turn_radians=spec.max_turn_radians/factor)
        geometries.append(build_hierarchy(refined))
    comparisons = []
    for i, coarse in enumerate(geometries[:-1]):
        fine = geometries[i+1]
        worst, weighted_sum, weight = 0., 0., 0
        for a, b in zip(coarse.fiber_records, fine.fiber_records):
            if a.fiber_id != b.fiber_id or a.radius_mm != b.radius_mm:
                raise ValueError("refinements changed physical fiber identity/radius")
            ua, ub = np.linspace(0, 1, len(a.points_mm)), np.linspace(0, 1, len(b.points_mm))
            u = np.unique(np.r_[ua, ub])
            pa = np.column_stack([np.interp(u, ua, a.points_mm[:, k]) for k in range(3)])
            pb = np.column_stack([np.interp(u, ub, b.points_mm[:, k]) for k in range(3)])
            d2 = np.sum((pa-pb)**2, axis=1)
            worst = max(worst, float(np.sqrt(d2.max())))
            weighted_sum += float(d2.sum())
            weight += len(d2)
        lc = sum(arclength_mm(r.points_mm)[-1] for r in coarse.fiber_records)
        lf = sum(arclength_mm(r.points_mm)[-1] for r in fine.fiber_records)
        qc = np.array(orientation_statistics(coarse)["all"]["tangent_second_moment"])
        qf = np.array(orientation_statistics(fine)["all"]["tangent_second_moment"])
        comparisons.append({"coarse_factor": factors[i], "fine_factor": factors[i+1],
                            "max_parameter_matched_centerline_distance_mm": worst,
                            "rms_union_knot_distance_mm": float(np.sqrt(weighted_sum/weight)),
                            "relative_total_length_change": float((lf-lc)/lf),
                            "tangent_tensor_frobenius_change": float(np.linalg.norm(qf-qc))})
    return {"factors": list(factors),
            "vertices": [sum(len(r.points_mm) for r in g.fiber_records) for g in geometries],
            "samples_per_crossing": [g.metadata["samples_per_crossing_used"] for g in geometries],
            "comparisons": comparisons,
            "scope": "Observed complete hierarchy discretization; distance bounds relate generated polylines, not an uncomputed continuum limit."}


def audit_clearance(geometry: HierarchyGeometry, *, probe_margin_mm=.003,
                    max_candidate_pairs=8_000_000, batch_size=100_000):
    """Continuous DIFFERENT-fiber separation audit for constant-radius polylines.

    Each segment is a closed capsule. A global midpoint/half-length broad phase
    is conservative; every omitted pair has clearance > probe_margin_mm.
    Exact segment distances are evaluated for retained pairs. This certifies
    the generated polyline tube union, not an interpolating cubic spline,
    equal-section packing, same-fiber self-contact, or mechanical equilibrium.
    A negative distance proves overlap for the capsule representation.
    """
    from .geometry import segment_distance  # previously independently validated
    _finite(probe_margin_mm, "probe_margin_mm", positive=True)
    _integer(batch_size, "batch_size", 1)
    _integer(max_candidate_pairs, "max_candidate_pairs", 1)
    starts, ends, radii, ids = [], [], [], []
    for i, r in enumerate(geometry.fiber_records):
        starts.append(r.points_mm[:-1])
        ends.append(r.points_mm[1:])
        radii.append(np.full(len(r.points_mm)-1, r.radius_mm))
        ids.append(np.full(len(r.points_mm)-1, i, dtype=int))
    a, b = np.concatenate(starts), np.concatenate(ends)
    radius, fiber_id = np.concatenate(radii), np.concatenate(ids)
    half = np.linalg.norm(b-a, axis=1)/2
    midpoint = (a+b)/2
    search = 2*float(np.max(radius+half))+probe_margin_mm
    tree = cKDTree(midpoint)
    # Estimate count before allocating the pair array to bound memory use.
    all_neighbors = int(tree.count_neighbors(tree, search))
    count_estimate = (all_neighbors-len(midpoint))//2
    if count_estimate > max_candidate_pairs:
        raise RuntimeError(f"clearance broad phase would allocate {count_estimate} pairs; refine scope or raise explicit budget")
    pairs = tree.query_pairs(search, output_type="ndarray")
    pairs = pairs[fiber_id[pairs[:, 0]] != fiber_id[pairs[:, 1]]]
    minimum = np.inf
    overlapping, close, tested = 0, 0, 0
    worst_pair = None
    for k in range(0, len(pairs), batch_size):
        p = pairs[k:k+batch_size]
        i, j = p[:, 0], p[:, 1]
        d = segment_distance(a[i], b[i], a[j], b[j])-radius[i]-radius[j]
        if len(d) and float(d.min()) < minimum:
            loc = int(np.argmin(d))
            minimum = float(d[loc])
            worst_pair = [geometry.fiber_records[fiber_id[i[loc]]].fiber_id,
                          geometry.fiber_records[fiber_id[j[loc]]].fiber_id]
        overlapping += int(np.sum(d <= 0))
        close += int(np.sum(d <= probe_margin_mm))
        tested += len(p)
    bound = min(minimum, probe_margin_mm)
    return {"certified_separated": bool(bound > 0),
            "minimum_clearance_lower_bound_mm": float(bound),
            "minimum_tested_clearance_mm": float(minimum) if np.isfinite(minimum) else None,
            "overlapping_capsule_pairs": overlapping,
            "pairs_within_probe_margin": close,
            "tested_segment_pairs": tested, "total_segments": len(a),
            "broadphase_radius_mm": search, "probe_margin_mm": probe_margin_mm,
            "closest_tested_fiber_pair": worst_pair,
            "scope": "All pairs of DIFFERENT constant-radius polyline fibers; same-fiber self-contact excluded."}


def _pack_curves(curves):
    curves = list(curves)
    offsets = np.r_[0, np.cumsum([len(c) for c in curves])].astype(np.int64)
    return np.concatenate(curves), offsets


def _unpack_curves(points, offsets):
    points, offsets = np.asarray(points), np.asarray(offsets)
    if (offsets.ndim != 1 or len(offsets) < 2 or offsets[0] != 0
            or offsets[-1] != len(points) or np.any(np.diff(offsets) < 2)):
        raise ValueError("invalid ragged curve offsets")
    return [points[int(a):int(b)] for a, b in zip(offsets[:-1], offsets[1:])]


def save_hierarchy(folder, geometry: HierarchyGeometry):
    """Write numeric NPZ without pickle plus versioned JSON provenance/schema."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fpoints, foffsets = _pack_curves(geometry.fibers)
    ynames, pnames = sorted(geometry.yarns), sorted(geometry.plies)
    ypoints, yoffsets = _pack_curves(geometry.yarns[k] for k in ynames)
    ppoints, poffsets = _pack_curves(geometry.plies[k] for k in pnames)
    np.savez_compressed(folder/"hierarchy_geometry.npz", fibers=fpoints, fiber_offsets=foffsets,
                        yarns=ypoints, yarn_offsets=yoffsets, plies=ppoints, ply_offsets=poffsets)
    meta = {"schema_version": SCHEMA_VERSION, "curve_basis": geometry.curve_basis,
            "length_unit": "mm", "spec": geometry.spec, "metadata": geometry.metadata,
            "fiber_provenance": geometry.provenance, "yarn_ids": ynames, "ply_ids": pnames,
            "npz_sha256": hashlib.sha256((folder/"hierarchy_geometry.npz").read_bytes()).hexdigest()}
    (folder/"hierarchy_geometry.json").write_text(json.dumps(meta, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return folder/"hierarchy_geometry.json"


def load_hierarchy(folder):
    folder = Path(folder)
    meta = json.loads((folder/"hierarchy_geometry.json").read_text(encoding="utf-8"))
    if meta.get("schema_version") != SCHEMA_VERSION or meta.get("length_unit") != "mm":
        raise ValueError("unsupported geometry schema/units")
    path = folder/"hierarchy_geometry.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta["npz_sha256"]:
        raise ValueError("numeric geometry hash does not match its provenance manifest")
    with np.load(path, allow_pickle=False) as z:
        fc = _unpack_curves(z["fibers"], z["fiber_offsets"])
        yc = _unpack_curves(z["yarns"], z["yarn_offsets"])
        pc = _unpack_curves(z["plies"], z["ply_offsets"])
    if len(fc) != len(meta["fiber_provenance"]) or len(yc) != len(meta["yarn_ids"]) or len(pc) != len(meta["ply_ids"]):
        raise ValueError("curve/provenance counts do not match")
    records = tuple(FiberCurve(p[:, :3], p[:, 3], **record)
                    for p, record in zip(fc, meta["fiber_provenance"]))
    return HierarchyGeometry(records, dict(zip(meta["yarn_ids"], yc)),
                             dict(zip(meta["ply_ids"], pc)), meta["spec"], meta["metadata"], meta["curve_basis"])


def main(argv=None):
    """Reproducible configuration -> geometry -> audit entry point."""
    import argparse
    import time
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--skip-clearance", action="store_true",
                        help="Save geometry without certifying different-fiber separation")
    parser.add_argument("--max-candidate-pairs", type=int, default=8_000_000)
    args = parser.parse_args(argv)
    spec = FabricSpec.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    t0 = time.perf_counter()
    geometry = build_hierarchy(spec)
    build_seconds = time.perf_counter()-t0
    save_hierarchy(args.out, geometry)
    summary = geometry.summary()
    summary["build_seconds"] = build_seconds
    summary["orientation_statistics"] = orientation_statistics(geometry)
    summary["config_sha256"] = hashlib.sha256(args.config.read_bytes()).hexdigest()
    if args.skip_clearance:
        summary["clearance_audit"] = {"status": "explicitly_skipped", "certified_separated": None}
    else:
        t0 = time.perf_counter()
        summary["clearance_audit"] = audit_clearance(geometry, max_candidate_pairs=args.max_candidate_pairs)
        summary["clearance_audit_seconds"] = time.perf_counter()-t0
    (args.out/"hierarchy_metrics.json").write_text(
        json.dumps(_json_value(summary), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(_json_value({key: summary[key] for key in (
        "fiber_count", "vertex_count", "build_seconds", "clearance_audit")})))
    return 0 if args.skip_clearance or summary["clearance_audit"]["certified_separated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
