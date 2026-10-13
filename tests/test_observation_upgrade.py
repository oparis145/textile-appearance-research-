import unittest
import numpy as np
from numpy.testing import assert_allclose
from scipy.integrate import quad

from textile_sim.surface_reference import (fresnel, surface_power, observe,
    angular_lod, observation_error, _deposit)
from textile_sim.observation_gate import paired_equivalence, choose_observation_lod
from textile_sim.local_volume_profile import (reconstruct_local_volume,
    frustum_volumes, global_volume_baseline)


class SurfaceReferenceTests(unittest.TestCase):
    def test_normal_fresnel(self):
        assert_allclose(fresnel([1.], 1.55), [(1.55-1)**2/(1.55+1)**2])

    def test_brewster(self):
        self.assertLess(float(fresnel(np.cos(np.arctan(1.55)), 1.55, 'p')), 1e-28)

    def test_index_matched(self):
        assert_allclose(fresnel([0., .1, .5, 1.], 1.), 0.)
        a, budget = surface_power(n_inside=1.)
        self.assertEqual(a.sum(), 0.)
        self.assertEqual(budget['entered_untraced'], 1.)

    def test_polarization_average(self):
        c = np.linspace(0, 1, 20)
        assert_allclose(fresnel(c), (fresnel(c, polarization='s')+fresnel(c, polarization='p'))/2)

    def test_fresnel_invalid(self):
        for c, n, p in [(-.1, 1.5, 'u'), (1.1, 1.5, 'u'), (.5, .9, 'u'), (.5, 1.5, 'v')]:
            with self.subTest(c=c, n=n, p=p), self.assertRaises(ValueError):
                fresnel(c, n, p)

    def test_circle_independent_impact_parameter_integral(self):
        # Independent b in [-1,1], not the production outgoing-angle quadrature.
        expected = quad(lambda b: float(fresnel(np.sqrt(1-b*b))), -1, 1,
                        epsabs=1e-12, epsrel=1e-12)[0]/2
        power, _ = surface_power(grid_size=2048)
        self.assertAlmostEqual(power.sum(), expected, places=10)

    def test_circle_phase_invariance(self):
        a, _ = surface_power(phase_rad=0., grid_size=512)
        b, _ = surface_power(phase_rad=1.1, grid_size=512)
        assert_allclose(a, b, rtol=0, atol=0)

    def test_square_projection(self):
        _, budget = surface_power(sides=4, phase_rad=np.pi/4, grid_size=512)
        self.assertAlmostEqual(budget['intercepted'], 1/np.sqrt(2), places=14)
        self.assertAlmostEqual(budget['area_ratio'], 2/np.pi, places=14)

    def test_budget_many_polygons(self):
        for sides in [3, 5, 16, 32, 64, 127, 512]:
            with self.subTest(sides=sides):
                p, b = surface_power(sides=sides, phase_rad=.17, grid_size=1024)
                self.assertTrue(np.all(p >= 0))
                self.assertAlmostEqual(b['reflected']+b['entered_untraced']+b['missed'], 1., places=12)

    def test_source_power_normalization(self):
        a, _ = surface_power(grid_size=2048)
        b, _ = surface_power(grid_size=2048, source_sigma_deg=2, source_order=81)
        self.assertAlmostEqual(a.sum(), b.sum(), places=9)

    def test_common_rotation(self):
        size, shift = 1024, 83
        angle = shift*2*np.pi/size
        a, _ = surface_power(sides=31, phase_rad=.13, grid_size=size)
        b, _ = surface_power(sides=31, phase_rad=.13+angle, source_center_rad=angle, grid_size=size)
        assert_allclose(np.roll(a, shift), b, rtol=1e-10, atol=1e-14)

    def test_cic_conservation_at_wrap(self):
        p = _deposit(np.array([0, 2*np.pi, -1e-12]), np.array([1., 2., 3.]), 128)
        self.assertAlmostEqual(p.sum(), 6., places=14)
        self.assertTrue(np.all(p >= 0))

    def test_observe_conservation(self):
        p, _ = surface_power(sides=32, grid_size=2048)
        for width in [0, .5, 2, 8]:
            y = observe(p, sigma_deg=width, detector_bins=64)
            self.assertAlmostEqual(p.sum(), y.sum(), places=13)
            self.assertTrue(np.all(y >= 0))

    def test_observe_uniform(self):
        p = np.ones(2048)/2048
        assert_allclose(observe(p, sigma_deg=8, detector_bins=64), np.ones(64)/64, atol=1e-14)

    def test_observe_reject_underresolved(self):
        with self.assertRaises(ValueError):
            observe(np.ones(128), sigma_deg=.1, detector_bins=32)

    def test_observe_reject_negative(self):
        with self.assertRaises(ValueError):
            observe(np.r_[-1., np.ones(127)], sigma_deg=2, detector_bins=32)

    def test_lod_conservation(self):
        p = np.arange(1, 513, dtype=float)
        for k in [1, 2, 16, 128, 512]:
            out = angular_lod(p, k)
            self.assertAlmostEqual(out.sum(), p.sum(), places=10)
        assert_allclose(angular_lod(p, len(p)), p)

    def test_lod_invalid(self):
        for groups in [0, True, 7, 600]:
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                angular_lod(np.ones(512), groups)

    def test_circle_quadrature_refinement(self):
        a, _ = surface_power(grid_size=2048, circle_order=4)
        b, _ = surface_power(grid_size=2048, circle_order=8)
        self.assertLess(observation_error(a, b)['relative_l2'], 1e-9)

    def test_polygon_optical_convergence(self):
        a, _ = surface_power(grid_size=4096)
        b, _ = surface_power(sides=1024, grid_size=4096)
        a, b = (observe(x, sigma_deg=2, detector_bins=128) for x in (a,b))
        self.assertLess(observation_error(a,b)['relative_l2'], .003)

    def test_zero_error(self):
        self.assertEqual(observation_error(np.zeros(16), np.zeros(16))['relative_l2'], 0.)


