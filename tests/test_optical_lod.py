"""Analytical optics checks independent of example output values."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
import numpy as np
from numpy.testing import assert_allclose

from textile_sim.optical_scene import MaterialSpectrum,OpticalScene,OpticalFiber
from textile_sim.optical_lod import (SGGXProjection,projected_area_density,
    sphere_quadrature,fibonacci_directions,fit_sggx_projected_area,
    trapezoid_weights,load_cie1931,planck_relative,spectral_xyz_weights,
    integrate_xyz,xyz_to_linear_srgb,paired_mean_interval)


def simple_scene():
    material=MaterialSpectrum.from_absorption("synthetic",(360,830),1.55,3.,"unit test synthetic")
    f=OpticalFiber("f","y","p","synthetic",np.array([[0.,0.,-1.],[0.,0.,1.]]),.01,family="warp")
    return OpticalScene((material,),(f,))


class ProjectionTests(unittest.TestCase):
    def test_single_cylinder_analytical_angular_area(self):
        d=np.array([[1,0,0],[0,0,1],[1,0,1]],float)
        result=projected_area_density(simple_scene(),d,2.)["all"]
        assert_allclose(result,[.02,0,.02/np.sqrt(2)],atol=1e-14)

    def test_partition_additivity_with_common_volume(self):
        s=simple_scene(); f=s.fibers[0]
        g=replace(f,fiber_id="g",yarn_id="z",ply_id="q",family="weft",points_mm=f.points_mm[:,[2,1,0]])
        s=OpticalScene(s.materials,(f,g))
        d=fibonacci_directions(42)
        total=projected_area_density(s,d,.7)["all"]
        for level in ("family","yarn","ply","material"):
            assert_allclose(sum(projected_area_density(s,d,.7,group_by=level).values()),total,atol=1e-14)

    def test_projection_rigid_rotation_covariance(self):
        s=simple_scene(); d=fibonacci_directions(60)
        q,_=np.linalg.qr(np.random.default_rng(782).normal(size=(3,3)))
        rotated=OpticalScene(s.materials,tuple(replace(f,points_mm=f.points_mm@q.T) for f in s.fibers))
        assert_allclose(projected_area_density(rotated,d@q.T,2.)["all"],
                        projected_area_density(s,d,2.)["all"],atol=2e-14)

    def test_line_refinement_invariant(self):
        s=simple_scene(); f=s.fibers[0]
        r=replace(f,points_mm=np.column_stack((np.zeros(100),np.zeros(100),np.linspace(-1,1,100))))
        d=fibonacci_directions(27)
        assert_allclose(projected_area_density(OpticalScene(s.materials,(r,)),d,1.)["all"],
                        projected_area_density(s,d,1.)["all"],rtol=1e-13)

    def test_length_similarity_density_inverse_scale(self):
        s=simple_scene(); scale=3.4
        large=OpticalScene(s.materials,tuple(replace(f,points_mm=f.points_mm*scale,radius_mm=f.radius_mm*scale) for f in s.fibers))
        d=fibonacci_directions(33)
        assert_allclose(projected_area_density(large,d,scale**3)["all"],
                        projected_area_density(s,d,1.)["all"]/scale,rtol=1e-13)

    def test_invalid_geometry_and_inputs_rejected(self):
        for d,v in (([[0,0,0]],1.),([[1,0,0]],0.),([[np.nan,0,0]],1.)):
            with self.assertRaises(ValueError): projected_area_density(simple_scene(),d,v)
        with self.assertRaises(ValueError): projected_area_density(simple_scene(),np.eye(3),1.,group_by="bsdf")
        s=simple_scene(); f=replace(s.fibers[0],cross_section="ellipse")
        with self.assertRaises(ValueError): projected_area_density(OpticalScene(s.materials,(f,)),np.eye(3),1.)


class SGGXTests(unittest.TestCase):
    def test_isotropic_normal_and_phase_normalization(self):
        m=SGGXProjection(np.eye(3)*9.)
        d,w=sphere_quadrature(40,80)
        assert_allclose(m.projected_area(d),3.,atol=1e-14)
        assert_allclose(m.normal_density(d),3./np.pi,atol=1e-14)
        self.assertAlmostEqual(float(w@m.normal_density(d)),12.,places=12) # D is not a probability density.
        self.assertAlmostEqual(float(w@m.specular_phase([0,0,1],d)),1.,places=12)

    def test_visible_and_phase_normalization_anisotropic(self):
        s=np.array([[1.4,.15,.05],[.15,.9,-.08],[.05,-.08,.45]])
        m=SGGXProjection(s); d,w=sphere_quadrature(120,240)
        for i in ([0,0,1],[.5,.3,.8]):
            self.assertAlmostEqual(float(w@m.visible_normal_density(i,d)),1.,delta=2e-4)
            self.assertAlmostEqual(float(w@m.specular_phase(i,d)),1.,delta=2e-4)

    def test_reciprocity_requires_directional_extinction_weight(self):
        m=SGGXProjection(np.diag([.3,1.,2.5]))
        i=np.array([1.,2.,3.]); i/=np.linalg.norm(i)
        o=fibonacci_directions(30)
        left=m.projected_area(i[None])[0]*m.specular_phase(i,o)
        right=np.array([m.projected_area(x[None])[0]*m.specular_phase(x,i[None])[0] for x in o])
        assert_allclose(left,right,rtol=1e-13,atol=1e-14)

    def test_exact_spd_target_fit_and_rotated_recovery(self):
        truth=np.array([[2.,.3,-.1],[.3,.8,.08],[-.1,.08,.5]])
        d=fibonacci_directions(160); target=SGGXProjection(truth).projected_area(d)
        fit,diag=fit_sggx_projected_area(d,target)
        assert_allclose(fit.matrix,truth,rtol=2e-7,atol=1e-8)
        self.assertLess(diag["training_relative_rmse"],1e-8)
        q,_=np.linalg.qr(np.random.default_rng(3).normal(size=(3,3)))
        rotated,_=fit_sggx_projected_area(d@q.T,target)
        assert_allclose(rotated.matrix,q@truth@q.T,rtol=2e-7,atol=1e-8)

    def test_phase_invariant_to_density_scale(self):
        a=SGGXProjection(np.diag([.3,.6,1.2])); b=SGGXProjection(a.matrix*16.)
        d=fibonacci_directions(50)
        assert_allclose(b.projected_area(d),4*a.projected_area(d),rtol=1e-13)
        assert_allclose(b.specular_phase([0,0,1],d),a.specular_phase([0,0,1],d),rtol=1e-13)

    def test_bad_spd_and_mutation_rejected(self):
        for s in (np.diag([1,1,0]),np.diag([1,1,-1]),np.ones((2,2)),np.array([[1,1,0],[0,1,0],[0,0,1]])):
            with self.assertRaises(ValueError): SGGXProjection(s)
        s=SGGXProjection(np.eye(3))
        with self.assertRaises(ValueError): s.matrix.setflags(write=True)
        with self.assertRaises(ValueError): fit_sggx_projected_area(np.eye(3),[0,0,0])


class SpectralTests(unittest.TestCase):
    def test_cie_original_checksum_and_reference_row(self):
        l,c=load_cie1931()
        self.assertEqual(c.shape,(471,3))
        assert_allclose(c[l==479][0],[.1042979,.1334528,.8566193],atol=1e-12)
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/"tampered.csv"; f.write_text("1,2,3,4")
            with self.assertRaises(ValueError): load_cie1931(f)

    def test_trapezoid_exact_constant_and_linear(self):
        x=np.array([1.,1.3,2.1,5.]); w=trapezoid_weights(x)
        self.assertAlmostEqual(w.sum(),4.)
        self.assertAlmostEqual(w@x,(25-1)/2)
        for y in ([1],[1,1],[2,1],[1,np.inf]):
            with self.assertRaises(ValueError): trapezoid_weights(y)

    def test_spectral_constant_response_and_linear_response_independent_knots(self):
        o,c=load_cie1931(); e=planck_relative(o,3000.)
        l=np.linspace(380,780,9); dense=np.linspace(380,780,41)
        w,info=spectral_xyz_weights(l,o,c,e); v,_=spectral_xyz_weights(dense,o,c,e)
        self.assertAlmostEqual(w[:,1].sum(),1.,places=13)
        response=lambda x:.2+.0005*(x-380)
        assert_allclose(response(l)@w,response(dense)@v,rtol=2e-14,atol=2e-14)
        assert_allclose(integrate_xyz(np.ones((4,len(l))),w),np.tile(info["white_xyz"],(4,1)),atol=1e-14)

    def test_broad_spectrum_quadrature_convergence(self):
        o,c=load_cie1931(); e=planck_relative(o,6500.)
        dense=np.arange(380,781); wd,_=spectral_xyz_weights(dense,o,c,e)
        response=lambda x:.12+.7*np.exp(-((x-535)/65)**2)
        truth=response(dense)@wd
        errors=[]
        for n in (9,17,33):
            l=np.linspace(380,780,n); w,_=spectral_xyz_weights(l,o,c,e)
            errors.append(np.linalg.norm(response(l)@w-truth))
        self.assertTrue(errors[2]<errors[1]<errors[0])
        self.assertLess(errors[2]/errors[0],.08)

    def test_planck_law_peak_and_temperature(self):
        l=np.arange(200.,3000.,1.)
        p=planck_relative(l,3000.)
        self.assertLess(abs(l[p.argmax()]-2.897771955e6/3000.),1.)
        for temp in (0,-1,np.inf):
            with self.assertRaises(ValueError): planck_relative(l,temp)
        self.assertTrue(np.isfinite(planck_relative([360,830],1.)).all())

    def test_xyz_d65_white_and_linear_superposition(self):
        white=np.array([.95047,1.,1.08883])
        assert_allclose(xyz_to_linear_srgb(white),np.ones(3),atol=2e-7)
        a=np.array([.1,.2,.3]);b=np.array([.2,.1,.05])
        assert_allclose(xyz_to_linear_srgb(a+b),xyz_to_linear_srgb(a)+xyz_to_linear_srgb(b),atol=1e-15)

    def test_paired_seed_confidence_uses_replicates(self):
        before=np.array([1.,8.,4.,3.]);after=before+.2
        m=paired_mean_interval(before,after)
        self.assertAlmostEqual(m["mean_delta"],.2)
        self.assertLess(m["standard_error"],1e-15)
        self.assertEqual(m["paired_count"],4)
        with self.assertRaises(ValueError): paired_mean_interval([1],[2])


class RendererWavelengthTransferTests(unittest.TestCase):
    def test_parameter_sweep_matches_fresh_wavelength_export(self):
        from textile_sim.optical_scene import export_mitsuba,mitsuba_scene_dictionary
        from textile_sim.render import RenderConfig,get_mitsuba
        from run_multiscale_optics_v3 import _set_wavelength
        mi=get_mitsuba()
        s=simple_scene()
        material=MaterialSpectrum.from_absorption("synthetic",(360,830),(1.48,1.68),(30,90),"synthetic transfer test")
        f=replace(s.fibers[0],points_mm=s.fibers[0].points_mm[:,[2,1,0]])
        s=OpticalScene((material,),(f,))
        c=RenderConfig(resolution=16,spp=8,light_azimuth_deg=30,light_elevation_deg=60)
        with tempfile.TemporaryDirectory() as p:
            base=Path(p)/"base";target=Path(p)/"target"
            manifest=export_mitsuba(s,base,380,max_smoothing_error_mm=0)
            export_mitsuba(s,target,610,max_smoothing_error_mm=0)
            updated=mi.load_dict(mitsuba_scene_dictionary(base,c))
            _set_wavelength(mi.traverse(updated),mi,manifest,s.material_map,610,s.background_n)
            fresh=mi.load_dict(mitsuba_scene_dictionary(target,c))
            a=np.asarray(mi.render(updated,seed=71,spp=8));b=np.asarray(mi.render(fresh,seed=71,spp=8))
            assert_allclose(a,b,rtol=2e-6,atol=1e-8)


if __name__=="__main__":
    unittest.main()
