"""Independent unit/physics checks for the versioned optical bridge."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
import numpy as np
from numpy.testing import assert_allclose

from textile_sim.optical_scene import (
    MaterialSpectrum, OpticalFiber, OpticalScene, BundleTolerance,
    polyline_bspline_controls, export_mitsuba, mitsuba_scene_dictionary,
    render_optical_scene, microstructure_statistics, extract_bundle_section,
    wave_inputs, ray_inputs, from_hierarchy,
)


def material(mid="a", index=1.55, mu=2.):
    return MaterialSpectrum.from_absorption(mid, [400., 700.], index, mu,
        source="synthetic constants for optical bridge validation")


def fiber(fid="f", center=(0.,0.,0.), direction=(0.,0.,1.), radius=.004,
          material_id="a", length=.4, family="warp", points=None):
    direction = np.asarray(direction, float)
    direction /= np.linalg.norm(direction)
    if points is None:
        points = np.asarray(center)+np.linspace(-length/2,length/2,5)[:,None]*direction
    return OpticalFiber(fid, "y_"+fid, "p_"+fid, material_id, points, radius, family=family)


class SceneContractTests(unittest.TestCase):
    def test_scalar_passivity_finiteness_and_spectral_domain(self):
        m = material()
        with self.assertRaises(ValueError): m.at(399.)
        with self.assertRaises(ValueError): m.at(701.)
        with self.assertRaises(ValueError): m.at(float("nan"))
        for bad in ([-.01,0.], [0., float("inf")]):
            with self.assertRaises(ValueError):
                MaterialSpectrum("x", (400,700), (1.5,1.5), bad, "test")
        with self.assertRaises(ValueError):
            MaterialSpectrum("x", (700,400), (1.5,1.5), (0,0), "test")
        with self.assertRaises(ValueError):
            MaterialSpectrum("x", (400,700), (1.5,-1.5), (0,0), "test")

    def test_absorption_units_and_beer_field_intensity_equivalence(self):
        m = material(mu=3.7)
        for wavelength in (400., 475., 550., 700.):
            o = m.at(wavelength)
            self.assertAlmostEqual(o["absorption_per_mm"], 3.7, places=13)
            for length_mm in (.001,.01,.2):
                field_decay = np.exp(-2*np.pi*o["kappa"]*length_mm/(wavelength*1e-6))
                self.assertAlmostEqual(field_decay**2, np.exp(-3.7*length_mm), places=14)

    def test_frozen_arrays_cannot_be_reenabled_or_alias_mutated(self):
        points = np.array([[0.,0.,-1.],[0.,0.,1.]])
        f = fiber(points=points)
        points[0,0] = 99.
        self.assertEqual(f.points_mm[0,0], 0.)
        with self.assertRaises(ValueError): f.points_mm[0,0] = 1.
        with self.assertRaises(ValueError): f.points_mm.setflags(write=True)

    def test_scene_identity_parent_and_units_validation(self):
        f = fiber()
        with self.assertRaises(ValueError): OpticalScene((material(),), (f,f))
        with self.assertRaises(ValueError): OpticalScene((material(),material()), (f,))
        with self.assertRaises(ValueError): OpticalScene((material(),), (replace(f,material_id="missing"),))
        with self.assertRaises(ValueError): OpticalScene((material(),), (f,),length_unit="um")
        with self.assertRaises(ValueError): OpticalScene((material(),), (f,),schema="textile.optical_scene/3.0")
        with self.assertRaises(ValueError):
            OpticalScene((material(),), (f,replace(f,fiber_id="b",yarn_id="other")))

    def test_json_hash_roundtrip_and_tamper_detection(self):
        scene = OpticalScene((material(),), (fiber(),), provenance_json='{"seed":5}')
        with tempfile.TemporaryDirectory() as d:
            p = scene.save(Path(d)/"scene.json")
            other = OpticalScene.load(p)
            self.assertEqual(scene.sha256, other.sha256)
            data = json.loads(p.read_text())
            data["fibers"][0]["radius_mm"] *= 2
            with self.assertRaises(ValueError): OpticalScene.from_dict(data)

    def test_nonfinite_and_zero_length_geometry_rejected(self):
        for points in ([[0,0,0],[0,0,0]], [[0,0,0],[0,float("nan"),1]]):
            with self.assertRaises(ValueError): fiber(points=points)
        with self.assertRaises(ValueError): fiber(radius=0)


class SplineExportTests(unittest.TestCase):
    def test_analytic_bound_independently_sampled_on_every_segment(self):
        rng = np.random.default_rng(101)
        p = np.cumsum(rng.normal(size=(25,3)), axis=0)*.003
        c, bound = polyline_bspline_controls(p)
        u = np.linspace(0,1,401)
        # Explicit cardinal cubic basis, separate from conversion implementation.
        b = np.stack(((1-u)**3, 3*u**3-6*u**2+4,
                      -3*u**3+3*u**2+3*u+1, u**3), axis=1)/6
        observed = 0.
        for j in range(len(p)-1):
            q = b@c[j:j+4]
            chord = (1-u[:,None])*p[j]+u[:,None]*p[j+1]
            observed = max(observed, float(np.linalg.norm(q-chord,axis=1).max()))
        self.assertLessEqual(observed, bound*(1+1e-12))
        assert_allclose(b[0]@c[:4], p[0], atol=1e-16)
        assert_allclose(b[-1]@c[-4:], p[-1], atol=1e-16)
        self.assertGreater(observed, .2*bound)

    def test_collinear_uniform_curve_is_unchanged(self):
        p = fiber().points_mm
        c,bound = polyline_bspline_controls(p)
        self.assertLess(bound,1e-16)
        self.assertEqual(len(c),len(p)+2)

    def test_polylines_require_explicit_smoothing_budget(self):
        f = fiber(points=[[0,0,-.1],[.01,0,0],[0,0,.1]])
        s = OpticalScene((material(),),(f,))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                export_mitsuba(s,d,550,max_smoothing_error_mm=0)
            m = export_mitsuba(s,d,550,max_smoothing_error_mm=.01)
            self.assertGreater(m["groups"][0]["max_centerline_smoothing_bound_mm"],0)

    def test_material_and_radius_grouping_preserves_absorption(self):
        mats=(material("a",mu=2),material("b",index=1.62,mu=12))
        fs=(fiber("f0",radius=.002),fiber("f1",radius=.004),
            fiber("f2",radius=.004,material_id="b"),fiber("f3",radius=.004,material_id="b"))
        scene=OpticalScene(mats,fs)
        with tempfile.TemporaryDirectory() as d:
            manifest=export_mitsuba(scene,d,550,max_smoothing_error_mm=0)
            self.assertEqual(len(manifest["groups"]),3)
            count=0
            for g in manifest["groups"]:
                mu=2 if g["material_id"]=="a" else 12
                sigma=g["bsdf"]["sigma_a"]["value"]
                self.assertAlmostEqual(sigma,mu*g["radius_mm"],places=14)
                self.assertAlmostEqual(np.exp(-sigma*1.8),np.exp(-mu*g["radius_mm"]*1.8),places=14)
                count+=g["fiber_count"]
            self.assertEqual(count,4)
            self.assertEqual(manifest["scene_sha256"],scene.sha256)

    def test_unsupported_cross_sections_and_strong_absorbers_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            scene=OpticalScene((material(),),(replace(fiber(),cross_section="ellipse"),))
            with self.assertRaises(ValueError): export_mitsuba(scene,d,550,max_smoothing_error_mm=0)
            m=MaterialSpectrum("a",(400,700),(1.5,1.5),(.4,.4),"synthetic strong absorber")
            with self.assertRaises(ValueError):
                export_mitsuba(OpticalScene((m,),(fiber(),)),d,550,max_smoothing_error_mm=0)

    def test_manifest_change_cannot_silently_retain_scene_identity(self):
        from textile_sim.render import RenderConfig
        s=OpticalScene((material(),),(fiber(),))
        with tempfile.TemporaryDirectory() as d:
            export_mitsuba(s,d,550,max_smoothing_error_mm=0)
            p=Path(d)/"manifest.json"
            modified=json.loads(p.read_text())
            modified["groups"][0]["bsdf"]["sigma_a"]["value"] *= 10
            p.write_text(json.dumps(modified))
            with self.assertRaises(ValueError): mitsuba_scene_dictionary(d,RenderConfig())

    def test_float32_conversion_error_is_bounded_and_extreme_domain_rejected(self):
        p=np.array([[.123456789,-.0987654321,-.1],
                    [.123456789,-.0987654321,0],
                    [.123456789,-.0987654321,.1]])
        s=OpticalScene((material(),),(fiber(points=p,radius=.003123456789),))
        with tempfile.TemporaryDirectory() as d:
            manifest=export_mitsuba(s,d,550,max_smoothing_error_mm=1e-12)
            g=manifest["groups"][0]
            controls=np.loadtxt(Path(d)/g["filename"])
            delta=np.linalg.norm(controls[:,:3].astype(np.float32).astype(float)-controls[:,:3],axis=1)
            self.assertLessEqual(float(delta.max()),g["float32_centerline_quantization_bound_mm"])
            self.assertAlmostEqual(abs(float(np.float32(s.fibers[0].radius_mm))-s.fibers[0].radius_mm),
                                   g["float32_radius_quantization_bound_mm"],places=17)
            extreme=OpticalScene((material(),),(fiber(points=[[1e40,0,0],[1e40,0,1e30]]),))
            with self.assertRaises(ValueError):
                export_mitsuba(extreme,d,550,max_smoothing_error_mm=1e30)


class SliceTests(unittest.TestCase):
    def setUp(self):
        self.scene=OpticalScene((material(),),
            (fiber("f0",center=(-.015,0,0)),fiber("f1",center=(.015,0,0))))

    def test_parallel_section_has_exact_circular_centers_and_ids(self):
        section=extract_bundle_section(self.scene,[0,0,0],[0,0,1])
        self.assertTrue(section.eligible)
        assert_allclose(section.centers_mm,[[-.015,0],[.015,0]],atol=1e-15)
        self.assertEqual(section.fiber_ids,("f0","f1"))
        self.assertAlmostEqual(section.diagnostics["min_circular_gap_mm"],.022)

    def test_oblique_section_reports_ellipse_and_refuses_circular_solver(self):
        angle=np.deg2rad(30)
        s=OpticalScene((material(),),(fiber(direction=(np.sin(angle),0,np.cos(angle))),))
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        row=section.diagnostics["rows"][0]
        self.assertFalse(section.eligible)
        self.assertAlmostEqual(row["ellipse_major_semiaxis_mm"],.004/np.cos(angle),places=14)
        self.assertIn("oblique_slice_is_elliptical_not_circular",row["reasons"])
        with self.assertRaises(ValueError): wave_inputs(section,s,550)
        with self.assertRaises(ValueError): ray_inputs(section,s,550)

    def test_small_angle_reduction_requires_explicit_approximation_mode(self):
        a=np.deg2rad(.04)
        s=OpticalScene((material(),),(fiber(direction=(np.sin(a),0,np.cos(a))),))
        self.assertFalse(extract_bundle_section(s,[0,0,0],[0,0,1]).eligible)
        section=extract_bundle_section(s,[0,0,0],[0,0,1],tolerance=BundleTolerance(mode="local_parallel"))
        self.assertTrue(section.eligible)
        self.assertGreater(section.diagnostics["rows"][0]["ellipse_area_ratio_vs_circle"],1.)

    def test_curvature_inside_window_not_hidden_by_normal_center_tangent(self):
        z=np.linspace(-.1,.1,31)
        p=np.column_stack((3*z*z,np.zeros_like(z),z))
        s=OpticalScene((material(),),(fiber(points=p),))
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        self.assertFalse(section.eligible)
        self.assertIn("nonparallel_or_curved_local_bundle",section.diagnostics["rows"][0]["reasons"])

    def test_short_support_multiple_crossings_and_coplanarity_are_rejected(self):
        examples=[fiber(length=.02),
            fiber(points=[[0,0,-.1],[.02,0,.1],[.04,0,-.1]]),
            fiber(points=[[-.1,0,0],[.1,0,0]])]
        for f in examples:
            s=OpticalScene((material(),),(f,))
            self.assertFalse(extract_bundle_section(s,[0,0,0],[0,0,1]).eligible)

    def test_failed_fiber_not_silently_dropped(self):
        f=replace(fiber("miss"),points_mm=np.array([[0,0,.1],[0,0,.2]]))
        s=OpticalScene(self.scene.materials,self.scene.fibers+(f,))
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        self.assertFalse(section.eligible)
        self.assertEqual(len(section.centers_mm),2)
        self.assertEqual(len(section.diagnostics["rows"]),3)

    def test_circle_overlap_rejected_and_scene_hash_guards_transfer(self):
        s=OpticalScene((material(),),(fiber("a"),fiber("b",center=(.001,0,0))))
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        self.assertFalse(section.eligible)
        self.assertTrue(section.diagnostics["circular_overlap"])
        section=extract_bundle_section(self.scene,[0,0,0],[0,0,1])
        changed=replace(self.scene,background_n=1.1)
        with self.assertRaises(ValueError): wave_inputs(section,changed,550)

    def test_slice_rotation_and_translation_preserve_geometry(self):
        angle=.71
        q=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
        shift=np.array([.3,-.1,.2])
        fs=tuple(replace(f,points_mm=f.points_mm@q.T+shift) for f in self.scene.fibers)
        s=OpticalScene(self.scene.materials,fs)
        sec=extract_bundle_section(s,shift,q@np.array([0,0,1]))
        self.assertTrue(sec.eligible)
        self.assertAlmostEqual(np.linalg.norm(sec.centers_mm[1]-sec.centers_mm[0]),.03,places=13)

    def test_medium_wavelength_and_heterogeneous_material_mapping(self):
        mats=(material("a",1.6,2),material("b",1.8,7))
        fs=(fiber("a",center=(-.015,0,0)),fiber("b",center=(.015,0,0),material_id="b"))
        s=OpticalScene(mats,fs,background_n=1.2)
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        w=wave_inputs(section,s,600); r=ray_inputs(section,s,600)
        self.assertAlmostEqual(w["wavelength_um"],.5)
        assert_allclose(w["radius_um"],4.)
        assert_allclose(w["n_complex"].real,[1.6/1.2,1.8/1.2])
        assert_allclose(r["n_fiber"],[1.6,1.8])
        assert_allclose(r["absorption_um_inv"],[.002,.007])
        self.assertEqual(r["n_host"],1.2)


class MicrostructureTests(unittest.TestCase):
    def test_orthogonal_equal_volume_tensor_and_rotation_covariance(self):
        fs=tuple(fiber(str(i),direction=d) for i,d in enumerate(np.eye(3)))
        s=OpticalScene((material(),),fs)
        stats=microstructure_statistics(s)["groups"]["all"]
        assert_allclose(stats["orientation_volume"],np.eye(3)/3,atol=1e-15)
        assert_allclose(stats["orientation_length"],np.eye(3)/3,atol=1e-15)
        angle=.7
        q=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        fs2=(fiber("a",direction=(1,0,0),radius=.003),fiber("b",direction=(0,1,0),radius=.006))
        s2=OpticalScene((material(),),fs2)
        c=np.array(microstructure_statistics(s2)["groups"]["all"]["orientation_volume"])
        rotated=OpticalScene(s2.materials,tuple(replace(f,points_mm=f.points_mm@q.T) for f in fs2))
        cr=np.array(microstructure_statistics(rotated)["groups"]["all"]["orientation_volume"])
        assert_allclose(cr,q@c@q.T,atol=1e-14)
        assert_allclose(np.diag(c),[.2,.8,0],atol=1e-15)

    def test_projected_lateral_area_matches_independent_spherical_integral(self):
        # A circular cylinder's lateral area projected orthogonally is 2*r*L*sin(theta).
        # Isotropic average sin(theta) is pi/4; this is a known geometry integral.
        z,w=np.polynomial.legendre.leggauss(256)
        directions=np.column_stack((np.sqrt(1-z*z),np.zeros_like(z),z))
        s=OpticalScene((material(),),(fiber(length=.4,radius=.004),))
        result=microstructure_statistics(s,directions)["groups"]["all"]
        projected=np.asarray(result["unoccluded_lateral_projected_area_mm2"])
        mean=float(.5*np.dot(w,projected))
        self.assertAlmostEqual(mean,np.pi*.004*.4/2,delta=2e-10)
        axes=microstructure_statistics(s)["groups"]["all"]["unoccluded_lateral_projected_area_mm2"]
        assert_allclose(axes,[2*.004*.4,2*.004*.4,0],atol=1e-15)


class ActualBridgeIntegrationTests(unittest.TestCase):
    def test_v2_hierarchy_keeps_materials_parents_and_real_solver_geometry(self):
        from textile_sim.hierarchy import YarnSpec, hex_ply, build_yarn
        yarn=YarnSpec("blend",(hex_ply(rings=1,spacing_mm=.012,radius_mm=.003,
            fiber_twist_per_mm=0,material_ids=("a","b")),))
        z=np.linspace(-.1,.1,41)
        geometry=build_yarn(yarn,np.column_stack((0*z,0*z,z)))
        scene=from_hierarchy(geometry,(material("a",1.5),material("b",1.62)))
        self.assertEqual(len(scene.fibers),7)
        self.assertEqual(tuple(f.fiber_id for f in scene.fibers),
                         tuple(f.fiber_id for f in geometry.fiber_records))
        self.assertEqual(tuple(f.material_id for f in scene.fibers),
                         tuple(f.material_id for f in geometry.fiber_records))
        section=extract_bundle_section(scene,[0,0,0],[0,0,1])
        self.assertTrue(section.eligible)
        self.assertEqual(len(np.unique(wave_inputs(section,scene,550)["n_complex"])),2)
        with tempfile.TemporaryDirectory() as d:
            export=export_mitsuba(scene,d,550,max_smoothing_error_mm=1e-12)
            self.assertEqual(len(export["groups"]),2)
            self.assertEqual(sum(g["fiber_count"] for g in export["groups"]),7)

    def test_existing_wave_and_ray_solvers_receive_a_passive_heterogeneous_bundle(self):
        from textile_sim.fiber_wave import cluster_scattering
        from textile_sim.ply_ray import trace_bundle
        mats=(material("a",1.5,3),material("b",1.6,5))
        fs=(fiber("a",center=(-.0015,0,0),radius=.001),
            fiber("b",center=(.0015,0,0),radius=.001,material_id="b"))
        s=OpticalScene(mats,fs)
        section=extract_bundle_section(s,[0,0,0],[0,0,1])
        wave=cluster_scattering(**wave_inputs(section,s,550),polarization="Ez",theta=np.linspace(-np.pi,np.pi,180))
        self.assertGreater(wave["Cabs"],0)
        self.assertLess(wave["relative_energy_flux_residual"],1e-10)
        ray=trace_bundle(**ray_inputs(section,s,550),n_rays=4000,seed=708)
        self.assertGreater(ray["energy"]["absorbed"],0)
        self.assertAlmostEqual(sum(ray["energy"].values()),1.,places=12)

    def test_actual_mitsuba_multigroup_render_and_export_hash_guard(self):
        from textile_sim.render import RenderConfig
        mats=(material("a",1.5,0),material("b",1.6,8))
        fs=(fiber("a",center=(-.06,0,0),direction=(0,1,0),radius=.02),
            fiber("b",center=(.06,0,0),direction=(0,1,0),radius=.025,material_id="b"))
        scene=OpticalScene(mats,fs)
        with tempfile.TemporaryDirectory() as d:
            export=export_mitsuba(scene,d,550,max_smoothing_error_mm=0)
            image,info=render_optical_scene(d,RenderConfig(resolution=24,spp=16,mode="furnace"))
            self.assertEqual(image.shape,(24,24,3))
            self.assertEqual(info["group_count"],2)
            self.assertEqual(info["mitsuba_version"],"3.9.1")
            self.assertTrue(np.isfinite(image).all())
            self.assertGreater(image.mean(),.2)
            self.assertLess(image.mean(),1.2)
            p=Path(d)/export["groups"][0]["filename"]
            p.write_text(p.read_text()+"\n")
            with self.assertRaises(ValueError): mitsuba_scene_dictionary(d,RenderConfig())


if __name__ == "__main__":
    unittest.main()
