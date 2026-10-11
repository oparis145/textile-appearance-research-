"""Independent analytical and adversarial review of material transport.

These tests use closed-form motions, dimensional invariants and identity
counterexamples.  They do not duplicate the production frame algorithm or
validate textile constitutive properties against measured specimens.
"""
from copy import deepcopy
from dataclasses import replace
import unittest

import numpy as np

from textile_sim.hierarchy import (
    FiberSpec, HierarchyGeometry, PlySpec, YarnSpec, build_yarn,
)
from textile_sim.material_transport import (
    FramedCurve, bind_material_reference, transport_framed_points,
    transport_material_reference,
)


def _rotation(axis, angle):
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    cross = np.array([[0., -axis[2], axis[1]],
                      [axis[2], 0., -axis[0]],
                      [-axis[1], axis[0], 0.]])
    return np.eye(3) + np.sin(angle)*cross + (1-np.cos(angle))*(cross@cross)


def _helix_fixture(*, scale=1., knot_count=81):
    s = np.linspace(0., 1.4, knot_count)
    fiber = FiberSpec("marked", "review_material", .003*scale,
                      offset_mm=(.027*scale, 0.))
    ply = PlySpec("ply", (fiber,), fiber_twist_per_mm=.875/scale)
    yarn = YarnSpec("yarn", (ply,))
    points = np.column_stack((np.zeros_like(s), np.zeros_like(s), s))*scale
    geometry = build_yarn(yarn, points, initial_normal=(1., 0., 0.))
    normals = {key: np.array([1., 0., 0.]) for key in geometry.yarns}
    return geometry, normals


def _nested_fixture():
    s = np.linspace(0., 1.4, 129)
    points = np.column_stack((.023*np.sin(1.7*s), .019*(np.cos(2.1*s)-1), s))
    fibers = (FiberSpec("a", "review_material", .002, (.008, 0.)),
              FiberSpec("b", "review_material", .002, (0., .008)))
    plies = (PlySpec("p0", fibers, (.031, 0.), 1.4, .27),
             PlySpec("p1", fibers, (-.031, 0.), -.9, -.12))
    geometry = build_yarn(YarnSpec("nested", plies, .62), points,
                          initial_normal=(1., 0., 0.))
    normals = {key: np.array([1., 0., 0.]) for key in geometry.yarns}
    return geometry, normals


def _bind(geometry, normals):
    return bind_material_reference(geometry, yarn_initial_normals=normals,
                                   correspondence="shared_vertex_indices")


def _transport(reference, target, normals, *, radius_mode="constant_reference",
               coordinates=None):
    if coordinates is None:
        coordinates = {key: curve.material_coordinates_mm
                       for key, curve in reference.yarns.items()}
    return transport_material_reference(reference, target, yarn_initial_normals=normals,
        deformed_parent_coordinates_mm=coordinates, radius_mode=radius_mode)


def _rigid_geometry(geometry, rotation, shift):
    transform = lambda p: p@rotation.T + shift
    return HierarchyGeometry(
        tuple(replace(f, points_mm=transform(f.points_mm)) for f in geometry.fiber_records),
        {key: transform(p) for key, p in geometry.yarns.items()},
        {key: transform(p) for key, p in geometry.plies.items()},
        deepcopy(geometry.spec), deepcopy(geometry.metadata))


def _by_id(state):
    return {fiber.fiber_id: fiber for fiber in state.fiber_records}


