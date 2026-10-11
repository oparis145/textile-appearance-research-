import unittest
import numpy as np
from textile_sim.geometry import (weave_pattern,periodic_crimp,parallel_frames,
    hex_pack, FabricConfig, build_fabric, segment_distance,certify_spline_clearance)


class GeometryTests(unittest.TestCase):
    def test_weave_fractions(self):
        for name,f in [('plain',.5),('twill',.5),('satin',.8)]:
            a=weave_pattern(name)
            self.assertAlmostEqual(float(a.mean()),f)
            self.assertTrue(np.all(a.sum(0)>0))
            self.assertTrue(np.all(a.sum(0)<len(a)))

    def test_crossing_separation_and_roles(self):
        pitch,h=.18,.082
        for name in ['plain','twill','satin']:
            a=weave_pattern(name)
            for i in range(-2,8):
                for j in range(-2,8):
                    zw=periodic_crimp(i*pitch,j,'warp',a,pitch,h)
                    zf=periodic_crimp(j*pitch,i,'weft',a,pitch,h)
                    self.assertAlmostEqual(float(abs(zw-zf)),2*h,places=11)
                    self.assertEqual(bool(zw>zf),bool(a[i%len(a),j%len(a)]))

    def test_hex_count_and_distance(self):
        for n in [0,1,2,3]:
            x=hex_pack(n,.018)
            self.assertEqual(len(x),1+3*n*(n+1))
            if n:
                d=np.linalg.norm(x[:,None]-x[None,:],axis=-1)
                d+=np.eye(len(x))*10
                self.assertGreaterEqual(d.min(),.018-1e-12)

    def test_frame_orthonormality(self):
        s=np.linspace(0,4,200)
        p=np.column_stack([s,.1*np.sin(s),.2*np.cos(2*s)])
        t,u,v=parallel_frames(p)
        for a in [t,u,v]:
            np.testing.assert_allclose(np.linalg.norm(a,axis=-1),1,atol=1e-12)
        for a,b in [(t,u),(t,v),(u,v)]:
            np.testing.assert_allclose(np.sum(a*b,axis=-1),0,atol=1e-12)

    def test_reproducibility_and_finite_geometry(self):
        c=FabricConfig(yarns_per_direction=3,fiber_rings=1,jitter_fraction=.02)
        a,b=build_fabric(c),build_fabric(c)
        self.assertEqual(a['fibers'].shape[0],42)
        np.testing.assert_array_equal(a['fibers'],b['fibers'])
        self.assertTrue(np.isfinite(a['fibers']).all())
        self.assertTrue(np.all(a['fibers'][:,:,3]>0))

    def test_impossible_envelope_rejected(self):
        with self.assertRaises(ValueError):
            build_fabric(FabricConfig(pitch_mm=.08))
        with self.assertRaises(ValueError):
            build_fabric(FabricConfig(plies=3,ply_orbit_mm=.02))

    def test_segment_distances_against_known_cases(self):
        a=np.array([[0,0,0],[0,0,0],[0,0,0],[0,0,0]],float)
        b=np.array([[1,0,0],[1,0,0],[1,0,0],[0,0,0]],float)
        c=np.array([[.5,-1,0],[0,2,0],[2,0,0],[0,1,0]],float)
        d=np.array([[.5,1,0],[1,2,0],[3,0,0],[0,2,0]],float)
        np.testing.assert_allclose(segment_distance(a,b,c,d),[0,2,1,1],atol=1e-14)

    def test_continuous_spline_certificate(self):
        x=np.linspace(-1,1,6)
        curves=np.array([np.column_stack([x,np.full(6,y),np.zeros(6),np.full(6,.01)])
                         for y in [0,.03]])
        good=certify_spline_clearance({'fibers':curves},subdivision=0,probe_margin_mm=.02)
        self.assertTrue(good['certified_separated'])
        self.assertAlmostEqual(good['minimum_clearance_lower_bound_mm'],.01,places=12)
        curves[1,:,1]=.015
        bad=certify_spline_clearance({'fibers':curves},subdivision=0)
        self.assertFalse(bad['certified_separated'])


if __name__=='__main__': unittest.main()
