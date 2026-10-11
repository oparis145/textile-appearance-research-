"""Analytic and conservation checks, independent of textile visual judgement."""
import unittest
import numpy as np

from textile_sim.aperture_wave import (fraunhofer, blur_incoherent,
    incoherent_average, woven_gap_mask, angular_mass_within, DiffractionResult)


class AperturePhysicsTests(unittest.TestCase):
    def test_parseval_complex_mask_and_padding(self):
        rng=np.random.default_rng(2718)
        mask=(rng.random((27,31))+.2j*rng.random((27,31)))
        expected=np.mean(abs(mask)**2)
        for pad in (1,2,4):
            r=fraunhofer(mask,(.8,1.3),.55,pad)
            self.assertAlmostEqual(r.total_power,expected,places=13)
            self.assertLess(r.diagnostics["parseval_abs_error"],1e-13)

    def test_closed_and_open_masks(self):
        self.assertEqual(fraunhofer(np.zeros((32,32)),1).total_power,0)
        r=fraunhofer(np.ones((32,32)),1,pad_factor=1)
        self.assertAlmostEqual(r.total_power,1,places=14)
        self.assertAlmostEqual(r.power[16,16],1,places=14)
        self.assertAlmostEqual(fraunhofer(np.ones((32,32)),1,pad_factor=4).total_power,1,places=14)

    def test_rectangular_slit_first_zero(self):
        mask=np.zeros((16,128)); mask[:,48:80]=1
        r=fraunhofer(mask,1,.55,8)
        p=r.power.sum(axis=0); zero=.55/32
        k=np.argmin(abs(r.theta_x_rad-zero))
        self.assertAlmostEqual(r.theta_x_rad[k],zero,places=14)
        self.assertLess(p[k]/p.max(),1e-25)

    def test_continuum_sinc_under_pixel_refinement(self):
        errors=[]
        # Same 256um illumination window,32um physical slit, constant angular bin.
        for dx in (2.,1.,.5):
            n=int(256/dx); w=int(32/dx)
            a=np.zeros((8,n));a[:,n//2-w//2:n//2+w//2]=1
            r=fraunhofer(a,(1,dx),.55,2)
            p=r.power.sum(axis=0); k=r.theta_x_rad.size//2+10
            actual=p[k]/p.max(); analytic=np.sinc(32*10/512)**2
            errors.append(abs(actual-analytic))
        self.assertLess(errors[1],errors[0]*.3)
        self.assertLess(errors[2],errors[1]*.3)
        self.assertLess(errors[2],1e-4)

    def test_padding_only_refines_angles(self):
        a=np.zeros((16,128));a[:,48:80]=1
        coarse=fraunhofer(a,1,.55,2)
        fine=fraunhofer(a,1,.55,8)
        # Native angular density at common bins has identical field values.
        xidx=np.arange(coarse.power.shape[1])*4
        yidx=np.arange(coarse.power.shape[0])*4
        self.assertTrue(np.allclose(coarse.angular_density,
            fine.angular_density[np.ix_(yidx,xidx)],rtol=2e-12,atol=2e-12))

    def test_incoherent_average_does_not_cancel_opposite_fields(self):
        a=woven_gap_mask((64,64),2,64,24)
        r1=fraunhofer(a,2,.55,2);r2=fraunhofer(-a,2,.55,2)
        avg=incoherent_average([r1,r2],[.5,.5],r1.theta_x_rad,r1.theta_y_rad)
        self.assertTrue(np.allclose(avg.power,r1.power,atol=1e-15))
        self.assertGreater(avg.total_power,0)

    def test_spectral_rebin_preserves_weighted_power(self):
        a=woven_gap_mask((48,64),2,64,24)
        rs=[fraunhofer(a*s,2,wl,2) for s,wl in ((1,.45),(.7,.55),(.4,.65))]
        weights=np.array([.2,.3,.5]);avg=incoherent_average(rs,weights)
        self.assertAlmostEqual(avg.total_power,sum(w*r.total_power for w,r in zip(weights,rs)),places=12)
        self.assertTrue(np.all(avg.power>=0))

    def test_incoherent_gaussian_adds_angular_variance(self):
        x=np.linspace(-.1,.1,401);p=np.zeros((401,401));p[200,200]=.4
        r=DiffractionResult(x,x,p,.4,{"lost_power":0})
        b=blur_incoherent(r,source_sigma_deg=.2,detector_sigma_deg=.3)
        variance=(b.power*x[None,:]**2).sum()/b.total_power
        expected=np.deg2rad(np.hypot(.2,.3))**2
        self.assertLess(abs(variance/expected-1),2e-6)
        self.assertAlmostEqual(b.total_power,.4,places=12)
        self.assertTrue(np.all(b.power>=0))

    def test_boundary_and_na_loss_are_accounted(self):
        x=np.linspace(-.01,.01,81);p=np.zeros((81,81));p[40,40]=.7
        r=DiffractionResult(x,x,p,.7,{"lost_power":0})
        b=blur_incoherent(r,source_sigma_deg=1,na=.005)
        self.assertAlmostEqual(b.total_power+b.diagnostics["angular_window_loss"]+
             b.diagnostics["na_rejected_power"],.7,places=12)
        self.assertGreater(b.diagnostics["angular_window_loss"],0)
        self.assertGreater(b.diagnostics["na_rejected_power"],0)

    def test_na_does_not_add_gap_transmission(self):
        a=woven_gap_mask((128,128),2,64,16)
        r=fraunhofer(a,2,.55,2)
        small=blur_incoherent(r,na=.005);large=blur_incoherent(r,na=.03)
        self.assertLessEqual(small.total_power,large.total_power)
        self.assertLessEqual(large.total_power,a.mean()+1e-14)

    def test_gap_projection_limits_and_disorder_repeatability(self):
        self.assertEqual(woven_gap_mask((64,64),2,64,0).sum(),0)
        self.assertEqual(woven_gap_mask((64,64),2,64,64).mean(),1)
        a=woven_gap_mask(jitter_fraction=.1,seed=3)
        self.assertTrue(np.array_equal(a,woven_gap_mask(jitter_fraction=.1,seed=3)))
        self.assertFalse(np.array_equal(a,woven_gap_mask(jitter_fraction=.1,seed=4)))

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):fraunhofer(np.ones((8,8)),0)
        with self.assertRaises(ValueError):fraunhofer(np.ones((8,8)),1,pad_factor=1.5)
        r=fraunhofer(np.ones((8,8)),1)
        with self.assertRaises(ValueError):blur_incoherent(r,-1)
        with self.assertRaises(ValueError):incoherent_average([r],[-1])

    def test_gaussian_beam_aperture_fraction_against_erf(self):
        from scipy.special import erf
        dx=.2;n=512;x=(np.arange(n)-n/2+.5)*dx;waist=10.
        beam=np.exp(-(x[:,None]**2+x[None,:]**2)/waist**2)
        mask=np.outer(abs(x)<7.5,abs(x)<7.5)
        # Actual half width is7.6um on this grid; compare pixel edge integral.
        half=.5*mask.any(axis=0).sum()*dx
        r=fraunhofer(mask,dx,.55,2,incident_field=beam)
        expected=erf(np.sqrt(2)*half/waist)**2
        self.assertLess(abs(r.total_power-expected),5e-5)
        self.assertAlmostEqual(r.total_power,r.input_transmission,places=13)

    def test_incident_field_scale_does_not_change_fraction(self):
        x=np.linspace(-1,1,64);beam=np.exp(-4*(x[:,None]**2+x[None,:]**2))
        a=np.ones((64,64));a[:32]=0
        r=fraunhofer(a,.5,incident_field=beam)
        s=fraunhofer(a,.5,incident_field=beam*7j)
        self.assertTrue(np.allclose(r.power,s.power,atol=1e-15))
        self.assertAlmostEqual(r.total_power,.5,places=12)

    def test_circular_acceptance_partial_bins(self):
        x=np.linspace(-.03,.03,121);dx=x[1]-x[0]
        r=DiffractionResult(x,x,np.ones((121,121))*dx*dx,1.,{})
        radius=.0131
        actual=angular_mass_within(r,np.rad2deg(radius),20)
        self.assertLess(abs(actual/(np.pi*radius**2)-1),1e-4)


if __name__=="__main__":unittest.main()
