"""Versioned fiber geometry / optical solver interface.

Lengths in the scene are millimeters; wavelengths are vacuum nanometers.
The contract preserves fiber identities and constituent materials.  No effective
index of a blend, SGGX fit, or 3D-to-2D wave equivalence is inferred here.

Mitsuba 3.9.1's audited hair BSDF uses radius-normalized absorption.  Its local
frame is intended for bsplinecurve, not linearcurve.  A polyline export therefore
requires an explicit smoothing tolerance and reports an analytic centerline
error bound.  The scalar-wavelength RGB backend is a monochromatic proxy, not a
spectral color-rendering calculation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
from typing import Mapping, Sequence
import hashlib
import json
import math
import numpy as np


SCENE_SCHEMA = "textile.optical_scene/2.0"
EXPORT_SCHEMA = "textile.mitsuba_export/2.0"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _provenance(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("provenance must be a JSON object")
    return _canonical(value)


def _readonly(value, shape_tail=None):
    a = np.asarray(value, dtype=np.float64)
    if not np.isfinite(a).all():
        raise ValueError("all array entries must be finite")
    if shape_tail is not None and a.shape[-len(shape_tail):] != shape_tail:
        raise ValueError(f"array must end in shape {shape_tail}")
    # bytes backing prevents setflags(write=True), unlike a read-only owning array.
    return np.frombuffer(np.ascontiguousarray(a).tobytes(), dtype=np.float64).reshape(a.shape)


def _positive(value, name):
    x = float(value)
    if not np.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return x


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _unit(value):
    a = np.asarray(value, dtype=float)
    if a.shape != (3,) or not np.isfinite(a).all() or np.linalg.norm(a) == 0:
        raise ValueError("expected a finite nonzero three-vector")
    return a / np.linalg.norm(a)


@dataclass(frozen=True)
class MaterialSpectrum:
    """Passive scalar n+i*k for the exp(-i omega t) convention.

    Linear interpolation only inside the supplied wavelength interval.  These
    samples do not establish causality/Kramers-Kronig consistency or birefringence.
    Source/status are mandatory so synthetic constants cannot masquerade as data.
    """
    material_id: str
    wavelength_nm: tuple[float, ...]
    n_real: tuple[float, ...]
    kappa: tuple[float, ...]
    source: str
    data_status: str = "synthetic"
    provenance_json: str = "{}"

    def __post_init__(self):
        _identifier(self.material_id, "material_id")
        _identifier(self.source, "source")
        if self.data_status not in ("synthetic", "measured", "literature"):
            raise ValueError("data_status must be synthetic, measured, or literature")
        arrays = [np.asarray(v, float) for v in
                  (self.wavelength_nm, self.n_real, self.kappa)]
        if any(a.ndim != 1 for a in arrays) or len(arrays[0]) < 2:
            raise ValueError("spectra require at least two 1D wavelength samples")
        if any(len(a) != len(arrays[0]) or not np.isfinite(a).all() for a in arrays):
            raise ValueError("spectral arrays must have equal length and finite values")
        lam, nr, ki = arrays
        if np.any(lam <= 0) or np.any(np.diff(lam) <= 0):
            raise ValueError("wavelength_nm must be positive and strictly increasing")
        if np.any(nr <= 0) or np.any(ki < 0):
            raise ValueError("positive real index and passive kappa >= 0 are required")
        for name, a in zip(("wavelength_nm", "n_real", "kappa"), arrays):
            object.__setattr__(self, name, tuple(map(float, a)))
        object.__setattr__(self, "provenance_json", _provenance(self.provenance_json))

    @classmethod
    def from_absorption(cls, material_id, wavelength_nm, n_real, absorption_per_mm,
                        source, data_status="synthetic", provenance_json="{}"):
        lam = np.asarray(wavelength_nm, dtype=float)
        nr = np.broadcast_to(np.asarray(n_real, dtype=float), lam.shape)
        mu = np.broadcast_to(np.asarray(absorption_per_mm, dtype=float), lam.shape)
        kappa = mu * (lam * 1e-6) / (4 * np.pi)
        return cls(material_id, tuple(lam), tuple(nr), tuple(kappa), source,
                   data_status, provenance_json)

    def at(self, wavelength_nm):
        lam = _positive(wavelength_nm, "vacuum wavelength_nm")
        if not self.wavelength_nm[0] <= lam <= self.wavelength_nm[-1]:
            raise ValueError(f"{self.material_id}: wavelength outside supplied spectral domain")
        nr = float(np.interp(lam, self.wavelength_nm, self.n_real))
        ki = float(np.interp(lam, self.wavelength_nm, self.kappa))
        return {"n_real": nr, "kappa": ki, "n_complex": complex(nr, ki),
                "absorption_per_mm": 4 * np.pi * ki / (lam * 1e-6)}

    def to_dict(self):
        return {"material_id": self.material_id, "wavelength_nm": self.wavelength_nm,
                "n_real": self.n_real, "kappa": self.kappa, "source": self.source,
                "data_status": self.data_status,
                "provenance_json": self.provenance_json}


@dataclass(frozen=True, eq=False)
class OpticalFiber:
    fiber_id: str
    yarn_id: str
    ply_id: str
    material_id: str
    points_mm: np.ndarray
    radius_mm: float
    curve_basis: str = "polyline"
    cross_section: str = "circle"
    family: str = "unspecified"
    provenance_json: str = "{}"

    def __post_init__(self):
        for name in ("fiber_id", "yarn_id", "ply_id", "material_id", "family"):
            _identifier(getattr(self, name), name)
        if self.curve_basis not in ("polyline", "cubic_bspline"):
            raise ValueError("unsupported curve basis")
        if self.cross_section not in ("circle", "ellipse", "arbitrary"):
            raise ValueError("unknown cross-section declaration")
        points = _readonly(self.points_mm, (3,))
        required = 2 if self.curve_basis == "polyline" else 4
        if points.ndim != 2 or len(points) < required:
            raise ValueError(f"{self.curve_basis} requires at least {required} points")
        if np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) <= 1e-15):
            raise ValueError("zero-length control-polyline segments are forbidden")
        object.__setattr__(self, "points_mm", points)
        object.__setattr__(self, "radius_mm", _positive(self.radius_mm, "radius_mm"))
        object.__setattr__(self, "provenance_json", _provenance(self.provenance_json))

    def to_dict(self):
        return {"fiber_id": self.fiber_id, "yarn_id": self.yarn_id,
                "ply_id": self.ply_id, "material_id": self.material_id,
                "points_mm": self.points_mm.tolist(), "radius_mm": self.radius_mm,
                "curve_basis": self.curve_basis, "cross_section": self.cross_section,
                "family": self.family, "provenance_json": self.provenance_json}


@dataclass(frozen=True, eq=False)
class OpticalScene:
    materials: tuple[MaterialSpectrum, ...]
    fibers: tuple[OpticalFiber, ...]
    background_n: float = 1.0
    schema: str = SCENE_SCHEMA
    length_unit: str = "mm"
    wavelength_unit: str = "nm_vacuum"
    provenance_json: str = "{}"

    def __post_init__(self):
        if self.schema != SCENE_SCHEMA or self.length_unit != "mm" or self.wavelength_unit != "nm_vacuum":
            raise ValueError("unsupported schema/units; explicit conversion required")
        mats, fibers = tuple(self.materials), tuple(self.fibers)
        if not mats or not fibers or any(not isinstance(m, MaterialSpectrum) for m in mats):
            raise ValueError("scene requires MaterialSpectrum values and at least one fiber")
        if any(not isinstance(f, OpticalFiber) for f in fibers):
            raise ValueError("scene fibers must be OpticalFiber values")
        ids = [m.material_id for m in mats]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate material_id")
        if len({f.fiber_id for f in fibers}) != len(fibers):
            raise ValueError("duplicate fiber_id")
        if any(f.material_id not in ids for f in fibers):
            raise ValueError("fiber refers to an undefined material")
        # A ply must have a unique yarn parent; a yarn has one family.
        parents, families = {}, {}
        for f in fibers:
            if f.ply_id in parents and parents[f.ply_id] != f.yarn_id:
                raise ValueError("a ply_id cannot have multiple yarn parents")
            if f.yarn_id in families and families[f.yarn_id] != f.family:
                raise ValueError("a yarn_id cannot have multiple families")
            parents[f.ply_id], families[f.yarn_id] = f.yarn_id, f.family
        object.__setattr__(self, "materials", mats)
        object.__setattr__(self, "fibers", fibers)
        object.__setattr__(self, "background_n", _positive(self.background_n, "background_n"))
        object.__setattr__(self, "provenance_json", _provenance(self.provenance_json))

    @property
    def material_map(self):
        return {m.material_id: m for m in self.materials}

    @property
    def bounds_mm(self):
        return np.array([np.min([f.points_mm.min(axis=0)-f.radius_mm for f in self.fibers], axis=0),
                         np.max([f.points_mm.max(axis=0)+f.radius_mm for f in self.fibers], axis=0)])

    def to_dict(self):
        return {"schema": self.schema, "length_unit": self.length_unit,
                "wavelength_unit": self.wavelength_unit, "background_n": self.background_n,
                "provenance_json": self.provenance_json,
                "materials": [m.to_dict() for m in self.materials],
                "fibers": [f.to_dict() for f in self.fibers]}

    @property
    def sha256(self):
        return hashlib.sha256(_canonical(self.to_dict()).encode("utf-8")).hexdigest()

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        payload["content_sha256"] = self.sha256
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, payload):
        d = dict(payload)
        expected = d.pop("content_sha256", None)
        d["materials"] = tuple(MaterialSpectrum(**m) for m in d["materials"])
        d["fibers"] = tuple(OpticalFiber(**f) for f in d["fibers"])
        scene = cls(**d)
        if expected is not None and scene.sha256 != expected:
            raise ValueError("scene content hash mismatch")
        return scene

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def from_hierarchy(geometry, materials, background_n=1.0):
    """Adapt the v2 hierarchy's frozen records, retaining all parent labels."""
    fibers = []
    for f in geometry.fiber_records:
        radii = np.asarray(f.radii_mm, dtype=float)
        if radii.ndim != 1 or len(radii) != len(f.points_mm) or not np.all(radii == radii[0]):
            raise ValueError("variable fiber radius requires a separately calibrated optical adapter")
        provenance = {name: getattr(f, name) for name in
                      ("yarn_index", "ply_index", "fiber_index", "kind") if hasattr(f, name)}
        fibers.append(OpticalFiber(f.fiber_id, f.yarn_id, f.ply_id, f.material_id,
                                  f.points_mm, float(radii[0]), geometry.curve_basis,
                                  f.cross_section, f.family, _canonical(provenance)))
    provenance = {"generator": "textile_sim.hierarchy", "geometry_spec": geometry.spec,
                  "geometry_metadata": geometry.metadata,
                  "material_assignment": "explicit fiber labels; no effective-medium blend"}
    return OpticalScene(tuple(materials), tuple(fibers), background_n,
                        provenance_json=_canonical(provenance))


