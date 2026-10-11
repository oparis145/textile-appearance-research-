"""Closed fiber meshes with dielectric interfaces and physical absorption.

This is a separate geometrical-optics reference, not the v4 radius-normalized
hair BCSDF.  Flat triangle normals determine reflection/refraction and medium
boundaries.  Pure absorption has sigma_t = mu_a in inverse millimeters, albedo
zero, and is integrated by Mitsuba's ``volpath``.  Circular-section taper and
mesh tessellation are geometry approximations; material twist, birefringence,
surface roughness, diffraction and a calibrated textile BSDF are not inferred.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import numbers
import time

import numpy as np

from .optical_scene import MaterialSpectrum
from .render import RenderConfig, direction, get_mitsuba

SCHEMA = "textile.closed_mesh_volume_optics/5.0"
MODEL = "closed triangle mesh; geometric face normals; real dielectric Fresnel; pure absorption; volpath"


@dataclass(frozen=True, eq=False)
class VolumeSceneHandle:
    """Bind a constructed backend scene to its semantic metadata identity.

    Backend mutation through external Mitsuba traversal is unsupported. This
    handle prevents accidentally pairing another scene's valid metadata with
    a render; it is not an attestation against deliberate backend mutation.
    """
    backend_scene: object = field(repr=False)
    scene_sha256: str

    def ray_intersect(self, *args, **kwargs):
        return self.backend_scene.ray_intersect(*args, **kwargs)

    def ray_test(self, *args, **kwargs):
        return self.backend_scene.ray_test(*args, **kwargs)

    def shapes(self):
        return self.backend_scene.shapes()


def _positive(value, name):
    if isinstance(value, (bool, str)) or not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _array_digest(a):
    a = np.ascontiguousarray(a)
    h = hashlib.sha256(_canonical([a.shape, a.dtype.str]).encode("ascii"))
    h.update(a.tobytes())
    return h.hexdigest()


def triangle_buffer_audit(vertices_mm, faces):
    """Measure float32 export error and reject collapsed/flipped triangles.

    This inspects stored topology and orientation. It does not establish an
    embedded, non-self-intersecting surface. Disconnected positive-volume
    components must already have been checked by their geometry producer.
    """
    v = np.asarray(vertices_mm, dtype=np.float64)
    raw_f = np.asarray(faces)
    if (v.ndim != 2 or v.shape[1] != 3 or len(v) < 4
            or not np.isfinite(v).all()):
        raise ValueError("vertices must be a finite N by 3 array")
    if (raw_f.ndim != 2 or raw_f.shape[1] != 3 or len(raw_f) < 4
            or raw_f.dtype.kind not in "iu" or np.any(raw_f < 0)
            or np.any(raw_f >= len(v)) or len(v) > np.iinfo(np.uint32).max):
        raise ValueError("faces require valid integer triangle indices")
    f = np.ascontiguousarray(raw_f, dtype=np.uint32)
    # Closed orientable topology: every directed edge has exactly one reverse.
    directed = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
    undirected = np.sort(directed, axis=1)
    _, inv, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    sign = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    balances = np.bincount(inv, weights=sign, minlength=len(counts))
    if np.any(counts != 2) or np.any(balances != 0):
        raise ValueError("mesh must be closed with consistent opposing edge winding")
    with np.errstate(over="ignore", invalid="ignore"):
        v32 = np.ascontiguousarray(v, dtype=np.float32)
    if not np.isfinite(v32).all():
        raise ValueError("float32 vertex overflow")
    q = v32.astype(np.float64)
    n = np.cross(v[f[:, 1]]-v[f[:, 0]], v[f[:, 2]]-v[f[:, 0]])
    nq = np.cross(q[f[:, 1]]-q[f[:, 0]], q[f[:, 2]]-q[f[:, 0]])
    areas, aq = np.linalg.norm(n, axis=1), np.linalg.norm(nq, axis=1)
    if (not np.isfinite(n).all() or np.any(areas <= 0) or np.any(aq <= 0)
            or np.any(np.einsum("ij,ij->i", n, nq) <= 0)):
        raise ValueError("degenerate or float32-collapsed/flipped triangle")
    origin = v.mean(axis=0)
    a, b = v-origin, q-origin
    volume = float(np.einsum("ij,ij->", a[f[:, 0]],
                           np.cross(a[f[:, 1]], a[f[:, 2]]))/6)
    qvolume = float(np.einsum("ij,ij->", b[f[:, 0]],
                            np.cross(b[f[:, 1]], b[f[:, 2]]))/6)
    if not np.isfinite(volume) or not np.isfinite(qvolume) or volume <= 0 or qvolume <= 0:
        raise ValueError("mesh must have positive signed volume before and after float32 export")
    meta = {"vertex_count": len(v), "face_count": len(f),
            "closed_oriented_edge_incidence": True,
            "self_intersection_certified_absent": False,
            "max_float32_displacement_mm": float(np.max(np.linalg.norm(q-v, axis=1))),
            "source_signed_volume_mm3": volume, "float32_signed_volume_mm3": qvolume,
            "float32_relative_volume_change": qvolume/volume-1,
            "minimum_source_triangle_area_mm2": float(areas.min()/2),
            "minimum_float32_triangle_area_mm2": float(aq.min()/2),
            "vertices_float32_sha256": _array_digest(v32),
            "faces_uint32_sha256": _array_digest(f)}
    return v32, f, meta


def _config(config):
    if not isinstance(config, RenderConfig):
        raise ValueError("RenderConfig required")
    for field in ("resolution", "spp"):
        _integer(getattr(config, field), field)
    _integer(config.seed, "seed", 0)
    _integer(config.rr_depth, "rr_depth")
    if isinstance(config.max_depth, bool) or not isinstance(config.max_depth, numbers.Integral):
        raise ValueError("max_depth must be an integer")
    if config.max_depth != -1:
        _integer(config.max_depth, "max_depth", 2)
    if config.mode not in ("reflection", "transmission", "furnace"):
        raise ValueError("closed mesh optics supports reflection, transmission and furnace")
    for field in ("light_elevation_deg", "light_azimuth_deg", "view_elevation_deg",
                  "view_azimuth_deg", "ambient"):
        if not np.isfinite(getattr(config, field)):
            raise ValueError(f"{field} must be finite")
    if not 0 < config.light_halfwidth_deg < 45 or config.ambient < 0:
        raise ValueError("finite positive source angular width < 45 degrees and nonnegative ambient required")
    _positive(config.width_fraction, "width_fraction")
    if not -90 <= config.view_elevation_deg <= 90 or not 0 <= config.light_elevation_deg <= 90:
        raise ValueError("view/source elevation out of range")
    return config


def material_boundary_properties(material, wavelength_nm, *, background_n=1., max_kappa_ratio=.01):
    """Scalar Fresnel of real indices + kappa-derived physical absorption.

    Imaginary-index Fresnel corrections are intentionally absent; the explicit
    small-kappa/n gate follows the current optical bridge's approximation.
    """
    if not isinstance(material, MaterialSpectrum):
        raise ValueError("MaterialSpectrum with provenance required")
    background_n = _positive(background_n, "background_n")
    max_kappa_ratio = _positive(max_kappa_ratio, "max_kappa_ratio")
    optical = material.at(wavelength_nm)
    ratio = optical["kappa"]/optical["n_real"]
    if ratio > max_kappa_ratio:
        raise ValueError("kappa/n exceeds the real-Fresnel approximation gate")
    mu = optical["absorption_per_mm"]
    props = {"bsdf": {"type": "dielectric", "int_ior": optical["n_real"],
                       "ext_ior": background_n}}
    if mu > 0:
        props["interior"] = {"type": "homogeneous", "sigma_t": float(mu),
                             "albedo": 0., "sample_emitters": False}
    meta = {"material": material.to_dict(), "wavelength_nm": float(wavelength_nm),
            "n_real": optical["n_real"], "kappa": optical["kappa"],
            "background_n": background_n, "absorption_per_mm": mu,
            "sigma_t_per_scene_unit": mu, "albedo": 0.,
            "kappa_over_n": ratio, "max_kappa_ratio": max_kappa_ratio,
            "absorbing_medium_installed": mu > 0,
            "absorption_mapping": "sigma_t = mu_a_per_mm; no radius multiplier"}
    return props, meta


def _rig(bounds_mm, config):
    mi = get_mitsuba()
    bounds = np.asarray(bounds_mm, dtype=float)
    if (bounds.shape != (2, 3) or not np.isfinite(bounds).all()
            or np.any(bounds[1] <= bounds[0])):
        raise ValueError("finite strictly positive 3D scene bounds required")
    center = bounds.mean(axis=0)
    span = float(np.max(bounds[1]-bounds[0]))
    view = direction(config.view_elevation_deg, config.view_azimuth_deg)
    up = np.array([0., 1., 0.])
    if abs(np.dot(up, view)) > .95:
        up = np.array([0., 0., 1.])
    up = up-np.dot(up, view)*view
    up /= np.linalg.norm(up)
    right = np.cross(view, up)
    corners = np.array([[bounds[i, 0], bounds[j, 1], bounds[k, 2]]
                        for i in (0, 1) for j in (0, 1) for k in (0, 1)])-center
    width = float(max(np.ptp(corners@right), np.ptp(corners@up)))
    half = .5*width*config.width_fraction
    transform = mi.ScalarTransform4f().look_at(origin=center+view*(10*span),
                    target=center, up=up).scale([half, half, 1.])
    d = {"type": "scene", "integrator": {"type": "volpath", "max_depth": config.max_depth,
                                          "rr_depth": config.rr_depth},
         "sensor": {"type": "orthographic", "to_world": transform,
                    "sampler": {"type": "independent", "sample_count": config.spp},
                    "film": {"type": "hdrfilm", "width": config.resolution,
                             "height": config.resolution, "pixel_format": "rgb",
                             "component_format": "float32", "rfilter": {"type": "box"}}}}
    emitter = {"type": "constant", "radiance": 1.}
    source_meta = {"mode": config.mode}
    if config.mode == "furnace":
        d["environment"] = emitter
    else:
        light = direction(config.light_elevation_deg, config.light_azimuth_deg)
        if config.mode == "transmission":
            light[2] *= -1
        distance = 20*span
        source_half = distance*np.tan(np.deg2rad(config.light_halfwidth_deg))
        source_up = [0., 1., 0.] if abs(light[1]) < .95 else [1., 0., 0.]
        tr = mi.ScalarTransform4f().look_at(origin=center+light*distance,
                    target=center, up=source_up).scale([source_half, source_half, 1.])
        omega_approx = 4*np.tan(np.deg2rad(config.light_halfwidth_deg))**2
        radiance = float(np.pi/omega_approx)
        d["key"] = {"type": "rectangle", "to_world": tr,
                    "emitter": {"type": "area", "radiance": radiance}}
        if config.ambient > 0:
            d["environment"] = {"type": "constant", "radiance": config.ambient}
        source_meta.update({"direction_from_center": light.tolist(),
                            "distance_mm": distance, "half_width_mm": float(source_half),
                            "radiance": radiance,
                            "normal_irradiance_normalization": "pi under small-source solid-angle approximation"})
    return d, {"bounds_mm": bounds.tolist(), "center_mm": center.tolist(),
               "span_mm": span, "film_width_mm": 2*half, "view_direction": view.tolist(),
               "camera_distance_mm": 10*span, "source": source_meta}


def build_volume_scene(meshes, materials, wavelength_nm, config, *, bounds_mm=None,
                       background_n=1., max_kappa_ratio=.01):
    """Construct a scene from audited TaperedTubeMesh objects.

    Each disconnected fiber retains a separate medium boundary/mesh. The
    caller must establish that material volumes do not overlap or self-cross.
    Closedness alone does not suffice for that physical assumption.
    """
    from .variable_radius import TaperedTubeMesh
    config = _config(config)
    meshes, materials = tuple(meshes), tuple(materials)
    if not meshes or any(not isinstance(m, TaperedTubeMesh) for m in meshes):
        raise ValueError("nonempty TaperedTubeMesh sequence required")
    if not materials or any(not isinstance(m, MaterialSpectrum) for m in materials):
        raise ValueError("nonempty MaterialSpectrum sequence required")
    ids = [m.profile.fiber_id for m in meshes]
    if len(ids) != len(set(ids)):
        raise ValueError("fiber IDs must be unique")
    lookup = {m.material_id: m for m in materials}
    if len(lookup) != len(materials):
        raise ValueError("material IDs must be unique")
    if {m.profile.material_id for m in meshes} != set(lookup):
        raise ValueError("every and only referenced material must be supplied")
    actual = np.stack((np.min([m.vertices_mm.min(axis=0) for m in meshes], axis=0),
                       np.max([m.vertices_mm.max(axis=0) for m in meshes], axis=0)))
    bounds = actual if bounds_mm is None else np.asarray(bounds_mm, dtype=float)
    if bounds.shape != (2, 3):
        raise ValueError("bounds shape must be (2, 3)")
    tol = 1e-12*max(1., float(np.max(np.abs(actual))))
    if np.any(actual[0] < bounds[0]-tol) or np.any(actual[1] > bounds[1]+tol):
        raise ValueError("declared rig bounds must contain every source mesh")
    mi = get_mitsuba()
    start = time.perf_counter()
    scene_dict, rig = _rig(bounds, config)
    material_rows, parameters = {}, {}
    for key, mat in sorted(lookup.items()):
        spec, row = material_boundary_properties(mat, wavelength_nm,
                        background_n=background_n, max_kappa_ratio=max_kappa_ratio)
        props = mi.Properties()
        props["bsdf"] = mi.load_dict(spec["bsdf"])
        if "interior" in spec:
            props["interior"] = mi.load_dict(spec["interior"])
        parameters[key], material_rows[key] = props, row
    mesh_rows = []
    for i, source in enumerate(meshes):
        v, f, audit = triangle_buffer_audit(source.vertices_mm, source.faces)
        mesh = mi.Mesh(f"fiber_{i:04d}", len(v), len(f), parameters[source.profile.material_id],
                       has_vertex_normals=False, has_vertex_texcoords=False)
        scene_parameters = mi.traverse(mesh)
        scene_parameters["vertex_positions"] = mi.Float(v.ravel())
        scene_parameters["faces"] = mi.UInt(f.ravel())
        scene_parameters.update()
        scene_dict[f"fiber_{i:04d}"] = mesh
        row = {"fiber_id": source.profile.fiber_id, "material_id": source.profile.material_id,
               "profile_sha256": source.profile.sha256, "mesh_sha256": source.sha256,
               "radial_segments": source.radial_segments, "buffer_audit": audit}
        mesh_rows.append(row)
    scene = mi.load_dict(scene_dict)
    metadata = {"schema_version": SCHEMA, "model": MODEL, "mitsuba_version": mi.__version__,
                "variant": mi.variant(), "scene_length_unit": "mm", "wavelength_unit": "vacuum_nm",
                "wavelength_nm": float(wavelength_nm), "materials": material_rows,
                "meshes": mesh_rows, "rig": rig, "render_config": asdict(config),
                "ignored_legacy_config_fields": ["ior", "absorption_per_mm", "longitudinal_roughness",
                                                   "azimuthal_roughness", "exposure"],
                "triangle_geometric_normals_only": True,
                "surface_roughness_model": "none; smooth dielectric on each flat triangle",
                "coherence": "incoherent scalar intensities",
                "caller_preconditions": "disjoint embedded closed material volumes; self-intersection is not certified by this adapter"}
    # Build time is observational metadata, not part of the semantic identity.
    metadata["scene_sha256"] = hashlib.sha256(_canonical(metadata).encode("utf-8")).hexdigest()
    metadata["scene_build_seconds"] = time.perf_counter()-start
    return VolumeSceneHandle(scene, metadata["scene_sha256"]), metadata


def render_volume_scene(scene, metadata, *, seed, spp):
    seed, spp = _integer(seed, "seed", 0), _integer(spp, "spp")
    if not isinstance(scene, VolumeSceneHandle) or metadata.get("schema_version") != SCHEMA:
        raise ValueError("volume scene metadata required")
    identity = {k: v for k, v in metadata.items() if k not in ("scene_sha256", "scene_build_seconds")}
    digest = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
    if digest != metadata.get("scene_sha256") or digest != scene.scene_sha256:
        raise ValueError("render scene and metadata identity do not agree")
    mi = get_mitsuba()
    start = time.perf_counter()
    image = np.array(mi.render(scene.backend_scene, seed=seed, spp=spp))
    seconds = time.perf_counter()-start
    n = metadata["render_config"]["resolution"]
    if image.shape != (n, n, 3) or not np.isfinite(image).all() or image.min() < -1e-7:
        raise RuntimeError("invalid or nonfinite/nonpassive rendered radiance")
    # A gray RGB backend is used to evaluate one scalar wavelength. Its three
    # channels are not independent spectral observations or independent samples.
    channel_error = float(np.max(np.abs(image-image[..., :1])))
    if channel_error > 2e-5*max(1., float(image.max())):
        raise RuntimeError("monochromatic scalar channels unexpectedly differ")
    row = {"scene_sha256": metadata["scene_sha256"], "seed": seed, "spp": spp,
           "render_seconds": seconds, "mean_radiance": float(image.mean()),
           "max_radiance": float(image.max()), "minimum_radiance": float(image.min()),
           "max_channel_disagreement": channel_error,
           "raw_float32_sha256": _array_digest(np.asarray(image, dtype=np.float32))}
    return image, row
