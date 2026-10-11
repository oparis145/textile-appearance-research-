import unittest
import numpy as np
from textile_sim.render import encode_srgb, hair_properties, RenderConfig, direction


class RenderUnitTests(unittest.TestCase):
    def test_absorption_units(self):
        c=RenderConfig(absorption_per_mm=2.)
        a=hair_properties(c,.004)['sigma_a']['value']
        # A diameter chord of 8um has exp(-mu*0.008) transmittance.
        self.assertAlmostEqual(np.exp(-a*2),np.exp(-2*.008),places=14)

    def test_srgb_known_endpoints(self):
        np.testing.assert_allclose(encode_srgb([0,1]),[0,1],atol=1e-14)
        self.assertAlmostEqual(float(encode_srgb(.0031308)),.040449936,places=8)

    def test_directions(self):
        for e in [-90,-20,0,43,90]:
            self.assertAlmostEqual(np.linalg.norm(direction(e,74)),1,places=14)

    def test_passivity_inputs(self):
        with self.assertRaises(ValueError):
            hair_properties(RenderConfig(absorption_per_mm=-1),.004)


if __name__=='__main__': unittest.main()
