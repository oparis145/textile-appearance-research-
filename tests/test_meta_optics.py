import unittest
import numpy as np
from textile_sim.meta_optics import(PupilConfig,phase_pupil,fresnel_propagate,
                                    roi_measurements,airy_intensity)


class MetaOpticsPhysicsTests(unittest.TestCase):
    def test_unit_pupil_power_and_declared_loss(self):
        for eta in (0.,.4,1.):
            c=PupilConfig(grid_size=128,pixel_um=1,conversion_efficiency=eta)
            p=phase_pupil(c,[(-10,-10),(10,-10),(-10,10),(10,10)])
            self.assertAlmostEqual(float((abs(p['field'])**2).sum()*c.pixel_um**2),eta,places=13)

    def test_parseval_under_padding_and_tilt(self):
        rng=np.random.default_rng(88)
        a=rng.normal(size=(31,32))+1j*rng.normal(size=(31,32));a/=np.linalg.norm(a)
        for pad in (1,2,3):
            r=fresnel_propagate(a,.5,.55,100,pad,(1,-.4))
            self.assertAlmostEqual(r['power'].sum(),.25,places=13)

    def test_zero_distance_identity(self):
        rng=np.random.default_rng(32);a=rng.normal(size=(32,32))+.1j
        r=fresnel_propagate(a,.7,.55,0,1)
        self.assertTrue(np.allclose(r['field'],a,atol=1e-13))

    def test_odd_grid_padding_preserves_physical_origin(self):
        a=np.zeros((31,33),complex);a[15,16]=1.
        for pad in (1,2,3):
            r=fresnel_propagate(a,.7,.55,0,pad)
            iy,ix=np.unravel_index(np.argmax(r['power']),r['power'].shape)
            self.assertAlmostEqual(r['x_um'][ix],0.)
            self.assertAlmostEqual(r['y_um'][iy],0.)

    def test_phase_quantization_passive_and_bounded_phase_error(self):
        c=PupilConfig(grid_size=128,pixel_um=1)
        ref=phase_pupil(c,[(-10,0),(10,0)])
        for levels in (2,4,8,16):
            q=phase_pupil(c,[(-10,0),(10,0)],levels=levels)
            error=abs(np.angle(np.exp(1j*(q['phase_rad']-ref['phase_rad']))))
            self.assertLessEqual(error.max(),np.pi/levels+1e-12)
            self.assertAlmostEqual((abs(q['field'])**2).sum(),c.conversion_efficiency,places=13)

    def test_focal_plane_profile_against_airy(self):
        c=PupilConfig(grid_size=512,pixel_um=.25,conversion_efficiency=1.)
        p=phase_pupil(c);r=fresnel_propagate(p['field'],c.pixel_um,.55,c.focal_um,2)
        centre=r['power'].shape[0]//2
        x=r['x_um'];actual=r['power'][centre]/r['power'][centre,centre]
        target=airy_intensity(x,.55,c.focal_um,c.radius_um)
        use=abs(x)<7
        self.assertLess(float(np.max(abs(actual[use]-target[use]))),.018)
        # The first Airy disk carries~83.8% for an ideal circular pupil.
        radius=1.219669891*.55*c.focal_um/(2*c.radius_um)
        m=roi_measurements(r,[(0,0)],radius)
        self.assertLess(abs(m['captured_power']-.8378),.012)

    def test_incident_tilt_focal_translation(self):
        c=PupilConfig(grid_size=256,pixel_um=.5)
        p=phase_pupil(c)
        r=fresnel_propagate(p['field'],c.pixel_um,.55,c.focal_um,4,(1,0))
        iy,ix=np.unravel_index(np.argmax(r['power']),r['power'].shape)
        predicted=c.focal_um*np.sin(np.deg2rad(1))
        self.assertLess(abs(r['x_um'][ix]-predicted),c.pixel_um)
        self.assertLess(abs(r['y_um'][iy]),c.pixel_um)

    def test_offaxis_carrier_wavelength_translation(self):
        c=PupilConfig(grid_size=256,pixel_um=.5)
        p=phase_pupil(c,[(10,0)])
        for wl in (.45,.55,.65):
            r=fresnel_propagate(p['field'],c.pixel_um,wl,c.focal_um,4)
            # Symmetric defocus preserves centroid around the shifted carrier.
            x=r['x_um'];y=r['y_um'];target=10*wl/c.design_wavelength_um
            use=(abs(x[None,:]-target)<12)&(abs(y[:,None])<12)
            mass=np.where(use,r['power'],0)
            actual=(mass*x[None,:]).sum()/mass.sum()
            self.assertLess(abs(actual-target),.15)

    def test_positive_disjoint_measurement_matrix_and_column_budget(self):
        c=PupilConfig(grid_size=128,pixel_um=1)
        targets=[(-10,-10),(10,-10),(-10,10),(10,10)];p=phase_pupil(c,targets)
        for wl in (.45,.55,.65):
            r=fresnel_propagate(p['field'],1,wl,c.focal_um,2,(.4,0))
            m=roi_measurements(r,targets,4)
            self.assertTrue(np.all(m['roi_power']>=0))
            self.assertLessEqual(m['captured_power'],c.conversion_efficiency+1e-13)
            self.assertAlmostEqual(m['captured_power']+m['outside_roi_power'],c.conversion_efficiency,places=12)

    def test_scalar_angular_spectrum_does_not_amplify(self):
        c=PupilConfig(grid_size=128,pixel_um=.5)
        p=phase_pupil(c)
        r=fresnel_propagate(p['field'],.5,.65,250,2,method='angular_spectrum')
        self.assertLessEqual(r['power'].sum(),c.conversion_efficiency+1e-13)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):phase_pupil(PupilConfig(conversion_efficiency=1.1))
        with self.assertRaises(ValueError):phase_pupil(weights=[-1])
        with self.assertRaises(ValueError):phase_pupil(levels=1)


if __name__=='__main__':unittest.main()
