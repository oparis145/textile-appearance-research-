"""Independent analytical and backend oracles for physical mesh absorption.

The render oracles use a straight closed prism viewed through parallel caps.
Their expected transmittance is analytic Beer attenuation, not a second call
to the production renderer.  RGB channels are one replicated scalar signal.
"""
from copy import deepcopy
from dataclasses import replace
import unittest

import numpy as np

from textile_sim.optical_scene import MaterialSpectrum
from textile_sim.render import RenderConfig, get_mitsuba
from textile_sim.variable_radius import VariableRadiusFiber, build_tapered_tube
from textile_sim.volume_optics import (
    build_volume_scene, material_boundary_properties,
    render_volume_scene, triangle_buffer_audit,
)


def straight_mesh(*, scale=1., radius=.2, length=1., radial_segments=16):
    points = np.array(((0., 0., 0.), (0., 0., length))) * scale
    labels = np.array((0., length)) * scale
    profile = VariableRadiusFiber(
        points_mm=points, material_coordinates_mm=labels,
        parent_material_coordinates_mm=labels, segment_radius_mm=np.array([radius*scale]),
        fiber_id="analytic_fiber", yarn_id="analytic_yarn", ply_id="analytic_ply",
        material_id="analytic", provenance_json='{"purpose":"closed-prism optical oracle"}')
    return build_tapered_tube(profile, radial_segments=radial_segments,
                              initial_normal=(1., 0., 0.))


def optical_material(mu=.7, n=1.):
    return MaterialSpectrum.from_absorption(
        "analytic", (450., 550., 650.), n, mu,
        source="synthetic analytical attenuation oracle; not measured textile data")


def axial_config(**kwargs):
    config = RenderConfig(mode="furnace", resolution=8, spp=256,
                          width_fraction=.3, view_elevation_deg=90.,
                          max_depth=64, rr_depth=128)
    return replace(config, **kwargs)


