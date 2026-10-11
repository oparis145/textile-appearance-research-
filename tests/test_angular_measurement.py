"""Optical probability conservation and independent likelihood checks."""
import unittest

import numpy as np
from scipy.stats import poisson

from textile_sim.angular_measurement import (
    periodic_density_integrals, backward_histogram_probabilities,
    aggregate_sectors, poisson_information, poisson_llr, poisson_monte_carlo,
)


class AngularIntegrationTests(unittest.TestCase):
    def test_known_fourier_polynomial_integrals_on_shifted_grid(self):
        for n in (63, 64):
            theta = -.371 + 2*np.pi*np.arange(n)/n
            f = .08+.02*np.cos(7*theta)+.01*np.sin(11*theta)
            edges = np.linspace(np.pi/2, 3*np.pi/2, 19)
            primitive = .08*edges+.02*np.sin(7*edges)/7-.01*np.cos(11*edges)/11
            np.testing.assert_allclose(periodic_density_integrals(theta, f, edges), np.diff(primitive), atol=1e-15)

    def test_real_nyquist_cosine_integral(self):
        n, origin = 32, .219
        theta = origin+2*np.pi*np.arange(n)/n
        f = .05+.01*np.cos((n//2)*(theta-origin))
        edges = np.array([.1, .41, 1.79])
        primitive = .05*edges+.01*np.sin((n//2)*(edges-origin))/(n//2)
        np.testing.assert_allclose(periodic_density_integrals(theta, f, edges), np.diff(primitive), atol=1e-15)

    def test_histogram_order_and_probability_preservation(self):
        density = np.arange(180)/100000
        expected = np.r_[density[135:], density[:45]]*(2*np.pi/180)
        fine = backward_histogram_probabilities(density)
        np.testing.assert_array_equal(fine, expected)
        for s in (1, 6, 18, 90):
            self.assertAlmostEqual(aggregate_sectors(fine, s).sum(), fine.sum(), places=15)
        with self.assertRaises(ValueError): aggregate_sectors(fine, 7)

    def test_bad_angular_grid_rejected(self):
        with self.assertRaises(ValueError):
            periodic_density_integrals(np.linspace(-np.pi, np.pi, 64), np.ones(64), [0, 1])


class PoissonInformationTests(unittest.TestCase):
    p = np.array([.025, .05, .01, .035, .08, .04])
    r = np.array([.05, .025, .025, .05, .025, .025])

    def test_KL_against_independent_poisson_logpmf_sum(self):
        # Explicit count distribution expectation for a one-sector Poisson.
        a, b, N = .22, .35, 20
        counts = np.arange(100)
        expected = np.sum(poisson.pmf(counts, N*a)*(poisson.logpmf(counts, N*a)-poisson.logpmf(counts, N*b)))
        actual = poisson_information([a], [b], N)
        self.assertAlmostEqual(actual["expected_log_likelihood_ratio_nats"], expected, places=13)

    def test_flux_shape_decomposition_and_profile_gain(self):
        info = poisson_information(self.p, self.r, 123)
        self.assertLess(info["decomposition_absolute_error_nats"], 1e-13)
        flux = poisson_information([self.p.sum()], [self.r.sum()], 123)
        self.assertEqual(flux["profile_gain_information_nats"], 0)
        self.assertAlmostEqual(info["total_flux_information_nats"], flux["expected_log_likelihood_ratio_nats"], places=13)
        # Proportional profiles contain no shape information despite unequal R.
        proportional = poisson_information(self.p, .7*self.p, 123)
        self.assertLess(abs(proportional["profile_gain_information_nats"]), 1e-13)
        self.assertGreater(proportional["total_flux_information_nats"], 0)

    def test_coarsening_cannot_increase_information(self):
        vals = [poisson_information(aggregate_sectors(self.p, s), aggregate_sectors(self.r, s), 100)
                for s in (1, 2, 6)]
        for field in ("expected_log_likelihood_ratio_nats", "profile_gain_information_nats"):
            self.assertTrue(np.all(np.diff([v[field] for v in vals]) >= -1e-12))

    def test_profile_likelihood_matches_explicit_gain_maximization(self):
        y, N = np.array([0, 2, 4, 1, 3, 5]), 90
        gp, gr = y.sum()/(N*self.p.sum()), y.sum()/(N*self.r.sum())
        expected = np.sum(poisson.logpmf(y, gp*N*self.p)-poisson.logpmf(y, gr*N*self.r))
        self.assertAlmostEqual(float(poisson_llr(y, self.p, self.r, N, True)), expected, places=13)
        self.assertEqual(float(poisson_llr(np.zeros(6), self.p, self.r, N, True)), 0)

    def test_scaling_zero_support_and_invalid_probabilities(self):
        a, b = poisson_information(self.p, self.r, 1), poisson_information(self.p, self.r, 1000)
        self.assertAlmostEqual(b["expected_log_likelihood_ratio_nats"], 1000*a["expected_log_likelihood_ratio_nats"])
        self.assertTrue(np.isinf(poisson_information([.1, .1], [.2, 0])["expected_log_likelihood_ratio_nats"]))
        self.assertEqual(poisson_information([.1, .1], [.2, 0], 0)["expected_log_likelihood_ratio_nats"], 0)
        with self.assertRaises(ValueError): poisson_information([.8, .5], [.1, .2])

    def test_saved_data_rebinning_vs_independent_total_and_grid_convergence(self):
        from pathlib import Path
        import json
        data = Path(__file__).resolve().parents[1]/"data"
        z = np.load(data/"fiber_wave_gaussian_beam.npz")
        ref = json.loads((data/"fiber_wave_gaussian_beam_metrics.json").read_text())
        edges = np.linspace(np.pi/2, 3*np.pi/2, 91)
        for case in ref["cases"]:
            label = f"{case['polarization']}_offset{case['offset_um']:g}"
            f = z[label+"_wave_scattered_power_fraction_per_rad"]
            p = periodic_density_integrals(z["theta_rad"], f, edges)
            coarse = periodic_density_integrals(z["theta_rad"][::4], f[::4], edges)
            self.assertLess(abs(p.sum()-case["R_wave"]), 2e-12)
            np.testing.assert_allclose(p, coarse, atol=3e-14, rtol=1e-11)
            r = backward_histogram_probabilities(z[label+"_ray_escaped_power_fraction_per_rad"])
            self.assertLess(abs(r.sum()-case["R_ray"]), 2e-14)
            self.assertTrue(np.all(p > 0) and np.all(r > 0))


if __name__ == "__main__":
    unittest.main()
