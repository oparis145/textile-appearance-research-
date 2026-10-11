"""Independent source normalization and coherent illumination tests."""
import unittest
import numpy as np

from textile_sim.fiber_wave import cylinder_scattering,cluster_scattering
from textile_sim.fiber_wave_beam import (gaussian_spectrum,incident_field,
                                        incident_line_flux,ClusterOperator,beam_scattering)


class GaussianSourceTests(unittest.TestCase):
    def test_waist_profile_and_two_plane_power_conservation(self):
        source=gaussian_spectrum(.55,10,offset_um=3,n_quad=64)
        y=np.linspace(-37,43,801)
        u,_,_=incident_field(source,np.zeros_like(y),y)
        np.testing.assert_allclose(u,np.exp(-(y-3)**2/100),atol=2e-13,rtol=2e-13)
        for x in (-40,0,40):
            line=incident_line_flux(source,x)
            self.assertLess(abs(line["relative_power_error"]),2e-11)

    def test_source_quadrature_can_fail_without_energy_renormalization(self):
        low=incident_line_flux(gaussian_spectrum(.55,10,n_quad=24),-40)
        high=incident_line_flux(gaussian_spectrum(.55,10,n_quad=64),-40)
        # Discrete plane-wave quadrature aliases at large transverse distances.
        # Retain and detect this; never use its spurious global norm as power.
        self.assertGreater(abs(low["relative_power_error"]),.01)
        self.assertLess(abs(high["relative_power_error"]),2e-11)

    def test_flux_norm_and_paraxial_limit(self):
        source=gaussian_spectrum(.55,10,n_quad=64)
        ratio=source["incident_power_um"]/source["paraxial_incident_power_um"]
        asymptote=1-1/(2*(source["k"]*10)**2)
        self.assertLess(ratio,1)
        self.assertLess(abs(ratio-asymptote),1e-8)
        self.assertGreater(source["incident_power_um"],0)

    def test_invalid_source_rejected(self):
        for kwargs in ({"wavelength_um":0},{"waist_um":.1},{"n_quad":4},{"offset_um":np.nan}):
            with self.assertRaises(ValueError):gaussian_spectrum(**kwargs)


class GaussianScatteringTests(unittest.TestCase):
    positions=np.array([[0.,0.],[1.,0.],[.5,.8660254]])
    theta=np.linspace(-np.pi,np.pi,360,endpoint=False)

    def test_arbitrary_illumination_operator_plane_wave_reduction(self):
        for pol in ("Ez","Hz"):
            op=ClusterOperator(self.positions,.35,.55,1.53+.02j,pol,n_terms=24)
            solution=op.solve(op.plane_coefficients(.23))
            ref=cluster_scattering(self.positions,.35,.55,1.53+.02j,pol,self.theta,n_terms=24,incident_angle=.23)
            np.testing.assert_allclose(op.far_field(solution,self.theta),ref["far_field"],rtol=2e-11,atol=2e-11)
            self.assertLess(abs(solution["extinction_interference_um"]-ref["Cext"]),1e-10)

    def test_single_cylinder_against_coherent_sum_of_exact_plane_wave_solutions(self):
        source=gaussian_spectrum(.55,3,offset_um=.2,waist_x_um=.5,n_quad=24)
        for pol in ("Ez","Hz"):
            op=ClusterOperator([[0,0]],.35,.55,1.53,pol,n_terms=24)
            result=beam_scattering(op,source,self.theta)
            expected=np.zeros(len(self.theta),complex)
            for alpha,q,kx,w in zip(source["alpha"],source["q"],source["kx"],source["weights"]):
                exact=cylinder_scattering(.35,.55,1.53,pol,self.theta,n_terms=24,incident_angle=alpha)
                expected+=w*np.exp(-1j*(q*.2+kx*.5))*exact["far_field"]
            np.testing.assert_allclose(result["far_field"],expected,rtol=2e-11,atol=2e-11)

    def test_index_matched_gaussian_has_no_scattering(self):
        source=gaussian_spectrum(.55,3,n_quad=64)
        op=ClusterOperator(self.positions,.35,.55,1.,"Ez",n_terms=24)
        result=beam_scattering(op,source,self.theta)
        self.assertEqual(result["R"],0)
        self.assertEqual(result["A"],0)
        self.assertEqual(result["T"],1)
        np.testing.assert_array_equal(result["far_field"],0)
        # Incident normalization is independently checked by a field integral.
        line=incident_line_flux(source,-5)
        self.assertLess(abs(line["relative_power_error"]),1e-9)

    def test_lossless_and_absorbing_flux_bounds(self):
        for index in (1.53,1.53+.02j):
            for pol in ("Ez","Hz"):
                op=ClusterOperator(self.positions,.35,.55,index,pol,n_terms=24)
                result=beam_scattering(op,gaussian_spectrum(.55,3,n_quad=64),self.theta)
                self.assertLess(result["relative_global_local_flux_error"],2e-10)
                self.assertGreater(result["R"],0)
                self.assertGreater(result["T"],0)
                self.assertLess(result["R"],1)
                self.assertGreater(result["A"],-1e-10)
                if index==1.53:self.assertLess(abs(result["A"]),1e-10)
                else:self.assertGreater(result["A"],0)

    def test_translation_of_beam_and_object_preserves_power(self):
        shift=np.array([.71,-.43])
        aop=ClusterOperator(self.positions,.35,.55,1.53,"Ez",n_terms=24)
        bop=ClusterOperator(self.positions+shift,.35,.55,1.53,"Ez",n_terms=24)
        a=beam_scattering(aop,gaussian_spectrum(.55,3,n_quad=64),self.theta)
        b=beam_scattering(bop,gaussian_spectrum(.55,3,offset_um=shift[1],waist_x_um=shift[0],n_quad=64),self.theta)
        phase=np.exp(-1j*(2*np.pi/.55)*(np.column_stack((np.cos(self.theta),np.sin(self.theta)))@shift))
        np.testing.assert_allclose(b["far_field"],a["far_field"]*phase,rtol=1e-10,atol=1e-10)
        self.assertLess(abs(a["R"]-b["R"]),1e-11)

    def test_source_and_backward_angular_quadrature_convergence(self):
        op=ClusterOperator(self.positions,.35,.55,1.53,"Ez",n_terms=24)
        a=beam_scattering(op,gaussian_spectrum(.55,3,n_quad=32),self.theta,angular_quad=128)
        b=beam_scattering(op,gaussian_spectrum(.55,3,n_quad=64),self.theta,angular_quad=256)
        self.assertLess(np.linalg.norm(a["far_field"]-b["far_field"])/np.linalg.norm(b["far_field"]),1e-9)
        self.assertLess(abs(a["R"]-b["R"]),1e-10)


if __name__=="__main__":unittest.main()