class BoundaryPhysicsTests(unittest.TestCase):
    def test_sigma_t_has_inverse_mm_units_with_no_radius_factor(self):
        props, row = material_boundary_properties(optical_material(2.7, 1.55), 550.)
        self.assertAlmostEqual(props["interior"]["sigma_t"], 2.7, places=13)
        self.assertEqual(props["interior"]["albedo"], 0.)
        self.assertFalse(props["interior"]["sample_emitters"])
        self.assertEqual(props["bsdf"]["int_ior"], 1.55)
        self.assertEqual(props["bsdf"]["ext_ior"], 1.)
        self.assertEqual(row["absorption_mapping"], "sigma_t = mu_a_per_mm; no radius multiplier")
        self.assertEqual(row["material"]["data_status"], "synthetic")

    def test_zero_absorption_has_no_redundant_medium(self):
        props, row = material_boundary_properties(optical_material(0., 1.55), 550.)
        self.assertNotIn("interior", props)
        self.assertFalse(row["absorbing_medium_installed"])
        self.assertEqual(row["sigma_t_per_scene_unit"], 0.)

    def test_index_matching_is_allowed_for_the_beer_oracle(self):
        props, row = material_boundary_properties(optical_material(.7, 1.), 550.)
        self.assertEqual(props["bsdf"]["int_ior"], props["bsdf"]["ext_ior"])
        self.assertAlmostEqual(row["absorption_per_mm"], .7, places=14)

    def test_absorption_at_three_wavelengths_obeys_kappa_conversion(self):
        mat = MaterialSpectrum("analytic", (450., 550., 650.), (1.4,)*3,
                               (1e-4, 2e-4, 4e-4), "synthetic kappa oracle")
        for wavelength, kappa in zip(mat.wavelength_nm, mat.kappa):
            with self.subTest(wavelength=wavelength):
                props, _ = material_boundary_properties(mat, wavelength)
                expected = 4*np.pi*kappa/(wavelength*1e-6)
                self.assertAlmostEqual(props["interior"]["sigma_t"], expected, places=12)

    def test_strong_absorption_gate_and_spectral_extrapolation_are_rejected(self):
        mat = MaterialSpectrum("analytic", (450., 650.), (1.5, 1.5), (.02, .02),
                               "synthetic outside weak-absorption scope")
        with self.assertRaisesRegex(ValueError, "kappa/n"):
            material_boundary_properties(mat, 550.)
        for wavelength in (449., 651., np.nan, 0.):
            with self.subTest(wavelength=wavelength), self.assertRaises(ValueError):
                material_boundary_properties(optical_material(), wavelength)
        for values in ({"background_n": 0.}, {"background_n": np.inf},
                       {"max_kappa_ratio": 0.}, {"max_kappa_ratio": True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                material_boundary_properties(optical_material(), 550., **values)


class TriangleBufferTests(unittest.TestCase):
    def test_closed_prism_export_matches_independent_volume(self):
        mesh = straight_mesh(radius=.037, length=.91, radial_segments=12)
        vertices, faces, row = triangle_buffer_audit(mesh.vertices_mm, mesh.faces)
        expected = 12*.5*np.sin(2*np.pi/12)*.037**2*.91
        self.assertAlmostEqual(row["source_signed_volume_mm3"], expected, places=17)
        self.assertEqual(vertices.dtype, np.float32)
        self.assertEqual(faces.dtype, np.uint32)
        self.assertTrue(row["closed_oriented_edge_incidence"])
        self.assertFalse(row["self_intersection_certified_absent"])
        self.assertLess(abs(row["float32_relative_volume_change"]), 2e-7)

    def test_open_mesh_or_reversed_winding_is_rejected(self):
        mesh = straight_mesh()
        for faces in (mesh.faces[:-1], mesh.faces[:, ::-1], mesh.faces.astype(float)):
            with self.subTest(shape=faces.shape), self.assertRaises(ValueError):
                triangle_buffer_audit(mesh.vertices_mm, faces)
        single_flip = mesh.faces.copy()
        single_flip[0] = single_flip[0, ::-1]
        with self.assertRaises(ValueError):
            triangle_buffer_audit(mesh.vertices_mm, single_flip)

    def test_float32_collapse_nonfinite_and_bad_indices_are_rejected(self):
        mesh = straight_mesh()
        with self.assertRaisesRegex(ValueError, "float32-collapsed"):
            triangle_buffer_audit(mesh.vertices_mm+1e9, mesh.faces)
        nonfinite = mesh.vertices_mm.copy(); nonfinite[0, 0] = np.inf
        with self.assertRaises(ValueError):
            triangle_buffer_audit(nonfinite, mesh.faces)
        faces = mesh.faces.copy(); faces[0, 0] = len(mesh.vertices_mm)
        with self.assertRaises(ValueError):
            triangle_buffer_audit(mesh.vertices_mm, faces)


class VolumeSceneContractTests(unittest.TestCase):
    def test_inside_ray_exits_closed_mesh_at_expected_cap(self):
        scene, metadata = build_volume_scene([straight_mesh()], [optical_material()],
                                             550., axial_config())
        mi = get_mitsuba()
        ray = mi.Ray3f(mi.Point3f(.023, .019, .5), mi.Vector3f(0., 0., 1.))
        hit = scene.ray_intersect(ray)
        self.assertTrue(bool(np.asarray(hit.is_valid())[0]))
        np.testing.assert_allclose(np.asarray(hit.p).ravel(), (.023, .019, 1.), atol=2e-7)
        np.testing.assert_allclose(np.asarray(hit.n).ravel(), (0., 0., 1.), atol=2e-7)
        self.assertAlmostEqual(float(np.asarray(hit.t)[0]), .5, places=6)
        self.assertTrue(metadata["triangle_geometric_normals_only"])

    def test_exported_side_uses_geometric_triangle_normal(self):
        mesh = straight_mesh(radial_segments=8)
        scene, _ = build_volume_scene([mesh], [optical_material()], 550., axial_config())
        face_id = 0
        center = mesh.vertices_mm[mesh.faces[face_id]].mean(axis=0)
        normal = mesh.face_normals[face_id]
        mi = get_mitsuba()
        ray = mi.Ray3f(mi.Point3f((center+.01*normal).tolist()),
                      mi.Vector3f((-normal).tolist()))
        hit = scene.ray_intersect(ray)
        self.assertTrue(bool(np.asarray(hit.is_valid())[0]))
        np.testing.assert_allclose(np.asarray(hit.n).ravel(), normal, atol=3e-7)
        np.testing.assert_allclose(np.asarray(hit.sh_frame.n).ravel(), normal, atol=3e-7)
        # Mitsuba exposes an empty vertex_normals parameter even when disabled.
        parameters = mi.traverse(scene.backend_scene)
        for key in parameters.keys():
            if key.endswith("vertex_normals"):
                self.assertEqual(np.asarray(parameters[key]).size, 0)
        self.assertFalse(scene.shapes()[0].has_vertex_normals())

    def test_build_identity_ignores_timing_and_covers_optical_properties(self):
        mesh, config = straight_mesh(), axial_config()
        _, a = build_volume_scene([mesh], [optical_material()], 550., config)
        _, b = build_volume_scene([mesh], [optical_material()], 550., config)
        _, c = build_volume_scene([mesh], [optical_material(.8)], 550., config)
        self.assertEqual(a["scene_sha256"], b["scene_sha256"])
        self.assertNotEqual(a["scene_sha256"], c["scene_sha256"])
        self.assertEqual(a["meshes"][0]["mesh_sha256"], mesh.sha256)

    def test_invalid_active_config_values_are_rejected(self):
        mesh, mat = straight_mesh(), optical_material()
        for change in ({"resolution": 0}, {"resolution": True}, {"spp": 0},
                       {"seed": -1}, {"rr_depth": 0}, {"max_depth": 1},
                       {"max_depth": -1.0}, {"mode": "unknown"},
                       {"view_elevation_deg": 91.}, {"light_elevation_deg": -1.},
                       {"light_azimuth_deg": np.nan}, {"light_halfwidth_deg": 0.},
                       {"light_halfwidth_deg": 45.}, {"light_halfwidth_deg": np.inf},
                       {"ambient": -1.}, {"width_fraction": 0.},
                       {"width_fraction": np.inf}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_volume_scene([mesh], [mat], 550., replace(axial_config(), **change))

    def test_bad_bounds_and_cropping_source_geometry_are_rejected(self):
        mesh, mat, config = straight_mesh(), optical_material(), axial_config()
        bad = (np.zeros((3, 2)), [[-.2, -.2, 0.], [.2, .2, 0.]],
               [[-.1, -.1, 0.], [.1, .1, 1.]],
               [[np.nan, -.2, 0.], [.2, .2, 1.]],
               [[-.2, -.2, 0.], [np.inf, .2, 1.]])
        for bounds in bad:
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                build_volume_scene([mesh], [mat], 550., config, bounds_mm=bounds)

    def test_duplicate_or_unmatched_material_identity_is_rejected(self):
        mesh, mat, config = straight_mesh(), optical_material(), axial_config()
        for meshes, materials in (([], [mat]), ([mesh, mesh], [mat]),
                                  ([mesh], []), ([mesh], [mat, mat]),
                                  ([mesh], [replace(mat, material_id="other")])):
            with self.subTest(meshes=len(meshes), materials=len(materials)), self.assertRaises(ValueError):
                build_volume_scene(meshes, materials, 550., config)

    def test_render_rejects_invalid_budget_and_corrupted_metadata(self):
        scene, metadata = build_volume_scene([straight_mesh()], [optical_material()],
                                             550., axial_config())
        for args in ({"seed": -1, "spp": 1}, {"seed": 1, "spp": 0},
                     {"seed": True, "spp": 1}, {"seed": 1, "spp": 1.5}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                render_volume_scene(scene, metadata, **args)
        for field, value in (("schema_version", "unknown"), ("scene_sha256", "0"*64)):
            changed = deepcopy(metadata); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                render_volume_scene(scene, changed, seed=1, spp=1)
        changed = deepcopy(metadata)
        changed["materials"]["analytic"]["sigma_t_per_scene_unit"] *= 2
        with self.assertRaises(ValueError):
            render_volume_scene(scene, changed, seed=1, spp=1)

    def test_valid_metadata_from_a_different_scene_is_rejected(self):
        scene, _ = build_volume_scene([straight_mesh()], [optical_material(.7)],
                                       550., axial_config())
        _, other_metadata = build_volume_scene([straight_mesh()], [optical_material(.9)],
                                                550., axial_config())
        with self.assertRaises(ValueError):
            render_volume_scene(scene, other_metadata, seed=1, spp=1)


class ActualVolumePhysicsOracles(unittest.TestCase):
    def test_index_matched_axial_transmission_obeys_beer_law(self):
        optical_depth = 1.2
        config = axial_config(resolution=16, spp=512)
        scene, meta = build_volume_scene([straight_mesh()], [optical_material(optical_depth)],
                                         550., config)
        image, row = render_volume_scene(scene, meta, seed=3371, spp=config.spp)
        expected = float(np.exp(-optical_depth))
        ray_count = config.resolution**2*config.spp
        tolerance = 6*np.sqrt(expected*(1-expected)/ray_count)+1e-4
        self.assertLess(abs(float(image.mean())-expected), tolerance)
        self.assertEqual(row["max_channel_disagreement"], 0.)
        self.assertTrue(np.isfinite(image).all())

    def test_clear_dielectric_in_constant_radiance_furnace_returns_unity(self):
        config = axial_config(resolution=8, spp=64)
        scene, meta = build_volume_scene([straight_mesh()], [optical_material(0., 1.55)],
                                         550., config)
        image, _ = render_volume_scene(scene, meta, seed=7717, spp=config.spp)
        np.testing.assert_allclose(image, 1., rtol=0., atol=2e-6)

    def test_unit_scaling_changes_mesh_volume_cubically_and_preserves_attenuation(self):
        config = axial_config(resolution=12, spp=512)
        unit_scale, mu = 8., .8
        baseline_mesh, scaled_mesh = straight_mesh(), straight_mesh(scale=unit_scale)
        self.assertAlmostEqual(scaled_mesh.signed_volume_mm3/baseline_mesh.signed_volume_mm3,
                               unit_scale**3, places=10)
        means = []
        for mesh, coefficient in ((baseline_mesh, mu), (scaled_mesh, mu/unit_scale)):
            scene, meta = build_volume_scene([mesh], [optical_material(coefficient)], 550., config)
            image, _ = render_volume_scene(scene, meta, seed=5527, spp=config.spp)
            means.append(float(image.mean()))
            self.assertAlmostEqual(meta["materials"]["analytic"]["sigma_t_per_scene_unit"],
                                   coefficient, places=13)
        expected = np.exp(-mu)
        tolerance = 6*np.sqrt(2*expected*(1-expected)/(config.resolution**2*config.spp))+1e-4
        self.assertLess(abs(means[1]-means[0]), tolerance)


if __name__ == "__main__":
    unittest.main()
