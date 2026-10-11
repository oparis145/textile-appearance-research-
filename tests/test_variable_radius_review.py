"""Independent analytic/topological oracles for the v5 solid-tube adapter.

These tests check physical/geometric invariants, not a second implementation of
the segment-to-node projection.  No rendered-image fidelity claim follows.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import numpy as np
from numpy.testing import assert_allclose
from scipy.spatial.transform import Rotation

from textile_sim.variable_radius import (
    VariableRadiusFiber,
    build_tapered_tube,
    load_tapered_tube,
    save_tapered_tube,
    sweep_tapered_tube,
)


def profile(points=None, radii=None, **kwargs):
    if points is None:
        points = np.column_stack((np.zeros(4), np.zeros(4), (0., .7, 1.9, 3.)))
    points = np.asarray(points, dtype=float)
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    labels = np.r_[0., np.cumsum(lengths)]
    values = dict(
        points_mm=points,
        material_coordinates_mm=labels,
        parent_material_coordinates_mm=labels,
        segment_radius_mm=np.full(len(points)-1, .12) if radii is None else radii,
        fiber_id="warp:0/ply:0/fiber:0",
        yarn_id="warp:0",
        ply_id="warp:0/ply:0",
        material_id="synthetic-review-material",
        family="warp",
    )
    values.update(kwargs)
    return VariableRadiusFiber(**values)


def tetrahedron_volume(vertices, faces):
    """Independent, translation-conditioned divergence integral."""
    q = np.asarray(vertices)-np.mean(vertices, axis=0)
    triangles = q[np.asarray(faces)]
    return float(np.einsum("ij,ij->i", triangles[:, 0],
                          np.cross(triangles[:, 1], triangles[:, 2])).sum()/6.)


def oriented_edge_audit(faces):
    edges = np.concatenate((faces[:, (0, 1)], faces[:, (1, 2)], faces[:, (2, 0)]))
    undirected, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0,
                                           return_inverse=True, return_counts=True)
    signs = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    balances = np.bincount(inverse, weights=signs)
    return undirected, counts, balances


def ray_triangle_hits(vertices, faces, origin, direction):
    """Two-sided Moller-Trumbore intersection independent of renderer code."""
    tri = np.asarray(vertices)[np.asarray(faces)]
    edge1, edge2 = tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]
    direction = np.asarray(direction, dtype=float)
    h = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
    determinant = np.einsum("ij,ij->i", edge1, h)
    safe = np.abs(determinant) > 1e-12
    inverse = np.divide(1., determinant, out=np.zeros_like(determinant), where=safe)
    s = np.asarray(origin)-tri[:, 0]
    u = inverse*np.einsum("ij,ij->i", s, h)
    q = np.cross(s, edge1)
    v = inverse*(q @ direction)
    distance = inverse*np.einsum("ij,ij->i", edge2, q)
    accepted = safe & (u >= -1e-10) & (v >= -1e-10) & (u+v <= 1+1e-10) & (distance > 1e-10)
    normals = np.cross(edge1, edge2)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    order = np.argsort(distance[accepted])
    return distance[accepted][order], normals[accepted][order]


class IndependentVariableRadiusReviewTests(unittest.TestCase):
    def test_uniform_radius_is_an_exact_fixed_point(self):
        p = profile()
        assert_allclose(p.node_radius_mm, .12, rtol=3e-15, atol=0.)
        assert_allclose(p.segment_frustum_volume_mm3, np.pi*.12**2*p.segment_length_mm,
                        rtol=3e-15, atol=0.)

    def test_unequal_lengths_and_radii_preserve_only_fiber_total(self):
        p = profile(radii=np.array((.04, .18, .07)))
        length = np.linalg.norm(np.diff(p.points_mm, axis=0), axis=1)
        source = np.pi*p.segment_radius_mm**2*length
        n = p.node_radius_mm
        continuous = np.pi*length*(n[:-1]**2+n[:-1]*n[1:]+n[1:]**2)/3
        self.assertAlmostEqual(float(continuous.sum()/source.sum()), 1., places=13)
        self.assertGreater(float(np.max(np.abs(continuous/source-1))), .1)
        self.assertTrue(np.all(n > 0.))

    def test_straight_cylinder_polygon_volume_matches_closed_form(self):
        p = profile()
        exact_circular_volume = np.pi*.12**2*3.
        for radial in (8, 16, 32, 64):
            mesh = build_tapered_tube(p, radial_segments=radial,
                                      initial_normal=(1., 0., 0.))
            factor = radial*np.sin(2*np.pi/radial)/(2*np.pi)
            expected = exact_circular_volume*factor
            self.assertAlmostEqual(mesh.signed_volume_mm3/expected, 1., places=12)
            self.assertAlmostEqual(tetrahedron_volume(mesh.vertices_mm, mesh.faces)/expected,
                                   1., places=12)

    def test_straight_taper_frustum_volume_matches_closed_form(self):
        points = np.array(((0., 0., 0.), (0., 0., 1.3)))
        r0, r1, height = .08, .24, 1.3
        for radial in (8, 16, 32):
            result = sweep_tapered_tube(points, np.array((r0, r1)),
                                        radial_segments=radial, initial_normal=(1., 0., 0.))
            polygon_area_factor = radial*np.sin(2*np.pi/radial)/2
            expected = polygon_area_factor*height*(r0*r0+r0*r1+r1*r1)/3
            actual = tetrahedron_volume(result["vertices_mm"], result["faces"])
            self.assertAlmostEqual(actual/expected, 1., places=12)

    def test_closed_mesh_has_consistent_orientations_and_sphere_topology(self):
        mesh = build_tapered_tube(profile(radii=np.array((.08, .13, .07))), radial_segments=12)
        faces = np.asarray(mesh.faces)
        self.assertTrue(np.all(faces >= 0))
        self.assertTrue(np.all(faces < len(mesh.vertices_mm)))
        self.assertTrue(np.all(np.diff(np.sort(faces, axis=1), axis=1) > 0))
        edges, counts, balances = oriented_edge_audit(faces)
        assert_allclose(counts, 2, rtol=0., atol=0.)
        assert_allclose(balances, 0., rtol=0., atol=0.)
        self.assertEqual(len(mesh.vertices_mm)-len(edges)+len(faces), 2)
        self.assertGreater(tetrahedron_volume(mesh.vertices_mm, faces), 0.)

    def test_tapered_side_normals_include_axial_slope(self):
        height, r0, r1, radial = 1.3, .08, .24, 32
        result = sweep_tapered_tube(np.array(((0., 0., 0.), (0., 0., height))),
                                    np.array((r0, r1)), radial_segments=radial,
                                    initial_normal=(1., 0., 0.))
        tri = result["vertices_mm"][result["faces"]]
        normals = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        centers = tri.mean(axis=1)
        side = (centers[:, 2] > 1e-10) & (centers[:, 2] < height-1e-10)
        effective_slope = (r1-r0)/height*np.cos(np.pi/radial)
        expected_axial = -effective_slope/np.sqrt(1+effective_slope**2)
        assert_allclose(normals[side, 2], expected_axial, rtol=3e-13, atol=3e-15)
        self.assertTrue(np.all(np.einsum("ij,ij->i", normals[side, :2], centers[side, :2]) > 0))

    def test_axial_ray_enters_and_exits_with_opposite_oriented_caps(self):
        mesh = build_tapered_tube(profile(), radial_segments=24, initial_normal=(1., 0., 0.))
        d, n = ray_triangle_hits(mesh.vertices_mm, mesh.faces,
                                (.031, .017, -1.), (0., 0., 1.))
        assert_allclose(d, (1., 4.), rtol=0., atol=1e-12)
        assert_allclose(n[:, 2], (-1., 1.), rtol=0., atol=1e-12)
        d_inside, n_inside = ray_triangle_hits(mesh.vertices_mm, mesh.faces,
                                             (.031, .017, 1.), (0., 0., 1.))
        assert_allclose(d_inside, (2.,), rtol=0., atol=1e-12)
        self.assertGreater(n_inside[0, 2], 0.)

    def test_explicit_frame_makes_sweep_rigid_motion_covariant(self):
        t = np.linspace(0., 1.2, 19)
        points = np.column_stack((np.cos(t), np.sin(t), .3*t))
        tangents = np.column_stack((-np.sin(t), np.cos(t), np.full_like(t, .3)))
        normal = np.array((1., 0., 0.))
        radii = .04*(1+.1*np.sin(2*t))
        rotation = Rotation.from_rotvec((.3, -.8, .4)).as_matrix()
        translation = np.array((11., -7., 3.))
        a = sweep_tapered_tube(points, radii, tangents=tangents,
                               initial_normal=normal, radial_segments=16)
        b = sweep_tapered_tube(points@rotation.T+translation, radii,
                               tangents=tangents@rotation.T, initial_normal=rotation@normal,
                               radial_segments=16)
        assert_allclose(b["vertices_mm"], a["vertices_mm"]@rotation.T+translation,
                        rtol=1e-13, atol=5e-14)
        assert_allclose(b["faces"], a["faces"], rtol=0., atol=0.)
        av = tetrahedron_volume(a["vertices_mm"], a["faces"])
        bv = tetrahedron_volume(b["vertices_mm"], b["faces"])
        self.assertAlmostEqual(bv/av, 1., places=11)

    def test_length_unit_scaling_changes_area_and_volume_consistently(self):
        a = profile(radii=np.array((.04, .18, .07)))
        scale = 7.3
        b = profile(points=a.points_mm*scale, radii=a.segment_radius_mm*scale)
        ma, mb = build_tapered_tube(a, radial_segments=16), build_tapered_tube(b, radial_segments=16)
        assert_allclose(mb.vertices_mm, ma.vertices_mm*scale, rtol=1e-13, atol=2e-14)
        self.assertAlmostEqual(mb.signed_volume_mm3/(ma.signed_volume_mm3*scale**3), 1., places=12)
        self.assertAlmostEqual(mb.surface_area_mm2/(ma.surface_area_mm2*scale**2), 1., places=12)
        assert_allclose(b.node_radius_mm, a.node_radius_mm*scale, rtol=3e-15)

    def test_circle_arc_axial_refinement_converges_to_continuous_tube_volume(self):
        radius, tube_radius, angle, radial = 10., .2, 1.3, 64
        polygon_factor = radial*np.sin(2*np.pi/radial)/(2*np.pi)
        target = np.pi*tube_radius**2*radius*angle*polygon_factor
        errors = []
        for count in (9, 17, 33, 65):
            t = np.linspace(0., angle, count)
            points = np.column_stack((radius*np.cos(t), radius*np.sin(t), np.zeros_like(t)))
            tangents = np.column_stack((-np.sin(t), np.cos(t), np.zeros_like(t)))
            result = sweep_tapered_tube(points, np.full(count, tube_radius), tangents=tangents,
                                        initial_normal=(0., 0., 1.), radial_segments=radial)
            actual = tetrahedron_volume(result["vertices_mm"], result["faces"])
            errors.append(abs(actual/target-1.))
        self.assertTrue(np.all(np.diff(errors) < 0.))
        self.assertTrue(np.all(np.array(errors[:-1])/np.array(errors[1:]) > 3.5))
        self.assertLess(errors[-1], 1e-4)

    def test_profile_arrays_do_not_alias_mutable_caller_storage(self):
        points = np.array(((0., 0., 0.), (0., 0., .8), (0., 0., 1.5)))
        radii = np.array((.07, .09))
        p = profile(points, radii)
        expected_points, expected_radius = p.points_mm.copy(), p.segment_radius_mm.copy()
        points[:] = 9.
        radii[:] = 9.
        assert_allclose(p.points_mm, expected_points, rtol=0., atol=0.)
        assert_allclose(p.segment_radius_mm, expected_radius, rtol=0., atol=0.)
        for array in (p.points_mm, p.segment_radius_mm, p.node_radius_mm,
                      p.material_coordinates_mm, p.parent_material_coordinates_mm):
            with self.assertRaises((ValueError, RuntimeError)):
                array.flat[0] = 100.

    def test_nonaxis_seed_mesh_roundtrip_preserves_exact_arrays(self):
        t = np.linspace(0., 1.2, 23)
        points = np.column_stack((np.cos(t), np.sin(t), .3*t))
        p = profile(points, np.full(len(points)-1, .04))
        temporary_root = Path(__file__).resolve().parents[1]/"scratch_runs"
        temporary_root.mkdir(exist_ok=True)
        for seed in (None, (.3, .2, .7)):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory(dir=temporary_root) as tmp:
                mesh = build_tapered_tube(p, radial_segments=12, initial_normal=seed)
                save_tapered_tube(tmp, mesh)
                restored = load_tapered_tube(tmp)
                self.assertEqual(restored.sha256, mesh.sha256)
                for key, array in mesh.arrays().items():
                    assert_allclose(restored.arrays()[key], array, rtol=0., atol=0.)

    def test_invalid_units_and_nonfinite_geometry_are_rejected(self):
        invalid = (
            {"length_unit": "m"},
            {"segment_radius_mm": np.array((.1, np.nan, .1))},
            {"segment_radius_mm": np.array((.1, -.1, .1))},
            {"material_coordinates_mm": np.array((0., .7, .6, 3.))},
            {"material_id": ""},
            {"cross_section": "ellipse"},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((ValueError, TypeError)):
                    profile(**kwargs)


if __name__ == "__main__":
    unittest.main()
