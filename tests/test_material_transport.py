"""Analytic, discrete conservation, frame and state-integrity transport checks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from textile_sim.hierarchy import (FiberCurve, HierarchyGeometry, YarnSpec, arclength_mm,
                                  build_yarn, hex_ply)
from textile_sim.material_transport import (FramedCurve, bind_material_reference,
    save_material_transport, transport_framed_points, transport_material_reference)


def straight(n=81, length=1.):
    u = np.linspace(0., length, n)
    return np.column_stack((np.zeros(n), np.zeros(n), u))


def fixture(*, nested=False, curved=False, n=81):
    u = np.linspace(0., 1., n)
    points = (np.column_stack((.035*np.sin(2.7*u), .027*(np.cos(2.1*u)-1), u))
              if curved else straight(n))
    plies = ((hex_ply(id="p0", rings=1, spacing_mm=.008, radius_mm=.0015,
                     fiber_twist_per_mm=1.3, offset_mm=(-.019, 0)),
              hex_ply(id="p1", rings=1, spacing_mm=.008, radius_mm=.0015,
                     fiber_twist_per_mm=-.7, offset_mm=(.019, 0))) if nested else
             (hex_ply(id="p0", rings=1, spacing_mm=.008, radius_mm=.0015,
                      fiber_twist_per_mm=1.3),))
    return build_yarn(YarnSpec("test_yarn", plies, ply_twist_per_mm=.9 if nested else 0),
                      points, initial_normal=(1, 0, 0))


def bind(geometry, normals=None):
    return bind_material_reference(geometry,
        yarn_initial_normals=normals or {key: (1, 0, 0) for key in geometry.yarns},
        correspondence="shared_vertex_indices")


def pose(reference, points=None, normals=None, mode="constant_reference", knots=None):
    return transport_material_reference(reference,
        points or {key: value.points_mm for key, value in reference.yarns.items()},
        yarn_initial_normals=normals or {key: value.initial_normal for key, value in reference.yarns.items()},
        deformed_parent_coordinates_mm=knots or {
            key: value.material_coordinates_mm for key, value in reference.yarns.items()},
        radius_mode=mode)


class MaterialTransportTests(unittest.TestCase):
    def test_identity_keeps_every_material_vertex_parent_and_label(self):
        source = fixture(nested=True, curved=True)
        reference = bind(source)
        state = pose(reference)
        output = state.to_hierarchy()
        for original, result, fiber in zip(source.fiber_records, output.fiber_records, state.fiber_records):
            self.assertEqual(original.provenance(), result.provenance())
            np.testing.assert_allclose(result.points_mm, original.points_mm, atol=3e-16, rtol=0)
            np.testing.assert_array_equal(fiber.material_coordinates_mm, arclength_mm(original.points_mm))
            np.testing.assert_allclose(fiber.segment_stretch, 1., atol=3e-14, rtol=0)
        self.assertEqual(state.summary()["fiber_vertices_added_or_removed"], 0)

    def test_rigid_motion_of_nested_curves_is_exact_with_carried_directors(self):
        source = fixture(nested=True, curved=True)
        reference = bind(source)
        rotation = Rotation.from_rotvec((.53, -.39, .71)).as_matrix()
        shift = np.array((.21, -.19, .31))
        transformed = {key: curve.points_mm@rotation.T+shift for key, curve in reference.yarns.items()}
        normals = {key: rotation@curve.initial_normal for key, curve in reference.yarns.items()}
        state = pose(reference, transformed, normals)
        for original, result in zip(source.fiber_records, state.fiber_records):
            np.testing.assert_allclose(result.points_mm, original.points_mm@rotation.T+shift,
                                       atol=1e-14, rtol=0)
            np.testing.assert_allclose(result.segment_stretch, 1., atol=2e-13, rtol=0)

    def test_helix_stretch_uses_frozen_phase_and_independent_chord_length(self):
        source = fixture(n=121)
        reference = bind(source)
        axial_stretch = 1.37
        state = pose(reference, {key: curve.points_mm*(1, 1, axial_stretch)
                                 for key, curve in reference.yarns.items()})
        for original, result in zip(source.fiber_records, state.fiber_records):
            expected = original.points_mm.copy(); expected[:, 2] *= axial_stretch
            np.testing.assert_allclose(result.points_mm, expected, atol=1e-15, rtol=0)
            dz = np.diff(original.points_mm[:, 2])
            radial_chord2 = np.sum(np.diff(original.points_mm[:, :2], axis=0)**2, axis=1)
            stretch = np.sqrt(radial_chord2+(axial_stretch*dz)**2)/np.sqrt(radial_chord2+dz**2)
            np.testing.assert_allclose(result.segment_stretch, stretch, atol=6e-14, rtol=0)
            np.testing.assert_array_equal(result.material_coordinates_mm,
                                          arclength_mm(original.points_mm))
        # The winding phase is retained from the reference, rather than adding
        # 37% more turns by sweeping again at the longer current parent arclength.
        off_axis = max(state.fiber_records, key=lambda f: np.linalg.norm(f.reference_points_mm[0, :2]))
        phase0 = np.unwrap(np.arctan2(off_axis.reference_points_mm[:, 1], off_axis.reference_points_mm[:, 0]))
        phase1 = np.unwrap(np.arctan2(off_axis.points_mm[:, 1], off_axis.points_mm[:, 0]))
        np.testing.assert_allclose(phase0, phase1, atol=2e-15, rtol=0)

    def test_constant_radius_reports_actual_discrete_volume_drift(self):
        reference = bind(fixture())
        state = pose(reference, {key: curve.points_mm*(1, 1, 1.12)
                                 for key, curve in reference.yarns.items()})
        summary = state.summary()
        self.assertGreater(summary["all"]["relative_cylinder_segment_volume_change"], .11)
        self.assertFalse(summary["physical_mass_conservation_certified"])
        self.assertFalse(summary["inextensibility_enforced"])
        for fiber in state.fiber_records:
            np.testing.assert_allclose(fiber.segment_volume_mm3/fiber.reference_segment_volume_mm3,
                                       fiber.segment_stretch, atol=1e-15, rtol=0)

    def test_incompressible_segments_conserve_proxy_with_nonuniform_stretch(self):
        reference = bind(fixture())
        target = {}
        for key, curve in reference.yarns.items():
            target[key] = curve.points_mm.copy()
            z = target[key][:, 2]
            target[key][:, 2] = .8*z+.3*z*z
        state = pose(reference, target, mode="incompressible_segments")
        for fiber in state.fiber_records:
            self.assertGreater(np.ptp(fiber.segment_radius_mm), 1e-5)
            np.testing.assert_allclose(fiber.segment_radius_mm**2*fiber.segment_stretch,
                                       fiber.reference.record.radius_mm**2, atol=1e-21, rtol=0)
            np.testing.assert_allclose(fiber.segment_volume_mm3, fiber.reference_segment_volume_mm3,
                                       atol=1e-22, rtol=2e-15)
        with self.assertRaisesRegex(ValueError, "variable-radius optical adapter"):
            state.to_hierarchy()
        with self.assertRaisesRegex(ValueError, "variable-radius optical adapter"):
            pose(reference, mode="incompressible_segments").to_hierarchy()

    def test_explicit_nonuniform_target_knots_preserve_material_attachment(self):
        reference = bind(fixture(n=47))
        key = next(iter(reference.yarns))
        u = np.unique(np.r_[0., .03, .09, .27, .51, .8, 1.])
        target = np.column_stack((np.zeros(len(u)), np.zeros(len(u)), 1.25*u))
        state = pose(reference, {key: target}, knots={key: u})
        for fiber in state.fiber_records:
            expected = fiber.reference_points_mm.copy(); expected[:, 2] *= 1.25
            np.testing.assert_allclose(fiber.points_mm, expected, atol=2e-15, rtol=0)
        self.assertEqual(len(state.yarns[key].points_mm), len(u))
        self.assertEqual(len(state.fiber_records[0].points_mm), 47)

    def test_relaxed_arclength_cannot_replace_reference_material_labels(self):
        reference = bind(fixture())
        key, source = next(iter(reference.yarns.items()))
        target = source.points_mm*(1, 1, 1.2)
        with self.assertRaisesRegex(ValueError, "original material coordinate"):
            pose(reference, {key: target}, knots={key: arclength_mm(target)})

    def test_full_local_offset_map_composes_and_inverts(self):
        u = np.linspace(0., 1., 39)
        a = FramedCurve(straight(len(u)), u, (1, 0, 0))
        b = FramedCurve(np.column_stack((.08*np.sin(2*u), .02*u*u, 1.1*u)), u, (1, .2, 0))
        c = FramedCurve(np.column_stack((-.04*u, .09*np.sin(3*u), .95*u)), u, (.8, -.1, .03))
        q = np.array((0., .023, .173, .511, .933, 1.))
        center, frame = a.evaluate(q)
        # Include an axial offset: throwing it away in a normal projection
        # would break both identity and inverse/composition checks.
        x = center+np.einsum("nij,nj->ni", frame, np.tile((.006, .03, -.019), (len(q), 1)))
        ab = transport_framed_points(a, b, x, q)
        abc = transport_framed_points(b, c, ab, q)
        ac = transport_framed_points(a, c, x, q)
        inverse = transport_framed_points(b, a, ab, q)
        np.testing.assert_allclose(abc, ac, atol=1e-15, rtol=0)
        np.testing.assert_allclose(inverse, x, atol=1e-15, rtol=0)

    def test_target_frame_refinement_reduces_smooth_pose_error(self):
        reference = bind(fixture(n=113))
        key = next(iter(reference.yarns))
        def target(n):
            u = np.linspace(0., 1., n)
            p = np.column_stack((.06*np.sin(4.3*u), .07*(np.cos(3.7*u)-1), 1.12*u))
            return pose(reference, {key: p}, knots={key: u})
        finest = target(1025)
        errors = []
        for count in (17, 33, 65):
            state = target(count)
            errors.append(max(float(np.max(np.linalg.norm(a.points_mm-b.points_mm, axis=1)))
                              for a, b in zip(state.fiber_records, finest.fiber_records)))
        # This whole nested sampled-tangent pipeline has no proved uniform
        # convergence order.  Max-error locations move relative to the fixed
        # child query grid; require measured convergence, not a nominal 4x ratio.
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])
        self.assertLess(errors[-1], 7e-5)

    def test_binding_requires_explicit_declared_correspondence(self):
        source = fixture()
        normals = {key: (1, 0, 0) for key in source.yarns}
        with self.assertRaises(TypeError):
            bind_material_reference(source, yarn_initial_normals=normals)
        with self.assertRaisesRegex(ValueError, "declaration"):
            bind_material_reference(source, yarn_initial_normals=normals, correspondence="nearest_point")
        source.plies[next(iter(source.plies))] = next(iter(source.plies.values()))[::2]
        with self.assertRaisesRegex(ValueError, "equal ply/yarn"):
            bind(source)

    def test_source_and_target_are_detached_from_caller_mutation(self):
        source = fixture(nested=True)
        source.spec["mutable_test"] = {"inside": [1, 2]}
        reference = bind(source)
        fingerprint = reference.sha256
        target = {key: value.points_mm.copy() for key, value in reference.yarns.items()}
        state = pose(reference, target)
        saved_state = state.sha256
        source.yarns[next(iter(source.yarns))][:] += 12
        source.plies[next(iter(source.plies))][:] -= 5
        source.spec["mutable_test"]["inside"].append(7)
        target[next(iter(target))][:] -= 8
        self.assertEqual(reference.sha256, fingerprint)
        self.assertEqual(state.sha256, saved_state)
        for array in (reference.yarns[next(iter(reference.yarns))].points_mm,
                      reference.plies[next(iter(reference.plies))].frames,
                      state.fiber_records[0].points_mm,
                      state.fiber_records[0].material_coordinates_mm,
                      state.fiber_records[0].segment_stretch):
            with self.assertRaises(ValueError):
                array.setflags(write=True)
        with self.assertRaises(TypeError):
            reference.yarns["new"] = next(iter(reference.yarns.values()))

    def test_repeat_pose_is_replayed_from_original_reference(self):
        reference = bind(fixture(curved=True))
        target = {key: value.points_mm*(1., 1., 1.07) for key, value in reference.yarns.items()}
        first = pose(reference, target)
        unused = pose(reference, {key: value*.93 for key, value in target.items()})
        second = pose(reference, target)
        self.assertNotEqual(first.sha256, unused.sha256)
        self.assertEqual(first.sha256, second.sha256)
        for a, b in zip(first.fiber_records, second.fiber_records):
            np.testing.assert_array_equal(a.points_mm, b.points_mm)

    def test_export_invalidates_reference_clearance_and_mechanics_claims(self):
        source = fixture()
        source.metadata["clearance_audit"] = {"certified_separated": True}
        source.metadata["physical_mechanics_solved"] = "not_applicable_fake_input"
        state = pose(bind(source))
        output = state.to_hierarchy()
        self.assertNotIn("clearance_audit", output.metadata)
        self.assertFalse(output.metadata["physical_mechanics_solved"])
        self.assertTrue(output.metadata["clearance_audit_required"])
        output.yarns[next(iter(output.yarns))][:] += 10
        np.testing.assert_allclose(state.yarns[next(iter(state.yarns))].points_mm,
                                   next(iter(source.yarns.values())), atol=0, rtol=0)

    def test_exact_parent_identifiers_and_unambiguous_labels_are_required(self):
        source = fixture(nested=True)
        reference = bind(source)
        with self.assertRaisesRegex(ValueError, "exactly the reference yarn IDs"):
            pose(reference, {"wrong_yarn": next(iter(source.yarns.values()))})
        broken = list(source.fiber_records)
        broken[-1] = replace(broken[-1], family="another_family")
        bad = HierarchyGeometry(tuple(broken), source.yarns.copy(), source.plies.copy(), {})
        with self.assertRaisesRegex(ValueError, "inconsistent family/index"):
            bind(bad)
        source.yarns["orphan"] = straight()
        with self.assertRaisesRegex(ValueError, "orphan"):
            bind(source)

    def test_degenerate_parent_and_frame_states_fail_fast(self):
        bad_curves = (np.array(((0, 0, 0), (0, 0, 0), (0, 0, 1))),
                      np.array(((0, 0, 0), (0, 0, 1), (0, 0, 0))),
                      np.array(((0, 0, 0), (0, 0, np.nan), (0, 0, 1))))
        for p in bad_curves:
            with self.subTest(curve=p.tolist()), self.assertRaises(ValueError):
                FramedCurve(p, (0., .5, 1.), (1, 0, 0))
        with self.assertRaises(ValueError):
            FramedCurve(straight(5), np.linspace(0, 1, 5), (0, 0, 1))
        with self.assertRaises(ValueError):
            FramedCurve(straight(5), (0, .3, .3, .8, 1), (1, 0, 0))
        with self.assertRaises(ValueError):
            FramedCurve(straight(5), (0, .2, .4, .6, np.inf), (1, 0, 0))
        with self.assertRaises(ValueError):
            pose(bind(fixture()), mode="average_radius")

    def test_queries_cannot_extrapolate_or_silently_change_parent_domain(self):
        parent = FramedCurve(straight(5), np.linspace(0, 1, 5), (1, 0, 0))
        for query in ((-.01, .5), (.5, 1.01), (np.nan,), ()):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parent.evaluate(query)
        target = FramedCurve(straight(5), np.linspace(0, 2, 5), (1, 0, 0))
        with self.assertRaisesRegex(ValueError, "same reference material labels"):
            transport_framed_points(parent, target, ((.1, 0, .5),), (.5,))

    def test_serialized_raw_arrays_are_complete_nonpickle_and_hash_bound(self):
        state = pose(bind(fixture(n=31)), mode="incompressible_segments")
        with tempfile.TemporaryDirectory() as temporary:
            paths = save_material_transport(temporary, state)
            payload = json.loads(paths["json"].read_text())
            self.assertEqual(payload["array_file_sha256"], hashlib.sha256(paths["npz"].read_bytes()).hexdigest())
            self.assertEqual(payload["summary"]["state_sha256"], state.sha256)
            with np.load(paths["npz"], allow_pickle=False) as arrays:
                for layout, fiber in zip(payload["array_layout"]["fibers"], state.fiber_records):
                    prefix = layout["array_prefix"]
                    np.testing.assert_array_equal(arrays[prefix+"/material_coordinates_mm"], fiber.material_coordinates_mm)
                    np.testing.assert_array_equal(arrays[prefix+"/segment_radius_mm"], fiber.segment_radius_mm)
                    np.testing.assert_array_equal(arrays[prefix+"/reference_points_mm"], fiber.reference_points_mm)
            with self.assertRaises(FileExistsError):
                save_material_transport(temporary, state)


if __name__ == "__main__":
    unittest.main()
