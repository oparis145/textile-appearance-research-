"""Positive, normalized circular compression of 2D outgoing power kernels.

This diagnostic fits a von Mises mixture to a conditional angular distribution.
It is not a 3D BSDF, Yu et al.'s ASG model, a Maxwell solver, or a replacement
for the geometry. Uncollided and exactly undeviated forward rays are separate
delta terms; they are not blurred into the continuous mixture.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from scipy.special import i0e, i1e, logsumexp
from scipy.stats import vonmises


def _a1_inverse(resultant, kappa_max=512.0):
    """Invert I1(kappa)/I0(kappa) by a stable initial estimate and Newton steps."""
    r = np.clip(np.asarray(resultant, float), 0.0, 1.0 - 1e-12)
    k = np.where(r < 0.53, 2*r + r**3 + 5*r**5/6,
                 np.where(r < 0.85, -0.4 + 1.39*r + 0.43/(1-r),
                          1/np.maximum(r**3 - 4*r*r + 3*r, 1e-15)))
    k = np.clip(k, 0, kappa_max)
    for _ in range(10):
        a = i1e(k) / i0e(k)
        derivative = np.where(k > 1e-7, 1-a*a-a/np.maximum(k, 1e-300), 0.5)
        k = np.clip(k - (a-r)/np.maximum(derivative, 1e-12), 0.0, kappa_max)
    return k


@dataclass
class VonMisesMixture:
    weights: np.ndarray
    means_rad: np.ndarray
    kappas: np.ndarray

    def __post_init__(self):
        self.weights = np.atleast_1d(np.asarray(self.weights, float))
        self.means_rad = np.atleast_1d(np.asarray(self.means_rad, float))
        self.kappas = np.atleast_1d(np.asarray(self.kappas, float))
        if not (self.weights.shape == self.means_rad.shape == self.kappas.shape):
            raise ValueError("mixture parameter arrays must have matching shapes")
        if not len(self.weights) or np.any(~np.isfinite(self.weights)) or np.any(self.weights < 0) or not np.isclose(self.weights.sum(), 1, atol=1e-10):
            raise ValueError("weights must be finite, nonnegative and sum to one")
        if np.any(~np.isfinite(self.means_rad)) or np.any(~np.isfinite(self.kappas)) or np.any(self.kappas < 0):
            raise ValueError("means must be finite and concentrations finite/nonnegative")
        self.means_rad = np.angle(np.exp(1j * self.means_rad))

    def density(self, theta):
        t = np.asarray(theta, float)
        log_density = (np.log(np.maximum(self.weights, 1e-300))
                       + self.kappas * (np.cos(t[..., None] - self.means_rad) - 1)
                       - np.log(2*np.pi) - np.log(i0e(self.kappas)))
        return np.exp(logsumexp(log_density, axis=-1))

    def interval_probability(self, low, high):
        """Exact numerical circular CDF difference, including intervals across pi."""
        low, high = np.broadcast_arrays(np.asarray(low, float), np.asarray(high, float))
        if np.any(high < low) or np.any(high-low > 2*np.pi+1e-10):
            raise ValueError("interval width must lie in [0,2*pi]")
        difference = (vonmises.cdf(high[..., None], self.kappas, loc=self.means_rad)
                      - vonmises.cdf(low[..., None], self.kappas, loc=self.means_rad))
        return np.sum(difference * self.weights, axis=-1)

    def bin_probabilities(self, edges):
        edges = np.asarray(edges, float)
        if edges.ndim != 1 or len(edges) < 2 or np.any(np.diff(edges) <= 0):
            raise ValueError("bin edges must be a strictly increasing 1D array")
        return self.interval_probability(edges[:-1], edges[1:])

    def to_dict(self):
        return {"weights": self.weights.tolist(), "means_rad": self.means_rad.tolist(), "kappas": self.kappas.tolist()}


def fit_von_mises_mixture(theta, observation_weights, n_components=8, seed=123,
                          n_init=4, max_iterations=600, tolerance=1e-10, kappa_max=512.0):
    """Weighted EM on circular observations, e.g. a finely binned ray histogram.

    All restart selection uses training likelihood only. Each M step solves
    the bounded von Mises maximum-likelihood concentration. The normalization
    2*pi*I0(kappa) is analytic; neither signed lobes nor output renormalization
    is needed. The returned likelihood is that of the supplied observations,
    not a claim of held-out fit quality.
    """
    theta = np.asarray(theta, float).ravel()
    w = np.asarray(observation_weights, float).ravel()
    if theta.shape != w.shape or not len(theta) or np.any(~np.isfinite(theta)) or np.any(~np.isfinite(w)) or np.any(w < 0) or w.sum() <= 0:
        raise ValueError("angles and nonnegative positive-total observation weights must match")
    if int(n_components) != n_components or n_components < 1 or n_init < 1 or max_iterations < 1 or kappa_max <= 0:
        raise ValueError("fit sizes and concentration cap must be positive")
    n_components = int(n_components)
    w = w / w.sum()
    keep = w > 0
    theta, w = theta[keep], w[keep]
    order = np.argsort(theta)
    theta, w = theta[order], w[order]
    rng = np.random.default_rng(seed)
    ct, st = np.cos(theta), np.sin(theta)
    best = None
    all_final = []
    for restart in range(n_init):
        if restart == 0:
            cumulative = np.cumsum(w)
            quantiles = (np.arange(n_components) + 0.5) / n_components
            mu = np.interp(quantiles, cumulative, theta)
        else:
            mu = rng.choice(theta, size=n_components, replace=True, p=w)
            mu += rng.normal(0, 0.08, size=n_components)
        pi = np.full(n_components, 1/n_components)
        kappa = np.full(n_components, max(1.0, 2*n_components**0.7))
        history = []
        for iteration in range(max_iterations):
            logits = (np.log(np.maximum(pi, 1e-300))[None, :]
                      + kappa[None, :] * (np.cos(theta[:, None]-mu[None, :])-1)
                      - np.log(2*np.pi)-np.log(i0e(kappa))[None, :])
            total = logsumexp(logits, axis=1)
            ll = float(np.sum(w*total))
            history.append(ll)
            if len(history) > 1 and abs(history[-1]-history[-2]) < tolerance:
                break
            responsibility = np.exp(logits-total[:, None]) * w[:, None]
            mass = np.sum(responsibility, axis=0)
            x = ct @ responsibility
            y = st @ responsibility
            mu = np.arctan2(y, x)
            resultant = np.hypot(x, y)/np.maximum(mass, 1e-300)
            kappa = _a1_inverse(resultant, kappa_max)
            pi = mass / mass.sum()
        model = VonMisesMixture(pi, mu, kappa)
        final_ll = float(np.sum(w*np.log(np.maximum(model.density(theta), 1e-300))))
        all_final.append(final_ll)
        if best is None or final_ll > best[0]:
            best = (final_ll, model, history, restart)
    return best[1], {
        "training_log_likelihood_per_observation": best[0],
        "training_log_likelihood_history": best[2], "selected_restart": best[3],
        "restart_final_log_likelihoods": all_final, "seed": int(seed),
        "n_components": n_components, "n_init": int(n_init),
        "max_iterations": int(max_iterations), "kappa_max": float(kappa_max),
        "selected_iterations": len(best[2]),
        "converged_by_likelihood_tolerance": bool(len(best[2]) > 1 and abs(best[2][-1]-best[2][-2]) < tolerance),
        "likelihood_tolerance": float(tolerance),
    }


@dataclass
class AngularPowerSurrogate:
    mixture: VonMisesMixture | None
    continuous_mass: float
    uncollided_forward: float
    encountered_forward_delta: float
    absorbed: float
    residual: float
    incident_angle_rad: float

    def density(self, theta):
        if self.mixture is None:
            return np.zeros_like(np.asarray(theta, float))
        return self.continuous_mass * self.mixture.density(theta)

    def bin_probabilities(self, edges):
        edges = np.asarray(edges, float)
        if not np.isclose(edges[-1]-edges[0], 2*np.pi, atol=1e-10):
            raise ValueError("power histograms must cover exactly one full angular period")
        p = np.zeros(len(edges)-1) if self.mixture is None else self.continuous_mass*self.mixture.bin_probabilities(edges)
        angle = (self.incident_angle_rad-edges[0])%(2*np.pi)+edges[0]
        index = np.searchsorted(edges, angle, side="right")-1
        p[index] += self.uncollided_forward + self.encountered_forward_delta
        return p

    def energy(self):
        fp = 0.0 if self.mixture is None else float(self.mixture.interval_probability(
            self.incident_angle_rad-np.pi/2, self.incident_angle_rad+np.pi/2))
        return {"backward": self.continuous_mass*(1-fp),
                "collided_forward": self.continuous_mass*fp+self.encountered_forward_delta,
                "uncollided_forward": self.uncollided_forward,
                "absorbed": self.absorbed, "residual": self.residual}

    def to_dict(self):
        return {"mixture": None if self.mixture is None else self.mixture.to_dict(),
                "continuous_mass": self.continuous_mass, "uncollided_forward": self.uncollided_forward,
                "encountered_forward_delta": self.encountered_forward_delta,
                "absorbed": self.absorbed, "residual": self.residual,
                "incident_angle_rad": self.incident_angle_rad}


def compress_trace_result(result, n_components=8, histogram_bins=720, seed=123, **fit_options):
    """Compress a trace_bundle(..., return_rays=True) output; keep deltas separate."""
    if "rays" not in result:
        raise ValueError("trace output must include individual rays")
    rays, summary = result["rays"], result["summary"]
    total = summary["n_rays"]
    alpha = summary["incident_angle_rad"]
    encountered_escape = rays["encountered"] & rays["escaped"]
    difference = np.angle(np.exp(1j*(rays["angle"]-alpha)))
    forward_delta = encountered_escape & (np.abs(difference) < 1e-12)
    continuous = encountered_escape & ~forward_delta
    continuous_mass = float(np.sum(rays["weight"][continuous])/total)
    delta_mass = float(np.sum(rays["weight"][forward_delta])/total)
    mixture, fit = None, {"n_components": 0, "reason": "no continuous escaped power"}
    if continuous_mass > 0:
        edges = np.linspace(-np.pi, np.pi, histogram_bins+1)
        counts = np.histogram(rays["angle"][continuous], bins=edges, weights=rays["weight"][continuous])[0]
        theta = 0.5*(edges[:-1]+edges[1:])
        mixture, fit = fit_von_mises_mixture(theta, counts, n_components, seed=seed, **fit_options)
    model = AngularPowerSurrogate(mixture, continuous_mass,
                                   result["energy"]["uncollided_forward"], delta_mass,
                                   result["energy"]["absorbed"], result["energy"]["residual"], alpha)
    fit["histogram_bins"] = int(histogram_bins)
    fit["training_n_rays"] = int(total)
    fit["training_trace_seed"] = int(summary["seed"])
    return model, fit


def jensen_shannon(p, q):
    """JS divergence in natural-log units, for already normalized probabilities."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    if p.shape != q.shape or np.any(p < -1e-14) or np.any(q < -1e-14) or not np.isclose(p.sum(), 1, atol=1e-8) or not np.isclose(q.sum(), 1, atol=1e-8):
        raise ValueError("JS inputs must be nonnegative normalized probability arrays")
    p, q = np.maximum(p, 0), np.maximum(q, 0)
    m = (p+q)/2
    first = p > 0
    second = q > 0
    return float(0.5*np.sum(p[first]*np.log(p[first]/m[first])) +
                 0.5*np.sum(q[second]*np.log(q[second]/m[second])))


