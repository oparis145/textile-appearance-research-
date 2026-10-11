"""Two-dimensional power ray tracing through nonoverlapping dielectric fibers.

All lengths are micrometres; all angles are radians.  Fibers are infinite along
z; propagation and surface normals lie in the x-y plane.  ``Ez`` (s) and ``Hz``
(p) remain independent polarization channels.  This module follows power,
not field amplitudes: it contains no interference, diffraction, or birefringence.

Fresnel roulette samples a lossless interface without changing ray weight.
Beer absorption reduces that weight along actual internal chord lengths.  Rays
that hit ``max_events`` retain their remaining power in an explicit residual.
No result is renormalized to hide absorption, truncation, or numerical failures.

The intercepted-ray angular cross section is NOT the Maxwell scattered-field
cross section.  In particular, the missing forward diffraction term precludes
equating the integral to an exact cylinder's extinction cross section.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def fresnel_dielectric(cos_i, n_i=1.0, n_t=1.55):
    """Return ``(R_s, R_p, cos_t, tir)`` for positive incident-angle cosine.

    ``R`` is a power fraction and ``1-R`` is the transmitted power fraction.
    Indices must be positive real scalars or broadcastable arrays.  Equal-index
    grazing incidence is treated by its continuous limit (R=0), not 0/0.
    """
    ci, ni, nt = np.broadcast_arrays(
        np.asarray(cos_i, dtype=float),
        np.asarray(n_i, dtype=float),
        np.asarray(n_t, dtype=float),
    )
    if np.any(~np.isfinite(ci)) or np.any((ci < -1e-12) | (ci > 1 + 1e-12)):
        raise ValueError("cos_i must be finite and lie in [0,1]")
    if np.any(~np.isfinite(ni)) or np.any(~np.isfinite(nt)) or np.any(ni <= 0) or np.any(nt <= 0):
        raise ValueError("indices must be finite, positive and real")
    ci = np.clip(ci, 0.0, 1.0)
    matched = ni == nt
    sin2_t = (ni / nt) ** 2 * np.maximum(0.0, 1.0 - ci * ci)
    tir = (sin2_t >= 1.0) & ~matched
    ct = np.sqrt(np.maximum(0.0, 1.0 - sin2_t))
    ds = ni * ci + nt * ct
    dp = nt * ci + ni * ct
    rs = np.divide(ni * ci - nt * ct, ds, out=np.ones_like(ci), where=ds > 0) ** 2
    rp = np.divide(nt * ci - ni * ct, dp, out=np.ones_like(ci), where=dp > 0) ** 2
    rs = np.where(tir, 1.0, np.where(matched, 0.0, rs))
    rp = np.where(tir, 1.0, np.where(matched, 0.0, rp))
    ct = np.where(matched, ci, ct)
    return np.clip(rs, 0.0, 1.0), np.clip(rp, 0.0, 1.0), ct, tir


def ray_circle_intersections(origins, directions, centers_um, radii_um, eps_um=1e-9):
    """Nearest strictly positive ray-circle distance for each ray and circle.

    Returns an (N,M) array; misses are +inf.  Directions must be unit vectors.
    Origins may lie inside circles.  Roots closer than ``eps_um`` are excluded
    to prevent a ray at a boundary from immediately re-hitting that boundary.
    """
    o = np.atleast_2d(np.asarray(origins, dtype=float))
    d = np.atleast_2d(np.asarray(directions, dtype=float))
    c = np.atleast_2d(np.asarray(centers_um, dtype=float))
    r = np.broadcast_to(np.asarray(radii_um, dtype=float), (len(c),))
    if o.shape != d.shape or o.shape[1] != 2 or c.shape[1] != 2:
        raise ValueError("origins/directions and centers must have two coordinates")
    if any(np.any(~np.isfinite(v)) for v in (o, d, c, r)) or np.any(r <= 0) or not np.isfinite(eps_um) or eps_um <= 0:
        raise ValueError("geometry must be finite, radii and epsilon positive")
    if not np.allclose(np.sum(d * d, axis=1), 1.0, rtol=1e-10, atol=1e-12):
        raise ValueError("directions must be unit vectors")
    q = o[:, None, :] - c[None, :, :]
    b = np.sum(q * d[:, None, :], axis=2)
    disc = b * b - (np.sum(q * q, axis=2) - r[None, :] ** 2)
    root = np.sqrt(np.maximum(0.0, disc))
    near, far = -b - root, -b + root
    t = np.where(near > eps_um, near, np.where(far > eps_um, far, np.inf))
    return np.where(disc >= 0.0, t, np.inf)


def hex_bundle(shells=1, radius_um=5.0, gap_um=0.25, rotate_rad=0.0):
    """Return centers and radii for 1+3*s*(s+1) fibers in a hexagonal cluster.

    The center pitch is ``2*radius_um + gap_um``.  ``shells=0,1,2`` give
    1, 7, and 19 fibers.  A strictly positive gap avoids contact singularities.
    """
    if int(shells) != shells or shells < 0 or not np.all(np.isfinite([radius_um, gap_um, rotate_rad])) or radius_um <= 0 or gap_um <= 0:
        raise ValueError("shells must be nonnegative integer; radius and gap positive")
    shells = int(shells)
    pitch = 2.0 * radius_um + gap_um
    centers = []
    for q in range(-shells, shells + 1):
        for r in range(-shells, shells + 1):
            if abs(q + r) <= shells:
                centers.append([pitch * (q + 0.5 * r), pitch * np.sqrt(3.0) * r / 2.0])
    centers = np.asarray(centers, dtype=float)
    co, si = np.cos(rotate_rad), np.sin(rotate_rad)
    centers = centers @ np.array([[co, si], [-si, co]])
    return centers, np.full(len(centers), radius_um)


def _validate_geometry(centers_um, radii_um):
    centers = np.asarray(centers_um, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 2 or len(centers) < 1:
        raise ValueError("centers_um must be a nonempty (M,2) array")
    radii = np.broadcast_to(np.asarray(radii_um, dtype=float), (len(centers),)).copy()
    if np.any(~np.isfinite(centers)) or np.any(~np.isfinite(radii)) or np.any(radii <= 0):
        raise ValueError("centers must be finite and radii finite and positive")
    distance = np.linalg.norm(centers[:, None] - centers[None, :], axis=2)
    np.fill_diagonal(distance, np.inf)
    if np.any(distance <= radii[:, None] + radii[None, :]):
        raise ValueError("fibers must be disjoint with a strictly positive gap")
    return centers, radii


def _one_chunk(origins, directions, pol, centers, radii, n_fiber, n_host,
               absorption, max_events, rng, record_count):
    n = len(origins)
    pos = origins.copy()
    direction = directions.copy()
    inside = np.full(n, -1, dtype=np.int32)
    weight = np.ones(n)
    absorbed = np.zeros(n)
    path_inside = np.zeros(n)
    encountered = np.zeros(n, dtype=bool)
    escaped = np.zeros(n, dtype=bool)
    failed = np.zeros(n, dtype=bool)
    events = np.zeros(n, dtype=np.int32)
    reflections = np.zeros(n, dtype=np.int32)
    transmissions = np.zeros(n, dtype=np.int32)
    tir_events = np.zeros(n, dtype=np.int32)
    entries = np.zeros(n, dtype=np.int32)
    active = np.ones(n, dtype=bool)
    paths = [[pos[i].copy()] for i in range(record_count)]
    eps = 1e-10 * float(np.max(radii)) + 1e-12

    # The extra final query lets a ray escaping immediately after its last
    # allowed interface be recognized without incorrectly charging residual.
    for _ in range(max_events + 1):
        ids = np.flatnonzero(active)
        if not len(ids):
            break
        old_inside = inside[ids]
        internal = old_inside >= 0
        hit_id = np.full(len(ids), -1, dtype=np.int32)
        distance = np.full(len(ids), np.inf)
        outside_local = np.flatnonzero(~internal)
        if len(outside_local):
            oi = ids[outside_local]
            all_t = ray_circle_intersections(pos[oi], direction[oi], centers, radii, eps)
            nearest = np.argmin(all_t, axis=1)
            distance[outside_local] = all_t[np.arange(len(oi)), nearest]
            hit_id[outside_local] = nearest
        inside_local = np.flatnonzero(internal)
        if len(inside_local):
            ii = ids[inside_local]
            ci = old_inside[inside_local]
            q = pos[ii] - centers[ci]
            b = np.sum(q * direction[ii], axis=1)
            disc = b * b - (np.sum(q * q, axis=1) - radii[ci] ** 2)
            ti = -b + np.sqrt(np.maximum(0.0, disc))
            bad = (disc < -eps * np.max(radii)) | (ti <= eps) | ~np.isfinite(ti)
            if np.any(bad):
                failed[ii[bad]] = True
                active[ii[bad]] = False
            distance[inside_local] = np.where(bad, np.inf, ti)
            hit_id[inside_local] = ci

        # A genuine miss outside the fibers is escaped power.  An internal
        # intersection failure remains residual and cannot masquerade as light.
        miss = ~np.isfinite(distance)
        ei = ids[miss & ~internal]
        escaped[ei] = True
        active[ei] = False
        eligible = (~miss) & (events[ids] < max_events) & active[ids]
        limited = ids[(~miss) & (events[ids] >= max_events)]
        active[limited] = False
        if not np.any(eligible):
            continue
        local = np.flatnonzero(eligible)
        ri = ids[local]
        ci = hit_id[local]
        was_inside = internal[local]
        travel = distance[local]
        pos[ri] += travel[:, None] * direction[ri]
        for k, point in zip(ri[ri < record_count], pos[ri[ri < record_count]]):
            paths[int(k)].append(point.copy())
        if np.any(was_inside):
            ai = ri[was_inside]
            length = travel[was_inside]
            path_inside[ai] += length
            previous_weight = weight[ai].copy()
            weight[ai] *= np.exp(-absorption[ci[was_inside]] * length)
            absorbed[ai] += previous_weight - weight[ai]

        encountered[ri] = True
        outward = (pos[ri] - centers[ci]) / radii[ci, None]
        outward /= np.linalg.norm(outward, axis=1)[:, None]
        opposing_normal = np.where(was_inside[:, None], -outward, outward)
        ci_angle = -np.sum(direction[ri] * opposing_normal, axis=1)
        if np.any(ci_angle < -1e-7):
            raise RuntimeError("intersection orientation is inconsistent")
        ci_angle = np.clip(ci_angle, 0.0, 1.0)
        ni = np.where(was_inside, n_fiber[ci], n_host)
        nt = np.where(was_inside, n_host, n_fiber[ci])
        rs, rp, ct, tir = fresnel_dielectric(ci_angle, ni, nt)
        reflect_probability = np.where(pol[ri] == 0, rs, rp)
        reflect = rng.random(len(ri)) < reflect_probability
        refract = ~reflect
        incoming = direction[ri].copy()
        if np.any(reflect):
            rri = ri[reflect]
            direction[rri] = incoming[reflect] + 2.0 * ci_angle[reflect, None] * opposing_normal[reflect]
            reflections[rri] += 1
            tir_events[rri] += tir[reflect]
        if np.any(refract):
            tri = ri[refract]
            eta = ni[refract] / nt[refract]
            direction[tri] = (eta[:, None] * incoming[refract]
                              + (eta * ci_angle[refract] - ct[refract])[:, None] * opposing_normal[refract])
            inside[tri] = np.where(was_inside[refract], -1, ci[refract])
            entries[tri] += ~was_inside[refract]
            transmissions[tri] += 1
        direction[ri] /= np.linalg.norm(direction[ri], axis=1)[:, None]
        events[ri] += 1

    return dict(
        angle=np.arctan2(direction[:, 1], direction[:, 0]),
        final_position=pos, final_direction=direction,
        weight=weight, absorbed=absorbed, path_inside_um=path_inside,
        encountered=encountered, escaped=escaped, failed=failed,
        events=events, reflections=reflections, transmissions=transmissions,
        tir_events=tir_events, entries=entries, paths=paths,
    )


def _mean_se(values):
    values = np.asarray(values, dtype=float)
    return float(np.mean(values)), float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else float("nan")


def trace_bundle(centers_um, radii_um, n_fiber=1.55, n_host=1.0,
                 n_rays=100000, seed=20261010, polarization="unpolarized",
                 beam="uniform", beam_width_um=None, beam_center_um=None,
                 gaussian_sigma_um=None, incident_angle_rad=0.0,
                 theta_bins=360, max_events=200, absorption_um_inv=0.0,
                 batch_size=16384, record_paths=0, return_rays=False):
    """Trace normally incident 2D rays through a fiber cross-section cluster.

    The default incoming direction is +x. ``incident_angle_rad`` rotates it.
    Output angle theta is always measured from +x, not from the beam direction.
    Reflection/backward and forward fractions use the incident-beam hemisphere.

    ``beam='uniform'`` samples a rectangular irradiance support in transverse
    coordinate b. Its default width is the projected cluster bounding width.
    ``beam='gaussian'`` samples the entire normalized Gaussian power density
    exp(-(b-b0)^2/(2*sigma^2))/(sqrt(2*pi)*sigma); no finite truncation is used.
    It requires ``gaussian_sigma_um``. Gaussian results have no plane-wave
    cross-section conversion. Uniform results multiply fractions by beam width.

    ``n_fiber`` and absorption may be scalars or per-fiber arrays. Absorption
    uses a fixed Beer attenuation in 1/um with real-index Fresnel interfaces;
    it is a weakly absorbing dielectric approximation, not complex-index optics.

    Returned angular densities integrate to escaped power, not unity. The
    ``energy`` dict partitions incident power into backward, collided_forward,
    uncollided_forward, absorbed, and residual. ``encountered`` means a boundary
    was reached; it is not a statement that Maxwell scattering is nonzero.
    """
    centers, radii = _validate_geometry(centers_um, radii_um)
    nf = np.broadcast_to(np.asarray(n_fiber, dtype=float), (len(centers),)).copy()
    mu = np.broadcast_to(np.asarray(absorption_um_inv, dtype=float), (len(centers),)).copy()
    if np.any(~np.isfinite(nf)) or np.any(nf <= 0) or not np.isfinite(n_host) or n_host <= 0:
        raise ValueError("indices must be positive finite real values")
    if np.any(~np.isfinite(mu)) or np.any(mu < 0):
        raise ValueError("absorption must be finite and nonnegative")
    for value, name, minimum in [(n_rays, "n_rays", 1), (theta_bins, "theta_bins", 4),
                                  (batch_size, "batch_size", 1), (max_events, "max_events", 0),
                                  (record_paths, "record_paths", 0)]:
        if int(value) != value or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    n_rays, theta_bins, max_events, batch_size = map(int, [n_rays, theta_bins, max_events, batch_size])
    record_paths = min(int(record_paths), n_rays)
    pol_name = polarization.lower()
    if pol_name not in {"s", "ez", "p", "hz", "unpolarized"}:
        raise ValueError("polarization must be Ez/s, Hz/p, or unpolarized")
    if beam not in {"uniform", "gaussian"}:
        raise ValueError("beam must be uniform or gaussian")
    if not np.isfinite(incident_angle_rad):
        raise ValueError("incident angle must be finite")
    d = np.array([np.cos(incident_angle_rad), np.sin(incident_angle_rad)])
    transverse = np.array([-d[1], d[0]])
    projected = centers @ transverse
    bmin, bmax = np.min(projected - radii), np.max(projected + radii)
    b0 = 0.5 * (bmin + bmax) if beam_center_um is None else float(beam_center_um)
    width = bmax - bmin if beam_width_um is None else float(beam_width_um)
    if not np.isfinite(b0) or not np.isfinite(width) or width <= 0:
        raise ValueError("beam center must be finite and beam width positive")
    if beam == "gaussian" and (gaussian_sigma_um is None or not np.isfinite(gaussian_sigma_um) or gaussian_sigma_um <= 0):
        raise ValueError("gaussian beam requires positive finite gaussian_sigma_um")
    if beam == "gaussian" and beam_width_um is not None:
        raise ValueError("beam_width_um does not define an untruncated Gaussian; use gaussian_sigma_um")
    launch_s = float(np.min(centers @ d - radii) - max(1.0, 0.01 * width))
    rng = np.random.default_rng(seed)
    all_chunks = []
    all_b = []
    recorded = []
    for start in range(0, n_rays, batch_size):
        size = min(batch_size, n_rays - start)
        if beam == "uniform":
            b = rng.uniform(b0 - width / 2.0, b0 + width / 2.0, size)
        else:
            b = rng.normal(b0, gaussian_sigma_um, size)
        origins = launch_s * d[None, :] + b[:, None] * transverse[None, :]
        direction = np.broadcast_to(d, (size, 2)).copy()
        if pol_name == "unpolarized":
            pol = rng.integers(0, 2, size, dtype=np.int8)
        else:
            pol = np.full(size, 0 if pol_name in {"s", "ez"} else 1, dtype=np.int8)
        nr = min(size, max(0, record_paths - start))
        chunk = _one_chunk(origins, direction, pol, centers, radii, nf, float(n_host), mu,
                           max_events, rng, nr)
        for i, points in enumerate(chunk.pop("paths")):
            endpoint = chunk["final_position"][i] + (2.0 * width + 2.0 * np.max(radii)) * chunk["final_direction"][i]
            if chunk["escaped"][i]:
                points.append(endpoint)
            recorded.append(np.asarray(points))
        chunk["polarization_code"] = pol
        all_chunks.append(chunk)
        all_b.append(b)
    rays = {key: np.concatenate([chunk[key] for chunk in all_chunks]) for key in all_chunks[0]}
    rays["impact_um"] = np.concatenate(all_b)
    relative_cos = np.cos(rays["angle"] - incident_angle_rad)
    forward = rays["escaped"] & (relative_cos >= 0)
    backward = rays["escaped"] & (relative_cos < 0)
    uncollided = forward & ~rays["encountered"]
    collided_forward = forward & rays["encountered"]
    residual = ~rays["escaped"]
    channels = {
        "backward": rays["weight"] * backward,
        "collided_forward": rays["weight"] * collided_forward,
        "uncollided_forward": rays["weight"] * uncollided,
        "absorbed": rays["absorbed"],
        "residual": rays["weight"] * residual,
    }
    energy, energy_se = {}, {}
    for key, value in channels.items():
        energy[key], energy_se[key] = _mean_se(value)
    closure_per_ray = sum(channels.values())
    edges = np.linspace(-np.pi, np.pi, theta_bins + 1)
    bin_width = np.diff(edges)
    angle_centers = 0.5 * (edges[1:] + edges[:-1])
    angular = {}
    angular_se = {}
    masks = {"all_escaped": rays["escaped"], "encountered_escaped": rays["escaped"] & rays["encountered"],
             "uncollided_escaped": rays["escaped"] & ~rays["encountered"]}
    for name, mask in masks.items():
        w = rays["weight"][mask]
        hist = np.histogram(rays["angle"][mask], bins=edges, weights=w)[0]
        hist2 = np.histogram(rays["angle"][mask], bins=edges, weights=w * w)[0]
        angular[name] = hist / n_rays / bin_width
        variance = np.maximum(0.0, hist2 - hist * hist / n_rays) / max(1, n_rays * (n_rays - 1))
        angular_se[name] = np.sqrt(variance) / bin_width
    encounter_fraction, encounter_se = _mean_se(rays["encountered"])
    summary = {
        "energy": energy, "energy_standard_error": energy_se,
        "energy_sum": float(sum(energy.values())),
        "max_per_ray_energy_closure_error": float(np.max(np.abs(closure_per_ray - 1.0))),
        "encountered_fraction": encounter_fraction,
        "encountered_fraction_standard_error": encounter_se,
        "mean_interface_events": float(np.mean(rays["events"])),
        "max_interface_events": int(np.max(rays["events"])),
        "mean_fiber_entries": float(np.mean(rays["entries"])),
        "mean_inside_path_um": float(np.mean(rays["path_inside_um"])),
        "mean_reflections": float(np.mean(rays["reflections"])),
        "total_tir_events": int(np.sum(rays["tir_events"])),
        "numerical_failure_count": int(np.sum(rays["failed"])),
        "n_rays": n_rays, "n_fibers": int(len(centers)), "seed": int(seed),
        "polarization": polarization, "beam": beam,
        "beam_width_um": width if beam == "uniform" else None,
        "gaussian_sigma_um": float(gaussian_sigma_um) if beam == "gaussian" else None,
        "beam_center_um": b0, "incident_angle_rad": float(incident_angle_rad),
        "max_events": max_events, "batch_size": batch_size,
        "n_host": float(n_host), "n_fiber": nf.tolist(), "absorption_um_inv": mu.tolist(),
        "model": "2D incoherent power rays, circular infinite isotropic dielectric fibers",
    }
    result: dict[str, Any] = {
        "summary": summary, "energy": energy, "energy_standard_error": energy_se,
        "theta_edges_rad": edges, "theta_rad": angle_centers,
        "angular_power_per_rad": angular,
        "angular_standard_error_per_rad": angular_se,
        "centers_um": centers, "radii_um": radii, "ray_paths_um": recorded,
    }
    if beam == "uniform":
        result["intercepted_ray_dcs_um_per_rad"] = angular["encountered_escaped"] * width
        result["intercepted_ray_dcs_standard_error_um_per_rad"] = angular_se["encountered_escaped"] * width
        result["geometric_cross_sections_um"] = {name: value * width for name, value in energy.items()}
        result["geometric_cross_sections_um"]["encountered"] = encounter_fraction * width
        summary["geometric_cross_sections_um"] = result["geometric_cross_sections_um"]
    if return_rays:
        result["rays"] = rays
    return result


def single_cylinder_ray_quadrature(radius_um=5.0, n_fiber=1.55, n_host=1.0,
                                   polarization="unpolarized", absorption_um_inv=0.0,
                                   n_impact=131072, max_internal_segments=256,
                                   theta_bins=180):
    """Independent geometric-optics solution using analytic deflection orders.

    Midpoint quadrature integrates uniform impact b over [-a,a]. If i=asin(b/a)
    and r=asin(n_host*sin(i)/n_fiber), external reflection has theta=pi-2*i.
    An entry/exit path with p internal chords has theta=(p-1)*pi-2*i+2*p*r
    and power (1-R)^2 R^(p-1) exp(-mu*p*2*a*cos(r)). This independently checks
    vector intersections, normals, repeated refraction, and ray roulette.

    The omitted power remaining inside after the last exit opportunity is
    reported as residual. Equal-index rays transmit into a forward delta.
    This is a ray limit, not an electromagnetic cylinder scattering solution.
    """
    if radius_um <= 0 or n_fiber <= 0 or n_host <= 0 or absorption_um_inv < 0:
        raise ValueError("radius/indices must be positive and absorption nonnegative")
    if int(n_impact) != n_impact or n_impact < 1 or max_internal_segments < 1:
        raise ValueError("quadrature sizes must be positive integers")
    b = -1.0 + (np.arange(n_impact) + 0.5) * (2.0 / n_impact)
    i = np.arcsin(b)
    sin_r = n_host / n_fiber * b
    tir = np.abs(sin_r) >= 1.0
    r = np.arcsin(np.clip(sin_r, -1.0, 1.0))
    rs, rp, _, _ = fresnel_dielectric(np.cos(i), n_host, n_fiber)
    pol = polarization.lower()
    if pol in {"ez", "s"}:
        channels = [(rs, 1.0)]
    elif pol in {"hz", "p"}:
        channels = [(rp, 1.0)]
    elif pol == "unpolarized":
        channels = [(rs, 0.5), (rp, 0.5)]
    else:
        raise ValueError("polarization must be Ez/s, Hz/p, or unpolarized")
    edges = np.linspace(-np.pi, np.pi, theta_bins + 1)
    hist = np.zeros(theta_bins)
    outgoing = np.zeros(2)
    absorbed, residual = 0.0, 0.0
    def add_hist(theta, power):
        wrapped = np.remainder(theta + np.pi, 2.0 * np.pi) - np.pi
        is_forward = np.cos(wrapped) >= 0
        outgoing[0] += np.sum(power[~is_forward])/n_impact
        outgoing[1] += np.sum(power[is_forward])/n_impact
        return np.histogram(wrapped, bins=edges, weights=power / n_impact)[0]
    for reflectance, mixture in channels:
        hist += add_hist(np.pi - 2 * i, mixture * reflectance)
        current = mixture * (1 - reflectance)
        current[tir] = 0
        attenuation = np.exp(-absorption_um_inv * 2 * radius_um * np.cos(r))
        for p in range(1, int(max_internal_segments) + 1):
            previous = current
            current = current * attenuation
            absorbed += float(np.mean(previous - current))
            exiting = current * (1 - reflectance)
            hist += add_hist((p - 1) * np.pi - 2 * i + 2 * p * r, exiting)
            current = current * reflectance
        residual += float(np.mean(current))
    angle = (edges[:-1] + edges[1:]) / 2
    backward, forward = map(float, outgoing)
    return {
        "theta_edges_rad": edges, "theta_rad": angle,
        "angular_power_per_rad": hist / np.diff(edges),
        "intercepted_ray_dcs_um_per_rad": 2 * radius_um * hist / np.diff(edges),
        "energy": {"backward": backward, "forward": forward, "absorbed": absorbed, "residual": residual},
        "energy_sum": backward + forward + absorbed + residual,
        "n_impact": int(n_impact), "max_internal_segments": int(max_internal_segments),
    }


def run_reference_suite(output_dir):
    """Generate reproducible independent prototype benchmarks (not fabric data)."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    angular_rows = []
    for shells in (0, 1, 2):
        for pol in ("Ez", "Hz", "unpolarized"):
            centers, radii = hex_bundle(shells, radius_um=5.0, gap_um=0.4)
            name = f"n{len(centers)}_{pol}"
            result = trace_bundle(centers, radii, n_rays=100000, seed=1000 + 31 * shells,
                                  polarization=pol, theta_bins=180, max_events=200)
            summaries[name] = result["summary"]
            for j, theta in enumerate(result["theta_rad"]):
                angular_rows.append([len(centers), pol, theta,
                                     result["angular_power_per_rad"]["encountered_escaped"][j],
                                     result["angular_standard_error_per_rad"]["encountered_escaped"][j],
                                     result["intercepted_ray_dcs_um_per_rad"][j]])
    centers, radii = hex_bundle(2, radius_um=5.0, gap_um=0.4)
    for mu in (0.005, 0.02):
        name = f"n19_mu{mu}"
        summaries[name] = trace_bundle(centers, radii, n_rays=100000, seed=2301,
                                      absorption_um_inv=mu)["summary"]
    centers, radii = hex_bundle(1, radius_um=5.0, gap_um=3.0)
    summaries["n7_open_gaps"] = trace_bundle(centers, radii, n_rays=100000, seed=2045)["summary"]
    comparison = {}
    for pol in ("Ez", "Hz", "unpolarized"):
        exact_ray = single_cylinder_ray_quadrature(polarization=pol)
        coarse = single_cylinder_ray_quadrature(polarization=pol, n_impact=32768)
        mc = trace_bundle([[0, 0]], [5], n_rays=200000, seed=3780, polarization=pol, theta_bins=180)
        step = np.diff(exact_ray["theta_edges_rad"])
        reference_p = exact_ray["angular_power_per_rad"] * step
        mc_p = mc["angular_power_per_rad"]["encountered_escaped"] * step
        coarse_p = coarse["angular_power_per_rad"] * step
        comparison[pol] = {
            "quadrature_energy": exact_ray["energy"],
            "mc_energy": mc["energy"],
            "mc_vs_quadrature_cdf_sup": float(np.max(np.abs(np.cumsum(reference_p - mc_p)))),
            "quadrature_grid_cdf_sup": float(np.max(np.abs(np.cumsum(reference_p - coarse_p)))),
            "mc_n_rays": 200000,
            "quadrature_n_impact": exact_ray["n_impact"],
        }
        np.savez_compressed(output / f"ply_ray_single_quadrature_{pol}.npz",
                            theta_rad=exact_ray["theta_rad"],
                            quadrature_dcs=exact_ray["intercepted_ray_dcs_um_per_rad"],
                            mc_dcs=mc["intercepted_ray_dcs_um_per_rad"],
                            mc_dcs_se=mc["intercepted_ray_dcs_standard_error_um_per_rad"])
    summaries["single_cylinder_independent_check"] = comparison
    convergence = []
    centers, radii = hex_bundle(1, radius_um=5.0, gap_um=0.4)
    for count in (2000, 10000, 50000):
        values, reported = [], []
        for seed in range(32):
            result = trace_bundle(centers, radii, n_rays=count, seed=3000 + seed)
            values.append(result["energy"]["backward"])
            reported.append(result["energy_standard_error"]["backward"])
        convergence.append({"n_rays": count, "n_seeds": 32,
                            "backward_mean": float(np.mean(values)),
                            "between_seed_std": float(np.std(values, ddof=1)),
                            "mean_reported_se": float(np.mean(reported)),
                            "backward_values": values})
    summaries["convergence"] = convergence
    with (output / "ply_ray_summary.json").open("w") as handle:
        json.dump(summaries, handle, indent=2, allow_nan=False)
    with (output / "ply_ray_angular.csv").open("w") as handle:
        handle.write("n_fibers,polarization,theta_rad,encountered_power_per_rad,standard_error_per_rad,intercepted_ray_dcs_um_per_rad\n")
        for row in angular_rows:
            handle.write(",".join(map(str, row)) + "\n")
    return summaries


