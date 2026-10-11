"""Independent v3 counterexamples and physical invariants.

These tests are authored separately from the mechanics and optical modules.
They test representational ambiguity, angular identifiability, frame/scale
covariance, and an analytically integrable spectral fixture. They do not assert
agreement with a measured fabric or certify a complete cloth transport model.
"""
from dataclasses import replace
import unittest

import numpy as np

from textile_sim.optical_scene import MaterialSpectrum, OpticalFiber, OpticalScene
from textile_sim.optical_lod import (
    SGGXProjection, fibonacci_directions, fit_sggx_projected_area,
    integrate_xyz, projected_area_density, spectral_xyz_weights,
)
from textile_sim.hierarchy import YarnSpec, hex_ply
from textile_sim.weave_draft import WeaveDraft
from textile_sim.weave_mechanics import (
    ReducedWeaveProblem, ReducedWeaveSpec, YarnElasticity,
    beam_energy_gradient_hessian, build_relaxed_hierarchy,
    equilibrium_residual, solve_equilibrium,
)


def _scene(tangents, *, scale=1., subdivisions=1):
    """Separated equal-length circular line elements, constant scalar material."""
    material = MaterialSpectrum("review", (400., 700.), (1.5, 1.5),
                                (0., 0.), "independent synthetic invariant fixture")
    fibers = []
    u = np.linspace(-.5, .5, subdivisions + 1)
    for j, t in enumerate(np.asarray(tangents, float)):
        t = t / np.linalg.norm(t)
        points = scale * (u[:, None] * t + np.array([0., 0., 3. * j]))
        fibers.append(OpticalFiber(f"fiber{j}", f"yarn{j}", f"ply{j}",
                                   "review", points, .25 * scale,
                                   family="warp" if j % 2 == 0 else "weft"))
    return OpticalScene((material,), tuple(fibers))


def _length_moment(scene):
    numerator, total = np.zeros((3, 3)), 0.
    for f in scene.fibers:
        e = np.diff(f.points_mm, axis=0)
        length = np.linalg.norm(e, axis=1)
        t = e / length[:, None]
        numerator += np.einsum("n,ni,nj->ij", length, t, t)
        total += length.sum()
    return numerator / total