def run_surrogate_experiment(output_dir="data"):
    from .ply_ray import hex_bundle, trace_bundle
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    centers, radii = hex_bundle(2, radius_um=5, gap_um=.4)
    train = trace_bundle(centers, radii, n_rays=200000, seed=5101, theta_bins=360, return_rays=True)
    validation = trace_bundle(centers, radii, n_rays=200000, seed=7202, theta_bins=360, return_rays=True)
    edges = validation["theta_edges_rad"]
    theta = validation["theta_rad"]
    width = np.diff(edges)
    empirical = validation["angular_power_per_rad"]["all_escaped"]*width
    training_p = train["angular_power_per_rad"]["all_escaped"]*width
    metrics = {"training_seed": 5101, "validation_seed": 7202, "rays_per_seed": 200000,
               "train_vs_validation_histogram_JS": jensen_shannon(training_p, empirical),
               "validation_energy": validation["energy"],
               "validation_energy_standard_error": validation["energy_standard_error"],
               "geometry": "19 circular fibers, radius5um, gap0.4um, n1.55; unpolarized +x", "models": {}}
    parameters, arrays = {}, {"theta_edges_rad": edges, "validation_bin_power": empirical, "training_bin_power": training_p}
    for components in (1, 4, 8, 16):
        model, fit = compress_trace_result(train, components, histogram_bins=720, seed=310+components)
        predicted = model.bin_probabilities(edges)
        metrics["models"][str(components)] = {
            "JS_divergence_nats": jensen_shannon(predicted, empirical),
            "CDF_sup_error": float(np.max(np.abs(np.cumsum(predicted-empirical)))),
            "bin_L1_error": float(np.sum(np.abs(predicted-empirical))),
            "backward_probability": model.energy()["backward"],
            "backward_probability_error": model.energy()["backward"]-validation["energy"]["backward"],
            "total_power_including_absorbed_residual": float(sum(model.energy().values())),
            "continuous_density_min": float(np.min(model.density(theta))),
            "fit": fit,
        }
        parameters[str(components)] = model.to_dict()
        arrays[f"components_{components}_bin_power"] = predicted
    with (output/"ply_ray_surrogate_metrics.json").open("w") as handle:
        json.dump(metrics, handle, indent=2, allow_nan=False)
    with (output/"ply_ray_surrogate_models.json").open("w") as handle:
        json.dump(parameters, handle, indent=2, allow_nan=False)
    np.savez_compressed(output/"ply_ray_surrogate_distributions.npz", **arrays)
    plot_surrogate_experiment(output)
    return metrics