def plot_reference_suite(output_dir):
    """Create an interpretable overview from the executed reference data."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from scipy.stats import chi2

    output = Path(output_dir)
    with (output / "ply_ray_summary.json").open() as handle:
        summary = json.load(handle)
    angular = np.genfromtxt(output / "ply_ray_angular.csv", delimiter=",", names=True, dtype=None, encoding="utf8")
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 9.3), layout="constrained")
    colors = ["#23648c", "#cf7545", "#4a8574"]
    centers, radii = hex_bundle(1, radius_um=5, gap_um=0.4)
    rays = trace_bundle(centers, radii, n_rays=80, seed=482, record_paths=80)
    ax = axes[0, 0]
    for path in rays["ray_paths_um"]:
        ax.plot(path[:, 0], path[:, 1], color=colors[0], linewidth=0.55, alpha=0.28)
    for center, radius in zip(centers, radii):
        ax.add_patch(Circle(center, radius, facecolor="#e7ecef", edgecolor="#3f596b", linewidth=1.0, alpha=0.85))
    ax.set(xlim=(-22, 22), ylim=(-18, 18), aspect="equal", xlabel="x (um)", ylabel="y (um)",
           title="A. Explicit refraction and repeated fiber encounters")
    ax.text(0.02, 0.97, "80 power-ray trajectories; incident +x", transform=ax.transAxes,
            va="top", fontsize=9, bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))

    ax = axes[0, 1]
    for count, color in zip((1, 7, 19), colors):
        rows = angular[(angular["n_fibers"] == count) & (angular["polarization"] == "unpolarized")]
        density = rows["encountered_power_per_rad"]
        ax.semilogy(np.rad2deg(rows["theta_rad"]), np.where(density > 0, density, np.nan),
                    color=color, linewidth=1.25, label=f"{count} fiber" if count == 1 else f"{count} fibers")
    ax.axvline(-90, color="#aeb5ba", linewidth=0.7)
    ax.axvline(90, color="#aeb5ba", linewidth=0.7)
    ax.set(xlim=(-180, 180), ylim=(0.002, 4), xlabel="Outgoing angle from +x (degrees)",
           ylabel="Power / incident beam power / rad",
           title="B. Bundle geometry changes angular redistribution")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.2)

    ax = axes[1, 0]
    names = ["n1_unpolarized", "n7_unpolarized", "n19_unpolarized", "n19_mu0.02", "n7_open_gaps"]
    labels = ["1 fiber", "7 fibers", "19 fibers", "19 fibers\nmu = 0.02/um", "7 fibers\ngap = 3 um"]
    base = np.zeros(len(names))
    for channel, label, color in [
        ("backward", "Backward", "#23648c"),
        ("collided_forward", "Encountered, forward", "#72abbd"),
        ("uncollided_forward", "Uncollided", "#b8d1a0"),
        ("absorbed", "Absorbed", "#ca845d"),
        ("residual", "Residual", "#bd5570"),
    ]:
        values = np.array([summary[name]["energy"][channel] for name in names])
        if np.any(values > 0):
            ax.bar(np.arange(len(names)), values, bottom=base, color=color, label=label, width=0.63)
        base += values
    ax.set(xticks=np.arange(len(names)), xticklabels=labels, ylim=(0, 1.19),
           ylabel="Fraction of incident beam power", title="C. Explicit energy accounting; no renormalization")
    ax.legend(frameon=False, fontsize=8, ncols=2, loc="upper center")
    ax.yaxis.grid(alpha=0.18)
    ax.set_axisbelow(True)

    ax = axes[1, 1]
    conv = summary["convergence"]
    n = np.array([row["n_rays"] for row in conv])
    predicted = np.array([row["mean_reported_se"] for row in conv])
    measured = np.array([row["between_seed_std"] for row in conv])
    df = np.array([row["n_seeds"] - 1 for row in conv])
    ax.fill_between(n, predicted * np.sqrt(chi2.ppf(0.025, df) / df),
                    predicted * np.sqrt(chi2.ppf(0.975, df) / df), color="#dbe8ef",
                    label="95% range for finite-seed SD")
    ax.loglog(n, predicted, "o-", color=colors[0], label="Per-ray standard error")
    ax.loglog(n, measured, "s--", color=colors[1], label=f"Observed SD over {conv[0]['n_seeds']} seeds")
    ax.set(xlabel="Incident rays per seed", ylabel="Backward-power sampling uncertainty",
           title="D. Sampling uncertainty and independent-seed check")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.2, which="both")
    fig.suptitle("Synthetic dielectric-fiber bundles: a numerically checked 2D ray baseline\n"
                 "n = 1.55, radius = 5 um, reference gap = 0.4 um; no coherence or diffraction",
                 fontsize=14, fontweight="semibold")
    fig.savefig(output / "ply_ray_overview.png", dpi=180)
    fig.savefig(output / "ply_ray_overview.svg")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data")
    args = parser.parse_args()
    data = run_reference_suite(args.output_dir)
    plot_reference_suite(args.output_dir)
    print(json.dumps({key: value["energy"] for key, value in data.items() if isinstance(value, dict) and "energy" in value}, indent=2))
