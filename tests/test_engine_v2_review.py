"""Independent cross-module checks from the v2 literature/physics review.

These fixtures use synthetic scalar dielectrics. They assess mathematical
contracts and geometry-to-solver transfer, not agreement with real fabrics.
"""
from dataclasses import replace
import unittest

import numpy as np
from numpy.testing import assert_allclose

from textile_sim.hierarchy import (
    FiberCurve, FiberSpec, PlySpec, YarnSpec, HierarchyGeometry,
    build_yarn, audit_clearance,
)
from textile_sim.optical_scene import (
    MaterialSpectrum, OpticalFiber, OpticalScene, BundleTolerance,
    extract_bundle_section, microstructure_statistics, wave_inputs, ray_inputs,
)


def crossing_fixture():
    a = np.array([[-.1, 0., 0.], [.1, 0., 0.]])
    b = np.array([[0., -.1, 0.], [0., .1, 0.]])
    records = (
        FiberCurve(a, np.full(2, .002), "a", "ya", "pa", "m", "test", 0, 0, 0),
        FiberCurve(b, np.full(2, .002), "b", "yb", "pb", "m", "test", 1, 0, 0),
    )
    return HierarchyGeometry(records, {"ya": a, "yb": b}, {"pa": a, "pb": b}, {})


def optical_fixture():
    mats = (
        MaterialSpectrum("a", (400, 700), (1.55, 1.60), (3e-4, 3e-4),
                         "synthetic review fixture; not measured textile data"),
        MaterialSpectrum("b", (400, 700), (1.65, 1.72), (7e-4, 7e-4),
                         "synthetic review fixture; not measured textile data"),
    )
    z = np.array([-.1, 0., .1])
    fibers = tuple(
        OpticalFiber("f" + str(i), "y" + str(i), "p" + str(i), mid,
                     np.column_stack((np.full(3, x), 0*z, z)), radius)
        for i, (mid, x, radius) in enumerate((("a", -.002, .0007), ("b", .002, .0011)))
    )
    return OpticalScene(mats, fibers, background_n=1.23)


class IndependentGeometryReviewTests(unittest.TestCase):
    def test_invalid_audit_batch_cannot_certify_an_actual_intersection(self):
        geometry = crossing_fixture()
        result = audit_clearance(geometry, batch_size=1)
        self.assertFalse(result["certified_separated"])
        self.assertAlmostEqual(result["minimum_tested_clearance_mm"], -.004, places=14)
        # Original reviewed implementation skipped the loop for batch_size=-1
        # and returned certified_separated=True. This guards the corrected gate.
        for name in ("batch_size", "max_candidate_pairs"):
            for value in (-1, 0, True, 1.5):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        audit_clearance(geometry, **{name: value})

    def test_frozen_fiber_storage_cannot_be_reenabled(self):
        record = crossing_fixture().fiber_records[0]
        for value in (record.points_mm, record.radii_mm):
            with self.assertRaises(ValueError):
                value.setflags(write=True)

    def test_nested_signed_twist_has_the_expected_mirror_symmetry(self):
        # Reflection y -> -y reverses handedness at BOTH hierarchy levels.
        # This checks the coupled convention, rather than only one straight helix.
        fiber = FiberSpec("f", "m", .001, (.005, .003),
                          migration_amplitude_mm=.0004, migration_period_mm=.137)
        ply = PlySpec("p", (fiber,), (.016, .004),
                      fiber_twist_per_mm=-2.1, fiber_phase_rad=-.2)
        yarn = YarnSpec("y", (ply,), ply_twist_per_mm=1.7, ply_phase_rad=.4)
        reflected_fiber = replace(fiber, offset_mm=(.005, -.003))
        reflected_ply = replace(ply, fibers=(reflected_fiber,), offset_mm=(.016, -.004),
                                fiber_twist_per_mm=2.1, fiber_phase_rad=.2)
        reflected_yarn = replace(yarn, plies=(reflected_ply,),
                                 ply_twist_per_mm=-1.7, ply_phase_rad=-.4)
        z = np.linspace(0., 1., 401)
        parent = np.column_stack((0*z, 0*z, z))
        a = build_yarn(yarn, parent, seed=10, initial_normal=(1, 0, 0))
        b = build_yarn(reflected_yarn, parent, seed=10, initial_normal=(1, 0, 0))
        assert_allclose(b.fiber_records[0].points_mm,
                        a.fiber_records[0].points_mm * (1., -1., 1.), atol=2e-14)
        assert_allclose(next(iter(b.plies.values())),
                        next(iter(a.plies.values())) * (1., -1., 1.), atol=2e-14)

    def test_stochastic_migration_is_independent_of_record_enumeration(self):
        first = FiberSpec("a", "m", .0005, (.006, 0.),
                          migration_amplitude_mm=.0003, migration_period_mm=.137)
        second = FiberSpec("b", "m", .0005, (-.006, 0.),
                           migration_amplitude_mm=.0003, migration_period_mm=.171)
        ply = PlySpec("p", (first, second), fiber_twist_per_mm=.7)
        a_yarn = YarnSpec("y", (ply,))
        b_yarn = replace(a_yarn, plies=(replace(ply, fibers=(second, first)),))
        z = np.linspace(0., .5, 301)
        parent = np.column_stack((0*z, 0*z, z))
        a = build_yarn(a_yarn, parent, seed=21, initial_normal=(1, 0, 0))
        b = build_yarn(b_yarn, parent, seed=21, initial_normal=(1, 0, 0))
        a_map = {f.fiber_id: f.points_mm for f in a.fiber_records}
        b_map = {f.fiber_id: f.points_mm for f in b.fiber_records}
        self.assertEqual(set(a_map), set(b_map))
        for key in a_map:
            np.testing.assert_array_equal(a_map[key], b_map[key])