class IndependentMaterialTransportReview(unittest.TestCase):
    def test_helix_stretch_preserves_phase_at_original_material_labels(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        stretch = 1.37
        target = {key: p*np.array([1., 1., stretch]) for key, p in geometry.yarns.items()}
        state = _transport(reference, target, normals)
        source = geometry.fiber_records[0]
        fiber = state.fiber_records[0]
        expected = source.points_mm*np.array([1., 1., stretch])
        np.testing.assert_allclose(fiber.points_mm, expected, atol=2e-14, rtol=2e-14)
        # Finite chord length of an analytic helix, not a derivative approximation.
        ds = 1.4/80
        transverse_chord2 = 4*.027**2*np.sin(2*np.pi*.875*ds/2)**2
        exact_stretch = np.sqrt((transverse_chord2+stretch**2*ds**2)
                                /(transverse_chord2+ds**2))
        np.testing.assert_allclose(fiber.segment_stretch, exact_stretch, rtol=3e-13)
        np.testing.assert_array_equal(fiber.material_coordinates_mm,
                                       reference.fiber_records[0].material_coordinates_mm)
        self.assertGreater(np.max(np.abs(fiber.deformed_arclength_mm
                                          -fiber.material_coordinates_mm)), .4)
        # Rebuilding at the same turns/mm attaches a different phase to labels.
        regenerated = build_yarn(YarnSpec.from_dict(geometry.spec["yarn"]),
            next(iter(target.values())), initial_normal=(1., 0., 0.))
        self.assertGreater(np.max(np.linalg.norm(
            regenerated.fiber_records[0].points_mm-fiber.points_mm, axis=1)), .04)

    def test_nonuniform_stretch_conserves_only_declared_segment_proxy(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        target = {}
        for key, p in geometry.yarns.items():
            q = p.copy(); q[:, 2] = p[:, 2] + .2*p[:, 2]**2
            target[key] = q
        constant = _transport(reference, target, normals)
        conserving = _transport(reference, target, normals,
                                 radius_mode="incompressible_segments")
        for fc, fv in zip(constant.fiber_records, conserving.fiber_records):
            np.testing.assert_allclose(fc.points_mm, fv.points_mm, atol=0., rtol=0.)
            np.testing.assert_allclose(fv.segment_volume_mm3, fv.reference_segment_volume_mm3,
                                       rtol=4e-15)
            expected_volume = np.pi*.003**2*np.linalg.norm(
                np.diff(geometry.fiber_records[0].points_mm, axis=0), axis=1)
            np.testing.assert_allclose(fv.segment_volume_mm3, expected_volume, rtol=4e-13)
            self.assertGreater(np.ptp(fv.segment_radius_mm), .0003)
            self.assertGreater(fc.segment_volume_mm3.sum()/expected_volume.sum()-1, .2)
        self.assertFalse(conserving.summary()["physical_mass_conservation_certified"])
        self.assertFalse(conserving.summary()["inextensibility_enforced"])
        with self.assertRaisesRegex(ValueError, "radius|radii|adapter|blocked"):
            conserving.to_hierarchy()

    def test_nested_nonrigid_transport_is_objective_under_joint_rigid_motion(self):
        geometry, normals = _nested_fixture()
        reference = _bind(geometry, normals)
        target = {}
        for key, p in geometry.yarns.items():
            s = p[:, 2]
            target[key] = p + np.column_stack((.037*s**2, .022*np.sin(2.3*s), .11*s))
        target_normals = {key: np.array([1., .15, .03]) for key in normals}
        base = _transport(reference, target, target_normals)
        rotation, shift = _rotation([1., 2., -.7], 1.19), np.array([2.3, -.71, 1.11])
        rotated_geometry = _rigid_geometry(geometry, rotation, shift)
        rotated_ref = _bind(rotated_geometry, {key: rotation@n for key, n in normals.items()})
        rotated = _transport(rotated_ref,
            {key: p@rotation.T+shift for key, p in target.items()},
            {key: rotation@n for key, n in target_normals.items()})
        for key, original in _by_id(base).items():
            transformed = _by_id(rotated)[key]
            np.testing.assert_allclose(transformed.points_mm,
                                       original.points_mm@rotation.T+shift, atol=3e-12)
            np.testing.assert_allclose(transformed.segment_stretch,
                                       original.segment_stretch, rtol=2e-11, atol=2e-11)
            np.testing.assert_allclose(transformed.segment_volume_mm3,
                                       original.segment_volume_mm3, rtol=2e-11)

    def test_nested_transport_is_invariant_to_simultaneous_frame_gauge_change(self):
        geometry, normals = _nested_fixture()
        reference = _bind(geometry, normals)
        target = {key: p*np.array([.83, 1.11, 1.32]) for key, p in geometry.yarns.items()}
        base = _transport(reference, target, normals)
        alpha = .713
        source_normals, target_normals = {}, {}
        for key in reference.yarns:
            for curve, out in ((reference.yarns[key], source_normals),
                                (base.yarns[key], target_normals)):
                out[key] = np.cos(alpha)*curve.frames[0, :, 1] + np.sin(alpha)*curve.frames[0, :, 2]
        changed_reference = _bind(geometry, source_normals)
        changed = _transport(changed_reference, target, target_normals)
        for key, fiber in _by_id(base).items():
            np.testing.assert_allclose(_by_id(changed)[key].points_mm, fiber.points_mm,
                                       atol=4e-12, rtol=4e-12)

    def test_same_centerline_with_changed_director_has_distinct_marked_fibers(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        angle = .67
        rotation = _rotation([0., 0., 1.], angle)
        spun = _transport(reference, geometry.yarns,
                           {key: rotation@n for key, n in normals.items()})
        expected = geometry.fiber_records[0].points_mm@rotation.T
        np.testing.assert_allclose(spun.fiber_records[0].points_mm, expected, atol=2e-14)
        self.assertGreater(np.linalg.norm(expected[0]-geometry.fiber_records[0].points_mm[0]), .01)

    def test_framed_point_map_roundtrip_retains_axial_offsets(self):
        # Parent knots differ. The inverse follows from orthogonal frames at
        # identical labels and must retain the full 3D offset, including z.
        sr = np.array([0., .13, .44, .77, 1.])
        sd = np.array([0., .09, .28, .51, .88, 1.])
        reference = FramedCurve(np.column_stack((sr*0, sr*0, sr)), sr, [1., 0., 0.])
        target = FramedCurve(np.column_stack((.17*sd**2, .1*np.sin(sd), 1.2*sd)),
                             sd, [1., .2, 0.])
        queries = np.array([.031, .183, .309, .629, .94])
        marked = np.column_stack((.02*np.cos(queries), -.03*np.sin(queries), queries+.011))
        moved = transport_framed_points(reference, target, marked, queries)
        recovered = transport_framed_points(target, reference, moved, queries)
        np.testing.assert_allclose(recovered, marked, atol=3e-15, rtol=3e-14)

    def test_explicit_material_knots_handle_different_target_mesh(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        key = next(iter(reference.yarns))
        fine_u = np.r_[0., .011, .097, .351, .906, 1.21,
                       reference.yarns[key].material_coordinates_mm[-1]]
        target = {key: np.column_stack((fine_u*0, fine_u*0, 1.3*fine_u))}
        state = _transport(reference, target, normals, coordinates={key: fine_u})
        expected = geometry.fiber_records[0].points_mm*np.array([1., 1., 1.3])
        np.testing.assert_allclose(state.fiber_records[0].points_mm, expected, atol=2e-14)
        self.assertEqual(len(state.yarns[key].points_mm), len(fine_u))
        self.assertEqual(len(state.fiber_records[0].points_mm), len(expected))

    def test_changed_current_arclength_cannot_replace_reference_endpoint_label(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        target = {key: p*1.3 for key, p in geometry.yarns.items()}
        relabelled = {key: curve.material_coordinates_mm*1.3 for key, curve in reference.yarns.items()}
        with self.assertRaisesRegex(ValueError, "original|endpoint|material"):
            _transport(reference, target, normals, coordinates=relabelled)

    def test_curved_parent_interpolation_converges_to_analytic_circle_offset(self):
        # The y-directed offset is exactly a binormal of this planar circle.
        # Its only position error is the analytically known chord sagitta, so
        # this probes curved resampling without using a production reference.
        s = np.linspace(0., 1., 81)
        source = np.column_stack((s*0, s*0, s))
        yarn = YarnSpec("review", (PlySpec("ply", (
            FiberSpec("offset", "review_material", .002, (.03, 0.)),)),))
        geometry = build_yarn(yarn, source, initial_normal=(0., 1., 0.))
        key = next(iter(geometry.yarns)); normals = {key: np.array([0., 1., 0.])}
        reference = _bind(geometry, normals)
        expected = np.column_stack((1-np.cos(s), np.full_like(s, .03), np.sin(s)))
        errors = []
        for count in (11, 21, 41):
            u = np.linspace(0., 1., count)
            target = {key: np.column_stack((1-np.cos(u), u*0, np.sin(u)))}
            state = _transport(reference, target, normals, coordinates={key: u})
            error = np.max(np.linalg.norm(state.fiber_records[0].points_mm-expected, axis=1))
            sagitta = 1-np.cos(.5/(count-1))
            self.assertAlmostEqual(error, sagitta, delta=2e-14)
            errors.append(error)
        # Linear position interpolation is second order here; the name RMF
        # does not make the complete interpolation pipeline fourth order.
        self.assertTrue(all(3.99 < a/b < 4.01 for a, b in zip(errors[:-1], errors[1:])))

    def test_support_is_not_silently_clamped_or_extrapolated(self):
        s = np.array([0., .4, 1.])
        curve = FramedCurve(np.column_stack((s*0, s*0, s)), s, [1., 0., 0.])
        for queries in ([-1e-6, .5], [.5, 1.+1e-6]):
            with self.assertRaisesRegex(ValueError, "extrapolat"):
                curve.evaluate(queries)
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        target = {key: p[:-1] for key, p in geometry.yarns.items()}
        short = {key: c.material_coordinates_mm[:-1] for key, c in reference.yarns.items()}
        with self.assertRaisesRegex(ValueError, "endpoint|original|material"):
            _transport(reference, target, normals, coordinates=short)

    def test_uniform_unit_scaling_changes_volume_cubically_not_strain(self):
        scale = 2.7
        states = []
        for factor in (1., scale):
            geometry, normals = _helix_fixture(scale=factor)
            reference = _bind(geometry, normals)
            states.append(_transport(reference,
                {key: p*np.array([1., 1., 1.27]) for key, p in geometry.yarns.items()},
                normals, radius_mode="incompressible_segments"))
        a, b = (s.fiber_records[0] for s in states)
        np.testing.assert_allclose(b.points_mm, scale*a.points_mm, atol=2e-14)
        np.testing.assert_allclose(b.material_coordinates_mm, scale*a.material_coordinates_mm, rtol=2e-14)
        np.testing.assert_allclose(b.segment_stretch, a.segment_stretch, rtol=3e-13)
        np.testing.assert_allclose(b.segment_radius_mm, scale*a.segment_radius_mm, rtol=3e-13)
        np.testing.assert_allclose(b.segment_volume_mm3, scale**3*a.segment_volume_mm3, rtol=3e-13)

    def test_reordering_storage_does_not_reassign_parent_identity(self):
        geometry, normals = _nested_fixture()
        permuted = HierarchyGeometry(tuple(reversed(geometry.fiber_records)),
            dict(reversed(list(geometry.yarns.items()))),
            dict(reversed(list(geometry.plies.items()))), deepcopy(geometry.spec),
            deepcopy(geometry.metadata))
        target = {key: p*np.array([1., 1., 1.19]) for key, p in geometry.yarns.items()}
        a = _transport(_bind(geometry, normals), target, normals)
        b = _transport(_bind(permuted, normals), target, normals)
        self.assertEqual(set(_by_id(a)), set(_by_id(b)))
        for key, fiber in _by_id(a).items():
            np.testing.assert_allclose(_by_id(b)[key].points_mm, fiber.points_mm, atol=0., rtol=0.)
            self.assertEqual(_by_id(b)[key].provenance(), fiber.provenance())

    def test_reference_hash_cannot_ignore_used_parent_correspondence(self):
        geometry, normals = _nested_fixture()
        reference = _bind(geometry, normals)
        mapping = dict(reference.ply_parent_material_coordinates_mm)
        key = next(iter(mapping)); changed = mapping[key].copy()
        changed[1:-1] = .97*changed[1:-1] + .03*changed[1:-1]**2/changed[-1]
        mapping[key] = changed
        try:
            altered = replace(reference, ply_parent_material_coordinates_mm=mapping)
        except (ValueError, TypeError):
            # This binding mode may reject all non-shared-index correspondences.
            return
        self.assertNotEqual(altered.sha256, reference.sha256,
            "A supported change of a map used in transport must change the reference digest")

    def test_direct_state_construction_cannot_falsely_claim_volume_conservation(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        constant = _transport(reference,
            {key: p*np.array([1., 1., 1.3]) for key, p in geometry.yarns.items()}, normals)
        with self.assertRaises((ValueError, TypeError)):
            replace(constant, radius_mode="incompressible_segments")

    def test_direct_state_cannot_mix_a_different_material_reference(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        state = _transport(reference, geometry.yarns, normals)
        shifted_geometry = _rigid_geometry(geometry, np.eye(3), np.array([0., .1, 0.]))
        different_reference = _bind(shifted_geometry, normals)
        with self.assertRaises((ValueError, TypeError)):
            replace(state, reference=different_reference)

    def test_direct_state_cannot_relabel_an_unrelated_fiber_pose_as_this_map(self):
        geometry, normals = _helix_fixture()
        reference = _bind(geometry, normals)
        state = _transport(reference, geometry.yarns, normals)
        original = state.fiber_records[0]
        # Translation retains every length, strain and volume value. Those
        # scalar checks alone cannot certify the declared parent-to-child map.
        translated = replace(original, points_mm=original.points_mm+np.array([.1, 0., 0.]))
        with self.assertRaises((ValueError, TypeError)):
            replace(state, fiber_records=(translated,))

    def test_declared_binding_requires_every_child_to_have_one_parent(self):
        geometry, normals = _nested_fixture()
        extra_yarn = next(iter(geometry.yarns))+"_second"
        records = list(geometry.fiber_records)
        # The generic geometry constructor allows the referenced yarn to exist;
        # the binder must still reject one ply attributed to two different yarns.
        records[0] = replace(records[0], yarn_id=extra_yarn, yarn_index=1)
        parents = dict(geometry.yarns); parents[extra_yarn] = next(iter(parents.values())).copy()
        ambiguous = HierarchyGeometry(tuple(records), parents, geometry.plies,
                                       deepcopy(geometry.spec), deepcopy(geometry.metadata))
        with self.assertRaisesRegex(ValueError, "parent|ply"):
            _bind(ambiguous, {**normals, extra_yarn: np.array([1., 0., 0.])})

    def test_constant_radius_export_invalidates_reference_clearance(self):
        geometry, normals = _helix_fixture()
        geometry.metadata["clearance_audit"] = {"certified_separated": True, "reference_only": True}
        reference = _bind(geometry, normals)
        state = _transport(reference, geometry.yarns, normals)
        output = state.to_hierarchy()
        self.assertNotIn("clearance_audit", output.metadata)
        self.assertTrue(output.metadata["clearance_audit_required"])
        self.assertFalse(output.metadata["reference_audits_inherited"])
        self.assertFalse(output.metadata["mass_conservation_certified"])


if __name__ == "__main__":
    unittest.main()
