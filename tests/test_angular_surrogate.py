import unittest

import numpy as np

from textile_sim.angular_surrogate import (VonMisesMixture, fit_von_mises_mixture,
                                          compress_trace_result, jensen_shannon)
from textile_sim.ply_ray import trace_bundle


class CircularMixtureTests(unittest.TestCase):
    def test_positivity_periodicity_and_continuous_normalization(self):
        model=VonMisesMixture([.25,.75],[-2.7,1.4],[0,80])
        theta=np.linspace(-np.pi,np.pi,32768,endpoint=False)
        density=model.density(theta)
        self.assertGreater(float(np.min(density)),0)
        self.assertAlmostEqual(float(np.mean(density)*2*np.pi),1,places=12)
        np.testing.assert_allclose(model.density(theta+2*np.pi),density,rtol=3e-12,atol=1e-13)
        edges=np.linspace(-np.pi,np.pi,361)
        p=model.bin_probabilities(edges)
        self.assertGreaterEqual(float(np.min(p)),-1e-14)
        self.assertAlmostEqual(float(p.sum()),1,places=12)
        self.assertAlmostEqual(float(model.interval_probability(1,1+2*np.pi)),1,places=12)

    def test_known_two_lobe_recovery_and_em_likelihood(self):
        reference=VonMisesMixture([.6,.4],[-.7,1.9],[10,4])
        theta=np.linspace(-np.pi,np.pi,720,endpoint=False)
        weights=reference.density(theta)
        model,record=fit_von_mises_mixture(theta,weights,2,seed=31,max_iterations=400)
        l1=np.mean(abs(reference.density(theta)-model.density(theta)))*2*np.pi
        self.assertLess(l1,3e-4)
        self.assertGreaterEqual(float(np.min(np.diff(record['training_log_likelihood_history']))),-1e-10)

    def test_zero_scattering_forward_delta_is_not_blurred(self):
        traced=trace_bundle([[0,0]],[5],n_fiber=1,n_rays=2000,beam_width_um=20,seed=74,return_rays=True)
        model,_=compress_trace_result(traced,4)
        self.assertIsNone(model.mixture)
        self.assertEqual(model.continuous_mass,0)
        self.assertAlmostEqual(model.uncollided_forward+model.encountered_forward_delta,1)
        p=model.bin_probabilities(np.linspace(-np.pi,np.pi,361))
        self.assertEqual(np.count_nonzero(p),1)
        self.assertAlmostEqual(p.sum(),1)

    def test_absorbed_power_and_uncollided_delta_are_preserved(self):
        traced=trace_bundle([[0,0]],[5],absorption_um_inv=.03,n_rays=6000,beam_width_um=20,seed=20,return_rays=True)
        model,_=compress_trace_result(traced,4,n_init=2,max_iterations=150)
        self.assertEqual(model.absorbed,traced['energy']['absorbed'])
        self.assertEqual(model.uncollided_forward,traced['energy']['uncollided_forward'])
        self.assertAlmostEqual(sum(model.energy().values()),1,places=12)
        p=model.bin_probabilities(np.linspace(-np.pi,np.pi,361))
        self.assertAlmostEqual(p.sum()+model.absorbed+model.residual,1,places=12)

    def test_js_bounds_and_invalid_input(self):
        self.assertEqual(jensen_shannon([.3,.7],[.3,.7]),0)
        self.assertAlmostEqual(jensen_shannon([1,0],[0,1]),np.log(2))
        with self.assertRaises(ValueError):jensen_shannon([.2,.2],[.5,.5])
        with self.assertRaises(ValueError):VonMisesMixture([-.2,1.2],[0,1],[1,1])


if __name__=='__main__':
    unittest.main()