class IndependentOpticalReviewTests(unittest.TestCase):
    def test_segment_refinement_preserves_physical_statistics(self):
        scene = optical_fixture()
        # Uneven subdivision should not give short segments equal statistical
        # weight to long segments, or change volume/projected-area totals.
        dense = []
        for f in scene.fibers:
            u = np.array([0., .01, .04, .2, .9, .99, 1.])
            p = (1-u[:, None])*f.points_mm[0]+u[:, None]*f.points_mm[-1]
            dense.append(replace(f, points_mm=p))
        refined = replace(scene, fibers=tuple(dense))
        direction = np.array([[1., 0., 0.], [1., 2., 3.], [0., 0., 1.]])
        a = microstructure_statistics(scene, direction)["groups"]["all"]
        b = microstructure_statistics(refined, direction)["groups"]["all"]
        for key in ("length_mm", "sum_cylinder_volume_mm3", "orientation_length",
                    "orientation_volume", "unoccluded_lateral_projected_area_mm2"):
            assert_allclose(a[key], b[key], rtol=2e-14, atol=1e-17)
        expected_volume = .2*np.pi*(.0007**2+.0011**2)
        self.assertAlmostEqual(a["sum_cylinder_volume_mm3"], expected_volume, places=17)
        self.assertAlmostEqual(a["unoccluded_lateral_projected_area_mm2"][0],
                               2*.2*(.0007+.0011), places=17)

    def test_whole_scene_similarity_reaches_the_actual_wave_and_ray_solvers(self):
        from textile_sim.fiber_wave import cluster_scattering
        from textile_sim.ply_ray import trace_bundle

        # Scaling all lengths AND vacuum wavelengths by k, while retaining
        # n(lambda/k)+i*kappa(lambda/k), preserves dimensionless Maxwell data.
        # 2D cross sections scale by k; Beer power fractions remain unchanged.
        a = optical_fixture()
        scale = 1.7
        b = OpticalScene(
            tuple(replace(m, wavelength_nm=tuple(scale*np.array(m.wavelength_nm)))
                  for m in a.materials),
            tuple(replace(f, points_mm=scale*f.points_mm, radius_mm=scale*f.radius_mm)
                  for f in a.fibers),
            background_n=a.background_n,
        )
        sa = extract_bundle_section(a, (0, 0, 0), (0, 0, 1))
        sb = extract_bundle_section(b, (0, 0, 0), (0, 0, 1),
                                    tolerance=BundleTolerance(half_window_mm=.02*scale))
        self.assertTrue(sa.eligible and sb.eligible)
        theta = np.linspace(-np.pi, np.pi, 91)
        for pol in ("Ez", "Hz"):
            with self.subTest(polarization=pol):
                wa = cluster_scattering(**wave_inputs(sa, a, 550.),
                                        polarization=pol, theta=theta)
                wb = cluster_scattering(**wave_inputs(sb, b, 550.*scale),
                                        polarization=pol, theta=theta)
                for key in ("Csca", "Cext", "Cabs", "dCsca_dtheta"):
                    assert_allclose(wb[key], scale*wa[key], rtol=3e-11, atol=1e-12)
                self.assertLess(wb["relative_energy_flux_residual"], 1e-10)
        ra = trace_bundle(**ray_inputs(sa, a, 550.), n_rays=1500, seed=91)
        rb = trace_bundle(**ray_inputs(sb, b, 550.*scale), n_rays=1500, seed=91)
        self.assertEqual(set(ra["energy"]), set(rb["energy"]))
        for key in ra["energy"]:
            self.assertAlmostEqual(ra["energy"][key], rb["energy"][key], places=11)

    def test_heterogeneous_wave_result_is_independent_of_storage_order(self):
        from textile_sim.fiber_wave import cluster_scattering

        a = optical_fixture()
        b = replace(a, materials=tuple(reversed(a.materials)), fibers=tuple(reversed(a.fibers)))
        sa = extract_bundle_section(a, (0, 0, 0), (0, 0, 1))
        sb = extract_bundle_section(b, (0, 0, 0), (0, 0, 1))
        theta = np.linspace(-np.pi, np.pi, 73)
        wa = cluster_scattering(**wave_inputs(sa, a, 550.), theta=theta)
        wb = cluster_scattering(**wave_inputs(sb, b, 550.), theta=theta)
        for key in ("Csca", "Cext", "Cabs", "dCsca_dtheta"):
            assert_allclose(wa[key], wb[key], rtol=1e-11, atol=1e-12)
        self.assertNotEqual(a.sha256, b.sha256)  # content order changes, physics does not


if __name__ == "__main__":
    unittest.main()