def polyline_bspline_controls(points_mm):
    """Return endpoint-preserving uniform cubic controls and a rigorous bound.

    On segment P1->P2, Q(t)-L(t) = B0(t) Delta2 P0 + B3(t) Delta2 P1.
    Both basis weights are nonnegative and B0+B3 <= 1/6. Thus max norm of
    second control difference / 6 bounds centerline displacement everywhere.
    This is not a contact/surface-error certificate for the resulting tubes.
    """
    p = np.asarray(points_mm, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2 or not np.isfinite(p).all():
        raise ValueError("finite polyline required")
    c = np.vstack((2*p[0]-p[1], p, 2*p[-1]-p[-2]))
    bound = float(np.max(np.linalg.norm(np.diff(c, n=2, axis=0), axis=1))/6)
    return c, bound


def _hair_parameters(material, radius_mm, wavelength_nm, background_n,
                     longitudinal_roughness, azimuthal_roughness, max_kappa_ratio):
    optical = material.at(wavelength_nm)
    if optical["n_real"] <= background_n:
        raise ValueError("Mitsuba hair bridge requires fiber n_real > background_n")
    if optical["kappa"] / optical["n_real"] > max_kappa_ratio:
        raise ValueError("strong absorption outside declared real-Fresnel hair approximation")
    for x in (longitudinal_roughness, azimuthal_roughness):
        if not np.isfinite(x) or not 0 < x < 1:
            raise ValueError("hair roughness must lie strictly in (0,1)")
    return {"type": "hair", "int_ior": optical["n_real"], "ext_ior": background_n,
            "sigma_a": {"type": "uniform", "value": optical["absorption_per_mm"]*radius_mm},
            "longitudinal_roughness": float(longitudinal_roughness),
            "azimuthal_roughness": float(azimuthal_roughness), "scale_tilt": 0.0}


def export_mitsuba(scene, output_directory, wavelength_nm, *, max_smoothing_error_mm,
                   longitudinal_roughness=.18, azimuthal_roughness=.20,
                   max_kappa_ratio=.01):
    """Export separate bsplinecurve files for each (material, radius) pair.

    No renderer import is needed to export. The manifest records the exact scene
    hash, group provenance, wavelength-specific physical constants and sigma_a.
    Caller must explicitly choose a tolerated polyline smoothing displacement.
    """
    tol = float(max_smoothing_error_mm)
    if not np.isfinite(tol) or tol < 0:
        raise ValueError("max_smoothing_error_mm must be finite and nonnegative")
    max_kappa_ratio = _positive(max_kappa_ratio, "max_kappa_ratio")
    groups, converted = defaultdict(list), {}
    for f in scene.fibers:
        if f.cross_section != "circle":
            raise ValueError(f"{f.fiber_id}: hair export supports circular fibers only")
        controls, bound = (polyline_bspline_controls(f.points_mm) if f.curve_basis == "polyline"
                           else (f.points_mm, 0.0))
        if bound > tol + 1e-14:
            raise ValueError(f"{f.fiber_id}: smoothing bound {bound:g} mm exceeds {tol:g} mm")
        with np.errstate(over="ignore", under="ignore"):
            quantized_controls = controls.astype(np.float32)
            quantized_radius = np.float32(f.radius_mm)
        if not np.isfinite(quantized_controls).all() or not np.isfinite(quantized_radius) or quantized_radius <= 0:
            raise ValueError("geometry outside pinned renderer's finite positive float32 domain")
        converted[f.fiber_id] = (controls, bound)
        groups[(f.material_id, f.radius_mm)].append(f)
    # Validate every material before writing any output.
    parameters = {key: _hair_parameters(scene.material_map[key[0]], key[1], wavelength_nm,
                  scene.background_n, longitudinal_roughness, azimuthal_roughness,
                  max_kappa_ratio) for key in groups}
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (key, fibers) in enumerate(sorted(groups.items())):
        filename = f"group_{i:04d}.curves"
        path = directory/filename
        with path.open("w", encoding="utf-8") as stream:
            for f in fibers:
                p, bound = converted[f.fiber_id]
                np.savetxt(stream, np.column_stack((p, np.full(len(p), f.radius_mm))), fmt="%.17g")
                stream.write("\n")
        m = scene.material_map[key[0]]
        optical = m.at(wavelength_nm)
        # Pinned bsplinecurve.cpp reads InputFloat=float. Cubic basis weights
        # are nonnegative and sum to one, so max control quantization bounds
        # the centerline change caused by float32 storage.
        quantization_bound = max(float(np.max(np.linalg.norm(
            converted[f.fiber_id][0].astype(np.float32).astype(float)-converted[f.fiber_id][0],
            axis=1))) for f in fibers)
        radius_quantization = abs(float(np.float32(key[1]))-key[1])
        rows.append({"filename": filename, "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "material_id": key[0], "radius_mm": key[1],
                     "fiber_ids": [f.fiber_id for f in fibers],
                     "fiber_count": len(fibers), "bsdf": parameters[key],
                     "n_real": optical["n_real"], "kappa": optical["kappa"],
                     "absorption_per_mm": optical["absorption_per_mm"],
                     "material_source": m.source, "data_status": m.data_status,
                     "max_centerline_smoothing_bound_mm": max(converted[f.fiber_id][1] for f in fibers),
                     "float32_centerline_quantization_bound_mm": quantization_bound,
                     "float32_radius_quantization_bound_mm": radius_quantization,
                     "source_bases": sorted({f.curve_basis for f in fibers})})
    manifest = {"schema": EXPORT_SCHEMA, "scene_schema": scene.schema,
                "scene_sha256": scene.sha256, "scene_units": "mm",
                "wavelength_nm_vacuum": float(wavelength_nm), "background_n": scene.background_n,
                "mitsuba_version": "3.9.1", "shape": "bsplinecurve", "groups": rows,
                "bounds_mm": scene.bounds_mm.tolist(),
                "max_smoothing_error_mm": tol, "max_kappa_over_n": max_kappa_ratio,
                "spectral_mode": "single-wavelength physical parameters in RGB scalar proxy",
                "absorption_mapping": "sigma_a_shader = mu_a_per_mm * radius_mm",
                "limitations": ["real-index Fresnel with Beer absorption; no complex-index interface",
                   "centerline smoothing bound is not a tube-contact certificate",
                   "no polarization, wavelength integration, or wave-interference transport",
                   "no spectral extrapolation; no effective refractive index assigned to blends"]}
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
    (directory/"manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


def mitsuba_scene_dictionary(export_directory, config):
    """Reuse the audited light/camera rig while retaining per-group BSDFs."""
    from .render import scene_dictionary
    directory = Path(export_directory)
    manifest = json.loads((directory/"manifest.json").read_text())
    expected = manifest.pop("manifest_sha256", None)
    if expected != hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest():
        raise ValueError("optical export manifest hash mismatch")
    if manifest["schema"] != EXPORT_SCHEMA or manifest["mitsuba_version"] != "3.9.1":
        raise ValueError("unsupported optical export")
    groups = manifest["groups"]
    if not groups:
        raise ValueError("empty export")
    for group in groups:
        p = directory/group["filename"]
        if hashlib.sha256(p.read_bytes()).hexdigest() != group["file_sha256"]:
            raise ValueError("exported curve file hash mismatch")
    bounds = np.asarray(manifest["bounds_mm"])
    width = float(np.max(bounds[1, :2]-bounds[0, :2]))
    if width <= 0:
        raise ValueError("scene has no transverse extent")
    d = scene_dictionary(directory/groups[0]["filename"], width, groups[0]["radius_mm"], config)
    del d["fibers"]
    # Shift all coordinates only through their curve data, never a transform that
    # might scale positions without radius. Camera rig targets the same bbox center.
    center = .5*(bounds[0]+bounds[1])
    from .render import get_mitsuba
    mi = get_mitsuba()
    shift = mi.ScalarTransform4f().translate(center.tolist())
    d["sensor"]["to_world"] = shift @ d["sensor"]["to_world"]
    if "key" in d:
        d["key"]["to_world"] = shift @ d["key"]["to_world"]
    for i, group in enumerate(groups):
        d[f"fibers_{i:04d}"] = {"type": "bsplinecurve", "filename": str((directory/group["filename"]).resolve()),
                                "bsdf": group["bsdf"]}
    return d


def render_optical_scene(export_directory, config, output_prefix=None):
    """Actual Mitsuba path tracing of a versioned export, without averaging n."""
    import time
    from dataclasses import asdict
    from .render import get_mitsuba, encode_srgb
    from PIL import Image
    mi = get_mitsuba()
    d = mitsuba_scene_dictionary(export_directory, config)
    t = time.perf_counter()
    compiled = mi.load_dict(d)
    build_seconds = time.perf_counter()-t
    t = time.perf_counter()
    image = np.asarray(mi.render(compiled, seed=config.seed, spp=config.spp))
    if not np.isfinite(image).all() or image.min() < -1e-6:
        raise RuntimeError("invalid rendered radiance")
    manifest = json.loads((Path(export_directory)/"manifest.json").read_text())
    info = {"scene_sha256": manifest["scene_sha256"], "mitsuba_version": mi.__version__,
            "variant": mi.variant(), "mode": config.mode, "resolution": config.resolution,
            "spp": config.spp, "seed": config.seed, "group_count": len(manifest["groups"]),
            "wavelength_nm_vacuum": manifest["wavelength_nm_vacuum"],
            "mean_linear": float(image.mean()), "max_linear": float(image.max()),
            "build_seconds": build_seconds, "render_seconds": time.perf_counter()-t,
            "quantity": "camera linear radiance average, not hemispherical reflectance",
            "spectral_mode": manifest["spectral_mode"], "render_config": asdict(config),
            "material_parameter_source": "export manifest per material/radius; config material fields unused"}
    if output_prefix is not None:
        p = Path(output_prefix)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(p)+"_linear.npy", image)
        Image.fromarray(np.round(255*encode_srgb(image, config.exposure)).astype(np.uint8)).save(str(p)+".png")
        Path(str(p)+".json").write_text(json.dumps(info, indent=2))
    return image, info


def microstructure_statistics(scene, directions=None):
    """Exact statistics of the represented polylines, not a fitted BSDF.

    Orientation tensors are length/volume weighted and normalized to trace one.
    Projected area is the sum of unoccluded lateral-cylinder areas 2*r*l*sin(a).
    It excludes endcaps, occlusion, multiple scattering and coherent interference.
    For a B-spline input this routine rejects the control polygon as geometry.
    """
    if any(f.curve_basis != "polyline" or f.cross_section != "circle" for f in scene.fibers):
        raise ValueError("statistics require actual circular polyline geometry")
    if directions is None:
        directions = np.eye(3)
    directions = np.asarray(directions, dtype=float)
    if directions.ndim != 2 or directions.shape[1] != 3 or len(directions) < 1:
        raise ValueError("directions must have shape (N,3)")
    directions = np.array([_unit(d) for d in directions])
    groups = defaultdict(list)
    for f in scene.fibers:
        for key in ("all", f"material:{f.material_id}", f"family:{f.family}",
                    f"yarn:{f.yarn_id}", f"ply:{f.ply_id}"):
            groups[key].append(f)
    result = {}
    for key, fibers in groups.items():
        ls, rs, ts = [], [], []
        for f in fibers:
            delta = np.diff(f.points_mm, axis=0)
            lengths = np.linalg.norm(delta, axis=1)
            ls.extend(lengths); rs.extend(np.full(len(lengths), f.radius_mm))
            ts.extend(delta/lengths[:, None])
        lengths, radii, tangent = np.asarray(ls), np.asarray(rs), np.asarray(ts)
        volumes = np.pi*radii**2*lengths
        c_length = np.einsum("i,ij,ik->jk", lengths, tangent, tangent)/lengths.sum()
        c_volume = np.einsum("i,ij,ik->jk", volumes, tangent, tangent)/volumes.sum()
        area = np.sum((2*radii*lengths)[:, None]*np.sqrt(np.maximum(0, 1-(tangent@directions.T)**2)), axis=0)
        result[key] = {"fiber_count": len(fibers), "segment_count": len(lengths),
                       "length_mm": float(lengths.sum()),
                       "sum_cylinder_volume_mm3": float(volumes.sum()),
                       "orientation_length": c_length.tolist(), "orientation_volume": c_volume.tolist(),
                       "orientation_volume_eigenvalues": np.linalg.eigvalsh(c_volume).tolist(),
                       "unoccluded_lateral_projected_area_mm2": area.tolist()}
    return {"schema": "textile.microstructure/2.0", "scene_sha256": scene.sha256,
            "directions": directions.tolist(), "groups": result,
            "volume_semantics": "sum of straight segment pi*r^2*length; excludes joints and overlap correction",
            "projected_area_semantics": "unoccluded lateral area sum, not extinction/opacity/BSDF",
            "sggx_status": "no SGGX matrix or optical depth inferred automatically"}


@dataclass(frozen=True)
class BundleTolerance:
    mode: str = "strict"
    half_window_mm: float = .02
    max_tilt_deg: float = .1
    max_tangent_change_deg: float = .2
    max_centerline_deviation_mm: float = 1e-5

    def __post_init__(self):
        if self.mode not in ("strict", "local_parallel"):
            raise ValueError("bundle mode must be strict or explicit local_parallel")
        _positive(self.half_window_mm, "half_window_mm")
        for value in (self.max_tilt_deg, self.max_tangent_change_deg):
            if not np.isfinite(value) or not 0 <= value < 90:
                raise ValueError("bundle angle tolerances must be finite in [0,90)")
        if not np.isfinite(self.max_centerline_deviation_mm) or self.max_centerline_deviation_mm < 0:
            raise ValueError("centerline tolerance must be nonnegative and finite")


@dataclass(frozen=True, eq=False)
class BundleSection:
    scene_sha256: str
    centers_mm: np.ndarray
    radii_mm: np.ndarray
    fiber_ids: tuple[str, ...]
    material_ids: tuple[str, ...]
    plane_origin_mm: np.ndarray
    plane_axes: np.ndarray
    eligible: bool
    mode: str
    diagnostics_json: str

    def __post_init__(self):
        for name in ("centers_mm", "radii_mm", "plane_origin_mm", "plane_axes"):
            object.__setattr__(self, name, _readonly(getattr(self, name)))
        n = len(self.radii_mm)
        if self.centers_mm.shape != (n,2) or self.radii_mm.shape != (n,) or np.any(self.radii_mm <= 0):
            raise ValueError("section requires N positive radii and Nx2 centers")
        if self.plane_origin_mm.shape != (3,) or self.plane_axes.shape != (3,3):
            raise ValueError("invalid section plane frame shape")
        if not np.allclose(self.plane_axes@self.plane_axes.T,np.eye(3),rtol=0,atol=1e-12) or np.linalg.det(self.plane_axes) < 0:
            raise ValueError("section frame must be right-handed orthonormal")
        for name in ("fiber_ids", "material_ids"):
            ids = tuple(getattr(self,name))
            if len(ids) != n or any(not isinstance(x,str) or not x for x in ids):
                raise ValueError("section IDs must align with its N centers")
            object.__setattr__(self,name,ids)
        if len(set(self.fiber_ids)) != n:
            raise ValueError("section fiber IDs must be unique")
        if self.mode not in ("strict", "local_parallel") or not isinstance(self.eligible,(bool,np.bool_)):
            raise ValueError("invalid section mode/eligibility flag")
        object.__setattr__(self,"diagnostics_json",_provenance(self.diagnostics_json))

    @property
    def diagnostics(self):
        return json.loads(self.diagnostics_json)


def _plane_frame(normal):
    n = _unit(normal)
    reference = np.eye(3)[np.argmin(np.abs(n))]
    u = _unit(reference-np.dot(reference, n)*n)
    v = np.cross(n, u)
    return np.stack((u, v, n))


def _polyline_section(fiber, origin, axes, tolerance):
    p, normal = fiber.points_mm, axes[2]
    row = {"fiber_id": fiber.fiber_id, "material_id": fiber.material_id,
           "cross_section": fiber.cross_section, "reasons": []}
    if fiber.curve_basis != "polyline":
        row["reasons"].append("unsupported_curve_basis_for_exact_section")
        return None, row
    if fiber.cross_section != "circle":
        row["reasons"].append("noncircular_intrinsic_section")
    delta = np.diff(p, axis=0)
    length = np.linalg.norm(delta, axis=1)
    arc = np.r_[0., np.cumsum(length)]
    signed = (p-origin)@normal
    eps = 1e-12*max(1., float(np.max(np.abs(p))))
    hits = []
    for j in range(len(delta)):
        a, b = signed[j], signed[j+1]
        if abs(a) <= eps and abs(b) <= eps:
            row["reasons"].append("centerline_segment_coplanar_with_slice")
            return None, row
        if a*b < 0 or abs(a) <= eps or abs(b) <= eps:
            u = float(np.clip(-a/(b-a), 0, 1))
            s = float(arc[j]+u*length[j])
            if not hits or abs(s-hits[-1][0]) > eps:
                hits.append((s, p[j]+u*delta[j]))
    row["intersection_count"] = len(hits)
    if len(hits) != 1:
        row["reasons"].append("no_unique_centerline_intersection")
        return None, row
    hit_arc, hit = hits[0]
    half = tolerance.half_window_mm
    if hit_arc < half or arc[-1]-hit_arc < half:
        row["reasons"].append("insufficient_axial_support_for_requested_window")
    lo, hi = max(0., hit_arc-half), min(arc[-1], hit_arc+half)
    overlap = np.maximum(0., np.minimum(arc[1:], hi)-np.maximum(arc[:-1], lo))
    active = overlap > 0
    tangents = delta[active]/length[active, None]
    chord = np.sum(tangents*overlap[active, None], axis=0)
    if np.linalg.norm(chord) < 1e-14:
        row["reasons"].append("degenerate_local_axis")
        return None, row
    tangent = _unit(chord)
    cosine = float(np.clip(abs(tangent@normal), 0, 1))
    tilt = float(np.degrees(np.arctan2(np.linalg.norm(np.cross(tangent, normal)), cosine)))
    changes = np.degrees(np.arctan2(np.linalg.norm(np.cross(tangents, tangent), axis=1),
                                   np.clip(tangents@tangent, -1, 1)))
    local_s = np.r_[lo, arc[(arc>lo)&(arc<hi)], hi]
    local_p = np.stack([np.interp(local_s, arc, p[:, j]) for j in range(3)], axis=1)
    offset = local_p-hit
    deviation = float(np.max(np.linalg.norm(offset-(offset@tangent)[:, None]*tangent, axis=1)))
    max_change = float(np.max(changes))
    row.update({"tilt_deg": tilt, "max_tangent_change_deg": max_change,
                "max_centerline_deviation_mm": deviation,
                "local_tangent": tangent.tolist(), "center_mm": hit.tolist(),
                "ellipse_minor_semiaxis_mm": fiber.radius_mm,
                "ellipse_major_semiaxis_mm": fiber.radius_mm/cosine if cosine>1e-15 else None,
                "ellipse_area_ratio_vs_circle": 1/cosine if cosine>1e-15 else None,
                "ellipse_semantics": "plane intersection of the local tangent cylinder, not a curved tube solution"})
    if tolerance.mode == "strict":
        tilt_tol, change_tol, deviation_tol = 1e-7, 1e-7, 1e-12
    else:
        tilt_tol, change_tol, deviation_tol = (tolerance.max_tilt_deg,
                       tolerance.max_tangent_change_deg, tolerance.max_centerline_deviation_mm)
    if tilt > tilt_tol:
        row["reasons"].append("oblique_slice_is_elliptical_not_circular")
    if max_change > change_tol or deviation > deviation_tol:
        row["reasons"].append("nonparallel_or_curved_local_bundle")
    return (hit-origin)@axes[:2].T, row


def extract_bundle_section(scene, plane_origin_mm, plane_normal, *, fiber_ids=None,
                           tolerance=BundleTolerance()):
    """Diagnose a local slice and accept only declared circular 2D approximations.

    Every selected fiber must have one supported crossing and pass the local
    straight/parallel criteria.  A failed fiber is never silently dropped to
    create an apparently eligible smaller bundle.  The infinite-cylinder model
    still discards all geometry outside the requested validation window.
    """
    origin = np.asarray(plane_origin_mm, dtype=float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("plane origin must be finite shape (3,)")
    axes = _plane_frame(plane_normal)
    selected = scene.fibers
    if fiber_ids is not None:
        ids = tuple(fiber_ids)
        if len(set(ids)) != len(ids) or set(ids)-{f.fiber_id for f in scene.fibers}:
            raise ValueError("unknown or duplicated selected fiber IDs")
        selected = tuple(f for f in scene.fibers if f.fiber_id in set(ids))
    if not selected:
        raise ValueError("must select at least one fiber")
    rows, centers, radii, ids, mats = [], [], [], [], []
    for f in selected:
        center, row = _polyline_section(f, origin, axes, tolerance)
        rows.append(row)
        if center is not None:
            centers.append(center); radii.append(f.radius_mm)
            ids.append(f.fiber_id); mats.append(f.material_id)
    centers = np.asarray(centers, dtype=float).reshape(-1, 2)
    radii = np.asarray(radii, dtype=float)
    min_gap = None
    if len(centers) > 1:
        distances = np.linalg.norm(centers[:, None]-centers[None, :], axis=2)
        gap = distances-radii[:, None]-radii[None, :]
        np.fill_diagonal(gap, np.inf)
        min_gap = float(np.min(gap))
    overlap = min_gap is not None and min_gap <= 0
    eligible = (len(centers) == len(selected) and not overlap
                and all(not row["reasons"] for row in rows))
    pack = None
    if eligible:
        extent = np.max(centers+radii[:, None], axis=0)-np.min(centers-radii[:, None], axis=0)
        pack = float(np.sum(np.pi*radii**2)/np.prod(extent))
    from dataclasses import asdict
    diagnostics = {"rows": rows, "all_selected_required": True, "eligible": eligible,
                   "scene_sha256": scene.sha256, "length_unit": "mm",
                   "plane_origin_mm": origin.tolist(), "plane_axes_rows_uvn": axes.tolist(),
                   "requested_tolerances": asdict(tolerance),
                   "strict_numerical_limits": {"tilt_deg":1e-7,"tangent_change_deg":1e-7,
                                               "centerline_deviation_mm":1e-12},
                   "mode": tolerance.mode, "half_window_mm": tolerance.half_window_mm,
                   "min_circular_gap_mm": min_gap, "circular_overlap": overlap,
                   "sum_circle_area_over_enclosing_axis_aligned_box": pack,
                   "warning": "local infinite-cylinder reduction; no global 3D wave propagation equivalence",
                   "approximation": "none beyond infinite axial extension" if tolerance.mode == "strict"
                                    else "local tangents/curvature replaced by parallel circular cylinders"}
    return BundleSection(scene.sha256, centers, radii, tuple(ids), tuple(mats),
                         origin, axes, eligible, tolerance.mode, _canonical(diagnostics))


def _eligible(section, scene):
    if section.scene_sha256 != scene.sha256:
        raise ValueError("section belongs to a different scene version")
    if not section.eligible:
        raise ValueError("section failed circular/parallel validity checks; inspect diagnostics")


def wave_inputs(section, scene, wavelength_nm):
    """Map to existing exact 2D solver with host-medium wavelength and relative n."""
    _eligible(section, scene)
    optical = [scene.material_map[mid].at(wavelength_nm) for mid in section.material_ids]
    return {"positions_um": np.array(section.centers_mm)*1000,
            "radius_um": np.array(section.radii_mm)*1000,
            "wavelength_um": float(wavelength_nm)*.001/scene.background_n,
            "n_complex": np.array([o["n_complex"] for o in optical])/scene.background_n}


def ray_inputs(section, scene, wavelength_nm, *, max_kappa_ratio=.01):
    """Map to real-Fresnel/Beer 2D rays; the weak-absorption limit is explicit."""
    _eligible(section, scene)
    _positive(max_kappa_ratio, "max_kappa_ratio")
    optical = [scene.material_map[mid].at(wavelength_nm) for mid in section.material_ids]
    if any(o["kappa"]/o["n_real"] > max_kappa_ratio for o in optical):
        raise ValueError("strong absorption outside declared real-Fresnel ray approximation")
    return {"centers_um": np.array(section.centers_mm)*1000,
            "radii_um": np.array(section.radii_mm)*1000,
            "n_fiber": np.array([o["n_real"] for o in optical]), "n_host": scene.background_n,
            "absorption_um_inv": np.array([o["absorption_per_mm"] for o in optical])*.001}
