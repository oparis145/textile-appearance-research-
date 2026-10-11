import unittest
import numpy as np
from textile_sim.camera import *


class CameraTests(unittest.TestCase):
    def test_mtf_analytic_values(self):
        fc=2*.04/.55
        np.testing.assert_allclose(circular_incoherent_mtf([0,fc,2*fc]),[1,0,0],atol=1e-14)
        self.assertAlmostEqual(float(circular_incoherent_mtf(.5*fc)),
            2/np.pi*(np.pi/3-.5*np.sqrt(.75)),places=14)

    def test_sinusoid_transfer_matches_mtf(self):
        n=256;k=11;pixel=.5
        x=np.arange(n)
        a=1+.5*np.cos(2*np.pi*k*x/n)[None,:]*np.ones((n,1))
        b=optical_filter(a,pixel,pad=0)
        amp=2*np.mean((b-1)*np.cos(2*np.pi*k*x/n)[None,:])
        self.assertAlmostEqual(amp,.5*float(circular_incoherent_mtf(k/(n*pixel))),places=12)

    def test_pixel_energy(self):
        a=np.random.default_rng(1).random((64,64,3))
        for b in [1,2,4,8]:
            v=integrate_pixels(a,b)
            np.testing.assert_allclose(v.sum(axis=(0,1))*b*b,a.sum(axis=(0,1)),rtol=1e-13)

    def test_flat_field_and_equal_exposure_photons(self):
        a=np.ones((64,64))*.3
        totals=[]
        for b in [1,2,4]:
            r=observe(a,1.,CameraConfig(binning=b),add_noise=False)
            np.testing.assert_allclose(r['image'],.3,atol=1e-12)
            totals.append(r['expected_electrons'].sum())
        np.testing.assert_allclose(totals,totals[0],rtol=1e-13)

    def test_shot_read_variance(self):
        r=observe(np.full((512,512),.4),1.,CameraConfig(electrons_per_um2_unit_radiance=50),True)
        observed=np.var(r['image']-.4)
        predicted=float(np.mean(r['radiance_noise_variance']))
        self.assertLess(abs(observed/predicted-1),.012)
        self.assertLess(abs(r['image'].mean()-.4),.001)

    def test_deterministic_seed(self):
        a=np.ones((64,64))
        np.testing.assert_array_equal(observe(a,1,CameraConfig())['image'],observe(a,1,CameraConfig())['image'])


if __name__=='__main__': unittest.main()
