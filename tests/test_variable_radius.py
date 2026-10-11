"""Analytical and contract oracles for v5 continuous radii and capped tubes."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from textile_sim.hierarchy import (YarnSpec, arclength_mm, build_yarn, hex_ply)
from textile_sim.material_transport import bind_material_reference, transport_material_reference
from textile_sim.variable_radius import (
    VariableRadiusFiber, build_tapered_tube, frustum_segment_volumes_mm3,
    load_tapered_tube, load_variable_radius_profiles, mesh_edge_audit,
    profiles_from_transport, save_tapered_tube, save_variable_radius_profiles,
    sweep_tapered_tube)


def sample_profile(points=None, radii=None, **kwargs):
    p = (np.column_stack((np.zeros(4), np.zeros(4), (0., .3, .7, 1.)))
         if points is None else np.asarray(points, dtype=float))
    r = np.asarray((.04, .08, .05) if radii is None else radii, dtype=float)
    labels = arclength_mm(p)
    values = dict(points_mm=p, material_coordinates_mm=labels,
                  parent_material_coordinates_mm=labels*.91, segment_radius_mm=r,
                  fiber_id="f0", yarn_id="y0", ply_id="p0", material_id="synthetic_a",
                  family="warp", kind="core", provenance_json='{"source":"analytic_test"}')
    values.update(kwargs)
    return VariableRadiusFiber(**values)


class RadiusProfileTests(unittest.TestCase):
    def test_nonuniform_lengths_use_length_weighted_area_then_one_global_scale(self):
        p = np.array(((0., 0., 0.), (0., 0., 1.), (0., 0., 4.)))
        f = sample_profile(p, (1., 2.))
        expected_raw = np.array((1., np.sqrt(13/4), 2.))
        v_raw = np.pi*((1+expected_raw[1]+13/4)/3
                       +(13/4+2*expected_raw[1]+4))
        q = np.sqrt(13*np.pi/v_raw)
        np.testing.assert_allclose(f.raw_node_radius_mm, expected_raw, rtol=1e-15, atol=0)
        self.assertAlmostEqual(f.radius_scale, q, places=15)
        np.testing.assert_allclose(f.node_radius_mm, q*expected_raw, rtol=1e-15, atol=0)
        self.assertAlmostEqual(f.segment_frustum_volume_mm3.sum()/(13*np.pi), 1., places=14)
        self.assertGreater(np.max(np.abs(f.segment_relative_volume_error)), .1)
        self.assertFalse(f.summary()["segment_volume_conservation_enforced"])

    def test_single_segment_is_a_constant_radius_cylinder(self):
        f = sample_profile(((1., 2., 3.), (1., 2., 5.)), (.007,))
        np.testing.assert_allclose(f.node_radius_mm, .007, rtol=2e-15, atol=0)
        self.assertAlmostEqual(f.segment_frustum_volume_mm3.sum(), np.pi*.007**2*2, places=18)
        self.assertLess(abs(f.radius_scale-1), 3e-16)

    def test_constant_source_radius_survives_irregular_sampling(self):
        z = np.array((0., .01, .34, 2., 2.02))
        f = sample_profile(np.column_stack((0*z, 0*z, z)), np.full(len(z)-1, .021))
        np.testing.assert_allclose(f.node_radius_mm, .021, rtol=3e-15, atol=0)
        self.assertLess(np.max(np.abs(f.segment_relative_volume_error)), 7e-15)

    def test_source_labels_and_metadata_are_not_replaced_by_deformed_arclength(self):
        f = sample_profile(material_coordinates_mm=np.array((0., .2, .4, .8)),
                           parent_material_coordinates_mm=np.array((0., .17, .5, .73)),
                           yarn_index=4, ply_index=2, fiber_index=3)
        np.testing.assert_array_equal(f.material_coordinates_mm, (0., .2, .4, .8))
        np.testing.assert_array_equal(f.parent_material_coordinates_mm, (0., .17, .5, .73))
        self.assertEqual(f.metadata()["yarn_index"], 4)
        self.assertNotEqual(f.material_coordinates_mm[-1], f.segment_length_mm.sum())

    def test_unit_rescaling_obeys_radius_area_volume_dimensions(self):
        f = sample_profile()
        q = 137.
        g = replace(f, points_mm=f.points_mm*q, material_coordinates_mm=f.material_coordinates_mm*q,
                    parent_material_coordinates_mm=f.parent_material_coordinates_mm*q,
                    segment_radius_mm=f.segment_radius_mm*q)
        np.testing.assert_allclose(g.node_radius_mm, q*f.node_radius_mm, rtol=1e-15, atol=1e-16)
        np.testing.assert_allclose(g.segment_frustum_volume_mm3, q**3*f.segment_frustum_volume_mm3,
                                   rtol=1e-15, atol=1e-16)
        np.testing.assert_allclose(g.segment_relative_volume_error, f.segment_relative_volume_error,
                                   atol=1e-15, rtol=0)

    def test_profile_arrays_are_detached_and_cannot_reenable_writeability(self):
        p = sample_profile().points_mm.copy()
        f = sample_profile(points=p)
        original = f.sha256
        p[:] += 4
        self.assertEqual(f.sha256, original)
        for name, array in f.arrays().items():
            with self.subTest(array=name), self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_digest_covers_parent_labels_ids_material_units_and_provenance(self):
        f = sample_profile()
        for field, value in (("fiber_id", "f1"), ("ply_id", "p1"), ("yarn_id", "y1"),
                             ("material_id", "synthetic_b"), ("family", "weft"),
                             ("yarn_index", 2), ("provenance_json", '{"source":"different"}'),
                             ("parent_material_coordinates_mm", f.parent_material_coordinates_mm*.9)):
            with self.subTest(field=field):
                self.assertNotEqual(replace(f, **{field: value}).sha256, f.sha256)

    def test_invalid_profiles_are_rejected(self):
        f = sample_profile()
        bad = ({"segment_radius_mm": (0., .1, .1)}, {"segment_radius_mm": (-1., .1, .1)},
               {"segment_radius_mm": (.1, np.nan, .1)}, {"segment_radius_mm": (.1, .2)},
               {"material_coordinates_mm": (1., 2., 3., 4.)},
               {"parent_material_coordinates_mm": (0., .2, .2, 1.)},
               {"points_mm": np.zeros((4, 3))}, {"length_unit": "m"},
               {"cross_section": "ellipse"}, {"fiber_id": " "}, {"material_id": "a\nb"},
               {"fiber_index": True}, {"provenance_json": "[]"},
               {"provenance_json": '{"bad":NaN}'})
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                replace(f, **kwargs)

    def test_transport_adapter_preserves_identities_source_hash_and_both_radius_modes(self):
        s = np.linspace(0., 1., 23)
        points = np.column_stack((0*s, 0*s, s))
        geometry = build_yarn(YarnSpec("sample", (hex_ply(id="p", rings=0, radius_mm=.0015),)),
                              points, initial_normal=(1, 0, 0))
        reference = bind_material_reference(geometry,
                    yarn_initial_normals={key: (1, 0, 0) for key in geometry.yarns},
                    correspondence="shared_vertex_indices")
        target = {key: curve.points_mm*(1, 1, 1.27) for key, curve in reference.yarns.items()}
        for mode in ("constant_reference", "incompressible_segments"):
            state = transport_material_reference(reference, target,
                yarn_initial_normals={key: (1, 0, 0) for key in reference.yarns},
                deformed_parent_coordinates_mm={key: curve.material_coordinates_mm for key, curve in reference.yarns.items()},
                radius_mode=mode)
            result = profiles_from_transport(state)
            for source, profile in zip(state.fiber_records, result):
                np.testing.assert_array_equal(profile.points_mm, source.points_mm)
                np.testing.assert_array_equal(profile.material_coordinates_mm, source.material_coordinates_mm)
                np.testing.assert_array_equal(profile.parent_material_coordinates_mm, source.parent_material_coordinates_mm)
                self.assertEqual(json.loads(profile.provenance_json)["source_state_sha256"], state.sha256)
                self.assertEqual(json.loads(profile.provenance_json)["source_radius_mode"], mode)
                for name, value in source.provenance().items():
                    self.assertEqual(getattr(profile, name), value)
        with self.assertRaises(TypeError):
            profiles_from_transport(geometry)


class TaperedTubeTests(unittest.TestCase):
    def test_straight_cylinder_matches_exact_regular_polygon_volume(self):
        radius, height, m = .047, 1.32, 24
        data = sweep_tapered_tube(((0., 0., 0.), (0., 0., height)), (radius, radius),
                                  radial_segments=m, initial_normal=(1, 0, 0))
        expected = .5*m*np.sin(2*np.pi/m)*radius**2*height
        self.assertAlmostEqual(data["signed_volume_mm3"], expected, places=17)
        topology = data["summary"]
        self.assertTrue(topology["every_edge_has_two_faces"])
        self.assertTrue(topology["edge_orientations_opposed"])
        self.assertEqual(topology["euler_characteristic"], 2)

    def test_straight_taper_matches_exact_regular_polygon_frustum(self):
        r0, r1, height, m = .07, .031, 1.4, 32
        data = sweep_tapered_tube(((0., 0., 0.), (0., 0., height)), (r0, r1), radial_segments=m)
        expected = .5*m*np.sin(2*np.pi/m)*height*(r0*r0+r0*r1+r1*r1)/3
        self.assertAlmostEqual(data["signed_volume_mm3"], expected, places=17)
        # Narrowing toward +z gives positive axial component in side normals.
        self.assertTrue(np.all(data["face_normals"][:2*m, 2] > 0))
        self.assertTrue(np.all(data["face_normals"][2*m:3*m, 2] < -.999999999999))
        self.assertTrue(np.all(data["face_normals"][-m:, 2] > .999999999999))

    def test_polygon_volume_deficit_converges_to_circle_without_renormalization(self):
        f = sample_profile(((0., 0., 0.), (0., 0., 1.)), (.03,))
        errors = []
        for count in (8, 16, 32, 64):
            mesh = build_tapered_tube(f, radial_segments=count)
            errors.append(1-mesh.signed_volume_mm3/(np.pi*.03**2))
            self.assertFalse(mesh.summary()["mesh_volume_renormalized"])
        self.assertTrue(all(a > b > 0 for a, b in zip(errors, errors[1:])))
        self.assertGreater(errors[-2]/errors[-1], 3.99)

    def test_geometric_surface_area_converges_to_cylinder_area(self):
        radius, height = .051, .79
        expected = 2*np.pi*radius*height+2*np.pi*radius**2
        errors = []
        for m in (12, 24, 48):
            mesh = sweep_tapered_tube(((0., 0., 0.), (0., 0., height)), (radius, radius), radial_segments=m)
            errors.append(abs(mesh["surface_area_mm2"]-expected))
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])
        self.assertLess(errors[-1]/expected, .002)

    def test_rigid_frame_covariance_rotates_positions_and_normals(self):
        u = np.linspace(0., .8, 27)
        p = np.column_stack((.04*np.sin(2*u), .03*u*u, u))
        r = .02+.004*np.sin(u)
        initial = np.array((1., .2, .1))
        rotation = Rotation.from_rotvec((.71, -.21, .31)).as_matrix()
        shift = np.array((1.2, -.39, 2.4))
        a = sweep_tapered_tube(p, r, radial_segments=13, initial_normal=initial)
        b = sweep_tapered_tube(p@rotation.T+shift, r, radial_segments=13, initial_normal=rotation@initial)
        np.testing.assert_allclose(b["vertices_mm"], a["vertices_mm"]@rotation.T+shift, rtol=0, atol=2e-15)
        np.testing.assert_allclose(b["face_normals"], a["face_normals"]@rotation.T, rtol=0, atol=3e-12)
        self.assertLess(abs(b["signed_volume_mm3"]/a["signed_volume_mm3"]-1), 5e-15)

    def test_mesh_translation_and_unit_scale_obey_dimensions(self):
        p = np.array(((0., 0., 0.), (0., 0., 1.)))
        r = np.array((.03, .045))
        a = sweep_tapered_tube(p, r, radial_segments=19)
        q = .001
        b = sweep_tapered_tube(p*q, r*q, radial_segments=19)
        self.assertAlmostEqual(b["signed_volume_mm3"]/(a["signed_volume_mm3"]*q**3), 1., places=14)
        self.assertAlmostEqual(b["surface_area_mm2"]/(a["surface_area_mm2"]*q**2), 1., places=14)
        far = sweep_tapered_tube(p+(1e6, -2e6, 3e6), r, radial_segments=19)
        self.assertLess(abs(far["signed_volume_mm3"]/a["signed_volume_mm3"]-1), 1e-8)

    def test_curved_tube_reports_actual_volume_and_does_not_certify_contact(self):
        u = np.linspace(0., 1.2, 31)
        p = np.column_stack((.2*np.cos(u), .2*np.sin(u), .05*u))
        f = sample_profile(p, np.full(len(p)-1, .012))
        mesh = build_tapered_tube(f, radial_segments=24)
        audit = mesh.summary()
        self.assertLess(audit["mesh_to_source_proxy_relative_volume_difference"], 0)
        self.assertGreater(abs(audit["mesh_to_source_proxy_relative_volume_difference"]), .001)
        self.assertFalse(audit["self_intersection_tested"])
        self.assertFalse(audit["inter_fiber_clearance_tested"])
        self.assertFalse(audit["physical_mass_conservation_certified"])
        self.assertGreater(audit["max_discrete_radius_curvature_indicator"], 0)

    def test_mesh_source_and_numeric_arrays_are_immutable(self):
        mesh = build_tapered_tube(sample_profile(), radial_segments=12)
        for key, array in mesh.arrays().items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                array.setflags(write=True)
        self.assertEqual(mesh.fiber_id, "f0")
        self.assertEqual(mesh.material_id, "synthetic_a")
        self.assertEqual(mesh.summary()["profile_sha256"], mesh.profile.sha256)

    def test_closed_or_bad_tube_inputs_are_rejected(self):
        p = np.array(((0., 0., 0.), (0., 0., 1.)))
        for kwargs in ({"radial_segments": 2}, {"radial_segments": 3.5}, {"radial_segments": True},
                       {"initial_normal": (0., 0., 1.)}, {"tangents": ((1., 0., 0.),)},
                       {"initial_normal": (np.nan, 0., 0.)}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                sweep_tapered_tube(p, (.1, .1), **kwargs)
        for points, radius in ((p, (.1,)), (p, (.1, -.1)),
                               (np.vstack((p, p[0])), (.1, .1, .1))):
            with self.assertRaises(ValueError):
                sweep_tapered_tube(points, radius)

    def test_edge_audit_detects_an_open_or_reversed_face(self):
        data = sweep_tapered_tube(((0., 0., 0.), (0., 0., 1.)), (.1, .1), radial_segments=8)
        self.assertFalse(mesh_edge_audit(data["faces"][:-1], len(data["vertices_mm"]))["every_edge_has_two_faces"])
        faces = data["faces"].copy()
        faces[0] = faces[0, ::-1]
        self.assertFalse(mesh_edge_audit(faces, len(data["vertices_mm"]))["edge_orientations_opposed"])


class RadiusArtifactTests(unittest.TestCase):
    def test_profile_roundtrip_recomputes_geometry_without_pickle_and_blocks_overwrite(self):
        f = sample_profile()
        with tempfile.TemporaryDirectory() as folder:
            save_variable_radius_profiles(folder, (f, replace(f, fiber_id="f1")))
            loaded = load_variable_radius_profiles(folder)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].sha256, f.sha256)
            np.testing.assert_array_equal(loaded[0].node_radius_mm, f.node_radius_mm)
            with self.assertRaises(FileExistsError):
                save_variable_radius_profiles(folder, (f,))

    def test_mesh_roundtrip_recomputes_frames_faces_and_volume(self):
        u = np.linspace(0., 1., 19)
        p = np.column_stack((.02*np.sin(3*u), .01*u*u, u))
        f = sample_profile(p, .01+.002*np.cos(u[:-1]))
        for seed in (None, np.array((1., .31, -.09))):
            with tempfile.TemporaryDirectory() as folder:
                original = build_tapered_tube(f, radial_segments=11, initial_normal=seed)
                save_tapered_tube(folder, original)
                loaded = load_tapered_tube(folder)
                self.assertEqual(loaded.sha256, original.sha256)
                self.assertEqual(loaded.summary(), original.summary())
                np.testing.assert_array_equal(loaded.vertices_mm, original.vertices_mm)

    def test_tampered_radius_is_rejected_even_after_npz_checksum_is_updated(self):
        f = sample_profile()
        with tempfile.TemporaryDirectory() as directory:
            files = save_variable_radius_profiles(directory, (f,))
            with np.load(files["npz"], allow_pickle=False) as stored:
                arrays = {key: stored[key] for key in stored.files}
            arrays["fiber_00000/node_radius_mm"][1] *= 1.1
            np.savez_compressed(files["npz"], **arrays)
            data = json.loads(files["json"].read_text())
            data["array_file_sha256"] = hashlib.sha256(files["npz"].read_bytes()).hexdigest()
            files["json"].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "node_radius_mm"):
                load_variable_radius_profiles(directory)

    def test_tampered_triangle_is_rejected_after_byte_checksum_update(self):
        with tempfile.TemporaryDirectory() as directory:
            files = save_tapered_tube(directory, build_tapered_tube(sample_profile(), radial_segments=8))
            with np.load(files["npz"], allow_pickle=False) as stored:
                arrays = {key: stored[key] for key in stored.files}
            arrays["mesh/faces"][0] = arrays["mesh/faces"][0, ::-1]
            np.savez_compressed(files["npz"], **arrays)
            data = json.loads(files["json"].read_text())
            data["array_file_sha256"] = hashlib.sha256(files["npz"].read_bytes()).hexdigest()
            files["json"].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "faces"):
                load_tapered_tube(directory)

    def test_empty_duplicate_and_redirected_artifacts_are_rejected(self):
        f = sample_profile()
        with tempfile.TemporaryDirectory() as directory:
            for value in ((), (f, f), (object(),)):
                with self.assertRaises(ValueError):
                    save_variable_radius_profiles(directory, value)
            files = save_variable_radius_profiles(directory, (f,))
            data = json.loads(files["json"].read_text())
            data["array_file"] = "../unrelated.npz"
            files["json"].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "redirection"):
                load_variable_radius_profiles(directory)


if __name__ == "__main__":
    unittest.main()