class ObservationGateTests(unittest.TestCase):
    def gate(self, a, b, **kw):
        return paired_equivalence(a, b, repeat_ids=list(range(len(a))),
            condition_ids=[str(i) for i in range(a.shape[1])], absolute_tolerance=.1, **kw)

    def test_identical(self):
        a = np.arange(12.).reshape(4,3)
        self.assertTrue(self.gate(a,a)['all_equivalent'])

    def test_zero_contained_is_not_equivalence(self):
        a = np.ones((4,1)); b = a+np.array([[-1.],[1.],[-1.],[1.]])
        r = self.gate(a,b)
        self.assertFalse(r['all_equivalent'])
        self.assertEqual(r['conditions'][0]['status'], 'inconclusive')

    def test_large_difference(self):
        a = np.ones((4,1))
        self.assertEqual(self.gate(a,a+.3)['conditions'][0]['status'], 'different')

    def test_pair_common_noise_cancels(self):
        a = np.random.default_rng(7).normal(size=(10,3))
        self.assertTrue(self.gate(a,a+.01)['all_equivalent'])

    def test_margin_can_block_acceptance(self):
        a = np.ones((4,1))
        self.assertFalse(self.gate(a,a, extra_error_margin=.2)['all_equivalent'])

    def test_multiplicity_widens(self):
        a = np.ones((10,1)); b = a+np.linspace(-.01,.01,10)[:,None]
        r1, r9 = self.gate(a,b), self.gate(a,b,family_size=9)
        self.assertGreater(r9['conditions'][0]['ci_upper'], r1['conditions'][0]['ci_upper'])

    def test_not_enough_repeats(self):
        with self.assertRaises(ValueError):
            self.gate(np.ones((2,1)),np.ones((2,1)))

    def test_nonfinite(self):
        a = np.ones((4,1)); a[0]=np.nan
        with self.assertRaises(ValueError): self.gate(a,a)

    def test_duplicate_repeat_ids(self):
        with self.assertRaises(ValueError):
            paired_equivalence(np.ones((4,1)),np.ones((4,1)),absolute_tolerance=.1,
                               repeat_ids=[1,1,2,3],condition_ids=['a'])

    def test_family_cannot_shrink(self):
        with self.assertRaises(ValueError): self.gate(np.ones((4,3)),np.ones((4,3)),family_size=2)

    def test_row_order_invariance(self):
        a = np.ones((6,2)); b = a+np.arange(12).reshape(6,2)*.001
        assert_allclose(self.gate(a,b)['conditions'][0]['ci_upper'],
                        self.gate(a[::-1],b[::-1])['conditions'][0]['ci_upper'])

    def test_observation_lod_selection(self):
        cs = [{'name':f'g{k}', 'cost':k, 'conditions':[{'condition':'test',
               'relative_l2':e,'relative_power_error':0.,'refinement_l2':.001}]} for k,e in [(8,.2),(16,.02),(32,.005)]]
        r=choose_observation_lod(cs,max_relative_l2=.03,max_relative_power=.01,max_refinement_l2=.002)
        self.assertEqual(r['selected'],'g16')

    def test_refinement_blocks_lod(self):
        cs=[{'name':'x','cost':1,'conditions':[{'condition':'test','relative_l2':0.,
             'relative_power_error':0.,'refinement_l2':.1}]}]
        self.assertIsNone(choose_observation_lod(cs,max_relative_l2=.01,max_relative_power=.01,max_refinement_l2=.001)['selected'])

    def test_missing_condition_rejected(self):
        row={'condition':'a','relative_l2':0.,'relative_power_error':0.,'refinement_l2':0.}
        cs=[{'name':'a','cost':1,'conditions':[row]},{'name':'b','cost':2,'conditions':[dict(row,condition='b')]}]
        with self.assertRaises(ValueError):
            choose_observation_lod(cs,max_relative_l2=.01,max_relative_power=.01,max_refinement_l2=.001)


