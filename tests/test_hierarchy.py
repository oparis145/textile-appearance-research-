"""Analytic geometry, coordinate covariance, and independent collision tests."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from textile_sim.hierarchy import (
    FiberCurve, FiberSpec, PlySpec, YarnSpec, FabricSpec, HierarchyGeometry,
    arclength_mm, audit_clearance, build_hierarchy, build_yarn, compare_sampling_refinement, hex_ply,
    load_hierarchy, orientation_statistics, rotation_minimizing_frames,
    save_hierarchy, swept_offset,
)
from textile_sim.weave_draft import WeaveDraft


def straight_z(n=101, length=1.):
    return np.column_stack((np.zeros(n), np.zeros(n), np.linspace(0, length, n)))


def tiny_fabric(**kwargs):
    ply = hex_ply(rings=1, spacing_mm=.011, radius_mm=.0025,
                  material_ids=("synthetic_A", "synthetic_B"), fiber_twist_per_mm=.7)
    yarn = YarnSpec("one_ply", (ply,))
    return FabricSpec(WeaveDraft.basket(3, 2), yarn, yarn, warp_count=3, weft_count=2,
                      warp_pitch_mm=.16, weft_pitch_mm=.19, **kwargs)


class HierarchyTests(unittest.TestCase):
    def test_straight_helix_uses_physical_arclength_and_signed_turns(self):
        z = np.r_[np.linspace(0, .1, 15, endpoint=False), np.linspace(.1, 1., 83)]
        center = np.column_stack((np.zeros(len(z)), np.zeros(len(z)), z))
        r, twist, phase = .017, -2.3, .43
        actual = swept_offset(center, (r, 0), twist, phase, initial_normal=(1, 0, 0))
        expected = np.column_stack((r*np.cos(2*np.pi*twist*z+phase),
                                    r*np.sin(2*np.pi*twist*z+phase), z))
        np.testing.assert_allclose(actual, expected, atol=2e-15)
        theta = np.unwrap(np.arctan2(actual[:, 1], actual[:, 0]))
        self.assertAlmostEqual(float((theta[-1]-theta[0])/(2*np.pi)), -2.3, places=13)

    def test_helix_length_converges_to_independent_analytic_length(self):
        radius, twist, length = .028, 3.2, 1.13
        exact = length*np.sqrt(1+(2*np.pi*twist*radius)**2)
        errors = []
        for n in (101, 201, 401):
            curve = swept_offset(straight_z(n, length), (radius, 0), twist,
                                 initial_normal=(1, 0, 0))
            observed = arclength_mm(curve)[-1]
            # Closed-form sum of helical chords is independent of the sweeper.
            count = n-1
            exact_chords = count*np.sqrt((length/count)**2+
                              (2*radius*np.sin(np.pi*twist*length/count))**2)
            self.assertAlmostEqual(float(observed), float(exact_chords), places=13)
            errors.append(abs(observed-exact))
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)
        self.assertLess(errors[2], 5e-5)

    def test_planar_curvature_has_no_frenet_normal_flip(self):
        theta = np.linspace(-1.2, 1.2, 301)
        points = np.column_stack((np.cos(theta), np.sin(theta), np.zeros_like(theta)))
        tangents = np.column_stack((-np.sin(theta), np.cos(theta), np.zeros_like(theta)))
        t, n1, n2 = rotation_minimizing_frames(points, tangents=tangents, initial_normal=(0, 0, 1))
        np.testing.assert_allclose(n1, np.tile((0, 0, 1), (len(points), 1)), atol=2e-15)
        np.testing.assert_allclose(np.cross(t, n1), n2, atol=2e-15)
        np.testing.assert_allclose(np.sum(n1*t, axis=1), 0., atol=2e-15)

    def test_double_reflection_against_analytic_helix_bishop_frame(self):
        # Frenet torsion tau=b/(a^2+b^2); Bishop phase is -tau*s.
        a, b = .7, .23
        errors = []
        for n in (41, 81):
            theta = np.linspace(0, 4.5, n)
            q = np.sqrt(a*a+b*b)
            p = np.column_stack((a*np.cos(theta), a*np.sin(theta), b*theta))
            t = np.column_stack((-a*np.sin(theta), a*np.cos(theta), np.full(n, b)))/q
            normal = np.column_stack((-np.cos(theta), -np.sin(theta), np.zeros(n)))
            binormal = np.column_stack((b*np.sin(theta), -b*np.cos(theta), np.full(n, a)))/q
            phase = -b/q*theta
            exact = np.cos(phase)[:, None]*normal+np.sin(phase)[:, None]*binormal
            _, actual, _ = rotation_minimizing_frames(p, tangents=t, initial_normal=(-1, 0, 0))
            errors.append(np.max(np.linalg.norm(actual-exact, axis=1)))
        self.assertLess(errors[1], 2e-8)
        self.assertGreater(errors[0]/errors[1], 12)

    def test_rigid_coordinate_covariance_with_explicit_initial_frame(self):
        s = np.linspace(0, .9, 127)
        center = np.column_stack((.07*np.sin(4*s), .03*np.cos(3*s), s))
        angle = .713
        axis = np.array((1., 2., 3.)); axis /= np.linalg.norm(axis)
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        r = np.eye(3)+np.sin(angle)*k+(1-np.cos(angle))*(k@k)
        offset = np.array((.7, -.3, 1.1))
        normal = np.array((1., 0., 0.))
        baseline = swept_offset(center, (.015, .008), -1.4, .2, initial_normal=normal)
        transformed = swept_offset(center@r.T+offset, (.015, .008), -1.4, .2,
                                   initial_normal=r@normal)
        np.testing.assert_allclose(transformed, baseline@r.T+offset, atol=2e-14)

    def test_cusps_and_degenerate_curves_are_rejected(self):
        with self.assertRaises(ValueError):
            arclength_mm([[0, 0, 0], [0, 0, 0]])
        with self.assertRaises(ValueError):
            rotation_minimizing_frames([[0, 0, 0], [0, 0, 1], [0, 0, 0]])
        with self.assertRaises(ValueError):
            rotation_minimizing_frames(straight_z(), initial_normal=(0, 0, 1))

    def test_nested_twist_measured_on_longer_ply_path(self):
        fiber = FiberSpec("f", "test", .001, (.004, 0))
        ply = PlySpec("p", (fiber,), (.032, 0), fiber_twist_per_mm=-3.5)
        yarn = YarnSpec("nested", (ply,), ply_twist_per_mm=2.2)
        center = straight_z(901)
        geo = build_yarn(yarn, center, initial_normal=(1, 0, 0))
        pc = next(iter(geo.plies.values()))
        p = geo.fiber_records[0].points_mm
        ds = arclength_mm(pc)
        _, n1, n2 = rotation_minimizing_frames(pc, initial_normal=(1, 0, 0))
        q = p-pc
        angle = np.unwrap(np.arctan2(np.sum(q*n2, axis=1), np.sum(q*n1, axis=1)))
        observed_turns = (angle[-1]-angle[0])/(2*np.pi)
        analytic_parent_length = np.sqrt(1+(2*np.pi*.032*2.2)**2)
        self.assertAlmostEqual(float(observed_turns), -3.5*float(ds[-1]), places=12)
        self.assertLess(abs(float(observed_turns)+3.5*analytic_parent_length), 2e-5)
        self.assertGreater(abs(float(observed_turns)+3.5), .3)

    def test_independent_radial_migration_is_bounded_deterministic_and_seeded(self):
        fiber = FiberSpec("f", "test", .001, (.01, 0),
                          migration_amplitude_mm=.0012, migration_period_mm=.17)
        yarn = YarnSpec("migrate", (PlySpec("p", (fiber,), fiber_twist_per_mm=1.1),))
        center = straight_z(1101)
        a = build_yarn(yarn, center, seed=3)
        b = build_yarn(yarn, center, seed=3)
        c = build_yarn(yarn, center, seed=4)
        np.testing.assert_array_equal(a.fibers[0], b.fibers[0])
        self.assertGreater(np.max(np.abs(a.fibers[0]-c.fibers[0])), .0001)
        radial = np.linalg.norm(a.fiber_records[0].points_mm-center, axis=1)
        self.assertGreaterEqual(radial.min(), .0088-1e-14)
        self.assertLessEqual(radial.max(), .0112+1e-14)
        self.assertGreater(np.ptp(radial), .0023)
        bad = (FiberSpec("a", "test", .003, (.01, 0), migration_amplitude_mm=.001),
               FiberSpec("b", "test", .003, (.017, 0), migration_amplitude_mm=.001))
        with self.assertRaises(ValueError):
            PlySpec("overlap", bad)

    def test_loop_excursion_is_one_continuous_fiber_with_matching_endpoints(self):
        base = FiberSpec("f", "test", .001, (.01, 0))
        loop = replace(base, loop_amplitude_mm=.006, loop_length_mm=.2, loop_center_fraction=.5)
        ca = build_yarn(YarnSpec("y", (PlySpec("p", (base,)),)), straight_z(1001)).fiber_records[0]
        cb = build_yarn(YarnSpec("y", (PlySpec("p", (loop,)),)), straight_z(1001)).fiber_records[0]
        difference = cb.points_mm-ca.points_mm
        np.testing.assert_allclose(difference[:401], 0., atol=2e-16)
        np.testing.assert_allclose(difference[600:], 0., atol=2e-16)
        self.assertAlmostEqual(float(np.linalg.norm(difference[500])), .006, places=13)
        self.assertEqual(cb.kind, "loop_excursion")
        self.assertGreater(arclength_mm(cb.points_mm)[-1], arclength_mm(ca.points_mm)[-1])
        # At the interval endpoint both first and second derivatives tend to 0.
        self.assertLess(np.linalg.norm(difference[401]), 5e-8)

    def test_rectangular_fabric_provenance_crossings_and_finite_sampling(self):
        spec = tiny_fabric()
        geo = build_hierarchy(spec)
        self.assertEqual(len(geo.yarns), 5)
        self.assertEqual(len(geo.plies), 5)
        self.assertEqual(len(geo.fiber_records), 35)
        self.assertEqual(set(geo.material_ids), {"synthetic_A", "synthetic_B"})
        self.assertGreater(len({len(f.points_mm) for f in geo.fiber_records}), 1)
        self.assertEqual(len({r.fiber_id for r in geo.fiber_records}), 35)
        self.assertLessEqual(geo.metadata["max_fiber_segment_mm"], spec.max_segment_mm)
        self.assertLessEqual(geo.metadata["max_polyline_turn_radians"], spec.max_turn_radians)
        step = geo.metadata["samples_per_crossing_used"]
        ywarp = next(v for k, v in geo.yarns.items() if k.startswith("warp:0000"))
        for i in range(spec.weft_count):
            yw = next(v for k, v in geo.yarns.items() if k.startswith(f"weft:{i:04d}"))
            z1 = ywarp[(i+spec.padding_crossings)*step, 2]
            z2 = yw[spec.padding_crossings*step, 2]
            sign = 1 if spec.draft.crossing(0, i) else -1
            self.assertAlmostEqual(float(sign*(z1-z2)), spec.crossing_center_distance_mm, places=13)
        with self.assertRaises(ValueError):
            geo.fiber_records[0].points_mm[0, 0] = 0

    def test_signed_two_ply_and_material_hierarchy_do_not_collapse(self):
        p0 = hex_ply(id="left", rings=1, radius_mm=.0015, spacing_mm=.005,
                     offset_mm=(-.012, 0), fiber_twist_per_mm=-2.5, material_ids=("A", "B"))
        p1 = replace(p0, id="right", offset_mm=(.012, 0), fiber_twist_per_mm=1.7)
        yarn = YarnSpec("two_ply", (p0, p1), ply_twist_per_mm=.8)
        geo = build_yarn(yarn, straight_z(501), initial_normal=(1, 0, 0))
        self.assertEqual(len(geo.fiber_records), 14)
        self.assertEqual(len(geo.plies), 2)
        centers = list(geo.plies.values())
        np.testing.assert_allclose(np.linalg.norm(centers[0]-centers[1], axis=1), .024, atol=2e-15)
        self.assertEqual({r.ply_index for r in geo.fiber_records}, {0, 1})
        self.assertEqual({r.material_id for r in geo.fiber_records}, {"A", "B"})

    def test_global_clearance_can_fail_despite_equal_cross_section_packing(self):
        # Two tightly twisted helices clear at equal z but approach at shifted z.
        fibers = (FiberSpec("a", "test", .003, (.005, 0)),
                  FiberSpec("b", "test", .003, (-.005, 0)))
        yarn = YarnSpec("tight", (PlySpec("p", fibers, fiber_twist_per_mm=100.),))
        geo = build_yarn(yarn, straight_z(601, .06), initial_normal=(1, 0, 0))
        audit = audit_clearance(geo, max_candidate_pairs=2_000_000)
        self.assertFalse(audit["certified_separated"])
        self.assertLess(audit["minimum_tested_clearance_mm"], -.0005)
        self.assertGreater(audit["overlapping_capsule_pairs"], 0)

    def test_clearance_against_analytic_skew_segments_and_hidden_intersection(self):
        def make(z):
            a = np.array([[-.1, 0, 0], [.1, 0, 0]])
            b = np.array([[0, -.1, z], [0, .1, z]])
            ra = FiberCurve(a, np.full(2, .002), "a", "ya", "pa", "m", "test", 0, 0, 0)
            rb = FiberCurve(b, np.full(2, .003), "b", "yb", "pb", "m", "test", 1, 0, 0)
            return HierarchyGeometry((ra, rb), {"ya": a, "yb": b}, {"pa": a, "pb": b}, {})
        separated = audit_clearance(make(.009), probe_margin_mm=.02)
        self.assertTrue(separated["certified_separated"])
        self.assertAlmostEqual(separated["minimum_tested_clearance_mm"], .004, places=13)
        # Vertex-only nearest distances are large but interiors intersect.
        collision = audit_clearance(make(0), probe_margin_mm=.02)
        self.assertFalse(collision["certified_separated"])
        self.assertAlmostEqual(collision["minimum_tested_clearance_mm"], -.005, places=13)

    def test_saved_ragged_arrays_and_provenance_roundtrip_and_tamper_rejection(self):
        geo = build_hierarchy(tiny_fabric())
        spec_copy = FabricSpec.from_dict(geo.spec)
        self.assertEqual(spec_copy.to_dict(), geo.spec)
        with tempfile.TemporaryDirectory() as folder:
            save_hierarchy(folder, geo)
            recovered = load_hierarchy(folder)
            self.assertEqual(recovered.provenance, geo.provenance)
            self.assertEqual(recovered.spec, geo.spec)
            self.assertEqual(recovered.metadata, geo.metadata)
            for a, b in zip(geo.fibers, recovered.fibers):
                np.testing.assert_array_equal(a, b)
            with (Path(folder)/"hierarchy_geometry.npz").open("ab") as f:
                f.write(b"changed")
            with self.assertRaises(ValueError):
                load_hierarchy(folder)

    def test_non_mm_or_unknown_fields_and_bad_envelopes_are_rejected(self):
        spec = tiny_fabric()
        data = spec.to_dict()
        data["units"]["length"] = "um"
        with self.assertRaises(ValueError):
            FabricSpec.from_dict(data)
        with self.assertRaises(ValueError):
            replace(spec, warp_pitch_mm=.002)
        with self.assertRaises(ValueError):
            replace(spec, warp_crimp_share=1.01)
        with self.assertRaises(ValueError):
            FiberSpec("f", "mat", float("nan"))
        with self.assertRaises(TypeError):
            FiberSpec("f", "mat", .002, fabricated_optical_n=1.5)

    def test_orientation_tensor_is_physical_second_moment(self):
        fiber = FiberSpec("f", "mat", .001)
        yarn = YarnSpec("y", (PlySpec("p", (fiber,)),))
        s = np.linspace(0, .5, 51)
        p = np.column_stack((s, s, np.zeros_like(s)))
        stats = orientation_statistics(build_yarn(yarn, p))
        expected = np.array([[.5, .5, 0], [.5, .5, 0], [0, 0, 0]])
        np.testing.assert_allclose(stats["all"]["tangent_second_moment"], expected, atol=2e-15)
        self.assertAlmostEqual(stats["all"]["rms_out_of_plane_tilt_deg"], 0)
        geo = build_hierarchy(tiny_fabric())
        for group in orientation_statistics(geo).values():
            q = np.array(group["tangent_second_moment"])
            self.assertAlmostEqual(float(np.trace(q)), 1., places=12)
            self.assertGreaterEqual(np.linalg.eigvalsh(q).min(), -1e-14)

    def test_complete_hierarchy_refinement_reduces_geometric_difference(self):
        result = compare_sampling_refinement(tiny_fabric(), factors=(1, 2, 4))
        a, b = result["comparisons"]
        self.assertGreater(result["vertices"][2], result["vertices"][1])
        self.assertGreater(result["vertices"][1], result["vertices"][0])
        self.assertGreater(a["max_parameter_matched_centerline_distance_mm"] /
                           b["max_parameter_matched_centerline_distance_mm"], 3.)
        self.assertLess(b["max_parameter_matched_centerline_distance_mm"], 2e-5)
        self.assertLess(abs(b["relative_total_length_change"]), 1e-4)


if __name__ == "__main__":
    unittest.main()
