"""Physical and numerical acceptance tests for the 2D fiber power tracer."""

import unittest

import numpy as np
from scipy.integrate import quad

from textile_sim.ply_ray import (fresnel_dielectric, hex_bundle, ray_circle_intersections,
                                single_cylinder_ray_quadrature, trace_bundle)


class FresnelTests(unittest.TestCase):
    def test_normal_incidence(self):
        rs, rp, ct, tir = fresnel_dielectric(1.0, 1.0, 1.55)
        expected = ((1.0 - 1.55) / (1.0 + 1.55)) ** 2
        self.assertAlmostEqual(float(rs), expected, places=14)
        self.assertAlmostEqual(float(rp), expected, places=14)
        self.assertAlmostEqual(float(ct), 1.0)
        self.assertFalse(tir)

    def test_brewster_and_total_internal_reflection(self):
        theta_b = np.arctan(1.55)
        rs, rp, _, tir = fresnel_dielectric(np.cos(theta_b), 1.0, 1.55)
        self.assertLess(float(rp), 1e-28)
        self.assertGreater(float(rs), 0.1)
        self.assertFalse(tir)
        rs, rp, _, tir = fresnel_dielectric(np.cos(np.deg2rad(60)), 1.55, 1.0)
        self.assertEqual(float(rs), 1.0)
        self.assertEqual(float(rp), 1.0)
        self.assertTrue(tir)

    def test_reciprocity_and_power_bounds(self):
        ci = np.linspace(0.01, 1.0, 200)
        rs, rp, ct, tir = fresnel_dielectric(ci, 1.0, 1.55)
        rsi, rpi, _, tiri = fresnel_dielectric(ct, 1.55, 1.0)
        np.testing.assert_allclose(rs, rsi, atol=4e-12)
        np.testing.assert_allclose(rp, rpi, atol=4e-12)
        self.assertFalse(np.any(tir | tiri))
        self.assertTrue(np.all((rs >= 0) & (rs <= 1) & (rp >= 0) & (rp <= 1)))

    def test_index_matching_including_grazing(self):
        rs, rp, ct, tir = fresnel_dielectric([0, 0.1, 1], 1, 1)
        np.testing.assert_array_equal(rs, [0, 0, 0])
        np.testing.assert_array_equal(rp, [0, 0, 0])
        np.testing.assert_allclose(ct, [0, 0.1, 1])
        self.assertFalse(np.any(tir))


class GeometryTests(unittest.TestCase):
    def test_intersection_roots_and_misses(self):
        origins = [[-3, 0], [0, 0], [-3, 2], [-3, 1]]
        directions = [[1, 0]] * 4
        t = ray_circle_intersections(origins, directions, [[0, 0]], [1])[:, 0]
        np.testing.assert_allclose(t[[0, 1, 3]], [2, 1, 3])
        self.assertTrue(np.isinf(t[2]))

    def test_boundary_self_intersection_is_excluded(self):
        t = ray_circle_intersections([[1, 0], [1, 0]], [[1, 0], [-1, 0]], [[0, 0]], [1])[:, 0]
        self.assertTrue(np.isinf(t[0]))
        self.assertAlmostEqual(t[1], 2.0)

    def test_hex_count_and_nonoverlap(self):
        for shells, expected in [(0, 1), (1, 7), (2, 19)]:
            c, r = hex_bundle(shells, 5, 0.25)
            self.assertEqual(len(c), expected)
            np.testing.assert_allclose(np.mean(c, axis=0), 0, atol=1e-14)
            if shells:
                d = np.linalg.norm(c[:, None] - c[None], axis=2)
                np.fill_diagonal(d, np.inf)
                self.assertAlmostEqual(float(np.min(d)), 10.25)


