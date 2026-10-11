"""Physics and convergence tests for the exact two-dimensional wave modules.

Run from textile_lab: python -m unittest discover -s tests -p 'test_fiber_wave.py' -v
These are synthetic numerical consistency checks, not validation against a
physical fabric.  Relative tolerances are stated explicitly in each test.
"""
import unittest
import numpy as np
from scipy import special

from textile_sim.fiber_wave import (cylinder_scattering, cylinder_coefficients,
                                    cluster_scattering, cluster_field,
                                    incoherent_cylinder_average)


class CylinderWaveTests(unittest.TestCase):
    def test_index_matching_zero_scattering(self):
        for pol in ("Ez", "Hz"):
            q = cylinder_scattering(4.0, .55, 1.0, pol, theta=[0, .9, 2.8])
            self.assertEqual(q["Csca"], 0)
            self.assertEqual(q["Cext"], 0)
            np.testing.assert_array_equal(q["far_field"], 0)

    def test_lossless_optical_theorem_and_angular_integral(self):
        for x in (.01, .3, 1.0, 5, 50, 150):
            for pol in ("Ez", "Hz"):
                q = cylinder_scattering(x * .55 / (2 * np.pi), .55, 1.53, pol, theta=[0])
                self.assertLess(abs(q["Cext"] - q["Csca"]) / q["Csca"], 1e-10)
                self.assertLess(abs(q["Csca_angular"] - q["Csca"]) / q["Csca"], 2e-11)
                self.assertLess(q["boundary_value_residual"], 5e-12)
                self.assertLess(q["boundary_derivative_residual"], 5e-12)
                self.assertLess(np.max(np.abs(q["t"].real + np.abs(q["t"]) ** 2)), 1e-10)

    def test_absorption_positive_for_passive_index(self):
        for pol in ("Ez", "Hz"):
            for kappa in (.001, .03, .2):
                q = cylinder_scattering(1.1, .55, 1.53 + 1j * kappa, pol, theta=[0])
                self.assertGreater(q["Cabs"], 0)
                self.assertLessEqual(q["Csca"], q["Cext"])
                self.assertLessEqual(q["modal_passivity_residual"], 1e-12)

    def test_small_size_analytic_rayleigh_limit_both_polarizations(self):
        # Independent low-x asymptotes of the Maxwell boundary equations:
        # Qsca_Ez = pi^2/8 (n^2-1)^2 x^3;
        # Qsca_Hz = pi^2/4 [(n^2-1)/(n^2+1)]^2 x^3.
        x, lam, n = .002, .55, 1.53
        a = x * lam / (2 * np.pi)
        expected = {"Ez": np.pi ** 2 / 8 * (n*n - 1) ** 2 * x ** 3,
                    "Hz": np.pi ** 2 / 4 * ((n*n - 1)/(n*n + 1)) ** 2 * x ** 3}
        for pol in ("Ez", "Hz"):
            q = cylinder_scattering(a, lam, n, pol, theta=[0])
            self.assertLess(abs(q["Csca"] / (2*a) / expected[pol] - 1), 1e-4)

    def test_multipole_convergence_not_just_conservation(self):
        theta = np.linspace(-np.pi, np.pi, 1024, endpoint=False)
        ref = cylinder_scattering(5, .55, 1.53, "Ez", theta, n_terms=100)
        low = cylinder_scattering(5, .55, 1.53, "Ez", theta, n_terms=20)
        default = cylinder_scattering(5, .55, 1.53, "Ez", theta)
        self.assertGreater(np.linalg.norm(low["dCsca_dtheta"] - ref["dCsca_dtheta"]) / np.linalg.norm(ref["dCsca_dtheta"]), .1)
        self.assertLess(np.linalg.norm(default["dCsca_dtheta"] - ref["dCsca_dtheta"]) / np.linalg.norm(ref["dCsca_dtheta"]), 1e-10)

    def test_actual_boundary_fields_against_exact_plane_wave(self):
        # Unlike a coefficient residual, this test compares the retained
        # expansion with the *untruncated* incident exp(ik*x) on the surface.
        phi = np.linspace(0, 2*np.pi, 719, endpoint=False)
        for pol in ("Ez", "Hz"):
            q = cylinder_coefficients(.8, .55, 1.53+.02j, pol)
            modes, x, m = q["modes"], q["x"], q["n_complex"]
            e = np.exp(1j * np.outer(phi, modes)) * 1j ** modes
            incident = np.exp(1j * x * np.cos(phi))
            outside = incident + e @ (q["t"] * special.hankel1(modes, x))
            inside = e @ (q["internal_q"] * special.jv(modes, m*x))
            gamma = m if pol == "Ez" else 1/m
            dout = 1j*np.cos(phi)*incident + e @ (q["t"] * special.h1vp(modes, x))
            din = e @ (gamma*q["internal_q"] * special.jvp(modes, m*x))
            self.assertLess(np.linalg.norm(outside-inside)/np.sqrt(len(phi)), 1e-10)
            self.assertLess(np.linalg.norm(dout-din)/np.sqrt(len(phi)), 1e-10)

    def test_angle_covariance_and_incoherent_intensity_average(self):
        theta = np.linspace(-np.pi, np.pi, 512, endpoint=False)
        one = cylinder_scattering(.7, .55, 1.53, "Ez", theta)
        rotated = cylinder_scattering(.7, .55, 1.53, "Ez", theta+.73, incident_angle=.73)
        np.testing.assert_allclose(rotated["far_field"], one["far_field"], atol=2e-13, rtol=2e-12)
        wavelengths, weights = np.array([.45, .65]), np.array([1, 3])
        avg = incoherent_cylinder_average(.7, wavelengths, 1.53, "Ez", theta, wavelength_weights=weights)
        a = cylinder_scattering(.7, .45, 1.53, "Ez", theta)
        b = cylinder_scattering(.7, .65, 1.53, "Ez", theta)
        np.testing.assert_allclose(avg["dCsca_dtheta"], .25*a["dCsca_dtheta"]+.75*b["dCsca_dtheta"], atol=1e-13, rtol=1e-12)
        self.assertAlmostEqual(avg["Csca"], .25*a["Csca"]+.75*b["Csca"], places=12)

    def test_invalid_parameters_rejected(self):
        for args in ((0,.55,1.5), (1,-.55,1.5), (1,.55,1.5-.01j), (1,.55,-1.5)):
            with self.assertRaises(ValueError): cylinder_scattering(*args)
        with self.assertRaises(ValueError): cylinder_scattering(1,.55,1.5,"TE")
        with self.assertRaises(ValueError): cylinder_scattering(1,.55,1.5,n_terms=2.5)
        with self.assertRaises(ValueError): incoherent_cylinder_average(1,[.55],1.5,wavelength_weights=[-1])


