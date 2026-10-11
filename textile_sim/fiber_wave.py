"""Exact 2-D Maxwell scattering by circular dielectric fibers.

All lengths are in micrometers.  Cylinders are infinite along z; the host is
vacuum/air (n=1), mu_r=1 everywhere, and exp(-i*omega*t) is used.  ``Ez`` means
the electric field is parallel to the cylinder axis; ``Hz`` means the magnetic
field is parallel.  These names avoid the inconsistent TE/TM naming found in
different literatures.  Hankel-1 is outgoing, so Im(n)>=0 is passive.

This is an independent implementation of the boundary-value equations and
Graf translation theorem, not code from the 2025 ray-wave cloth paper.  A
finite cylinder *cross-section* cluster remains infinite and parallel along z:
it is not a full 3-D twisted yarn or a measured real textile.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from scipy import special
from scipy.linalg import solve


def _parameters(radius_um, wavelength_um, n_complex, polarization, n_terms):
    a, lam, m = float(radius_um), float(wavelength_um), complex(n_complex)
    if not np.isfinite(a) or not np.isfinite(lam) or a <= 0 or lam <= 0:
        raise ValueError("radius_um and wavelength_um must be positive finite values")
    if not np.isfinite(m) or m.real <= 0 or m.imag < 0:
        raise ValueError("A passive dielectric index requires Re(n)>0 and Im(n)>=0")
    if polarization not in ("Ez", "Hz"):
        raise ValueError("polarization must be 'Ez' or 'Hz'")
    x = 2 * np.pi * a / lam
    # A conservative starting truncation, not a mathematical error guarantee.
    # Users must still check N convergence, particularly near resonances or gaps.
    order = max(5, int(np.ceil(x + 4 * np.cbrt(x) + 10))) if n_terms is None else int(n_terms)
    if order < 1 or (n_terms is not None and order != n_terms):
        raise ValueError("n_terms denotes the positive maximum multipole order N")
    return a, lam, m, x, order


def cylinder_coefficients(radius_um, wavelength_um, n_complex, polarization="Ez", n_terms=None):
    """Return diagonal T coefficients t_n and internal coefficients q_n.

    Incident J_n + t_n H_n^(1) = q_n J_n(m*x) at the surface.
    Derivative condition: J_n' + t_n H_n' = gamma q_n J_n'(m*x),
    where gamma=m for Ez and gamma=1/m for Hz.  Thus

      t_n = [gamma J_n'(mx) J_n(x) - J_n'(x) J_n(mx)] /
            [H_n'(x) J_n(mx) - gamma H_n(x) J_n'(mx)].

    Cross-section formulas below use this t_n, whose real part is nonpositive
    for a lossless fiber; many texts instead define a_n=-t_n.
    """
    a, lam, m, x, order = _parameters(radius_um, wavelength_um, n_complex, polarization, n_terms)
    modes = np.arange(-order, order + 1)
    j = special.jv(modes, x)
    jp = special.jvp(modes, x)
    h = special.hankel1(modes, x)
    hp = special.h1vp(modes, x)
    jm = special.jv(modes, m * x)
    jmp = special.jvp(modes, m * x)
    gamma = m if polarization == "Ez" else 1 / m
    denominator = hp * jm - gamma * h * jmp
    if m == 1:
        # Mathematically exact index matching, avoiding cancellation noise.
        t, q = np.zeros(modes.size, complex), np.ones(modes.size, complex)
    else:
        t = (gamma * jmp * j - jp * jm) / denominator
        q = (j * hp - jp * h) / denominator
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(q)):
        raise FloatingPointError("Bessel expansion exceeded floating-point range; change order or use scaled special functions")
    value_residual = np.linalg.norm(j + t * h - q * jm) / max(np.linalg.norm(j), 1e-300)
    derivative_residual = np.linalg.norm(jp + t * hp - gamma * q * jmp) / max(np.linalg.norm(jp), 1e-300)
    return {"modes": modes, "t": t, "internal_q": q, "surface_h": h,
            "x": x, "n_terms": order, "radius_um": a, "wavelength_um": lam,
            "n_complex": m, "polarization": polarization,
            "boundary_value_residual": float(value_residual),
            "boundary_derivative_residual": float(derivative_residual)}


def cylinder_scattering(radius_um, wavelength_um, n_complex, polarization="Ez", theta=None, n_terms=None,
                        incident_angle=0.0):
    """Exact single-cylinder differential and total cross-sections.

    theta and incident_angle are in radians from +x.  ``far_field`` is the
    dimensionless F(theta) in u_s ~ sqrt(2/(pi*k*r))*exp(i*(kr-pi/4))*F.
    dCsca_dtheta has units um/rad, and Csca/Cext/Cabs have units um (per unit
    infinite-cylinder axial length).  Returned cross-sections do not depend on
    the user's theta quadrature.  No intensity or absorption is clipped.
    """
    result = cylinder_coefficients(radius_um, wavelength_um, n_complex, polarization, n_terms)
    theta = np.linspace(-np.pi, np.pi, 1440, endpoint=False) if theta is None else np.atleast_1d(np.asarray(theta, float))
    if not np.all(np.isfinite(theta)) or not np.isfinite(incident_angle):
        raise ValueError("All observation and illumination angles must be finite")
    k = 2 * np.pi / result["wavelength_um"]
    t, modes = result["t"], result["modes"]
    far = np.exp(1j * np.outer(theta - incident_angle, modes)) @ t
    csca = 4 / k * np.vdot(t, t).real
    cext = -4 / k * np.sum(t).real
    cabs = cext - csca
    # Independent angular integration of the explicitly evaluated far field.
    nquad = max(512, 8 * (2 * result["n_terms"] + 1))
    tq = 2 * np.pi * np.arange(nquad) / nquad
    fq = np.exp(1j * np.outer(tq - incident_angle, modes)) @ t
    angular_csca = 4 / k * np.mean(np.abs(fq) ** 2)
    result.update({"theta": theta, "incident_angle": float(incident_angle),
                   "far_field": far, "dCsca_dtheta": 2 / (np.pi * k) * np.abs(far) ** 2,
                   "Csca": float(csca), "Cext": float(cext), "Cabs": float(cabs),
                   "Csca_angular": float(angular_csca), "angular_samples_for_integral": nquad,
                   "optical_theorem_Cext": float(-4 / k * np.real(np.sum(t))),
                   "modal_passivity_residual": float(np.max(t.real + np.abs(t) ** 2))})
    return result


def _cluster_far_field(theta, modes, b, positions, k):
    theta = np.atleast_1d(np.asarray(theta, float))
    angular = np.exp(1j * np.outer(theta, modes)) @ (b * (-1j) ** modes).T
    directions = np.column_stack((np.cos(theta), np.sin(theta)))
    phases = np.exp(-1j * k * (directions @ positions.T))
    return np.sum(angular * phases, axis=1)


def cluster_scattering(positions_um, radius_um, wavelength_um, n_complex, polarization="Ez", theta=None,
                       n_terms=None, incident_angle=0.0, quadrature_samples=None):
    """Coupled exact multipoles for nonoverlapping parallel circular cylinders.

    radius_um and n_complex may be scalars or length-M arrays.  A common N is
    used.  b[j,n] is the raw coefficient of H_n^(1)(k*r_j)*exp(i*n*phi_j).
    Surface-Hankel scaling of the unknowns improves the linear system's
    conditioning without changing the boundary-value problem.

    Cabs = Cext-Csca is compared with an independent sum of boundary energy
    fluxes, ``Cabs_local_flux``.  Csca is integrated from the far field; it is
    never set to Cext-Cabs or normalized to enforce conservation.
    """
    positions = np.asarray(positions_um, float)
    if positions.ndim != 2 or positions.shape[1] != 2 or len(positions) < 1 or not np.all(np.isfinite(positions)):
        raise ValueError("positions_um must be a finite array with shape (M,2)")
    count = len(positions)
    radii = np.broadcast_to(np.asarray(radius_um, float), (count,)).copy()
    indices = np.broadcast_to(np.asarray(n_complex, complex), (count,)).copy()
    raw = [_parameters(a, wavelength_um, n, polarization, n_terms) for a, n in zip(radii, indices)]
    order = max(p[4] for p in raw)
    if not np.isfinite(incident_angle):
        raise ValueError("incident_angle must be finite")
    for j in range(count):
        for ell in range(j):
            if np.linalg.norm(positions[j] - positions[ell]) <= radii[j] + radii[ell]:
                raise ValueError("Cylinders must be disjoint with a strictly positive gap")
    coeffs = [cylinder_coefficients(a, wavelength_um, n, polarization, order) for a, n in zip(radii, indices)]
    modes = coeffs[0]["modes"]
    width = len(modes)
    k = 2 * np.pi / float(wavelength_um)
    t = np.stack([c["t"] for c in coeffs])
    h = np.stack([c["surface_h"] for c in coeffs])
    direction = np.array([np.cos(incident_angle), np.sin(incident_angle)])
    plane_c = np.exp(1j * k * (positions @ direction))[:, None] * (1j ** modes * np.exp(-1j * modes * incident_angle))[None, :]
    matrix = np.eye(count * width, dtype=complex)
    # G[jn,lm] = H_(m-n)(k|c_j-c_l|) exp(i(m-n) arg(c_j-c_l)).
    difference = modes[None, :] - modes[:, None]
    translation_modes = np.arange(-2 * order, 2 * order + 1)
    translation_indices = difference + 2 * order
    for j in range(count):
        js = slice(j * width, (j + 1) * width)
        for ell in range(count):
            if ell == j:
                continue
            delta = positions[j] - positions[ell]
            distance = np.linalg.norm(delta)
            beta = np.arctan2(delta[1], delta[0])
            # Each block is Toeplitz: compute only its 4N+1 unique special-
            # function values, not (2N+1)^2 redundant evaluations.
            unique_translation = special.hankel1(translation_modes, k * distance) * np.exp(1j * translation_modes * beta)
            translation = unique_translation[translation_indices]
            block = (t[j] * h[j])[:, None] * translation / h[ell][None, :]
            matrix[js, ell * width:(ell + 1) * width] = -block
    rhs = (t * h * plane_c).reshape(-1)
    u = solve(matrix, rhs, assume_a="gen", check_finite=True)
    linear_residual = np.linalg.norm(matrix @ u - rhs) / max(np.linalg.norm(rhs), 1e-300)
    b = u.reshape(count, width) / h
    local_c = plane_c.copy()
    for j in range(count):
        for ell in range(count):
            if ell == j:
                continue
            delta = positions[j] - positions[ell]
            beta = np.arctan2(delta[1], delta[0])
            unique_translation = special.hankel1(translation_modes, k * np.linalg.norm(delta)) * np.exp(1j * translation_modes * beta)
            translation = unique_translation[translation_indices]
            local_c[j] += translation @ b[ell]
    theta = np.linspace(-np.pi, np.pi, 1440, endpoint=False) if theta is None else np.atleast_1d(np.asarray(theta, float))
    if not np.all(np.isfinite(theta)):
        raise ValueError("theta must contain finite angles")
    far = _cluster_far_field(theta, modes, b, positions, k)
    forward = _cluster_far_field(np.array([incident_angle]), modes, b, positions, k)[0]
    extent = np.max(np.linalg.norm(positions - np.mean(positions, axis=0), axis=1) + radii)
    if quadrature_samples is None:
        target = max(512, int(16 * (order + k * extent + 1)))
        quadrature_samples = 1 << (target - 1).bit_length()
    quadrature_samples = int(quadrature_samples)
    if quadrature_samples < 16:
        raise ValueError("quadrature_samples must be at least 16")
    quad_theta = 2 * np.pi * np.arange(quadrature_samples) / quadrature_samples
    quad_far = _cluster_far_field(quad_theta, modes, b, positions, k)
    csca = 4 / k * np.mean(np.abs(quad_far) ** 2)
    cext = -4 / k * forward.real
    # Independent inward energy flux of regular + outgoing waves at each
    # cylinder boundary: -(4/k) sum_n[Re(c_n* b_n) + |b_n|^2].
    local_abs = -4 / k * np.sum(np.real(np.conj(local_c) * b) + np.abs(b) ** 2, axis=1)
    cabs = cext - csca
    return {"theta": theta, "far_field": far, "dCsca_dtheta": 2 / (np.pi * k) * np.abs(far) ** 2,
            "Csca": float(csca), "Cext": float(cext), "Cabs": float(cabs),
            "Cabs_local_flux": float(np.sum(local_abs)), "Cabs_per_cylinder": local_abs,
            "energy_flux_residual": float(cabs - np.sum(local_abs)),
            "relative_energy_flux_residual": float(abs(cabs - np.sum(local_abs)) / max(abs(cext), abs(csca), 1e-300)),
            "linear_system_residual": float(linear_residual),
            "positions_um": positions, "radius_um": radii, "n_complex": indices,
            "wavelength_um": float(wavelength_um), "polarization": polarization,
            "incident_angle": float(incident_angle), "n_terms": order, "modes": modes,
            "b": b, "local_c": local_c, "plane_c": plane_c,
            "internal_q": np.stack([c["internal_q"] for c in coeffs]),
            "angular_samples_for_integral": quadrature_samples}


def cluster_field(result, x_um, y_um):
    """Evaluate total complex Ez or Hz on arbitrary broadcastable points.

    Uses the converged solution returned by cluster_scattering.  This is the
    scalar field component, not full vector energy density.  At an exact
    cylinder interface either trace is equal up to numerical truncation.
    """
    x, y = np.broadcast_arrays(np.asarray(x_um, float), np.asarray(y_um, float))
    shape = x.shape
    points = np.column_stack((x.ravel(), y.ravel()))
    positions, radii = result["positions_um"], result["radius_um"]
    modes, k = result["modes"], 2 * np.pi / result["wavelength_um"]
    alpha = result["incident_angle"]
    owner = np.full(len(points), -1, dtype=int)
    for j, (center, radius) in enumerate(zip(positions, radii)):
        owner[np.linalg.norm(points - center, axis=1) < radius] = j
    field = np.zeros(len(points), complex)
    outside = owner < 0
    pout = points[outside]
    field[outside] = np.exp(1j * k * (pout @ np.array([np.cos(alpha), np.sin(alpha)])))
    for j, center in enumerate(positions):
        delta = pout - center
        r = np.linalg.norm(delta, axis=1)
        phi = np.arctan2(delta[:, 1], delta[:, 0])
        field[outside] += np.sum(special.hankel1(modes[None, :], k * r[:, None]) * np.exp(1j * phi[:, None] * modes) * result["b"][j], axis=1)
        inside = owner == j
        if np.any(inside):
            delta_i = points[inside] - center
            ri = np.linalg.norm(delta_i, axis=1)
            phii = np.arctan2(delta_i[:, 1], delta_i[:, 0])
            field[inside] = np.sum(special.jv(modes[None, :], result["n_complex"][j] * k * ri[:, None]) * np.exp(1j * phii[:, None] * modes) * result["internal_q"][j] * result["local_c"][j], axis=1)
    return field.reshape(shape)


def incoherent_cylinder_average(radius_um, wavelengths_um, n_complex, polarization="Ez", theta=None,
                                incident_angles=(0.0,), wavelength_weights=None, angle_weights=None):
    """Average *intensities* of mutually incoherent source wavelengths/angles.

    Weights are normalized incident irradiance fractions.  n_complex may be a
    scalar or one index for each wavelength.  No coherent amplitude average is
    returned because this experiment explicitly assumes mutually incoherent
    illumination components.
    """
    wavelengths = np.atleast_1d(np.asarray(wavelengths_um, float))
    angles = np.atleast_1d(np.asarray(incident_angles, float))
    indices = np.broadcast_to(np.asarray(n_complex, complex), wavelengths.shape)
    ww = np.ones(wavelengths.size) if wavelength_weights is None else np.asarray(wavelength_weights, float)
    aw = np.ones(angles.size) if angle_weights is None else np.asarray(angle_weights, float)
    if ww.shape != wavelengths.shape or aw.shape != angles.shape or np.any(ww < 0) or np.any(aw < 0) or not np.all(np.isfinite(ww)) or not np.all(np.isfinite(aw)) or ww.sum() <= 0 or aw.sum() <= 0:
        raise ValueError("Weights must be finite, nonnegative, matched to samples, and have positive sum")
    ww, aw = ww / ww.sum(), aw / aw.sum()
    theta = np.linspace(-np.pi, np.pi, 1440, endpoint=False) if theta is None else np.atleast_1d(np.asarray(theta, float))
    differential = np.zeros(theta.size)
    csca = cext = cabs = 0.0
    for lam, index, wlam in zip(wavelengths, indices, ww):
        base = cylinder_coefficients(radius_um, lam, index, polarization)
        k = 2 * np.pi / lam
        for alpha, wa in zip(angles, aw):
            far = np.exp(1j * np.outer(theta - alpha, base["modes"])) @ base["t"]
            differential += wlam * wa * 2 / (np.pi * k) * np.abs(far) ** 2
        cs = 4 / k * np.vdot(base["t"], base["t"]).real
        ce = -4 / k * np.sum(base["t"]).real
        csca += wlam * cs
        cext += wlam * ce
        cabs += wlam * (ce - cs)
    return {"theta": theta, "dCsca_dtheta": differential, "Csca": float(csca), "Cext": float(cext), "Cabs": float(cabs),
            "wavelengths_um": wavelengths, "incident_angles": angles, "wavelength_weights": ww, "angle_weights": aw}


def run_experiments(output_dir=None):
    """Write reproducible numerical experiments; never treated as measured data."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path(output_dir) if output_dir else Path(__file__).resolve().parents[1] / "data"
    output.mkdir(parents=True, exist_ok=True)
    theta = np.linspace(-np.pi, np.pi, 2048, endpoint=False)
    wavelength, index = 0.55, 1.53
    sizes = np.geomspace(0.01, 150, 100)
    sweep = {}
    metrics = {"conventions": {"length_unit": "um", "index": "synthetic n=1.53; not a named real fiber", "time_convention": "exp(-i omega t)", "geometry": "infinite circular cylinder along z; incident +x"}}
    for pol in ("Ez", "Hz"):
        vals = []
        for x in sizes:
            a = x * wavelength / (2 * np.pi)
            q = cylinder_scattering(a, wavelength, index, pol, theta=np.array([0.0]))
            vals.append([q["Csca"] / (2 * a), q["Cext"] / (2 * a), q["Cabs"] / (2 * a), q["boundary_value_residual"], q["boundary_derivative_residual"], q["n_terms"]])
        sweep[pol] = np.asarray(vals)
    np.savez_compressed(output / "fiber_wave_size_sweep.npz", size_parameter=sizes, **sweep)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for pol in ("Ez", "Hz"):
        axes[0].loglog(sizes, sweep[pol][:, 0], label=pol)
        axes[1].semilogx(sizes, sweep[pol][:, 0], label=pol)
    axes[0].set(xlabel="Size parameter 2 pi a / wavelength", ylabel="Scattering efficiency Csca / (2a)", title="Exact cylinder: small to optical-size fiber")
    axes[1].set(xlabel="Size parameter 2 pi a / wavelength", ylabel="Scattering efficiency Csca / (2a)", title="Lossless synthetic dielectric n = 1.53", ylim=(0, 4.5))
    for ax in axes: ax.grid(alpha=.2); ax.legend()
    fig.savefig(output / "fiber_wave_size_sweep.png", dpi=180); plt.close(fig)
    profiles = {}
    metrics["cylinder_checks"] = {}
    for pol in ("Ez", "Hz"):
        one = cylinder_scattering(5.0, .55, index, pol, theta)
        broad = incoherent_cylinder_average(5.0, np.linspace(.45, .65, 15), index, pol, theta, np.deg2rad(np.linspace(-3, 3, 9)))
        profiles[pol + "_monochromatic"] = one["dCsca_dtheta"]
        profiles[pol + "_incoherent"] = broad["dCsca_dtheta"]
        metrics["cylinder_checks"][pol] = {key: one[key] for key in ("Csca", "Cext", "Cabs", "Csca_angular", "boundary_value_residual", "boundary_derivative_residual", "n_terms")}
    np.savez_compressed(output / "fiber_wave_angular_profiles.npz", theta_rad=theta, **profiles)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for ax, pol in zip(axes, ("Ez", "Hz")):
        ax.semilogy(np.rad2deg(theta), profiles[pol + "_monochromatic"], lw=1, label="550 nm, plane wave")
        ax.semilogy(np.rad2deg(theta), profiles[pol + "_incoherent"], lw=1.8, label="450-650 nm + +/-3 deg source")
        ax.set(xlabel="Outgoing propagation angle (deg)", ylabel="dCsca / dtheta (um/rad)", title=f"{pol}: radius 5 um, synthetic n = 1.53", xlim=(-180, 180), ylim=(1e-4, 400)); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.savefig(output / "fiber_wave_angular_profiles.png", dpi=180); plt.close(fig)
    # A controlled seven-cylinder cross-section.  This includes coherent
    # electromagnetic coupling among fibers, not just isolated-fiber sums.
    ring = 1.0 * np.column_stack((np.cos(np.arange(6) * np.pi / 3), np.sin(np.arange(6) * np.pi / 3)))
    positions = np.vstack((np.zeros(2), ring))
    rng = np.random.default_rng(271828)
    disordered = positions + rng.normal(0, .045, positions.shape)
    cluster_results = {}
    cluster_profiles = {}
    for pol in ("Ez", "Hz"):
        exact = cluster_scattering(positions, .35, .55, index, pol, theta)
        disorder = cluster_scattering(disordered, .35, .55, index, pol, theta)
        single = cylinder_scattering(.35, .55, index, pol, theta)
        coupling_free = single["far_field"] * np.sum(np.exp(1j * (2 * np.pi / .55) * (positions[:, 0][None, :] - np.column_stack((np.cos(theta), np.sin(theta))) @ positions.T)), axis=1)
        independent = 2 / (np.pi * (2 * np.pi / .55)) * np.abs(coupling_free) ** 2
        cluster_profiles[pol + "_coupled"] = exact["dCsca_dtheta"]
        cluster_profiles[pol + "_single_scattering"] = independent
        cluster_profiles[pol + "_disordered"] = disorder["dCsca_dtheta"]
        metrics["cluster_" + pol] = {key: exact[key] for key in ("Csca", "Cext", "Cabs", "Cabs_local_flux", "relative_energy_flux_residual", "linear_system_residual", "n_terms", "angular_samples_for_integral")}
        metrics["cluster_" + pol]["coupling_free_intensity_relative_L2_error"] = float(np.linalg.norm(independent - exact["dCsca_dtheta"]) / np.linalg.norm(exact["dCsca_dtheta"]))
        independent_csca = float(2 * np.pi * np.mean(independent))
        independent_cext = float(len(positions) * single["Cext"])
        metrics["cluster_" + pol]["coupling_free_Csca"] = independent_csca
        metrics["cluster_" + pol]["coupling_free_Cext"] = independent_cext
        metrics["cluster_" + pol]["coupling_free_apparent_Cabs"] = independent_cext - independent_csca
        metrics["cluster_" + pol]["disorder_intensity_relative_L2_change"] = float(np.linalg.norm(disorder["dCsca_dtheta"] - exact["dCsca_dtheta"]) / np.linalg.norm(exact["dCsca_dtheta"]))
        cluster_results[pol] = exact
    np.savez_compressed(output / "fiber_wave_cluster_profiles.npz", theta_rad=theta, positions_um=positions, disordered_positions_um=disordered, **cluster_profiles)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for ax, pol in zip(axes, ("Ez", "Hz")):
        for suffix, label in (("_coupled", "Coupled Maxwell"), ("_single_scattering", "Independent amplitudes"), ("_disordered", "Coupled, perturbed positions")):
            ax.semilogy(np.rad2deg(theta), cluster_profiles[pol + suffix], label=label, lw=1.1)
        ax.set(xlabel="Outgoing propagation angle (deg)", ylabel="dCsca / dtheta (um/rad)", title=f"Seven fibers, a=0.35 um, {pol}", ylim=(1e-5, 300), xlim=(-180, 180)); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.savefig(output / "fiber_wave_cluster_profiles.png", dpi=180); plt.close(fig)
    # Multipole and quadrature convergence are deliberately recorded, not
    # implied by conservation (a too-small lossless truncation can conserve).
    convergence = []
    for order in (4, 6, 8, 10, 14, 18, 22, 26):
        c = cluster_scattering(positions, .35, .55, index, "Ez", theta, n_terms=order, quadrature_samples=2048)
        ref = cluster_results["Ez"]
        convergence.append({"N": order, "Csca": c["Csca"], "Cext": c["Cext"], "relative_energy_flux_residual": c["relative_energy_flux_residual"], "intensity_relative_L2_to_default": float(np.linalg.norm(c["dCsca_dtheta"] - ref["dCsca_dtheta"]) / np.linalg.norm(ref["dCsca_dtheta"]))})
    metrics["cluster_multipole_convergence"] = convergence
    metrics["size_sweep_max_relative_lossless_energy_error"] = float(max(np.max(np.abs(sweep[p][:, 2]) / np.maximum(sweep[p][:, 1], 1e-30)) for p in sweep))
    metrics["size_sweep_max_boundary_residual"] = float(max(np.max(sweep[p][:, 3:5]) for p in sweep))
    # Passive absorbing check, independent local flux vs global optical theorem.
    absorbing = cluster_scattering(positions, .35, .55, 1.53 + .02j, "Ez", theta=np.array([0.0]))
    metrics["absorbing_cluster"] = {key: absorbing[key] for key in ("Csca", "Cext", "Cabs", "Cabs_local_flux", "relative_energy_flux_residual")}
    metrics["absorbing_cluster"]["Cabs_per_cylinder"] = absorbing["Cabs_per_cylinder"].tolist()
    # Field image (component magnitude squared; NOT vector energy density).
    grid = np.linspace(-2.1, 2.1, 180)
    xx, yy = np.meshgrid(grid, grid)
    field = cluster_field(cluster_results["Ez"], xx, yy)
    np.savez_compressed(output / "fiber_wave_cluster_field.npz", x_um=grid, y_um=grid, field_real=field.real, field_imag=field.imag)
    fig, ax = plt.subplots(figsize=(5.8, 5), constrained_layout=True)
    im = ax.imshow(np.abs(field) ** 2, origin="lower", extent=(grid[0], grid[-1], grid[0], grid[-1]), cmap="magma", vmin=0, vmax=np.percentile(np.abs(field) ** 2, 99))
    for center in positions: ax.add_patch(plt.Circle(center, .35, fill=False, ec="white", lw=.6))
    ax.set(xlabel="x (um); illumination travels right", ylabel="y (um)", title="Coupled Maxwell |Ez|^2; 550 nm")
    fig.colorbar(im, ax=ax, label="|Ez / incident Ez|^2")
    fig.savefig(output / "fiber_wave_cluster_field.png", dpi=180); plt.close(fig)
    (output / "fiber_wave_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def run_textile_benchmark(output_dir=None, n_rays=150000):
    """Matched optical-size wave/ray benchmark with explicit forward exclusion.

    This calls ply_ray's original geometry and ray tracer rather than silently
    substituting a different fiber packing.  It compares absolute cross-
    sections in equal 2-degree angular bins, with no normalization to force
    ray/wave agreement.  It is a finite, small ensemble, not the Yu et al.
    paper's 3-D Gaussian-beam calibration or a measured textile validation.
    """
    import time
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .ply_ray import hex_bundle, trace_bundle
    output = Path(output_dir) if output_dir else Path(__file__).resolve().parents[1] / "data"
    output.mkdir(parents=True, exist_ok=True)
    positions, radii = hex_bundle(shells=1, radius_um=5.0, gap_um=.4)
    rng = np.random.default_rng(20261010)
    geometries = [positions]
    for _ in range(2):
        while True:
            candidate = positions + rng.normal(0, .06, positions.shape)
            distances = np.linalg.norm(candidate[:, None] - candidate[None, :], axis=2)
            np.fill_diagonal(distances, np.inf)
            if np.min(distances) > 2 * radii[0]:
                geometries.append(candidate)
                break
    wavelengths = np.array([.45, .55, .65])
    bins, subsamples = 180, 48
    edges = np.linspace(-np.pi, np.pi, bins + 1)
    centers = .5 * (edges[:-1] + edges[1:])
    step = edges[1] - edges[0]
    theta = -np.pi + (np.arange(bins * subsamples) + .5) * 2 * np.pi / (bins * subsamples)
    mask = np.abs(centers) > np.deg2rad(6)
    backward = np.cos(centers) < 0
    meta = {"model": "exact 2D cylinder cluster vs incoherent geometric power rays",
            "geometry": "ply_ray.hex_bundle(shells=1, radius_um=5, gap_um=.4)",
            "index": "fixed synthetic n=1.55 (no material-specific dispersion)",
            "wavelengths_um": wavelengths.tolist(), "polarizations": ["Ez", "Hz"],
            "n_geometries": 3, "geometry_ensemble": "regular hexagon plus two center-jitter realizations, sigma=.06 um",
            "geometry_seed": 20261010, "bin_width_deg": 2, "subsamples_per_bin": subsamples,
            "forward_exclusion_half_angle_deg": 6,
            "averaging": "equal incoherent irradiance weights across 3 wavelengths and 3 geometries",
            "ray_count_per_geometry_per_polarization": n_rays,
            "comparison": "absolute um/rad, no energy or shape renormalization; forward exclusion avoids comparing the direct diffraction peak with an absent ray term",
            "earlier_same_configuration_unoptimized_solve_seconds": 9.88561500799915,
            "wave_convergence": [], "ray_cases": [], "comparison_metrics": {}}
    arrays = {"theta_rad": theta, "theta_bin_centers_rad": centers, "theta_bin_edges_rad": edges,
              "geometries_um": np.asarray(geometries), "radii_um": radii,
              "wavelengths_um": wavelengths, "off_forward_mask": mask}
    started = time.perf_counter()
    for pol in ("Ez", "Hz"):
        wave_average = np.zeros(theta.size)
        ray_average = np.zeros(bins)
        ray_variance = np.zeros(bins)
        raw_profile = None
        raw_ray = None
        raw_se = None
        wave_backscatter = 0.0
        ray_backscatter = 0.0
        ray_backscatter_variance = 0.0
        for gi, geometry in enumerate(geometries):
            for wavelength in wavelengths:
                t0 = time.perf_counter()
                low = cluster_scattering(geometry, radii, wavelength, 1.55, pol, theta=theta)
                tlow = time.perf_counter() - t0
                t0 = time.perf_counter()
                high = cluster_scattering(geometry, radii, wavelength, 1.55, pol, theta=theta, n_terms=low["n_terms"] + 8)
                thigh = time.perf_counter() - t0
                relative_change = float(np.linalg.norm(high["dCsca_dtheta"] - low["dCsca_dtheta"]) / np.linalg.norm(high["dCsca_dtheta"]))
                initial_order = low["n_terms"]
                attempts = [{"N_low": low["n_terms"], "N_high": high["n_terms"], "relative_L2": relative_change,
                             "seconds_low": tlow, "seconds_high": thigh}]
                # Near-field coupling can excite modes beyond the isolated-
                # cylinder heuristic.  Preserve the failed comparison and
                # increase order; never relax the declared acceptance gate.
                while relative_change > 1e-7 and high["n_terms"] < initial_order + 32:
                    low, tlow = high, thigh
                    t0 = time.perf_counter()
                    high = cluster_scattering(geometry, radii, wavelength, 1.55, pol, theta=theta, n_terms=low["n_terms"]+8)
                    thigh = time.perf_counter()-t0
                    relative_change = float(np.linalg.norm(high["dCsca_dtheta"]-low["dCsca_dtheta"])/np.linalg.norm(high["dCsca_dtheta"]))
                    attempts.append({"N_low":low["n_terms"],"N_high":high["n_terms"],"relative_L2":relative_change,
                                     "seconds_low":tlow,"seconds_high":thigh})
                meta["wave_convergence"].append({"polarization": pol, "geometry_index": gi,
                    "wavelength_um": float(wavelength), "N_low": low["n_terms"], "N_high": high["n_terms"],
                    "seconds_low": tlow, "seconds_high": thigh,
                    "order_attempts": attempts,
                    "angular_intensity_relative_L2_change": relative_change,
                    "relative_Csca_change": abs(low["Csca"]-high["Csca"])/high["Csca"],
                    "Csca_um": high["Csca"], "Cext_um": high["Cext"],
                    "global_vs_local_flux_relative_residual": high["relative_energy_flux_residual"]})
                if relative_change > 1e-7:
                    raise RuntimeError(f"Textile wave multipole convergence gate failed: {pol}, geometry={gi}, wavelength={wavelength}, relL2={relative_change}")
                wave_average += high["dCsca_dtheta"] / (len(geometries) * len(wavelengths))
                if gi == 0 and np.isclose(wavelength, .55):
                    raw_profile = high["dCsca_dtheta"].copy()
                    meta.setdefault("single_configuration", {})[pol] = {"Csca_um": high["Csca"], "Cext_um": high["Cext"], "N": high["n_terms"], "seconds": thigh}
                    isolated = cylinder_scattering(radii[0], wavelength, 1.55, pol, theta=theta)
                    k = 2 * np.pi / wavelength
                    directions = np.column_stack((np.cos(theta), np.sin(theta)))
                    free_amplitude = isolated["far_field"] * np.sum(np.exp(1j*k*(geometry[:, 0][None, :] - directions @ geometry.T)), axis=1)
                    independent = 2 / (np.pi*k) * np.abs(free_amplitude)**2
                    arrays[pol + "_coupling_free_coherent_dcs"] = independent
                    meta["single_configuration"][pol]["coupling_free_relative_intensity_L2_error"] = float(np.linalg.norm(independent-raw_profile)/np.linalg.norm(raw_profile))
                    meta["single_configuration"][pol]["coupling_free_Csca_um"] = float(2*np.pi*np.mean(independent))
                    meta["single_configuration"][pol]["coupling_free_Cext_um"] = float(len(radii)*isolated["Cext"])
            t0 = time.perf_counter()
            ray = trace_bundle(geometry, radii, n_fiber=1.55, n_rays=n_rays, seed=74519+gi,
                               polarization=pol, theta_bins=bins, max_events=200)
            elapsed = time.perf_counter()-t0
            if ray["summary"]["numerical_failure_count"] != 0 or ray["energy"]["residual"] > 1e-4:
                raise RuntimeError("Matched ray benchmark has unresolved failures or event truncation")
            ray_average += ray["intercepted_ray_dcs_um_per_rad"] / len(geometries)
            ray_variance += (ray["intercepted_ray_dcs_standard_error_um_per_rad"] / len(geometries))**2
            width = ray["summary"]["beam_width_um"]
            ray_backscatter += width * ray["energy"]["backward"] / len(geometries)
            ray_backscatter_variance += (width * ray["energy_standard_error"]["backward"] / len(geometries))**2
            meta["ray_cases"].append({"polarization": pol, "geometry_index": gi, "seconds": elapsed,
                                     "beam_width_um": width, "energy": ray["energy"],
                                     "max_per_ray_energy_error": ray["summary"]["max_per_ray_energy_closure_error"],
                                     "numerical_failures": ray["summary"]["numerical_failure_count"]})
            if gi == 0:
                raw_ray = ray["intercepted_ray_dcs_um_per_rad"].copy()
                raw_se = ray["intercepted_ray_dcs_standard_error_um_per_rad"].copy()
        wave_binned = wave_average.reshape(bins, subsamples).mean(axis=1)
        raw_binned = raw_profile.reshape(bins, subsamples).mean(axis=1)
        ray_se = np.sqrt(ray_variance)
        wave_backscatter = float(np.sum(wave_binned[backward]) * step)
        meta["comparison_metrics"][pol] = {
            "single_wavelength_regular_geometry_off_forward_relative_L2": float(np.linalg.norm(raw_ray[mask]-raw_binned[mask])/np.linalg.norm(raw_binned[mask])),
            "averaged_off_forward_relative_L2": float(np.linalg.norm(ray_average[mask]-wave_binned[mask])/np.linalg.norm(wave_binned[mask])),
            "averaged_off_forward_relative_L1": float(np.sum(np.abs(ray_average[mask]-wave_binned[mask]))/np.sum(wave_binned[mask])),
            "wave_off_forward_cross_section_um": float(np.sum(wave_binned[mask])*step),
            "ray_off_forward_cross_section_um": float(np.sum(ray_average[mask])*step),
            "wave_backward_cross_section_um": wave_backscatter,
            "ray_backward_cross_section_um": ray_backscatter,
            "ray_backward_standard_error_um": float(np.sqrt(ray_backscatter_variance)),
            "relative_backward_cross_section_difference": float((ray_backscatter-wave_backscatter)/wave_backscatter)}
        meta["comparison_metrics"][pol]["forward_cone_sensitivity"] = []
        for cutoff in (2, 6, 12, 20, 40, 90):
            keep = np.abs(centers) > np.deg2rad(cutoff)
            meta["comparison_metrics"][pol]["forward_cone_sensitivity"].append({
                "exclusion_half_angle_deg": cutoff,
                "relative_L2": float(np.linalg.norm((ray_average-wave_binned)[keep])/np.linalg.norm(wave_binned[keep])),
                "relative_L1": float(np.sum(np.abs(ray_average-wave_binned)[keep])/np.sum(wave_binned[keep])),
                "wave_cross_section_um": float(wave_binned[keep].sum()*step),
                "ray_cross_section_um": float(ray_average[keep].sum()*step)})
        arrays.update({pol+"_single_wave_dcs": raw_profile, pol+"_wave_ensemble_dcs": wave_average,
                       pol+"_single_wave_binned_dcs": raw_binned, pol+"_wave_ensemble_binned_dcs": wave_binned,
                       pol+"_single_ray_binned_dcs": raw_ray, pol+"_single_ray_binned_se": raw_se,
                       pol+"_ray_ensemble_binned_dcs": ray_average, pol+"_ray_ensemble_binned_se": ray_se})
    meta["total_benchmark_wall_seconds"] = time.perf_counter()-started
    meta["max_multipole_intensity_relative_L2_change"] = max(c["angular_intensity_relative_L2_change"] for c in meta["wave_convergence"])
    meta["max_global_local_flux_relative_residual"] = max(c["global_vs_local_flux_relative_residual"] for c in meta["wave_convergence"])
    np.savez_compressed(output / "fiber_wave_textile_matched.npz", **arrays)
    (output / "fiber_wave_textile_matched_metrics.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for col, pol in enumerate(("Ez", "Hz")):
        ax = axes[0, col]
        ax.semilogy(np.rad2deg(theta), arrays[pol+"_single_wave_dcs"], lw=.7, alpha=.65, label="Coupled wave: 550 nm, regular geometry")
        ax.semilogy(np.rad2deg(centers), arrays[pol+"_single_ray_binned_dcs"], lw=1.3, label="Ray: same geometry, 2 deg bins")
        ax.set(title=f"{pol}: same 7 fibers, radius 5 um, gap 0.4 um", ylabel="Absolute differential cross-section (um/rad)", xlim=(-180, 180), ylim=(1e-2, 2000))
        ax.legend(fontsize=7, loc="upper right"); ax.grid(alpha=.2)
        ax = axes[1, col]
        wave, ray, se = arrays[pol+"_wave_ensemble_binned_dcs"], arrays[pol+"_ray_ensemble_binned_dcs"], arrays[pol+"_ray_ensemble_binned_se"]
        ax.plot(np.rad2deg(centers), np.where(mask,wave,np.nan), lw=1.5, label="Wave: 3 wavelengths x 3 geometries")
        ax.plot(np.rad2deg(centers), np.where(mask,ray,np.nan), lw=1.5, label="Ray: same 3 geometries")
        ax.fill_between(np.rad2deg(centers), np.where(mask,np.maximum(0,ray-2*se),np.nan), np.where(mask,ray+2*se,np.nan), alpha=.18)
        ax.axvspan(-6, 6, color="gray", alpha=.2, label="Excluded forward +/-6 deg")
        ymax = 1.13 * max(np.max(wave[mask]), np.max(ray[mask]))
        ax.set(title=f"Equal 2 deg bins; off-forward relative L2 = {meta['comparison_metrics'][pol]['averaged_off_forward_relative_L2']:.3f}", xlabel="Outgoing propagation angle (deg)", ylabel="Absolute differential cross-section (um/rad)", xlim=(-180, 180), ylim=(0, ymax))
        ax.legend(fontsize=7, loc="upper right"); ax.grid(alpha=.2)
    fig.suptitle("Synthetic optical-size bundle benchmark: no ray/wave renormalization", fontsize=14)
    fig.savefig(output / "fiber_wave_textile_matched.png", dpi=180); plt.close(fig)
    return meta


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--textile-benchmark", action="store_true", help="Run matched optical-size wave/ray benchmark instead of canonical cases")
    args = parser.parse_args()
    result = run_textile_benchmark() if args.textile_benchmark else run_experiments()
    print(json.dumps(result, indent=2))