def plot_surrogate_experiment(output_dir="data"):
    """Regenerate the figure from saved evidence without rerunning ray fitting."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output=Path(output_dir)
    with (output/"ply_ray_surrogate_metrics.json").open() as handle:
        metrics=json.load(handle)
    with np.load(output/"ply_ray_surrogate_distributions.npz") as archive:
        arrays={key:archive[key] for key in archive.files}
    edges=arrays['theta_edges_rad']
    theta=0.5*(edges[:-1]+edges[1:])
    width=np.diff(edges)
    empirical=arrays['validation_bin_power']
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    colors = ["#95a0ac", "#d08a56", "#408e9a", "#225c87"]
    axes[0].semilogy(np.rad2deg(theta), empirical/width, color="black", alpha=.65, lw=1, label="Held-out 200k rays")
    for components, color in zip((1,4,8,16), colors):
        p=arrays[f"components_{components}_bin_power"]
        label=f"{components} lobe" if components == 1 else f"{components} lobes"
        axes[0].semilogy(np.rad2deg(theta), p/width, color=color, lw=1.4, label=label)
        axes[1].plot(np.rad2deg(theta), np.cumsum(p-empirical), color=color, label=label)
    axes[0].set(xlim=(-180,180), xlabel="Outgoing angle (degrees)", ylabel="Power fraction per rad", title="Positive circular mixtures", ylim=(.01,2))
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].axhline(0,color="black",lw=.6)
    axes[1].set(xlim=(-180,180), xlabel="Outgoing angle (degrees)", ylabel="Predicted CDF - held-out CDF", title="Errors remain visible")
    counts=np.array([1,4,8,16])
    js=np.array([metrics["models"][str(n)]["JS_divergence_nats"] for n in counts])
    axes[2].plot(counts,js,"o-",color=colors[-1],label="Surrogate vs held-out")
    axes[2].axhline(metrics["train_vs_validation_histogram_JS"],linestyle="--",color=colors[1],label="Two ray histograms")
    axes[2].set(xlabel="Number of mixture components", ylabel="JS divergence (natural-log units)", title="Compression / accuracy tradeoff", xticks=counts)
    axes[2].legend(fontsize=8,frameon=False)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle("2D diagnostic compression, independent training and validation rays\nNot a three-dimensional BSDF or a reproduction of the ray-wave paper's shading model",fontsize=12)
    fig.savefig(output/"ply_ray_surrogate_overview.png",dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    data=run_surrogate_experiment()
    print(json.dumps({k:{m:v for m,v in d.items() if m!='fit'} for k,d in data['models'].items()},indent=2))