class LocalVolumeTests(unittest.TestCase):
    def test_constant_radius(self):
        r = reconstruct_local_volume(np.ones(32), np.full(32, .003))
        assert_allclose(r['node_radii'], .003, rtol=1e-7)
        self.assertLess(r['max_relative_volume_error'], 1e-10)

    def test_known_linear_profile(self):
        nodes = np.linspace(.002,.004,33); l=np.linspace(.01,.03,32)
        radii=np.sqrt(frustum_volumes(l,nodes)/(np.pi*l))
        out=reconstruct_local_volume(l,radii)
        assert_allclose(out['segment_volumes'],frustum_volumes(l,nodes),rtol=1e-10)

    def test_smooth_incompressible_stretch(self):
        x=(np.arange(128)+.5)/128; stretch=1+.2*np.sin(2*np.pi*x)
        l=.01*stretch; r=.003/np.sqrt(stretch)
        out=reconstruct_local_volume(l,r)
        assert_allclose(out['segment_volumes'],np.full(128,np.pi*.003**2*.01),rtol=1e-10)

    def test_old_rule_preserves_total_not_local(self):
        l=np.array([1.,2.,3.,4.]); r=np.array([1.,1.1,1.15,1.2])
        old=global_volume_baseline(l,r)
        assert_allclose(frustum_volumes(l,old).sum(),(np.pi*l*r*r).sum())
        self.assertGreater(np.max(abs(frustum_volumes(l,old)/(np.pi*l*r*r)-1)), .01)

    def test_infeasible_small_big_small(self):
        with self.assertRaises(ValueError):
            reconstruct_local_volume([1.,1.,1.],[.01,1.,.01])

    def test_scale_similarity(self):
        l=np.linspace(.01,.02,64); r=.003*(1+.03*np.sin(np.arange(64)/8))
        a=reconstruct_local_volume(l,r); b=reconstruct_local_volume(l*100,r*100)
        assert_allclose(a['node_radii']*100,b['node_radii'],rtol=2e-7)
        assert_allclose(a['segment_volumes']*1e6,b['segment_volumes'],rtol=1e-10)

    def test_single_segment(self):
        a=reconstruct_local_volume([2.],[.3])
        assert_allclose(a['segment_volumes'],[np.pi*.3**2*2],rtol=1e-10)

    def test_invalid_input(self):
        for lengths,radii in [([],[]),([0.],[1.]),([1.],[-1.]),([1.,2.],[1.]),([1.],[np.nan])]:
            with self.subTest(lengths=lengths), self.assertRaises(ValueError):
                reconstruct_local_volume(lengths,radii)

    def test_stretch_grid_sweep(self):
        for count in [16,64,256]:
            for amp in [.03,.1,.25]:
                x=(np.arange(count)+.5)/count
                stretch=1+amp*np.sin(2*np.pi*x)
                with self.subTest(count=count,amp=amp):
                    out=reconstruct_local_volume(stretch/count,.003/np.sqrt(stretch))
                    self.assertLess(out['max_relative_volume_error'],1e-9)





