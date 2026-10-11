"""Ideal Poisson angular measurements of SAVED 2-D Gaussian-beam solutions.

No Maxwell/ray solver is called here.  Backward angular sectors partition the
same hemisphere; their probabilities retain each model's own reflected power.
This is a conditional model-discrimination calculation, not a camera, a
metasurface, a material classifier, or a human-perception simulation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.special import rel_entr, xlogy


SECTOR_COUNTS = (1, 6, 18, 90)


def periodic_density_integrals(theta_rad, density_per_rad, edges_rad):
    """Integrate a real periodic trigonometric interpolant over angular bins.

    Samples must cover exactly one 2*pi period on a uniform grid (no repeated
    endpoint).  Edges may be unwrapped, e.g. pi/2 .. 3*pi/2.  Every Fourier mode
    is integrated analytically, including the real Nyquist cosine.  This is
    exact for the interpolant, not a claim of exactness for under-sampled data.
    No integral is clipped or renormalized.
    """
    theta = np.asarray(theta_rad, dtype=float)
    density = np.asarray(density_per_rad, dtype=float)
    edges = np.asarray(edges_rad, dtype=float)
    if (theta.ndim != 1 or len(theta) < 4 or density.shape != theta.shape
            or edges.ndim != 1 or len(edges) < 2
            or not np.all(np.isfinite(theta))
            or not np.all(np.isfinite(density))
            or not np.all(np.isfinite(edges))):
        raise ValueError("Finite one-dimensional periodic samples and edges required")
    spacing = 2*np.pi/len(theta)
    if not np.allclose(np.diff(theta), spacing, atol=2e-12, rtol=2e-12):
        raise ValueError("Samples must span one uniform 2*pi period")
    if np.any(np.diff(edges) <= 0) or edges[-1]-edges[0] > 2*np.pi+1e-12:
        raise ValueError("Edges must increase over at most one period")
    coefficients = np.fft.rfft(density)/len(theta)
    modes = np.arange(1, len(coefficients))
    multiplicity = np.full(len(modes), 2.0)
    if len(theta) % 2 == 0:
        multiplicity[-1] = 1.0  # Real Nyquist cosine, not a complex exponential.
    c = coefficients[1:]*np.exp(-1j*modes*theta[0])*multiplicity
    mode_integrals = (np.exp(1j*modes[:, None]*edges[None, 1:])
                      - np.exp(1j*modes[:, None]*edges[None, :-1]))/(1j*modes[:, None])
    return coefficients[0].real*np.diff(edges) + np.real(c @ mode_integrals)


def backward_histogram_probabilities(density_per_rad):
    """Exact histogram-bin masses, ordered from +90 to +270 degrees.

    Input bins cover [-pi, pi), uniformly; bin count must be divisible by four.
    No assumption about an unresolved within-bin distribution is needed.
    """
    density = np.asarray(density_per_rad, dtype=float)
    if density.ndim != 1 or len(density) % 4 or len(density) < 4:
        raise ValueError("Full-circle histogram length must be divisible by four")
    if not np.all(np.isfinite(density)) or np.any(density < 0):
        raise ValueError("Histogram must be finite and nonnegative")
    n = len(density)
    return np.concatenate((density[3*n//4:], density[:n//4]))*(2*np.pi/n)


def aggregate_sectors(fine_probabilities, sectors):
    """Merge adjacent nonoverlapping angular bins, preserving total power."""
    p = np.asarray(fine_probabilities, dtype=float)
    if p.ndim < 1 or not isinstance(sectors, (int, np.integer)) or sectors < 1:
        raise ValueError("Positive integer number of sectors required")
    if p.shape[-1] % sectors:
        raise ValueError("Requested sectors must exactly divide the fine bins")
    return p.reshape(p.shape[:-1]+(sectors, p.shape[-1]//sectors)).sum(axis=-1)


def _probabilities(p):
    p = np.asarray(p, dtype=float)
    if (p.ndim != 1 or len(p) == 0 or not np.all(np.isfinite(p))
            or np.any(p < 0) or p.sum() > 1+1e-12 or p.sum() <= 0):
        raise ValueError("Detected-event probabilities must have total in (0,1]")
    return p


def poisson_information(p_true, p_other, incident_photons=1.0):
    """Directed expected LLR / Poisson KL, in nats, with exact decomposition.

    N is a known EXPECTED incident count. Y_j are independent Poisson(N*p_j).
    An exactly fixed realized incident count would instead be multinomial.
    The profile-gain term conditions on reflected total and uses q_j=p_j/R.
    """
    p = _probabilities(p_true)
    r = _probabilities(p_other)
    if p.shape != r.shape or not np.isfinite(incident_photons) or incident_photons < 0:
        raise ValueError("Equal shapes and finite nonnegative expected photons required")
    pt, rt = p.sum(), r.sum()
    flux = float(rel_entr(pt, rt)+rt-pt)
    shape = float(pt*np.sum(rel_entr(p/pt, r/rt)))
    direct = float(np.sum(rel_entr(p, r)+r-p))
    scaled = lambda value: incident_photons*value if incident_photons > 0 else 0.0
    return {
        "expected_log_likelihood_ratio_nats": scaled(direct),
        "expected_deviance": 2*scaled(direct),
        "total_flux_information_nats": scaled(flux),
        "profile_gain_information_nats": scaled(shape),
        "conditional_shape_KL_per_reflected_photon": shape/pt,
        "expected_reflected_photons": incident_photons*pt,
        "decomposition_absolute_error_nats": (scaled(abs(direct-flux-shape))
                                             if np.isfinite(direct) else None),
    }


def poisson_llr(counts, p_wave, p_ray, incident_photons, profile_gain=False):
    """Log L(wave)/L(ray), either known incident mean or profiled common gain.

    Profiling separately gives g_hat = sum(Y)/(N*R_model), leaving a conditional
    angular-shape likelihood.  At zero reflected photons that statistic is 0.
    """
    pw, pr = _probabilities(p_wave), _probabilities(p_ray)
    y = np.asarray(counts, dtype=float)
    if pw.shape != pr.shape or y.ndim < 1 or y.shape[-1] != len(pw) or np.any(y < 0):
        raise ValueError("Nonnegative count array must match probability channels")
    if not np.all(np.isfinite(y)) or not np.isfinite(incident_photons) or incident_photons < 0:
        raise ValueError("Finite counts and nonnegative expected photons required")
    if profile_gain:
        pw, pr = pw/pw.sum(), pr/pr.sum()
        offset = 0.0
    else:
        offset = incident_photons*(pw.sum()-pr.sum())
    return np.sum(xlogy(y, pw)-xlogy(y, pr), axis=-1)-offset


def ray_dictionary_bootstrap(p_wave, p_ray, ray_count, repeats=400, seed=20261011):
    """Plug-in multinomial sampling sensitivity of the ray dictionary.

    Valid for this saved lossless Fresnel-roulette simulation: every ray has
    weight one and one final category.  The unobserved forward category is
    retained.  This is not a posterior over physical model discrepancy.
    """
    pw, pr = _probabilities(p_wave), _probabilities(p_ray)
    rng = np.random.default_rng(seed)
    samples = rng.multinomial(ray_count, np.r_[pr, 1-pr.sum()], size=repeats)[:, :-1]/ray_count
    out = {}
    for sectors in SECTOR_COUNTS:
        p = aggregate_sectors(pw, sectors)
        rays = aggregate_sectors(samples, sectors)
        flux = rel_entr(p.sum(), rays.sum(axis=1))+rays.sum(axis=1)-p.sum()
        shape = p.sum()*np.sum(rel_entr(p/p.sum(), rays/rays.sum(axis=1)[:, None]), axis=1)
        out[str(sectors)] = {
            "known_N_KL_per_incident_photon_percentile_2p5_97p5": np.percentile(flux+shape, [2.5, 97.5]).tolist(),
            "profile_KL_per_incident_photon_percentile_2p5_97p5": np.percentile(shape, [2.5, 97.5]).tolist(),
            "bootstrap_repeats": repeats,
        }
    return out


def _wilson(errors, trials):
    z = 1.959963984540054
    p = errors/trials
    denominator = 1+z*z/trials
    middle = (p+z*z/(2*trials))/denominator
    radius = z*np.sqrt(p*(1-p)/trials+z*z/(4*trials**2))/denominator
    return [float(middle-radius), float(middle+radius)]


def poisson_monte_carlo(p_wave, p_ray, incident_photons=100, trials=40000, seed=20261012):
    """Independent Poisson trials under each hypothesis, equal prior odds.

    Fine-bin photons are merged for nested sector layouts.  No detector adds
    photons.  Errors use independent fair coins on exact likelihood ties.
    Profile-gain scores discard total count; both count-generating hypotheses
    still retain their original reflected powers.
    """
    pw, pr = _probabilities(p_wave), _probabilities(p_ray)
    rng = np.random.default_rng(seed)
    out = {str(s): {mode: {} for mode in ("known_N", "profile_gain")} for s in SECTOR_COUNTS}
    for truth, p in (("wave", pw), ("ray", pr)):
        counts = rng.poisson(incident_photons*p, size=(trials, len(p)))
        for sectors in SECTOR_COUNTS:
            a, b = aggregate_sectors(pw, sectors), aggregate_sectors(pr, sectors)
            y = aggregate_sectors(counts, sectors)
            for mode in ("known_N", "profile_gain"):
                profile = mode == "profile_gain"
                score = poisson_llr(y, a, b, incident_photons, profile)
                decision_wave = score > 0
                ties = score == 0
                decision_wave[ties] = rng.random(np.count_nonzero(ties)) < .5
                errors = np.count_nonzero(~decision_wave if truth == "wave" else decision_wave)
                if truth == "wave":
                    info = poisson_information(a, b, incident_photons)
                    expected = info["profile_gain_information_nats" if profile else "expected_log_likelihood_ratio_nats"]
                else:
                    info = poisson_information(b, a, incident_photons)
                    expected = -info["profile_gain_information_nats" if profile else "expected_log_likelihood_ratio_nats"]
                mean, se = float(np.mean(score)), float(np.std(score, ddof=1)/np.sqrt(trials))
                out[str(sectors)][mode][truth] = {
                    "error_fraction": errors/trials,
                    "error_95pct_Wilson_interval": _wilson(errors, trials),
                    "mean_LLR_nats": mean,
                    "expected_LLR_nats": expected,
                    "mean_LLR_standard_error": se,
                    "mean_LLR_z_discrepancy": (mean-expected)/se if se > 0 else 0.0,
                    "exact_ties": int(np.count_nonzero(ties)),
                }
    for sectors in SECTOR_COUNTS:
        for mode in ("known_N", "profile_gain"):
            v = out[str(sectors)][mode]
            v["balanced_error_fraction"] = .5*(v["wave"]["error_fraction"]+v["ray"]["error_fraction"])
    return {"expected_incident_photons": incident_photons, "trials_per_truth": trials,
            "seed": seed, "sectors": out}


def run_measurement_analysis(data_dir=None):
    """Post-process the saved 550-nm, w0=10-um, seven-cylinder benchmark."""
    start = time.perf_counter()
    data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parents[1]/"data"
    source_file = data_dir/"fiber_wave_gaussian_beam.npz"
    source_metrics_file = data_dir/"fiber_wave_gaussian_beam_metrics.json"
    saved = np.load(source_file)
    reference = json.loads(source_metrics_file.read_text())
    theta = saved["theta_rad"]
    edges = np.linspace(np.pi/2, 3*np.pi/2, 91)
    ray_count = int(reference["ray_count_per_case"])
    arrays = {"backward_fine_edges_rad": edges}
    result = {
        "description": "Ideal 2-D angular photon counting of two fixed simulated optical models; not experimental or perceptual evidence",
        "source_files": [source_file.name, source_metrics_file.name],
        "wavelength_um": reference["wavelength_um"],
        "sectors": list(SECTOR_COUNTS),
        "expected_incident_photon_counts": [100, 1000, 10000],
        "ray_dictionary_sample_count": ray_count,
        "assumptions": ["Independent Poisson incident illumination with known mean N, unit detection efficiency, full backward angular acceptance",
                        "No dark/read noise, finite detector blur, calibration error, bandwidth, or 3-D finite-length effects",
                        "Gain-profile statistic conditions on total reflected photons; physical reflected probabilities remain unchanged",
                        "Ray angular bins are 2 degrees; no inference below the saved ray resolution"],
        "cases": [], "monte_carlo": [],
    }
    for case_index, case in enumerate(reference["cases"]):
        label = f"{case['polarization']}_offset{case['offset_um']:g}"
        density = saved[label+"_wave_scattered_power_fraction_per_rad"]
        pw = periodic_density_integrals(theta, density, edges)
        pr = backward_histogram_probabilities(saved[label+"_ray_escaped_power_fraction_per_rad"])
        _probabilities(pw), _probabilities(pr)
        counts = pr*ray_count
        if np.max(np.abs(counts-np.rint(counts))) > 1e-7:
            raise ValueError("Ray dictionary is not the required weight-one multinomial sample")
        arrays[label+"_wave_probability_2deg"] = pw
        arrays[label+"_ray_probability_2deg"] = pr
        convergence = {}
        for stride in (2, 4, 8):
            coarse = periodic_density_integrals(theta[::stride], density[::stride], edges)
            convergence[str(len(theta[::stride]))] = {
                "max_absolute_bin_error_vs_8640": float(np.max(np.abs(coarse-pw))),
                "relative_bin_L1_error_vs_8640": float(np.sum(np.abs(coarse-pw))/pw.sum()),
            }
        crude_midpoint = backward_histogram_probabilities(density).reshape(90, 48).sum(axis=1)
        c = {
            "label": label, "polarization": case["polarization"], "offset_um": case["offset_um"],
            "R_wave": float(pw.sum()), "R_ray": float(pr.sum()),
            "R_wave_difference_vs_independent_GL512_reference": float(pw.sum()-case["R_wave"]),
            "R_ray_difference_vs_saved_total": float(pr.sum()-case["R_ray"]),
            "spectral_integral_subsample_convergence": convergence,
            "crude_8640_midpoint_total_R_error": float(crude_midpoint.sum()-case["R_wave"]),
            "minimum_ray_bin_count": int(round(counts.min())),
            "minimum_wave_bin_probability": float(pw.min()),
            "ray_dictionary_KL_bootstrap": ray_dictionary_bootstrap(pw, pr, ray_count, seed=20261011+case_index),
            "information": [],
        }
        for sectors in SECTOR_COUNTS:
            p, r = aggregate_sectors(pw, sectors), aggregate_sectors(pr, sectors)
            for N in result["expected_incident_photon_counts"]:
                forward = poisson_information(p, r, N)
                backward = poisson_information(r, p, N)
                c["information"].append({
                    "sectors": sectors, "width_deg": 180/sectors, "expected_incident_photons": N,
                    "wave_true": forward, "ray_true": backward,
                    "max_ray_dictionary_mean_uncertainty_over_shot_SD": float(np.sqrt(N*(1-r)/ray_count).max()),
                })
        result["cases"].append(c)
        if label in ("Ez_offset0", "Hz_offset10"):
            mc = poisson_monte_carlo(pw, pr, 100, seed=20261012+case_index)
            mc["label"] = label
            result["monte_carlo"].append(mc)
    np.savez_compressed(data_dir/"angular_measurement_probabilities.npz", **arrays)
    _plot_measurement(result, arrays, data_dir)
    result["total_wall_seconds"] = time.perf_counter()-start
    (data_dir/"angular_measurement_metrics.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"cases": len(result["cases"]), "wall_seconds": result["total_wall_seconds"],
                      "files": ["angular_measurement_probabilities.npz", "angular_measurement_metrics.json",
                                "angular_measurement_information.png", "angular_measurement_errors.png"]}, indent=2))
    return result


def _plot_measurement(result, arrays, data_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), layout="constrained")
    colors = ("#2563eb", "#0f766e", "#c2410c")
    for pol_index, pol in enumerate(("Ez", "Hz")):
        ax = axes[pol_index]
        for c in [c for c in result["cases"] if c["polarization"] == pol]:
            vals = [v for v in c["information"] if v["expected_incident_photons"] == 100]
            color = colors[int(c["offset_um"]/5)]
            ax.plot(SECTOR_COUNTS, [v["wave_true"]["expected_log_likelihood_ratio_nats"] for v in vals],
                    "o-", color=color, label=f"offset {c['offset_um']:g} um, known N")
            ax.plot(SECTOR_COUNTS, [v["wave_true"]["profile_gain_information_nats"] for v in vals],
                    "s--", ms=4, color=color, alpha=.8)
        ax.set(xscale="log", xticks=SECTOR_COUNTS, xticklabels=SECTOR_COUNTS,
               xlabel="Nonoverlapping backward sectors", ylabel="Expected log-likelihood ratio (nats)",
               title=f"{pol}: N = 100 incident photons")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8, loc="upper left")
        ax.text(.03, .63, "solid: known incident mean\ndashed: nuisance gain / shape only",
                transform=ax.transAxes, fontsize=8)
    ax = axes[2]
    center = next(c for c in result["cases"] if c["label"] == "Ez_offset0")
    for s, color in zip(SECTOR_COUNTS, ("#64748b", "#c2410c", "#0f766e", "#2563eb")):
        vals = [v for v in center["information"] if v["sectors"] == s]
        ax.loglog([v["expected_incident_photons"] for v in vals],
                  [v["wave_true"]["expected_log_likelihood_ratio_nats"] for v in vals], "o-", color=color,
                  label=f"{s} sectors ({180/s:g} deg)")
    ax.set(xlabel="Expected incident photons N", ylabel="Expected log-likelihood ratio (nats)",
           title="Centered Ez: ideal photon budget")
    ax.grid(alpha=.2)
    ax.legend(fontsize=8)
    fig.suptitle("Angular information survives similar total reflection | fixed simulated models, ideal shot noise", fontsize=13)
    fig.savefig(data_dir/"angular_measurement_information.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for ax, mc in zip(axes, result["monte_carlo"]):
        for mode, style, name in (("known_N", "o-", "Known N"), ("profile_gain", "s--", "Nuisance gain / shape only")):
            rates = [mc["sectors"][str(s)][mode]["balanced_error_fraction"] for s in SECTOR_COUNTS]
            ax.plot(SECTOR_COUNTS, rates, style, label=name)
        ax.axhline(.5, color=".65", linestyle=":", label="Equal-prior guessing")
        ax.set(xscale="log", xticks=SECTOR_COUNTS, xticklabels=SECTOR_COUNTS, ylim=(0, .54),
               xlabel="Nonoverlapping backward sectors", ylabel="Balanced model-discrimination error",
               title=f"{mc['label'].replace('_', ' ')} | N = 100")
        ax.grid(alpha=.2)
        ax.legend(fontsize=9)
    fig.suptitle("Independent Poisson trials: 40,000 per true model, fixed seeds\nConditional simulation errors; no human or real-camera validation", fontsize=12)
    fig.savefig(data_dir/"angular_measurement_errors.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None)
    run_measurement_analysis(parser.parse_args().data_dir)