class TraceTests(unittest.TestCase):
    def test_index_matched_is_forward_and_energy_exact(self):
        c, r = hex_bundle(1)
        out = trace_bundle(c, r, n_fiber=1, n_rays=4000, seed=4, return_rays=True)
        e = out["energy"]
        self.assertEqual(e["backward"], 0)
        self.assertEqual(e["absorbed"], 0)
        self.assertEqual(e["residual"], 0)
        self.assertAlmostEqual(e["uncollided_forward"] + e["collided_forward"], 1)
        self.assertLess(np.max(np.abs(out["rays"]["angle"])), 1e-13)
        self.assertEqual(out["summary"]["numerical_failure_count"], 0)

    def test_index_matched_absorption_against_independent_chord_quadrature(self):
        radius, mu = 5.0, 0.04
        out = trace_bundle([[0, 0]], [radius], n_fiber=1, absorption_um_inv=mu,
                           n_rays=40000, seed=42, return_rays=True)
        expected_t = quad(lambda b: np.exp(-mu * 2 * np.sqrt(radius * radius - b * b)),
                          -radius, radius, epsabs=1e-11)[0] / (2 * radius)
        se = out["energy_standard_error"]["collided_forward"]
        self.assertLess(abs(out["energy"]["collided_forward"] - expected_t), 5 * se)
        analytic_chord = 2 * np.sqrt(radius * radius - out["rays"]["impact_um"] ** 2)
        np.testing.assert_allclose(out["rays"]["path_inside_um"], analytic_chord, atol=5e-10)
        np.testing.assert_allclose(out["rays"]["weight"], np.exp(-mu * analytic_chord), atol=2e-11)
        self.assertLess(out["summary"]["max_per_ray_energy_closure_error"], 1e-14)

    def test_uniform_gap_fraction_and_cross_section(self):
        out = trace_bundle([[0, 0]], [5], beam_width_um=20, n_rays=40000, seed=22)
        p = out["energy"]["uncollided_forward"]
        se = out["energy_standard_error"]["uncollided_forward"]
        self.assertLess(abs(p - 0.5), 5 * se)
        self.assertLess(abs(out["geometric_cross_sections_um"]["encountered"] - 10), 20 * 5 * se)
        self.assertAlmostEqual(np.sum(out["angular_power_per_rad"]["all_escaped"] * np.diff(out["theta_edges_rad"])), 1.0, places=12)

    def test_gaussian_interception_analytic(self):
        from scipy.special import erf
        out = trace_bundle([[0, 0]], [5], beam="gaussian", gaussian_sigma_um=4,
                           n_rays=40000, seed=28)
        expected = erf(5 / (np.sqrt(2) * 4))
        self.assertLess(abs(out["summary"]["encountered_fraction"] - expected),
                        5 * out["summary"]["encountered_fraction_standard_error"])
        self.assertNotIn("geometric_cross_sections_um", out)

    def test_absorbing_multifiber_energy_and_no_hidden_residual(self):
        c, r = hex_bundle(2)
        out = trace_bundle(c, r, absorption_um_inv=0.01, n_rays=16000, seed=72, return_rays=True)
        self.assertAlmostEqual(sum(out["energy"].values()), 1, places=13)
        self.assertLess(out["summary"]["max_per_ray_energy_closure_error"], 2e-15)
        self.assertEqual(out["summary"]["numerical_failure_count"], 0)
        self.assertGreater(out["energy"]["absorbed"], 0.1)
        self.assertLess(out["energy"]["residual"], 1e-3)
        self.assertGreater(out["summary"]["mean_fiber_entries"], 1)
        escaped = out["rays"]["escaped"]
        np.testing.assert_allclose(out["rays"]["weight"][escaped],
                                   np.exp(-0.01 * out["rays"]["path_inside_um"][escaped]), atol=4e-15)

    def test_event_limit_power_is_residual_not_forced_escape(self):
        out = trace_bundle([[0, 0]], [5], n_rays=5000, seed=50, max_events=1)
        self.assertGreater(out["energy"]["residual"], 0.7)
        self.assertAlmostEqual(sum(out["energy"].values()), 1, places=14)
        self.assertLess(out["summary"]["max_interface_events"], 2)
        zero = trace_bundle([[0, 0]], [5], n_rays=2000, max_events=0)
        self.assertEqual(zero["energy"]["residual"], 1)

    def test_first_reflection_matches_independent_fresnel_quadrature(self):
        for pol in ("Ez", "Hz"):
            out = trace_bundle([[0, 0]], [5], n_rays=60000, seed=60, polarization=pol,
                               max_events=1, return_rays=True)
            channel = 0 if pol == "Ez" else 1
            expected = quad(lambda b: float(fresnel_dielectric(np.sqrt(1 - b * b), 1, 1.55)[channel]),
                            -1, 1, epsabs=2e-11)[0] / 2
            reflected_power = np.mean(out["rays"]["reflections"] > 0)
            se = np.sqrt(expected * (1 - expected) / 60000)
            self.assertLess(abs(reflected_power - expected), 5 * se)

    def test_entire_angular_distribution_against_analytic_deflection_orders(self):
        n = 50000
        # The DKW bound for an IID empirical CDF is distribution-free. A small
        # additional deterministic quadrature allowance is stated explicitly.
        allowed = np.sqrt(np.log(2 / 1e-4) / (2 * n)) + 2e-4
        for pol in ("Ez", "Hz"):
            reference = single_cylinder_ray_quadrature(polarization=pol, n_impact=65536,
                                                        max_internal_segments=192, theta_bins=180)
            out = trace_bundle([[0, 0]], [5], polarization=pol, n_rays=n, seed=167, theta_bins=180)
            width = np.diff(out["theta_edges_rad"])
            reference_cdf = np.cumsum(reference["angular_power_per_rad"] * width)
            mc_cdf = np.cumsum(out["angular_power_per_rad"]["encountered_escaped"] * width)
            self.assertLess(np.max(np.abs(reference_cdf - mc_cdf)), allowed)
            self.assertAlmostEqual(reference["energy_sum"], 1, places=10)
            self.assertLess(reference["energy"]["residual"], 1e-7)

    def test_rotation_covariance(self):
        c, r = hex_bundle(1, gap_um=0.7)
        a = 0.43
        rotation = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
        one = trace_bundle(c, r, n_rays=5000, seed=66, return_rays=True)
        two = trace_bundle(c @ rotation, r, incident_angle_rad=a, n_rays=5000, seed=66, return_rays=True)
        for key in one["energy"]:
            self.assertAlmostEqual(one["energy"][key], two["energy"][key], places=10)
        angular_difference = np.angle(np.exp(1j * (two["rays"]["angle"] - one["rays"]["angle"] - a)))
        self.assertLess(np.max(np.abs(angular_difference)), 1e-7)

    def test_invalid_overlap_and_parameters_rejected(self):
        with self.assertRaises(ValueError):
            trace_bundle([[0, 0], [5, 0]], [5, 5], n_rays=10)
        with self.assertRaises(ValueError):
            trace_bundle([[0, 0]], [5], n_fiber=-1, n_rays=10)
        with self.assertRaises(ValueError):
            trace_bundle([[0, 0]], [5], absorption_um_inv=-0.1, n_rays=10)


if __name__ == "__main__":
    unittest.main()
