"""Saved-artifact checks with small synthetic fixtures and rehashed corruption.

The radiance fixture is an analytic array, not an actual renderer invocation.
Tests update the outer checksums after corruption, so failure must come from
the numerical/schema contract rather than merely a stale file checksum.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from textile_sim.hierarchy import FiberSpec, PlySpec, YarnSpec, audit_clearance, build_yarn, save_hierarchy
from textile_sim.material_transport import bind_material_reference, transport_material_reference, save_material_transport
from textile_sim.optical_lod import SGGXProjection, fibonacci_directions, paired_mean_interval, projected_area_density
from textile_sim.optical_scene import MaterialSpectrum, export_mitsuba, from_hierarchy, microstructure_statistics
from verify_material_transport_artifacts_v4 import run


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger(root):
    path = root/"experiment_manifest.json"
    m = json.loads(path.read_text()) if path.exists() else {
        "status": "passed", "requested_render": True, "actual_render_count": 54,
        "scope": "unit-test fixture with analytic arrays; no renderer was executed"}
    m["output_sha256"] = {p.relative_to(root).as_posix(): _sha(p)
                           for p in root.rglob("*") if p.is_file() and p != path}
    _write(path, m)


def _projection_fixture(folder, state, scene, volume):
    train, hold = fibonacci_directions(12), fibonacci_directions(31, .371)
    truth = projected_area_density(scene, hold, volume)["all"]
    rms = float(np.sqrt(np.mean(truth**2)))
    arrays = {"train_directions": train, "heldout_directions": hold,
              "heldout_truth_per_mm": truth}
    rows = []
    for level in ("all", "family", "yarn", "ply"):
        groups, prediction, fits = projected_area_density(scene, train, volume, group_by=level), np.zeros(len(hold)), {}
        for key, values in groups.items():
            # A declared synthetic isotropic approximation, not a fitted optimum.
            matrix = np.eye(3)*float(np.mean(values))**2
            prediction += SGGXProjection(matrix).projected_area(hold)
            fits[key] = {"matrix_per_mm2": matrix.tolist()}
        rows.append({"level": level, "group_count": len(groups), "parameters": 6*len(groups),
            "heldout_relative_rmse": float(np.sqrt(np.mean((prediction-truth)**2))/rms),
            "heldout_max_error_over_rms_target": float(np.max(np.abs(prediction-truth))/rms), "fit_groups": fits})
        arrays[level+"_heldout_prediction_per_mm"] = prediction
    np.savez_compressed(folder/(state+"_projected_area_fits.npz"), **arrays)
    return {"scene_sha256": scene.sha256, "averaging_volume_mm3": volume,
            "training_direction_count": len(train), "heldout_direction_count": len(hold),
            "heldout_target_rms_per_mm": rms, "levels": rows}


def _make_fixture(root):
    s = np.linspace(0., .8, 17)
    points = np.column_stack((s, s*0, .018*np.sin(2*np.pi*s/.8)))
    yarn = YarnSpec("review", (PlySpec("ply", (
        FiberSpec("a", "review", .002, (.015, 0.)),
        FiberSpec("b", "review", .002, (-.015, 0.))), fiber_twist_per_mm=.3),))
    initial = build_yarn(yarn, points, initial_normal=(0., 0., 1.))
    target = points.copy(); target[:, 2] *= 1.2
    regenerated = build_yarn(yarn, target, initial_normal=(0., 0., 1.))
    normals = {key: np.array([0., 0., 1.]) for key in initial.yarns}
    reference = bind_material_reference(initial, yarn_initial_normals=normals,
                                        correspondence="shared_vertex_indices")
    states = {}
    for mode in ("constant_reference", "incompressible_segments"):
        states[mode] = transport_material_reference(reference, regenerated.yarns,
            yarn_initial_normals=normals, deformed_parent_coordinates_mm={
                key: c.material_coordinates_mm for key, c in reference.yarns.items()}, radius_mode=mode)
        save_material_transport(root/"tracking"/mode, states[mode])
    geometries = {"initial": initial, "regenerated": regenerated,
                  "transported": states["constant_reference"].to_hierarchy()}
    audits = {name: audit_clearance(g) for name, g in geometries.items()}
    for name, g in geometries.items(): save_hierarchy(root/"geometry"/name, g)
    errors, angles = [], []
    for a, b in zip(regenerated.fiber_records, geometries["transported"].fiber_records):
        errors.extend(np.linalg.norm(a.points_mm-b.points_mm, axis=1))
        u, v = np.diff(a.points_mm, axis=0), np.diff(b.points_mm, axis=0)
        angles.extend(np.rad2deg(np.arccos(np.clip(np.einsum("ij,ij->i", u, v)
            /(np.linalg.norm(u, axis=1)*np.linalg.norm(v, axis=1)), -1., 1.))))
    _write(root/"geometry_metrics.json", {"length_unit": "mm",
        "states": {k: g.summary() for k, g in geometries.items()}, "clearance_audits": audits,
        "identity_max_point_error_mm": 0., "transport_states": {k: s.summary() for k, s in states.items()},
        "incompressible_optical_export": {"blocked": True},
        "regenerated_vs_transported": {
            "rms_vertex_position_difference_mm": float(np.sqrt(np.mean(np.square(errors)))),
            "maximum_vertex_position_difference_mm": float(np.max(errors)),
            "rms_segment_tangent_angle_difference_deg": float(np.sqrt(np.mean(np.square(angles)))),
            "maximum_segment_tangent_angle_difference_deg": float(np.max(angles))}})
    materials = (MaterialSpectrum("review", (400., 700.), (1.5, 1.5), (0., 0.), "synthetic test material"),)
    scenes = {name: from_hierarchy(g, materials) for name, g in geometries.items()}
    union = np.stack((np.min([s.bounds_mm[0] for s in scenes.values()], axis=0),
                      np.max([s.bounds_mm[1] for s in scenes.values()], axis=0)))
    volume = float(np.prod(union[1]-union[0])); folder = root/"optics"; folder.mkdir()
    metrics = {"status": "rendered", "states": list(geometries), "rendered_radius_mode": "constant_reference",
        "scene_sha256": {}, "exported_clearance_budgets": {}, "microstructure": {}, "projection_fits": {},
        "union_bounds_mm": union.tolist(), "averaging_volume_mm3": volume,
        "wavelengths_nm": [450., 550., 650.], "seeds": [19, 47],
        "records": [], "comparisons": [], "actual_render_count": 54}
    for name, scene in scenes.items():
        scene.save(folder/(name+"_scene.json")); metrics["scene_sha256"][name] = scene.sha256
        metrics["microstructure"][name] = microstructure_statistics(scene)
        exported = export_mitsuba(scene, folder/(name+"_curves"), 450., max_smoothing_error_mm=.005)
        displacement = max(row["max_centerline_smoothing_bound_mm"] + row["float32_centerline_quantization_bound_mm"]
                           + row["float32_radius_quantization_bound_mm"] for row in exported["groups"])
        source_gap = audits[name]["minimum_clearance_lower_bound_mm"]
        metrics["exported_clearance_budgets"][name] = {"source_clearance_lower_bound_mm": source_gap,
            "maximum_tube_displacement_bound_mm": displacement,
            "exported_clearance_lower_bound_mm": source_gap-2*displacement}
        metrics["projection_fits"][name] = _projection_fixture(folder, name, scene, volume)
    raw = {"wavelengths_nm": np.array(metrics["wavelengths_nm"]), "seeds": np.array(metrics["seeds"])}
    for state_index, state in enumerate(scenes):
        for light_index, light in enumerate(("R0", "R90", "T45")):
            k = state+"__"+light
            seed = np.arange(2)[:, None, None, None]
            raw[k] = (.2+.05*state_index+.03*light_index+.01*np.arange(12).reshape(1, 2, 2, 3)
                      +.017*seed+.002*state_index*seed)
            metrics["records"].append({"state": state, "light": light, "array_file": "spectral_radiance.npz",
                "array_key": k, "actual_render_count": 6, "seeds": metrics["seeds"], "wavelengths_nm": metrics["wavelengths_nm"]})
    for light in ("R0", "R90", "T45"):
        for before in ("initial", "regenerated"):
            a, b = (raw[s+"__"+light].astype(float).mean(axis=(1, 2)) for s in (before, "transported"))
            metrics["comparisons"].append({"light": light, "from_state": before, "to_state": "transported",
                "from_mean_radiance": a.mean(axis=0).tolist(), "to_mean_radiance": b.mean(axis=0).tolist(),
                "relative_mean_radiance_change": ((b.mean(axis=0)-a.mean(axis=0))/a.mean(axis=0)).tolist(),
                "paired_interval": paired_mean_interval(a, b)})
    np.savez_compressed(folder/"spectral_radiance.npz", **raw)
    metrics["spectral_radiance_sha256"] = _sha(folder/"spectral_radiance.npz")
    _write(folder/"optical_metrics.json", metrics); _ledger(root)


class MaterialTransportArtifactReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.base_temp.name)/"fixture"; cls.base.mkdir()
        _make_fixture(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.base_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"case"
        shutil.copytree(self.base, self.root)

    def _rewrite_tracking(self, edit):
        folder = self.root/"tracking"/"constant_reference"
        path = folder/"material_transport.npz"
        with np.load(path, allow_pickle=False) as z: arrays = {k: z[k].copy() for k in z.files}
        edit(arrays); np.savez_compressed(path, **arrays)
        doc = json.loads((folder/"material_transport.json").read_text())
        doc["array_file_sha256"] = _sha(path); _write(folder/"material_transport.json", doc)
        _ledger(self.root)

    def test_complete_saved_arrays_are_recomputed(self):
        result = run(self.root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["optics"]["verified_saved_render_count"], 54)
        self.assertEqual(len(result["optics"]["paired_comparisons"]), 6)
        self.assertAlmostEqual(result["tracking"]["incompressible_segments"]["all"]
            ["relative_cylinder_segment_volume_change"], 0., places=13)

    def test_explicit_skipped_render_status_has_zero_saved_render_count(self):
        path = self.root/"optics"/"optical_metrics.json"; m = json.loads(path.read_text())
        m.update(status="skipped", records=[], comparisons=[], actual_render_count=0)
        m.pop("spectral_radiance_sha256"); _write(path, m)
        (path.parent/"spectral_radiance.npz").unlink()
        manifest = json.loads((self.root/"experiment_manifest.json").read_text())
        manifest.update(actual_render_count=0, requested_render=False)
        _write(self.root/"experiment_manifest.json", manifest); _ledger(self.root)
        result = run(self.root)
        self.assertEqual(result["optics"]["verified_saved_render_count"], 0)
        self.assertFalse(result["checks"]["saved_seed_arrays_and_paired_intervals"])

    def test_rehashed_false_strain_is_rejected_from_positions(self):
        def edit(a): a["fiber_00000/segment_stretch"][0] *= 1.1
        self._rewrite_tracking(edit)
        with self.assertRaisesRegex(ValueError, "segment_stretch"):
            run(self.root)

    def test_rehashed_improper_frame_is_rejected(self):
        def edit(a): a["yarns_00000/deformed/frames"][:, :, 1] *= -1
        self._rewrite_tracking(edit)
        with self.assertRaisesRegex(ValueError, "determinant"):
            run(self.root)

    def test_rehashed_nonfinite_radiance_is_rejected(self):
        path = self.root/"optics"/"spectral_radiance.npz"
        with np.load(path, allow_pickle=False) as z: arrays = {k: z[k].copy() for k in z.files}
        arrays["initial__R0"][0, 0, 0, 0] = np.nan
        np.savez_compressed(path, **arrays)
        metrics = json.loads((path.parent/"optical_metrics.json").read_text())
        metrics["spectral_radiance_sha256"] = _sha(path); _write(path.parent/"optical_metrics.json", metrics)
        _ledger(self.root)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            run(self.root)

    def test_rehashed_invented_paired_interval_is_rejected(self):
        path = self.root/"optics"/"optical_metrics.json"; m = json.loads(path.read_text())
        m["comparisons"][0]["paired_interval"]["mean_delta"][0] += .5
        _write(path, m); _ledger(self.root)
        with self.assertRaisesRegex(ValueError, "paired seed interval"):
            run(self.root)

    def test_rehashed_missing_required_material_labels_are_rejected(self):
        self._rewrite_tracking(lambda a: a.pop("fiber_00000/material_coordinates_mm"))
        with self.assertRaisesRegex(ValueError, "missing/duplicate tracking array"):
            run(self.root)


if __name__ == "__main__":
    unittest.main()
