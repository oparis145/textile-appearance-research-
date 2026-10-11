"""Independent render/camera physics gates, including executed-scene evidence.

Expensive rendering runs live in validate_render.py and are not repeated by
unit-test discovery. Evidence gates skip when their requested phase has not
yet run. A complete deliverable should run both phases and have no such skips.
"""

import json
from pathlib import Path
import unittest

import numpy as np

from textile_sim.camera import CameraConfig,circular_incoherent_mtf,optical_filter,integrate_pixels,observe
from validate_render import numerical_pupil_overlap,absorption_source_audit


METRICS=Path(__file__).resolve().parents[1]/"data"/"render_validation_metrics.json"


class IndependentOpticsChecks(unittest.TestCase):
    def test_circular_otf_from_geometric_pupil_autocorrelation(self):
        cutoff=2*.04/.55
        for nu in (0,.17,.43,.77,.97,1.04):
            expected=numerical_pupil_overlap(nu)
            actual=float(circular_incoherent_mtf(nu*cutoff,.55,.04))
            self.assertLess(abs(actual-expected),1e-10)

    def test_oblique_grating_transfer_includes_pixel_area_response(self):
        n=256;b=4;kx,ky=7,11;pixel=.5
        yy,xx=np.indices((n,n))
        phase=2*np.pi*(kx*xx+ky*yy)/n
        image=1+.4*np.cos(phase)
        out=integrate_pixels(optical_filter(image,pixel,pad=0),b)
        y,x=np.indices(out.shape)
        phi=2*np.pi*(kx*(b*x+(b-1)/2)+ky*(b*y+(b-1)/2))/n
        transfer=2*np.mean((out-1)*np.cos(phi))/.4
        box=np.prod([np.sin(np.pi*k*b/n)/(b*np.sin(np.pi*k/n)) for k in (kx,ky)])
        expected=numerical_pupil_overlap(np.hypot(kx,ky)/(n*pixel)/(2*.04/.55))*box
        self.assertLess(abs(transfer-expected),1e-10)

    def test_radius_normalized_absorption_matches_pinned_source_and_beer_units(self):
        record=absorption_source_audit()
        self.assertTrue(record["has_nonsymmetric_flag"])
        self.assertEqual(len(record["normalized_chord_expressions"]),3)
        for case in record["checks"]:
            self.assertLess(case["absolute_error"],2e-15)

    def test_camera_metadata_distinguishes_collection_sampling_and_preclip_variance(self):
        a=np.full((32,32),.3)
        fine=observe(a,.8,CameraConfig(na=.04,binning=1),add_noise=False)
        coarse=observe(a,.8,CameraConfig(na=.12,binning=4),add_noise=False)
        self.assertIn("object-referred",fine["pixel_coordinates"])
        self.assertIn("NA collection not automatic",fine["photon_budget_definition"])
        self.assertIn("before full-well clipping",fine["variance_definition"])
        self.assertAlmostEqual(fine["expected_electrons"].sum(),coarse["expected_electrons"].sum(),places=9)
        self.assertAlmostEqual(coarse["output_nyquist_per_um"],.5/(.8*4))
        self.assertTrue(fine["output_sampling_resolves_optical_cutoff"])
        self.assertFalse(coarse["output_sampling_resolves_optical_cutoff"])


class EvidenceMixin:
    def evidence(self,key):
        if not METRICS.exists():self.skipTest("Execute validate_render.py first")
        record=json.loads(METRICS.read_text())
        if key not in record:self.skipTest(f"Validation phase {key} is not complete")
        return record,record[key]


