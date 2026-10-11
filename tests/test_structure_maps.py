"""Independent analytical visibility and attribute oracles for structure maps."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from textile_sim.hierarchy import FiberSpec, PlySpec, YarnSpec, build_yarn
from visualization.structure_maps import (
    OrthographicCamera, build_structure_surface, hierarchy_geometry_sha256,
    load_structure_maps, make_topdown_camera, save_structure_maps,
    surface_from_arrays, trace_structure_maps,
)


ROOT = Path(__file__).resolve().parents[1]


def plane(a=0., b=0., c=0., half=1., reverse=False, objects=None):
    xy = np.array([[-half, -half], [half, -half], [half, half], [-half, half]])
    vertices = np.column_stack((xy, a*xy[:, 0]+b*xy[:, 1]+c))
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    if reverse:
        faces = faces[:, ::-1]
    return surface_from_arrays(vertices, faces, vertex_tangent=[1., 0., a], objects=objects)


def small_hierarchy():
    fibers = (FiberSpec(id="left", material_id="A", radius_mm=.002, offset_mm=(-.0065, 0)),
              FiberSpec(id="right", material_id="B", radius_mm=.002, offset_mm=(.0065, 0)))
    ply = PlySpec(id="p", fibers=fibers, fiber_twist_per_mm=0.)
    yarn = YarnSpec(id="y", plies=(ply,), ply_twist_per_mm=0.)
    return build_yarn(yarn, np.array([[-.1, 0, 0], [0., 0, 0], [.1, 0, 0]]), initial_normal=[0, 0, 1])


class TestStructureMapGeometry(unittest.TestCase):
    def test_horizontal_plane_same_hit_height_normal_tangent(self):
        surface = plane(c=.35)
        camera = make_topdown_camera(surface.bounds_mm, resolution=(12, 16),
                                    extent_xy_mm=(-.8, .8, -.6, .6), padding_fraction=0)
        result = trace_structure_maps(surface, camera, supersample=1)
        a = result.arrays
        self.assertTrue(a["valid_mask"].all())
        np.testing.assert_allclose(a["height_mm"], .35, atol=2e-7)
        np.testing.assert_allclose(a["world_normal"], np.broadcast_to([0, 0, 1], (12, 16, 3)), atol=1e-7)
        np.testing.assert_allclose(a["world_tangent"], np.broadcast_to([1, 0, 0], (12, 16, 3)), atol=1e-7)
        np.testing.assert_array_equal(a["position_mm"][..., 2], a["height_mm"])
        np.testing.assert_array_equal(a["fiber_index"], -np.ones((12, 16), dtype=np.int32))
        np.testing.assert_array_equal(a["object_index"], np.zeros((12, 16), dtype=np.int32))
        self.assertEqual(result.metadata["actual_lighting_render_calls"], 0)
        self.assertEqual(result.metadata["actual_primary_ray_queries"], 12*16)

    def test_tilted_plane_analytical_world_height_and_normal(self):
        a, b, c = .3, -.2, .7
        surface = plane(a, b, c)
        camera = make_topdown_camera(surface.bounds_mm, resolution=(10, 12),
                                    extent_xy_mm=(-.7, .7, -.6, .6))
        result = trace_structure_maps(surface, camera, supersample=2)
        maps = result.arrays
        expected = a*maps["position_mm"][..., 0]+b*maps["position_mm"][..., 1]+c
        normal = np.array([-a, -b, 1.]); normal /= np.linalg.norm(normal)
        np.testing.assert_allclose(maps["height_mm"], expected, atol=3e-7)
        np.testing.assert_allclose(maps["world_normal"], np.broadcast_to(normal, (10, 12, 3)), atol=2e-7)
        self.assertGreater(float(np.min(np.abs(maps["ray_distance_mm"]-maps["height_mm"]))), .1)
        self.assertTrue(np.all(maps["coverage"] == 1))

    def test_backface_normal_is_not_flipped_to_camera(self):
        surface = plane(reverse=True)
        camera = make_topdown_camera(surface.bounds_mm, resolution=8, extent_xy_mm=(-.5, .5, -.5, .5))
        result = trace_structure_maps(surface, camera, supersample=1)
        np.testing.assert_allclose(result.arrays["world_normal"][..., 2], -1., atol=1e-7)

    def test_nearest_occluder_owns_all_attributes_and_ids(self):
        xy = np.array([[-1,-1], [1,-1], [1,1], [-1,1]], float)
        vertices = np.vstack((np.column_stack((xy, np.zeros(4))),
                              np.column_stack((xy*.4, np.full(4, .25)))))
        faces = np.array([[0,1,2], [0,2,3], [4,5,6], [4,6,7]])
        objects = [{"object_id":"bottom", "ply_id":"p0", "yarn_id":"y", "material_id":"A"},
                   {"object_id":"top", "ply_id":"p1", "yarn_id":"y", "material_id":"B"}]
        surface = surface_from_arrays(vertices, faces, vertex_tangent=[1,0,0],
                                      face_object_index=np.array([0,0,1,1]), objects=objects)
        camera = make_topdown_camera(surface.bounds_mm, resolution=16, extent_xy_mm=(-.8,.8,-.8,.8))
        maps = trace_structure_maps(surface, camera, supersample=2).arrays
        inside = (np.abs(maps["position_mm"][...,0]) < .4) & (np.abs(maps["position_mm"][...,1]) < .4)
        np.testing.assert_array_equal(maps["object_index"], inside.astype(np.int32))
        np.testing.assert_array_equal(maps["material_index"], inside.astype(np.int32))
        np.testing.assert_allclose(maps["height_mm"], .25*inside, atol=1e-7)
        self.assertTrue(maps["valid_mask"].all())

    def test_subpixel_coverage_does_not_replace_center_physics(self):
        surface = plane(half=.3)
        camera = make_topdown_camera(surface.bounds_mm, resolution=2, extent_xy_mm=(-1,1,-1,1))
        result = trace_structure_maps(surface, camera, supersample=2)
        self.assertFalse(result.arrays["valid_mask"].any())
        np.testing.assert_allclose(result.arrays["coverage"], .25)
        self.assertTrue(np.isnan(result.arrays["height_mm"]).all())
        self.assertTrue(np.isnan(result.arrays["world_normal"]).all())
        self.assertTrue((result.arrays["object_index"] == -1).all())
        self.assertEqual(int(result.supersampled["valid_mask"].sum()), 4)
        self.assertEqual(result.metadata["actual_primary_ray_queries"], 20)

    def test_oblique_camera_position_is_ray_equation(self):
        surface = plane(half=2.)
        theta = .2; c, s = np.cos(theta), np.sin(theta)
        camera = OrthographicCamera([0,0,2], [1,0,0], [0,c,s], [0,s,-c], .8,.8,(8,10))
        result = trace_structure_maps(surface, camera, supersample=1)
        row, col = np.indices((8,10))
        x = ((col+.5)/10-.5)*.8; y = (.5-(row+.5)/8)*.8
        origins = (camera.origin_mm+x[...,None]*camera.right+y[...,None]*camera.up).astype(np.float32)
        direction = camera.view_direction.astype(np.float32)
        expected_t = -origins[...,2]/direction[2]
        expected_p = origins+expected_t[...,None]*direction
        # Mitsuba reconstructs si.p from triangle coordinates while this oracle
        # uses the independent origin+t*d expression. Both paths use float32;
        # allow four relative machine-epsilon units of their input coordinate
        # scale, rather than a fixed world-unit tolerance that breaks scaling.
        coordinate_scale = max(float(np.max(np.abs(surface.vertices_mm))),
                               float(np.max(np.abs(origins))))
        roundoff_bound = 4*np.finfo(np.float32).eps*coordinate_scale
        np.testing.assert_allclose(result.arrays["ray_parameter_mm"], expected_t,
                                   atol=roundoff_bound, rtol=0)
        np.testing.assert_allclose(result.arrays["position_mm"], expected_p,
                                   atol=roundoff_bound, rtol=0)
        np.testing.assert_allclose(result.arrays["height_mm"], 0, atol=3e-7, rtol=0)

    def test_polygon_cylinder_has_exact_cross_section_height_and_normal(self):
        count=32; theta=2*np.pi*np.arange(count)/count
        ring=np.column_stack((np.sin(theta),np.cos(theta)))
        vertices=np.vstack((np.column_stack((np.full(count,-2.),ring)),
                            np.column_stack((np.full(count,2.),ring))))
        faces=[]
        for k in range(count):
            j=(k+1)%count
            faces.extend(((k,count+k,j),(count+k,count+j,j)))
        surface=surface_from_arrays(vertices,np.array(faces),vertex_tangent=[1,0,0])
        camera=make_topdown_camera(surface.bounds_mm,resolution=(16,10),extent_xy_mm=(-1,1,-.8,.8))
        maps=trace_structure_maps(surface,camera,supersample=1).arrays
        mid=(np.arange(count)+.5)*2*np.pi/count
        front=np.cos(mid)>1e-10
        ny,nz=np.sin(mid[front]),np.cos(mid[front])
        y=maps["position_mm"][...,1]
        candidates=(np.cos(np.pi/count)-y[...,None]*ny)/nz
        choice=np.argmin(candidates,axis=-1)
        expected_z=np.min(candidates,axis=-1)
        expected_n=np.stack((np.zeros_like(y),ny[choice],nz[choice]),axis=-1)
        np.testing.assert_allclose(maps["height_mm"],expected_z,atol=3e-7)
        np.testing.assert_allclose(maps["world_normal"],expected_n,atol=4e-7)
        np.testing.assert_allclose(maps["world_tangent"][...,0],1.,atol=1e-7)

    def test_barycentric_centerline_tangent_is_normalized_interpolant(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
        tangent=np.array([[1,0,0],[0,1,0],[1,1,0]],float)
        tangent/=np.linalg.norm(tangent,axis=1)[:,None]
        surface=surface_from_arrays(vertices,np.array([[0,1,2]]),vertex_tangent=tangent)
        camera=make_topdown_camera(surface.bounds_mm,resolution=1,extent_xy_mm=(.2,.3,.2,.3))
        actual=trace_structure_maps(surface,camera,supersample=1).arrays["world_tangent"][0,0]
        expected=.5*tangent[0]+.25*tangent[1]+.25*tangent[2]
        expected/=np.linalg.norm(expected)
        np.testing.assert_allclose(actual,expected,atol=1e-7)

    def test_identical_queries_deterministic_and_arrays_immutable(self):
        surface=plane(c=.2)
        camera=make_topdown_camera(surface.bounds_mm,resolution=8,extent_xy_mm=(-1.2,1.2,-1.2,1.2))
        a=trace_structure_maps(surface,camera,supersample=2)
        b=trace_structure_maps(surface,camera,supersample=2)
        for name in a.arrays:
            np.testing.assert_array_equal(a.arrays[name],b.arrays[name])
            with self.assertRaises(ValueError):a.arrays[name].setflags(write=True)
        with self.assertRaises(TypeError):a.arrays["coverage"]=np.zeros((8,8))
        metadata=a.metadata; metadata["length_unit"]="m"
        self.assertEqual(a.metadata["length_unit"],"mm")

    def test_directed_tangent_preserved_not_forced_headless(self):
        surface=surface_from_arrays(np.array([[-1,-1,0],[1,-1,0],[0,1,0]],float),
                                    np.array([[0,1,2]]),vertex_tangent=[-1,0,0])
        camera=make_topdown_camera(surface.bounds_mm,resolution=1,extent_xy_mm=(-.1,.1,-.1,.1))
        np.testing.assert_allclose(trace_structure_maps(surface,camera,supersample=1).arrays["world_tangent"][0,0],[-1,0,0])


class TestStructureMapContracts(unittest.TestCase):
    def test_hierarchy_ids_and_ply_proxy_radius_are_traceable(self):
        geometry=small_hierarchy(); original=hierarchy_geometry_sha256(geometry)
        envelope=build_structure_surface(geometry,level="ply_envelope",radial_segments=16)
        explicit=build_structure_surface(geometry,level="explicit_fiber",radial_segments=16)
        self.assertEqual(original,hierarchy_geometry_sha256(geometry))
        self.assertEqual(envelope.metadata["source_geometry_sha256"],original)
        self.assertEqual(explicit.metadata["source_geometry_sha256"],original)
        self.assertEqual(len(envelope.objects),1); self.assertEqual(len(explicit.objects),2)
        obj=envelope.objects[0]
        self.assertTrue(obj["presentation_proxy"]); self.assertIsNone(obj["material_id"])
        self.assertEqual(obj["material_ids"],["A","B"])
        self.assertAlmostEqual(obj["radius_min_mm"],.0085,places=14)
        self.assertAlmostEqual(obj["nominal_circle_area_fraction_max"],2*.002**2/.0085**2,places=14)
        self.assertEqual(obj["child_fiber_ids"],[f.fiber_id for f in geometry.fiber_records])
        self.assertGreater(envelope.metadata["max_float32_vertex_displacement_mm"],0)

    def test_mixed_ply_has_valid_hit_but_no_fake_single_material(self):
        surface=build_structure_surface(small_hierarchy(),level="ply_envelope",radial_segments=16)
        camera=make_topdown_camera(surface.bounds_mm,resolution=8,extent_xy_mm=(-.05,.05,-.005,.005))
        result=trace_structure_maps(surface,camera,supersample=1)
        self.assertTrue(result.arrays["valid_mask"].all())
        self.assertTrue((result.arrays["material_index"]==-1).all())
        self.assertTrue((result.arrays["fiber_index"]==-1).all())
        self.assertTrue((result.arrays["ply_index"]==0).all())

    def test_surface_copies_caller_data(self):
        vertices=np.array([[-1,-1,0],[1,-1,0],[0,1,0]],float)
        faces=np.array([[0,1,2]])
        surface=surface_from_arrays(vertices,faces,vertex_tangent=[1,0,0])
        digest=surface.sha256; vertices[:]=100; faces[:]=0
        self.assertEqual(surface.sha256,digest)
        self.assertLess(float(surface.vertices_mm.max()),2)
        with self.assertRaises(ValueError):surface.vertices_mm.setflags(write=True)

    def test_invalid_geometry_camera_and_budgets_rejected(self):
        vertices=np.array([[-1,-1,0],[1,-1,0],[0,1,0]],float)
        for faces in (np.array([[0,0,1]]),np.array([[0,1,4]]),np.array([[0.,1.,2.]])):
            with self.assertRaises(ValueError):surface_from_arrays(vertices,faces,vertex_tangent=[1,0,0])
        with self.assertRaises(ValueError):surface_from_arrays(vertices,np.array([[0,1,2]]),vertex_tangent=[0,0,0])
        with self.assertRaises(ValueError):OrthographicCamera([0,0,1],[1,0,0],[0,1,0],[0,0,1],1,1,(8,8))
        with self.assertRaises(ValueError):build_structure_surface(small_hierarchy(),max_triangles=1)
        with self.assertRaises(ValueError):build_structure_surface(small_hierarchy(),level="explicit_fiber",envelope_scale=2)
        with self.assertRaises(ValueError):build_structure_surface(small_hierarchy(),envelope_scale=float("nan"))

    def test_atomic_nonpickle_roundtrip_center_and_optional_samples(self):
        surface=plane(c=.12)
        camera=make_topdown_camera(surface.bounds_mm,resolution=8,extent_xy_mm=(-1.2,1.2,-1.2,1.2))
        result=trace_structure_maps(surface,camera,supersample=2)
        (ROOT/"scratch_runs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/"scratch_runs") as folder:
            output=Path(folder)/"maps"
            save_structure_maps(output,result,include_supersampled=True)
            restored=load_structure_maps(output)
            for key in result.arrays:np.testing.assert_array_equal(result.arrays[key],restored.arrays[key])
            for key in result.supersampled:np.testing.assert_array_equal(result.supersampled[key],restored.supersampled[key])
            self.assertTrue(restored.metadata["npz_crc_verified"])
            self.assertTrue(restored.metadata["saved_supersamples"])
            with self.assertRaises(FileExistsError):save_structure_maps(output,result)
            raw=output/"structure_maps.npz"; raw.write_bytes(raw.read_bytes()[:-20])
            with self.assertRaises(ValueError):load_structure_maps(output)

    def test_save_default_omits_supersamples_without_losing_coverage(self):
        surface=plane(); camera=make_topdown_camera(surface.bounds_mm,resolution=4)
        result=trace_structure_maps(surface,camera,supersample=2)
        with tempfile.TemporaryDirectory(dir=ROOT/"scratch_runs") as folder:
            save_structure_maps(folder,result)
            restored=load_structure_maps(folder)
            self.assertEqual(len(restored.supersampled),0)
            np.testing.assert_array_equal(restored.arrays["coverage"],result.arrays["coverage"])
            self.assertFalse(restored.metadata["saved_supersamples"])


if __name__ == "__main__":
    unittest.main()
