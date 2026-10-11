"""Independent constitutive, beam, topology, similarity and optical-contract checks."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from textile_sim.hierarchy import YarnSpec, audit_clearance, hex_ply, load_hierarchy, save_hierarchy
from textile_sim.optical_scene import MaterialSpectrum, from_hierarchy
from textile_sim.weave_draft import WeaveDraft
from textile_sim.weave_mechanics import (
    YarnElasticity, ReducedWeaveSpec, ReducedWeaveProblem, beam_energy_gradient_hessian,
    solve_equilibrium, equilibrium_residual, build_relaxed_hierarchy,
)


def small_spec(**changes):
    options = dict(warp_count=2, weft_count=2, segments_per_crossing=4)
    options.update(changes)
    return ReducedWeaveSpec(WeaveDraft.plain(), .012, .012, **options)


class WeaveMechanicsTests(unittest.TestCase):
    def test_exact_extension_energy_against_direct_lengths(self):
        z = np.array([.01, .03, -.02, .006])
        h = .12
        m = YarnElasticity(.3, 0., .97)
        ell = np.sqrt(h*h+np.diff(np.r_[0., z, 0.])**2)
        direct = np.sum(.5*m.axial_stiffness_N/(m.rest_fraction*h)*((ell-m.rest_fraction*h)**2-(h-m.rest_fraction*h)**2))
        self.assertAlmostEqual(beam_energy_gradient_hessian(z, h, m)[0], direct, places=16)

    def test_analytic_gradient_against_independent_scalar_energy_difference(self):
        rng = np.random.default_rng(6001)
        z = rng.normal(0., .001, 9); h = .07; eps = 1e-7
        m = YarnElasticity(.06, 7e-7, .99)
        def independent_energy(x):
            full = np.r_[0., x, 0.]
            ell = np.linalg.norm(np.column_stack((np.full(len(full)-1, h), np.diff(full))), axis=1)
            axial = m.axial_stiffness_N/(2*m.rest_fraction*h)*np.sum((ell-m.rest_fraction*h)**2-(h-m.rest_fraction*h)**2)
            bend = m.bending_stiffness_N_mm2/(2*h**3)*np.sum(np.diff(full, n=2)**2)
            return axial+bend
        grad = beam_energy_gradient_hessian(z, h, m)[1]
        numeric = np.array([(independent_energy(z+eps*np.eye(len(z))[k])-independent_energy(z-eps*np.eye(len(z))[k]))/(2*eps) for k in range(len(z))])
        np.testing.assert_allclose(grad, numeric, rtol=2e-8, atol=1e-11)

    def test_hessian_against_gradient_difference_and_psd(self):
        rng = np.random.default_rng(109)
        z = rng.normal(0., .003, 8); h = .08; eps = 1e-7
        for rest in (1., .98):
            m = YarnElasticity(.02, 1e-6, rest)
            _, _, analytic = beam_energy_gradient_hessian(z, h, m)
            numeric = np.column_stack([(beam_energy_gradient_hessian(z+eps*np.eye(len(z))[k], h, m)[1]-beam_energy_gradient_hessian(z-eps*np.eye(len(z))[k], h, m)[1])/(2*eps) for k in range(len(z))])
            np.testing.assert_allclose(analytic, numeric, rtol=2e-8, atol=1e-10)
            self.assertGreater(np.linalg.eigvalsh(analytic).min(), 0.)

    def test_flat_unloaded_state_is_exact_minimum_with_pretension(self):
        for m in (YarnElasticity(), YarnElasticity(.01, 0., .97), YarnElasticity(0., 1e-6)):
            energy, gradient, hessian = beam_energy_gradient_hessian(np.zeros(7), .1, m)
            self.assertEqual(energy, 0.)
            np.testing.assert_array_equal(gradient, 0.)
            self.assertGreaterEqual(np.linalg.eigvalsh(hessian).min(), -1e-15)

    def test_simply_supported_beam_uniform_load_converges_second_order(self):
        # Independent continuum EB solution: w=q*x*(L^3-2Lx^2+x^3)/(24B).
        length, bending, load = 1.2, 3e-6, 2e-7
        m = YarnElasticity(0., bending)
        errors = []
        for elements in (12, 24, 48):
            h = length/elements
            x = np.arange(1, elements)*h
            stiffness = beam_energy_gradient_hessian(np.zeros(elements-1), h, m)[2]
            observed = np.linalg.solve(stiffness, np.full(elements-1, load*h))
            exact = load*x*(length**3-2*length*x*x+x**3)/(24*bending)
            errors.append(np.max(np.abs(observed-exact)))
            self.assertLess(np.linalg.norm(stiffness@observed-load*h, np.inf), 2e-15)
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)
        self.assertLess(errors[-1], 2e-6)

    def test_initial_crossings_and_fixed_endpoints_are_exact(self):
        p = ReducedWeaveProblem(small_spec())
        z = p.initial_heights()
        np.testing.assert_allclose((p.constraint_matrix@z)[:p.crossing_count], p.spec.crossing_separation_mm, atol=2e-17)
        for curve in p.centerlines(z).values():
            np.testing.assert_array_equal(curve[[0, -1], 2], 0.)
        self.assertLess(p.constraint_diagnostics(z)["max_violation_mm"], 1e-15)

    def test_conservative_orthogonal_bound_is_sharp_for_straight_tracks(self):
        # Closest points between tilted orthogonal tracks have this exact gap.
        lw, lf, desired = .25, .32, .028
        crossing = desired*np.sqrt(1+lw*lw+lf*lf)
        w = np.array([0., 1., lw]); f = np.array([1., 0., lf])
        base = np.array([0., 0., crossing])
        params = np.linalg.lstsq(np.column_stack((w, -f)), -base, rcond=None)[0]
        distance = np.linalg.norm(base+w*params[0]-f*params[1])
        self.assertAlmostEqual(distance, desired, places=14)
        # Using only crossing vertical gap as Euclidean clearance is false.
        self.assertLess(distance, crossing)

    def test_parallel_pitch_bound_rejects_intersecting_envelopes(self):
        with self.assertRaisesRegex(ValueError, "parallel warp"):
            small_spec(warp_pitch_mm=.026)
        with self.assertRaisesRegex(ValueError, "parallel weft"):
            small_spec(weft_pitch_mm=.026)

    def test_solve_decreases_energy_and_independently_satisfies_kkt(self):
        p = ReducedWeaveProblem(small_spec())
        result = solve_equilibrium(p)
        self.assertTrue(result.diagnostics["independent_kkt_certified"])
        self.assertGreater(result.diagnostics["energy_reduction_fraction"], .15)
        independent = equilibrium_residual(p, result.heights_mm)
        self.assertLess(independent["stationarity_relative_to_gradient"], 2e-5)
        self.assertLess(independent["max_constraint_violation_mm"], 1e-11)
        self.assertLess(p.constraint_diagnostics(result.heights_mm)["max_abs_slope"], p.spec.max_slope+1e-10)
        with self.assertRaises(ValueError):
            result.heights_mm.setflags(write=True)

    def test_common_stiffness_scaling_preserves_equilibrium_and_scales_energy(self):
        base = small_spec()
        a = solve_equilibrium(ReducedWeaveProblem(base))
        for factor in (1e-3, 1e3):
            m = replace(base.warp_elasticity,
                axial_stiffness_N=base.warp_elasticity.axial_stiffness_N*factor,
                bending_stiffness_N_mm2=base.warp_elasticity.bending_stiffness_N_mm2*factor)
            b = solve_equilibrium(ReducedWeaveProblem(replace(base, warp_elasticity=m, weft_elasticity=m)))
            np.testing.assert_allclose(a.heights_mm, b.heights_mm, rtol=3e-6, atol=1e-9)
            self.assertAlmostEqual(b.diagnostics["final_energy_excess_N_mm"]/a.diagnostics["final_energy_excess_N_mm"], factor, delta=2e-8*factor)

    def test_physical_length_similarity_scales_bending_by_length_squared(self):
        base = small_spec(); scale = 1.7
        a = solve_equilibrium(ReducedWeaveProblem(base))
        m = replace(base.warp_elasticity, bending_stiffness_N_mm2=base.warp_elasticity.bending_stiffness_N_mm2*scale**2)
        scaled = replace(base, warp_envelope_radius_mm=base.warp_envelope_radius_mm*scale,
            weft_envelope_radius_mm=base.weft_envelope_radius_mm*scale,
            warp_pitch_mm=base.warp_pitch_mm*scale, weft_pitch_mm=base.weft_pitch_mm*scale,
            clearance_mm=base.clearance_mm*scale, warp_elasticity=m, weft_elasticity=m)
        b = solve_equilibrium(ReducedWeaveProblem(scaled))
        np.testing.assert_allclose(b.heights_mm, scale*a.heights_mm, atol=2e-9)
        self.assertAlmostEqual(b.diagnostics["final_energy_excess_N_mm"]/a.diagnostics["final_energy_excess_N_mm"], scale, places=9)

    def test_stiffer_warp_changes_crimp_distribution_while_topology_is_retained(self):
        spec = small_spec()
        a = solve_equilibrium(ReducedWeaveProblem(spec))
        spec = replace(spec, warp_elasticity=replace(spec.warp_elasticity, bending_stiffness_N_mm2=20*spec.warp_elasticity.bending_stiffness_N_mm2))
        p = ReducedWeaveProblem(spec); b = solve_equilibrium(p)
        fa = a.diagnostics["relaxed"]["families"]; fb = b.diagnostics["relaxed"]["families"]
        self.assertLess(fb["warp"]["crimp_ratio"], .4*fa["warp"]["crimp_ratio"])
        self.assertGreater(fb["weft"]["crimp_ratio"], fa["weft"]["crimp_ratio"])
        self.assertGreaterEqual(np.min((p.constraint_matrix@b.heights_mm)[:p.crossing_count]), p.spec.crossing_separation_mm-1e-10)

    def test_rest_length_changes_tension_and_crimp_at_fixed_bending_stiffness(self):
        spec = small_spec()
        a = solve_equilibrium(ReducedWeaveProblem(spec))
        p = ReducedWeaveProblem(replace(spec, warp_elasticity=replace(spec.warp_elasticity, rest_fraction=1/1.04)))
        b = solve_equilibrium(p)
        np.testing.assert_array_equal(a.initial_heights_mm, b.initial_heights_mm)
        fa = a.diagnostics["relaxed"]["families"]; fb = b.diagnostics["relaxed"]["families"]
        self.assertLess(fb["warp"]["crimp_ratio"], fa["warp"]["crimp_ratio"])
        self.assertGreater(fb["weft"]["crimp_ratio"], fa["weft"]["crimp_ratio"])
        self.assertGreater(fb["warp"]["axial_force_min_N"], fa["warp"]["axial_force_min_N"])

    def test_refined_weave_heights_and_energy_converge_under_same_physics(self):
        cases = []
        for n in (4, 8, 16):
            p = ReducedWeaveProblem(small_spec(segments_per_crossing=n))
            r = solve_equilibrium(p)
            cases.append((p.centerlines(r.heights_mm), r.diagnostics["final_energy_excess_N_mm"]))
        differences, energy_differences = [], []
        for (coarse, ea), (fine, eb) in zip(cases[:-1], cases[1:]):
            delta = []
            for key, points in fine.items():
                axis = 1 if key[0] == "warp" else 0
                delta.extend(np.interp(points[:,axis],coarse[key][:,axis],coarse[key][:,2])-points[:,2])
            differences.append(np.sqrt(np.mean(np.square(delta))))
            energy_differences.append(abs(ea-eb))
        self.assertGreater(differences[0]/differences[1], 3.2)
        self.assertGreater(energy_differences[0]/energy_differences[1], 3.2)

    def test_compression_invalid_stiffness_and_units_are_rejected(self):
        for kwargs in ({"rest_fraction": 1.001}, {"rest_fraction": 0.}, {"axial_stiffness_N": -1.},
                       {"axial_stiffness_N": 0., "bending_stiffness_N_mm2": 0.}, {"axial_stiffness_N": True}):
            with self.assertRaises(ValueError):
                YarnElasticity(**kwargs)
        data = small_spec().to_dict(); data["units"]["length"] = "um"
        with self.assertRaises(ValueError):
            ReducedWeaveSpec.from_dict(data)
        with self.assertRaises(ValueError):
            small_spec(max_slope=.6)
        with self.assertRaises(ValueError):
            small_spec(segments_per_crossing=True)

    def test_spec_roundtrip_is_exact_and_infeasible_initialization_rejected(self):
        s = small_spec()
        self.assertEqual(s.to_dict(), ReducedWeaveSpec.from_dict(s.to_dict()).to_dict())
        with self.assertRaisesRegex(ValueError, "initialization violates"):
            ReducedWeaveProblem(replace(s, max_slope=.03)).initial_heights()
        p = ReducedWeaveProblem(s)
        with self.assertRaisesRegex(ValueError, "initial point must be feasible"):
            solve_equilibrium(p, np.zeros(p.dimension))

    def test_optical_export_preserves_ids_clearance_and_hash_roundtrip(self):
        warp = YarnSpec("warp_yarn", (hex_ply(id="p", rings=1, spacing_mm=.009, radius_mm=.002,
            fiber_twist_per_mm=.35, material_ids=("synthetic_A",)),))
        weft = YarnSpec("weft_yarn", (hex_ply(id="p", rings=1, spacing_mm=.009, radius_mm=.002,
            fiber_twist_per_mm=-.35, material_ids=("synthetic_B",)),))
        p = ReducedWeaveProblem(small_spec())
        r = solve_equilibrium(p)
        a = build_relaxed_hierarchy(p, r.initial_heights_mm, warp, weft, subdivisions=3)
        b = build_relaxed_hierarchy(p, r, warp, weft, subdivisions=3)
        self.assertEqual([f.fiber_id for f in a.fiber_records], [f.fiber_id for f in b.fiber_records])
        self.assertEqual(len(b.fiber_records), 28)
        self.assertTrue(audit_clearance(b)["certified_separated"])
        materials = [MaterialSpectrum.from_absorption(material_id=mid, wavelength_nm=[400,700],
            n_real=1.5, absorption_per_mm=1., source="synthetic test") for mid in ("synthetic_A", "synthetic_B")]
        scene = from_hierarchy(b, materials)
        with tempfile.TemporaryDirectory() as folder:
            save_hierarchy(folder, b)
            restored = load_hierarchy(folder)
            self.assertEqual(scene.sha256, from_hierarchy(restored, materials).sha256)
        self.assertEqual(b.metadata["equilibrium_status"], "independently_kkt_certified")
        larger = YarnSpec("too_big", (hex_ply(radius_mm=.003, spacing_mm=.013),))
        with self.assertRaisesRegex(ValueError, "exceeds declared"):
            build_relaxed_hierarchy(p, r, larger, weft)


if __name__ == "__main__":
    unittest.main()