class V5AdapterTests(unittest.TestCase):
    def fixture(self, root):
        import hashlib, json
        folder=root/'optics'; folder.mkdir()
        a=np.ones((3,2,3,3,4,2,2),dtype=np.float32)*.1
        a[0]+=.03
        np.savez(folder/'spectral_radiance.npz',radiance=a)
        m={'schema_version':'variable_radius_optics_experiment_v5.0','status':'rendered',
           'states':['constant_reference','incompressible_segments'],'lights':['R0','R90','T45'],
           'radiance_axes':['radial_segments','state','light','wavelength_nm','seed','row','column'],
           'radial_segments':[16,32,64],'wavelengths_nm':[450,550,650],'seeds':[11,13,17,19],
           'resolution':2,'spectral_radiance_sha256':hashlib.sha256((folder/'spectral_radiance.npz').read_bytes()).hexdigest()}
        (folder/'optical_metrics.json').write_text(json.dumps(m))
        return folder,m

    def test_schema_compatible_adapter_and_seed_count(self):
        import tempfile
        from pathlib import Path
        from textile_sim.observation_gate import audit_v5_radial_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            out=audit_v5_radial_pair(root,coarse=32,fine=64,absolute_tolerance=.001)
            self.assertEqual(out['repeat_count'],4)
            self.assertEqual(len(out['conditions']),18)
            self.assertTrue(out['all_equivalent'])
            self.assertEqual(out['new_renders'],0)
            self.assertFalse(out['reference_certified_converged'])

    def test_adapter_reports_non_equivalence(self):
        import tempfile
        from pathlib import Path
        from textile_sim.observation_gate import audit_v5_radial_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            out=audit_v5_radial_pair(root,coarse=16,fine=64,absolute_tolerance=.001)
            self.assertTrue(all(r['status']=='different' for r in out['conditions']))

    def test_archive_tamper_rejected(self):
        import tempfile
        from pathlib import Path
        from textile_sim.observation_gate import audit_v5_radial_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,_=self.fixture(root)
            with (folder/'spectral_radiance.npz').open('ab') as f: f.write(b'tamper')
            with self.assertRaises(ValueError):
                audit_v5_radial_pair(root,coarse=32,fine=64,absolute_tolerance=.001)

    def test_axis_swap_rejected(self):
        import tempfile,json
        from pathlib import Path
        from textile_sim.observation_gate import audit_v5_radial_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,m=self.fixture(root)
            m['radiance_axes'][3],m['radiance_axes'][4]=m['radiance_axes'][4],m['radiance_axes'][3]
            (folder/'optical_metrics.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):
                audit_v5_radial_pair(root,coarse=32,fine=64,absolute_tolerance=.001)


class ReviewRegressionTests(unittest.TestCase):
    def test_unseen_detector_resolution_reveals_alignment(self):
        ref,_=surface_power(grid_size=4096)
        poly,_=surface_power(sides=256,grid_size=4096)
        e={}
        for bins in [256,512]:
            r,p=(observe(x,sigma_deg=.5,detector_bins=bins) for x in (ref,poly))
            e[bins]=observation_error(r,p)['relative_l2']
        self.assertLess(e[256],.03)
        self.assertGreater(e[512],.2)

    def test_polygon_quarter_phase_changes_narrow_observation(self):
        a,_=surface_power(sides=256,grid_size=4096,phase_rad=0)
        b,_=surface_power(sides=256,grid_size=4096,phase_rad=.25*2*np.pi/256)
        a,b=(observe(x,sigma_deg=.5,detector_bins=256) for x in (a,b))
        self.assertGreater(observation_error(a,b)['relative_l2'],.1)

    def test_produced_volume_independent_closed_formula(self):
        radii=np.array([.003,.0031,.0032,.00315]); lengths=np.array([.01,.02,.011,.007])
        x=reconstruct_local_volume(lengths,radii)['node_radii']
        # Independent integral of the squared linear interpolation at Simpson nodes.
        val=np.pi*lengths*(x[:-1]**2+4*((x[:-1]+x[1:])/2)**2+x[1:]**2)/6
        assert_allclose(val,np.pi*lengths*radii*radii,rtol=1e-10)

    def test_cli_dry_run_does_not_write(self):
        import tempfile, subprocess, sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            script=Path(__file__).resolve().parents[1]/'run_observation_upgrade.py'
            done=subprocess.run([sys.executable,str(script),'--output',str(out),'--dry-run'],capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertFalse(out.exists())

    def test_cli_refuses_overwrite(self):
        import tempfile, subprocess, sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); (out/'keep.txt').write_text('untouched')
            script=Path(__file__).resolve().parents[1]/'run_observation_upgrade.py'
            done=subprocess.run([sys.executable,str(script),'--output',str(out)],capture_output=True,text=True)
            self.assertNotEqual(done.returncode,0)
            self.assertEqual((out/'keep.txt').read_text(),'untouched')


class AdditionalMetadataTests(unittest.TestCase):
    def test_boolean_repeat_ids_rejected(self):
        with self.assertRaises(ValueError):
            paired_equivalence(np.ones((3,1)), np.ones((3,1)), absolute_tolerance=.1,
                               repeat_ids=[True,2,3],condition_ids=['a'])

    def test_v5_string_seed_metadata_rejected(self):
        import tempfile,json
        from pathlib import Path
        from textile_sim.observation_gate import audit_v5_radial_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,m=V5AdapterTests().fixture(root)
            m['seeds']=['11','13','17','19']
            (folder/'optical_metrics.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):
                audit_v5_radial_pair(root,coarse=32,fine=64,absolute_tolerance=.001)


if __name__ == '__main__': unittest.main()