class IndependentOpticalScaleReview(unittest.TestCase):
    def test_equal_tangent_covariance_does_not_determine_projected_area(self):
        # An analytic fourth/higher-moment counterexample: each distribution has
        # Q=diag(1/2,1/2,0), yet its mean sin(angle) response is different.
        a = _scene([[1, 0, 0], [0, 1, 0]])
        b = _scene([[1, 1, 0], [1, -1, 0]])
        np.testing.assert_allclose(_length_moment(a), np.diag([.5, .5, 0]), atol=1e-15)
        np.testing.assert_allclose(_length_moment(a), _length_moment(b), atol=1e-15)
        directions = np.array([[1., 0., 0.], [1., 1., 0.]])
        pa = projected_area_density(a, directions, 1.)["all"]
        pb = projected_area_density(b, directions, 1.)["all"]
        np.testing.assert_allclose(pa, [.5, 1 / np.sqrt(2)], atol=1e-14)
        np.testing.assert_allclose(pb, [1 / np.sqrt(2), .5], atol=1e-14)
        self.assertGreater(abs(pa[0] - pb[0]), .2)

    def test_projection_additivity_refinement_and_dimension_scaling(self):
        tangents = [[1., .2, .1], [-.1, 1., .4], [.3, .2, 1.]]
        d = fibonacci_directions(73)
        a = _scene(tangents)
        split = _scene(tangents, subdivisions=17)
        volume = 8.3
        target = projected_area_density(a, d, volume)["all"]
        np.testing.assert_allclose(projected_area_density(split, d, volume)["all"],
                                   target, rtol=2e-14, atol=2e-14)
        for grouping in ("family", "yarn", "ply", "material"):
            pieces = projected_area_density(split, d, volume, group_by=grouping)
            np.testing.assert_allclose(sum(pieces.values()), target,
                                       rtol=2e-14, atol=2e-14)
        # r,L scale by a, while the averaging volume scales by a^3.
        scale = 2.7
        scaled = projected_area_density(_scene(tangents, scale=scale), d,
                                         volume * scale**3)["all"]
        np.testing.assert_allclose(scaled, target / scale, rtol=2e-14)

    def test_angular_fit_rejects_unidentifiable_sampling(self):
        for d in (np.tile([1., 0., 0.], (20, 1)),
                  np.column_stack((np.cos(np.arange(20)),
                                   np.sin(np.arange(20)), np.zeros(20)))):
            # More than six samples is insufficient if their quadratic design
            # has rank<6. A tiny training residual cannot identify a 3D S.
            with self.assertRaisesRegex(ValueError, "rank|identif|span"):
                fit_sggx_projected_area(d, np.ones(len(d)))

    def test_sggx_joint_rotation_and_density_scaling(self):
        axis = np.array([1., 2., 3.]); axis /= np.linalg.norm(axis)
        cross = np.array([[0., -axis[2], axis[1]],
                          [axis[2], 0., -axis[0]],
                          [-axis[1], axis[0], 0.]])
        angle = .73
        rotation = np.eye(3) + np.sin(angle)*cross + (1-np.cos(angle))*(cross@cross)
        s = np.array([[.7, .12, -.05], [.12, 1.4, .2], [-.05, .2, 2.8]])
        model = SGGXProjection(s)
        transformed = SGGXProjection(rotation@s@rotation.T)
        scaled = SGGXProjection(3.7**2 * s)
        d = fibonacci_directions(89)
        wi = np.array([.3, -.4, .8]); wi /= np.linalg.norm(wi)
        rd = d@rotation.T
        np.testing.assert_allclose(transformed.projected_area(rd),
                                   model.projected_area(d), rtol=3e-15)
        np.testing.assert_allclose(transformed.normal_density(rd),
                                   model.normal_density(d), rtol=5e-15)
        np.testing.assert_allclose(transformed.specular_phase(rotation@wi, rd),
                                   model.specular_phase(wi, d), rtol=1e-14)
        np.testing.assert_allclose(scaled.projected_area(d),
                                   3.7*model.projected_area(d), rtol=3e-15)
        np.testing.assert_allclose(scaled.normal_density(d),
                                   3.7*model.normal_density(d), rtol=5e-15)
        np.testing.assert_allclose(scaled.specular_phase(wi, d),
                                   model.specular_phase(wi, d), rtol=5e-15)

    def test_sggx_matrix_average_is_not_linear_area_mixture(self):
        # A useful guard against treating an SPD interpolation as an exact
        # physical mixture. Jensen gives the sign; the axial case is analytic.
        a = SGGXProjection(np.diag([.04, 1., 1.]))
        b = SGGXProjection(np.diag([1., .04, 1.]))
        average = SGGXProjection((a.matrix+b.matrix)/2)
        d = np.vstack(([1., 0., 0.], fibonacci_directions(91)))
        mixture = .5*(a.projected_area(d)+b.projected_area(d))
        rms = average.projected_area(d)
        self.assertGreaterEqual(float(np.min(rms-mixture)), -1e-14)
        self.assertAlmostEqual(mixture[0], .6, places=14)
        self.assertAlmostEqual(rms[0], np.sqrt(.52), places=14)
        self.assertGreater(rms[0]-mixture[0], .12)

    def test_spectral_weights_integrate_known_linear_response(self):
        # Constant synthetic observer/SPD has an exactly integrable answer.
        # The render grid is deliberately nonuniform and not on observer nodes.
        render_nm = np.array([415.5, 481.2, 533.7, 681.1])
        observer_nm = np.arange(400., 701., 1.)
        xyz = np.tile([2., 1., .5], (len(observer_nm), 1))
        source = np.ones(len(observer_nm))
        weights, metadata = spectral_xyz_weights(render_nm, observer_nm, xyz, source)
        response = .3 + .002*(render_nm-400.)
        mean = .3 + .002*((render_nm[0]+render_nm[-1])/2-400.)
        np.testing.assert_allclose(integrate_xyz(response, weights),
                                   mean*np.array([2., 1., .5]), rtol=3e-15)
        self.assertAlmostEqual(metadata["source_photopic_mass_outside_interval"],
                               1-(681.1-415.5)/300., places=14)


class IndependentMechanicsReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = ReducedWeaveSpec(WeaveDraft.plain(), .012, .012,
                                    warp_count=2, weft_count=2,
                                    segments_per_crossing=4)
        cls.problem = ReducedWeaveProblem(cls.spec)
        cls.result = solve_equilibrium(cls.problem)
        cls.yarn = YarnSpec("review_yarn", (hex_ply(
            id="review_ply", rings=0, radius_mm=.002, spacing_mm=.006,
            material_ids=("synthetic_review",)),))

    def test_pinned_beam_sine_modes_match_analytic_discrete_spectrum(self):
        # For pinned endpoint heights the difference Laplacian has the known
        # sine basis, not periodic Fourier modes. At zero height its eigenvalues
        # are c*mu + B/h^3*mu^2, with mu=4*sin(k*pi/(2*(n+1)))^2.
        n, h = 19, .073
        material = YarnElasticity(.3, 2e-6, .971)
        _, _, stiffness = beam_energy_gradient_hessian(np.zeros(n), h, material)
        c = material.axial_stiffness_N/(material.rest_fraction*h)*(1-material.rest_fraction)
        for k in (1, 7, n):
            mode = np.sin(k*np.pi*np.arange(1, n+1)/(n+1))
            mu = 4*np.sin(k*np.pi/(2*(n+1)))**2
            eigenvalue = c*mu+material.bending_stiffness_N_mm2/h**3*mu**2
            np.testing.assert_allclose(stiffness@mode, eigenvalue*mode,
                                       rtol=2e-12, atol=2e-15)

    def test_nonlinear_beam_energy_force_and_hessian_obey_dimensions(self):
        # Scaling geometry by a and B by a^2 at fixed EA preserves strain:
        # energy -> a*energy, nodal force -> force, Hessian -> Hessian/a.
        h = .081
        z = .007*np.sin(np.arange(1, 12)*.47)+.001*np.cos(np.arange(1, 12)*1.13)
        m = YarnElasticity(.37, 6.1e-6, .962)
        energy, force, stiffness = beam_energy_gradient_hessian(z, h, m)
        a = 3.4
        scaled = replace(m, bending_stiffness_N_mm2=m.bending_stiffness_N_mm2*a*a)
        ee, ff, kk = beam_energy_gradient_hessian(a*z, a*h, scaled)
        self.assertAlmostEqual(ee/(a*energy), 1., places=13)
        np.testing.assert_allclose(ff, force, rtol=3e-13, atol=1e-16)
        np.testing.assert_allclose(kk, stiffness/a, rtol=3e-13, atol=1e-16)

    def test_relaxed_export_binds_the_problem_and_actual_state(self):
        p, result, yarn = self.problem, self.result, self.yarn
        # Before the v3 review fix these both exported as KKT-certified while
        # retaining stale diagnostics from a different solved state/problem.
        stale_state = replace(result, heights_mm=result.initial_heights_mm)
        self.assertGreater(equilibrium_residual(p, stale_state.heights_mm)["stationarity_relative"],
                           10*result.stationarity_tolerance)
        with self.assertRaisesRegex(ValueError, "state hash"):
            build_relaxed_hierarchy(p, stale_state, yarn, yarn)
        other = ReducedWeaveProblem(replace(self.spec, warp_elasticity=replace(
            self.spec.warp_elasticity,
            bending_stiffness_N_mm2=20*self.spec.warp_elasticity.bending_stiffness_N_mm2)))
        self.assertGreater(equilibrium_residual(other, result.heights_mm)["stationarity_relative"],
                           10*result.stationarity_tolerance)
        with self.assertRaisesRegex(ValueError, "different mechanics problem"):
            build_relaxed_hierarchy(other, result, yarn, yarn)

    def test_export_recomputes_kkt_instead_of_trusting_diagnostic_dictionary(self):
        p, result, yarn = self.problem, self.result, self.yarn
        misleading = replace(result, diagnostics={"independent_kkt_certified": True,
            "kkt": {"stationarity_relative": 1.e20, "forged_diagnostic": True}})
        geometry = build_relaxed_hierarchy(p, misleading, yarn, yarn)
        checked = equilibrium_residual(p, result.heights_mm)
        self.assertEqual(geometry.metadata["equilibrium_kkt"], checked)
        self.assertNotIn("forged_diagnostic", geometry.metadata["equilibrium_kkt"])
        self.assertFalse(geometry.metadata["fiber_material_points_conserved"])

    def test_invalid_slope_does_not_inherit_the_configured_clearance_certificate(self):
        p = self.problem
        z = p.initial_heights().copy()
        # Alter an interior off-crossing sample without changing crossing order.
        # A configured-L bound is invalid once the actual graph is steeper.
        z[0] += .12
        diag = p.constraint_diagnostics(z)
        self.assertFalse(diag["configured_slope_bound_satisfied"])
        self.assertIsNone(diag["conservative_orthogonal_envelope_clearance_mm"])
        self.assertGreater(diag["max_abs_slope"], p.spec.max_slope)
        w, f = (diag["family_max_abs_slope"][name] for name in ("warp", "weft"))
        # The newly reported bound uses observed family Lipschitz constants.
        expected = diag["min_crossing_separation_mm"]/np.sqrt(1+w*w+f*f)-.024
        self.assertAlmostEqual(diag["observed_slope_orthogonal_envelope_clearance_bound_mm"],
                               expected, places=15)
        with self.assertRaisesRegex(ValueError, "infeasible"):
            build_relaxed_hierarchy(p, z, self.yarn, self.yarn)

    def test_rectangular_asymmetric_weave_is_covariant_under_family_exchange(self):
        # A non-square pattern, distinct pitches/stiffnesses/radii and unequal
        # initialization share expose family indexing and over/under mistakes.
        a = ReducedWeaveSpec(WeaveDraft(((1, 1, 0), (0, 1, 1)), "review_rectangular"),
            .011, .013, warp_count=3, weft_count=2, warp_pitch_mm=.31,
            weft_pitch_mm=.27, clearance_mm=.002, segments_per_crossing=4,
            initial_warp_share=.4,
            warp_elasticity=YarnElasticity(.03, 2.2e-6, .992),
            weft_elasticity=YarnElasticity(.017, 7.e-6, .982))
        b = replace(a, draft=a.draft.transposed(),
            warp_count=a.weft_count, weft_count=a.warp_count,
            warp_pitch_mm=a.weft_pitch_mm, weft_pitch_mm=a.warp_pitch_mm,
            warp_envelope_radius_mm=a.weft_envelope_radius_mm,
            weft_envelope_radius_mm=a.warp_envelope_radius_mm,
            warp_elasticity=a.weft_elasticity, weft_elasticity=a.warp_elasticity,
            initial_warp_share=1-a.initial_warp_share)
        pa, pb = ReducedWeaveProblem(a), ReducedWeaveProblem(b)
        # Verify the equations independently of optimizer termination. Family
        # exchange is a permutation of interior height DOFs, including on a
        # non-feasible perturbed state. It must preserve E, gradient and Hessian.
        permutation = np.empty(pb.dimension, dtype=int)
        for track_a in pa.tracks:
            track_b = next(track for track in pb.tracks
                           if track.family != track_a.family
                           and track.index == track_a.index)
            permutation[track_b.variable_slice] = np.arange(pa.dimension)[track_a.variable_slice]
        perturbed = pa.initial_heights() + .001*np.sin(.913*np.arange(pa.dimension))
        ea, ga, ha = pa.energy_gradient_hessian(perturbed)
        eb, gb, hb = pb.energy_gradient_hessian(perturbed[permutation])
        self.assertAlmostEqual(eb/ea, 1., places=14)
        np.testing.assert_allclose(gb, ga[permutation], rtol=2e-14, atol=1e-17)
        np.testing.assert_allclose(hb, ha[np.ix_(permutation, permutation)],
                                   rtol=2e-14, atol=1e-15)
        # The default force gate permits a few-picometre coordinate difference
        # in this conditioned fixture. Tighten the solver rather than weakening
        # the independent geometric covariance tolerance below.
        ra = solve_equilibrium(pa, stationarity_tolerance=1e-10)
        rb = solve_equilibrium(pb, stationarity_tolerance=1e-10)
        ca, cb = pa.centerlines(ra.heights_mm), pb.centerlines(rb.heights_mm)
        for (family, index), points in ca.items():
            other = cb[("weft" if family == "warp" else "warp", index)]
            np.testing.assert_allclose(other, points[:, [1, 0, 2]], atol=3e-9, rtol=1e-7)
        self.assertAlmostEqual(ra.diagnostics["final_energy_excess_N_mm"]/
                               rb.diagnostics["final_energy_excess_N_mm"], 1., places=10)


if __name__ == "__main__":
    unittest.main()