class ClusterWaveTests(unittest.TestCase):
    positions = np.array([[0.,0.],[1.,0.],[.5,.866025403784]])
    theta = np.linspace(-np.pi,np.pi,768,endpoint=False)

    def test_single_cylinder_reduction(self):
        for pol in ("Ez","Hz"):
            a = cylinder_scattering(.35,.55,1.53+.02j,pol,self.theta)
            b = cluster_scattering([[0,0]],.35,.55,1.53+.02j,pol,self.theta)
            np.testing.assert_allclose(a["far_field"],b["far_field"],rtol=2e-12,atol=2e-12)
            self.assertLess(abs(a["Csca"]-b["Csca"])/a["Csca"],1e-12)
            self.assertLess(b["relative_energy_flux_residual"],1e-12)

    def test_lossless_and_absorbing_global_local_flux_agreement(self):
        for pol in ("Ez","Hz"):
            for index in (1.53,1.53+.02j):
                q=cluster_scattering(self.positions,.35,.55,index,pol,self.theta)
                self.assertLess(q["linear_system_residual"],1e-11)
                self.assertLess(q["relative_energy_flux_residual"],2e-10)
                self.assertGreaterEqual(np.min(q["Cabs_per_cylinder"]),-1e-10)
                if index == 1.53:
                    self.assertLess(abs(q["Cabs"])/q["Cext"],2e-10)
                else:
                    self.assertGreater(q["Cabs"],0)

    def test_translation_covariance_of_amplitude_and_cross_sections(self):
        alpha, shift = .29,np.array([3.13,-1.67])
        a=cluster_scattering(self.positions,.35,.55,1.53,"Ez",self.theta,incident_angle=alpha)
        b=cluster_scattering(self.positions+shift,.35,.55,1.53,"Ez",self.theta,incident_angle=alpha)
        phase=np.exp(1j*(2*np.pi/.55)*((np.array([np.cos(alpha),np.sin(alpha)])-np.column_stack((np.cos(self.theta),np.sin(self.theta))))@shift))
        np.testing.assert_allclose(b["far_field"],a["far_field"]*phase,rtol=2e-10,atol=2e-10)
        self.assertLess(abs(a["Cext"]-b["Cext"])/a["Cext"],1e-11)
        np.testing.assert_allclose(b["dCsca_dtheta"],a["dCsca_dtheta"],rtol=2e-10,atol=2e-10)

    def test_rotation_covariance_and_reciprocity(self):
        beta=.72
        rot=np.array([[np.cos(beta),-np.sin(beta)],[np.sin(beta),np.cos(beta)]])
        a=cluster_scattering(self.positions,.35,.55,1.53,"Hz",theta=[.4],incident_angle=-.2)
        b=cluster_scattering(self.positions@rot.T,.35,.55,1.53,"Hz",theta=[.4+beta],incident_angle=-.2+beta)
        c=cluster_scattering(self.positions,.35,.55,1.53,"Hz",theta=[-.2+np.pi],incident_angle=.4+np.pi)
        np.testing.assert_allclose(a["far_field"],b["far_field"],rtol=2e-10,atol=2e-10)
        np.testing.assert_allclose(a["far_field"],c["far_field"],rtol=2e-10,atol=2e-10)

    def test_order_and_angular_quadrature_convergence(self):
        a=cluster_scattering(self.positions,.35,.55,1.53,"Ez",self.theta,n_terms=18,quadrature_samples=512)
        b=cluster_scattering(self.positions,.35,.55,1.53,"Ez",self.theta,n_terms=24,quadrature_samples=2048)
        self.assertLess(np.linalg.norm(a["dCsca_dtheta"]-b["dCsca_dtheta"])/np.linalg.norm(b["dCsca_dtheta"]),1e-8)
        self.assertLess(abs(a["Csca"]-b["Csca"])/b["Csca"],1e-9)

    def test_index_matching_cluster_and_field(self):
        q=cluster_scattering(self.positions,.35,.55,1.,"Ez",self.theta)
        self.assertEqual(q["Csca"],0)
        xx,yy=np.meshgrid(np.linspace(-1,2,15),np.linspace(-1,2,17))
        f=cluster_field(q,xx,yy)
        np.testing.assert_allclose(f,np.exp(1j*2*np.pi/.55*xx),atol=1e-10,rtol=1e-10)

    def test_full_cluster_boundary_trace_and_weighted_derivative(self):
        # Direct field evaluation just inside/outside every physical surface.
        # Extrapolation and finite differences are independent of the modal
        # algebraic residual and also reveal an inadequate coupling truncation.
        angle=np.linspace(0,2*np.pi,89,endpoint=False)
        radial=np.column_stack((np.cos(angle),np.sin(angle)))
        radius,h=.35,1e-7
        for pol in ("Ez","Hz"):
            n=1.53+.02j
            q=cluster_scattering(self.positions,radius,.55,n,pol,theta=[0],n_terms=22)
            for center in self.positions:
                f=[]
                for offset in (2*h,h,-h,-2*h):
                    p=center+(radius+offset)*radial
                    f.append(cluster_field(q,p[:,0],p[:,1]))
                outer,inner=2*f[1]-f[0],2*f[2]-f[3]
                dout,din=(f[0]-f[1])/h,(f[2]-f[3])/h
                factor=1 if pol=="Ez" else 1/n**2
                self.assertLess(np.linalg.norm(outer-inner)/max(np.linalg.norm(inner),1e-30),1e-8)
                self.assertLess(np.linalg.norm(dout-factor*din)/max(np.linalg.norm(dout),1e-30),2e-5)

    def test_separated_fiber_limit_reduces_coupling(self):
        errors=[]
        for distance in (1.,4.,16.,64.):
            q=cluster_scattering([[0,0],[distance,0]],.08,.55,1.3,"Ez",theta=[0])
            t=cylinder_coefficients(.08,.55,1.3,"Ez",q["n_terms"])["t"]
            independent=q["plane_c"]*t
            errors.append(np.linalg.norm(q["b"]-independent)/np.linalg.norm(independent))
            self.assertLess(q["relative_energy_flux_residual"],1e-10)
        self.assertTrue(np.all(np.diff(errors)<0))
        self.assertLess(errors[-1],.02)

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError): cluster_scattering([[0,0],[.6,0]],.35,.55,1.53)
        with self.assertRaises(ValueError): cluster_scattering([[0,0],[.7,0]],.35,.55,1.53)


if __name__ == "__main__":
    unittest.main()