class ExecutedRenderChecks(EvidenceMixin,unittest.TestCase):
    def test_coverage_uses_actual_sensor_rays_and_has_substantial_core(self):
        _,d=self.evidence("coverage")
        self.assertGreater(d["fully_sampled_covered_pixels"],100)
        self.assertGreater(d["fully_sampled_open_pixels"],10)
        self.assertGreater(d["mean_coverage"],.1)
        self.assertLess(d["mean_coverage"],1.)

    def test_lossless_furnace_including_covered_pixels(self):
        _,groups=self.evidence("furnace_depth_groups")
        if "-1" not in groups:self.skipTest("Unlimited furnace group not complete")
        d=groups["-1"]
        self.assertEqual(d["n_seeds"],3)
        for key in ("full_mean","center_covered_mean","fully_covered_mean"):
            tolerance=max(.007,5*d[key+"_seed_se"])
            self.assertLess(abs(d[key]-1),tolerance)

    def test_finite_path_depth_bias_is_measured_and_not_hidden(self):
        _,groups=self.evidence("furnace_depth_groups")
        if "32" not in groups or "full_mean_bias_vs_unlimited" not in groups["32"]:
            self.skipTest("Depth comparison not complete")
        self.assertLess(groups["2"]["fully_covered_mean"],groups["-1"]["fully_covered_mean"]-.05)
        self.assertLess(abs(groups["32"]["covered_mean_bias_vs_unlimited"]),
                        abs(groups["2"]["covered_mean_bias_vs_unlimited"]))
        for depth in (2,4,8,16,32):
            self.assertLess(groups[str(depth)]["full_mean_bias_vs_unlimited"],.007)

    def test_source_hemispheres_have_correct_camera_orientation(self):
        _,d=self.evidence("empty_scene_source_orientation")
        self.assertAlmostEqual(d["furnace"]["mean"],1,places=5)
        self.assertAlmostEqual(d["hemisphere_reflection"]["mean"],0,places=5)
        self.assertAlmostEqual(d["hemisphere_transmission"]["mean"],1,places=5)

    def test_upper_plus_lower_illumination_is_linear(self):
        _,d=self.evidence("hemisphere_source_linearity")
        for key in ("full_mean","fully_covered_mean"):
            self.assertLess(abs(d[key]-1),max(.007,5*d[key+"_seed_se"]))
        self.assertLess(d["pixel_rmse_sum_vs_unlimited_mean"],.1)

    def test_passive_absorption_lowers_furnace_response(self):
        _,cases=self.evidence("cases")
        if "furnace_abs2_seed12101" not in cases:self.skipTest("Absorbing furnace not complete")
        d=cases["furnace_abs2_seed12101"]
        self.assertGreater(d["fully_covered_mean"],0)
        self.assertLess(d["fully_covered_mean"],.995)

    def test_actual_cloth_sampling_converges_on_independent_reference(self):
        _,d=self.evidence("sampling_convergence")
        if "1024" not in d or "predicted_rmse_with_reference_noise_from_1024" not in d["1024"]:
            self.skipTest("Sampling convergence not complete")
        self.assertLess(d["256"]["mean_rmse_to_reference"],d["64"]["mean_rmse_to_reference"])
        self.assertLess(d["1024"]["mean_rmse_to_reference"],d["256"]["mean_rmse_to_reference"])
        scale=np.array([d[str(s)]["variance_times_spp"] for s in (64,256,1024)])
        self.assertLess(scale.max()/scale.min(),2.)


class ExecutedCameraChecks(EvidenceMixin,unittest.TestCase):
    def test_fixed_physical_area_preserves_photon_budget_across_binning(self):
        _,d=self.evidence("camera")
        for row in d["fixed_area_photon_and_noise_checks"]:
            self.assertLess(abs(row["expected_total_photoelectrons"]/row["predicted_total_photoelectrons"]-1),1e-12)

    def test_independent_seed_noise_matches_area_and_read_noise_scaling(self):
        _,d=self.evidence("camera")
        for row in d["fixed_area_photon_and_noise_checks"]:
            self.assertLess(abs(row["radiance_variance_ratio"]-1),.012)
            self.assertLess(abs(row["mean_radiance_error"]),5*row["mean_radiance_standard_error"])

    def test_dark_readout_retains_unbiased_negative_estimates(self):
        _,d=self.evidence("camera")
        dark=d["bias_subtracted_dark"]
        self.assertLess(abs(dark["mean"]),.001)
        self.assertLess(abs(dark["negative_fraction"]-.5),.01)
        self.assertLess(abs(dark["variance"]/dark["predicted_variance"]-1),.015)

    def test_saturation_is_explicitly_outside_unsaturated_variance_claim(self):
        _,d=self.evidence("camera")
        s=d["saturation_limit"]
        self.assertEqual(s["saturation_fraction"],1.)
        self.assertLess(s["mean_clipped_estimate"],s["linear_scene_value"])
        self.assertGreater(s["returned_preclip_variance"],s["measured_clipped_variance"])


if __name__=="__main__":unittest.main()
