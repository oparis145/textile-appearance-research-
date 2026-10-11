"""Small analytic fixtures exercise v5 artifact verification; no rendering.

Fixture arrays are explicitly synthetic test data, not saved evidence of a
renderer call. Corruption cases update both local hashes and the producer
ledger, so they require semantic/raw-data rejection rather than checksum alone.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from textile_sim.hierarchy import FiberCurve, audit_clearance
from textile_sim.optical_lod import paired_mean_interval
from textile_sim.optical_scene import MaterialSpectrum
from textile_sim.render import RenderConfig
from textile_sim.variable_radius import (VariableRadiusFiber, build_tapered_tube,
    load_variable_radius_profiles, save_variable_radius_profiles)
from textile_sim.volume_optics import triangle_buffer_audit
import verify_variable_radius_artifacts_v5 as verifier


ROOT = Path(__file__).resolve().parents[1]
STATES, LIGHTS, RADIALS, WAVES, SEEDS = verifier.STATES, verifier.LIGHTS, (8, 12), (550.,), (11, 29, 47, 71)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def array_sha(value):
    array = np.ascontiguousarray(value)
    h = hashlib.sha256(canon([array.shape, array.dtype.str]).encode("ascii"))
    h.update(array.tobytes())
    return h.hexdigest()


def ledger(root):
    path = root/"experiment_manifest.json"
    value = json.loads(path.read_text())
    value["output_sha256"] = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*")
                              if p.is_file() and p != path}
    dump(path, value)


def totals(profiles):
    p = profiles[0]
    local = p.segment_relative_volume_error
    source, frustum = float(p.segment_volume_proxy_mm3.sum()), float(p.segment_frustum_volume_mm3.sum())
    return {"fiber_count": 1, "vertex_count": len(p.points_mm), "segment_count": len(p.segment_radius_mm),
            "source_cylinder_volume_proxy_mm3": source, "total_frustum_integral_mm3": frustum,
            "frustum_total_relative_error": frustum/source-1,
            "node_radius_min_mm": float(p.node_radius_mm.min()), "node_radius_max_mm": float(p.node_radius_mm.max()),
            "local_segment_volume_relative_error_min": float(local.min()),
            "local_segment_volume_relative_error_max": float(local.max()),
            "local_absolute_error_percentile_99": float(np.quantile(np.abs(local), .99)),
            "profiles": [p.summary()]}


def fixture(root, rendered=True):
    points = np.array(((0., 0., 0.), (.63, 0., 0.), (1.05, 0., 0.)))
    reference_labels = np.array((0., .6, 1.))
    profile_sets, clearances = {}, {}
    for mode in STATES:
        radius = np.full(2, .04)/(np.sqrt(1.05) if mode == STATES[1] else 1.)
        profile = VariableRadiusFiber(points, reference_labels, reference_labels, radius,
                    "warp:0/ply:0/fiber:0", "warp:0", "warp:0/ply:0", "synthetic-fixture",
                    family="warp", provenance_json=canon({
                        "source_radius_mode": mode, "source_reference_sha256": "a"*64,
                        "source_state_sha256": ("b" if mode == STATES[0] else "c")*64,
                        "fixture_without_renderer_calls": True}))
        profile_sets[mode] = (profile,)
        save_variable_radius_profiles(root/"profiles"/mode, (profile,))
        f = FiberCurve(points, np.full(3, profile.node_radius_mm.max()), profile.fiber_id,
                        profile.yarn_id, profile.ply_id, profile.material_id, "warp", 0, 0, 0)
        clearances[mode] = audit_clearance(SimpleNamespace(fiber_records=(f,)))
    geometry = {"schema_version": "variable_radius_geometry_v5.0", "length_unit": "mm",
                "same_centerlines_for_both_states": True, "states": {},
                "mesh_levels": {str(n): {} for n in RADIALS}}
    mesh_rows = {}
    for mode, profiles in profile_sets.items():
        geometry["states"][mode] = {**totals(profiles), "clearance": clearances[mode],
                "transport_state_sha256": ("b" if mode == STATES[0] else "c")*64,
                "reference_sha256": "a"*64}
        p = profiles[0]
        for n in RADIALS:
            mesh = build_tapered_tube(p, radial_segments=n, initial_normal=(0., 0., 1.))
            vertices, faces, audit = triangle_buffer_audit(mesh.vertices_mm, mesh.faces)
            folder = root/"meshes"/f"radial_{n:03d}"/mode
            folder.mkdir(parents=True)
            np.savez_compressed(folder/"renderer_buffers.npz", **{
                "fiber_0000/vertices_mm": vertices, "fiber_0000/faces": faces})
            source = float(p.segment_volume_proxy_mm3.sum())
            frustum = float(p.segment_frustum_volume_mm3.sum())
            volume, factor = mesh.signed_volume_mm3, n*np.sin(2*np.pi/n)/(2*np.pi)
            summary = {"fiber_count": 1, "radial_segments": n, "vertex_count": len(vertices),
                "face_count": len(faces), "source_cylinder_volume_proxy_mm3": source,
                "total_frustum_integral_mm3": frustum, "total_signed_volume_mm3": volume,
                "float32_total_signed_volume_mm3": audit["float32_signed_volume_mm3"],
                "mesh_to_source_proxy_relative_error": volume/source-1,
                "mesh_to_frustum_relative_error": volume/frustum-1,
                "straight_regular_polygon_volume_factor": factor,
                "residual_after_polygon_factor": volume/(frustum*factor)-1,
                "max_float32_displacement_mm": audit["max_float32_displacement_mm"],
                "different_fiber_clearance_lower_bound_mm": clearances[mode]["minimum_clearance_lower_bound_mm"]-2*audit["max_float32_displacement_mm"],
                "same_fiber_self_intersection_certified_absent": False, "smooth_circle_normal_half_bin_deg": 180./n}
            row = {"array_prefix": "fiber_0000", "fiber_id": p.fiber_id, "material_id": p.material_id,
                   "profile_sha256": p.sha256, "mesh_sha256": mesh.sha256,
                   "radial_segments": n, "buffer_audit": audit, "geometry_summary": mesh.summary()}
            mesh_rows[(n, mode)] = [{k: v for k, v in row.items() if k not in ("array_prefix", "geometry_summary")}]
            manifest = {"schema_version": "variable_radius_mesh_buffers_v5.0", "length_unit": "mm",
                "initial_normal": [0., 0., 1.], "vertices_dtype": "float32", "faces_dtype": "uint32",
                "render_shading_normals": "flat geometric triangle normals",
                "arrays_sha256": sha(folder/"renderer_buffers.npz"), "fibers": [row],
                "summary": summary, "clearance_source": clearances[mode]}
            dump(folder/"mesh_manifest.json", manifest)
            geometry["mesh_levels"][str(n)][mode] = {**summary,
                "mesh_manifest": (folder/"mesh_manifest.json").relative_to(root).as_posix()}
    dump(root/"geometry_metrics.json", geometry)
    profiles = [p for ps in profile_sets.values() for p in ps]
    bounds = np.stack((np.min([np.min(p.points_mm-p.node_radius_mm[:, None], axis=0) for p in profiles], axis=0),
                       np.max([np.max(p.points_mm+p.node_radius_mm[:, None], axis=0) for p in profiles], axis=0))).tolist()
    configs = {light: asdict(RenderConfig(resolution=3, spp=2,
                    mode="transmission" if light == "T45" else "reflection")) for light in LIGHTS}
    metrics = {"schema_version": "variable_radius_optics_experiment_v5.0",
        "status": "rendered" if rendered else "skipped", "states": list(STATES), "lights": list(LIGHTS),
        "radial_segments": list(RADIALS), "wavelengths_nm": list(WAVES), "seeds": list(SEEDS),
        "resolution": 3, "spp": 2, "radiance_axes": ["radial_segments", "state", "light", "wavelength_nm", "seed", "row", "column"],
        "radiance_channel": "RGB channel 0; channel agreement checked before saving", "union_bounds_mm": bounds,
        "lighting_configs": configs, "actual_render_count": 0, "records": [], "comparisons": [],
        "spectral_radiance_sha256": None, "primary_radius_family_size": 3,
        "primary_radius_radial_segments": RADIALS[-1], "refinement_family_size": 6,
        "fixture_without_renderer_calls": True}
    producer = {"schema_version": "variable_radius_experiment_v5.0", "status": "passed",
        "source_sha256": {"textile_sim/variable_radius.py": sha(ROOT/"textile_sim/variable_radius.py")},
        "input_sha256": {"analytic_fixture_definition": "d"*64},
        "input_hashes_unchanged": True, "source_hashes_unchanged": True,
        "requested_render": rendered, "planned_render_count": 48 if rendered else 0,
        "actual_render_count": 48 if rendered else 0, "resolution": 3, "spp": 2,
        "replicates": 4, "radial_segments": list(RADIALS), "wavelengths_nm": list(WAVES),
        "completed_batches": [], "fixture_without_renderer_calls": True}
    if rendered:
        raw = np.empty((2, 2, 3, 1, 4, 3, 3), dtype=np.float32)
        material = MaterialSpectrum.from_absorption("synthetic-fixture", (450., 650.), 1.5, 3.,
                                        source="Analytic verifier fixture; no rendering performed")
        optical = material.at(550.)
        entry = {"material": material.to_dict(), "wavelength_nm": 550., "n_real": optical["n_real"],
            "kappa": optical["kappa"], "absorption_per_mm": optical["absorption_per_mm"],
            "sigma_t_per_scene_unit": optical["absorption_per_mm"], "albedo": 0.,
            "kappa_over_n": optical["kappa"]/optical["n_real"], "background_n": 1., "max_kappa_ratio": .01,
            "absorbing_medium_installed": True}
        for ri, n in enumerate(RADIALS):
            for si, state in enumerate(STATES):
                for li, light in enumerate(LIGHTS):
                    scene = {"schema_version": "textile.closed_mesh_volume_optics/5.0",
                        "scene_length_unit": "mm", "wavelength_unit": "vacuum_nm", "wavelength_nm": 550.,
                        "triangle_geometric_normals_only": True, "meshes": mesh_rows[(n, state)],
                        "materials": {"synthetic-fixture": entry}, "render_config": configs[light],
                        "rig": {"bounds_mm": bounds, "test_rig": light}, "fixture_without_renderer_calls": True}
                    scene["scene_sha256"] = hashlib.sha256(canon(scene).encode()).hexdigest()
                    scene_name = f"scenes/{ri}_{si}_{li}.json"
                    dump(root/"optics"/scene_name, scene)
                    for ki, seed in enumerate(SEEDS):
                        image = np.array((1+ri*.1)*(1+si*.03)*(li+1)*(ki+1.1)*(1+.01*np.arange(9).reshape(3, 3)), dtype=np.float32)
                        raw[ri, si, li, 0, ki] = image
                        metrics["records"].append({"radial_segments": n, "state": state, "light": light,
                            "wavelength_nm": 550., "seed": seed, "array_index": [ri, si, li, 0, ki],
                            "actual_render_count": 1, "spp": 2, "scene_metadata_file": scene_name,
                            "scene_sha256": scene["scene_sha256"], "raw_float32_sha256": array_sha(np.repeat(image[..., None], 3, axis=-1)),
                            "saved_scalar_sha256": array_sha(image), "saved_scalar_mean_radiance": float(image.astype(float).mean())})
                    producer["completed_batches"].append({"radial_segments": n, "state": state, "light": light,
                        "wavelength_nm": 550., "actual_render_count": 4})
        np.savez_compressed(root/"optics/spectral_radiance.npz", radiance=raw)
        metrics["spectral_radiance_sha256"] = sha(root/"optics/spectral_radiance.npz")
        metrics["actual_render_count"] = 48
        means = raw.astype(float).mean(axis=(-2, -1))
        def contrast(a, b, family):
            av, bv = a.mean(axis=0), b.mean(axis=0)
            return {"mean_before": av.tolist(), "mean_after": bv.tolist(),
                "relative_mean_change_percent": (100*(bv-av)/av).tolist(),
                "paired_95": paired_mean_interval(a, b),
                "paired_bonferroni": paired_mean_interval(a, b, 1-.05/family) if family else None,
                "bonferroni_family_size": family}
        for ri, n in enumerate(RADIALS):
            for li, light in enumerate(LIGHTS):
                metrics["comparisons"].append({"kind": "radius", "radial_segments": n, "light": light,
                    "reference_state": STATES[0], "state": STATES[1],
                    **contrast(means[ri, 0, li].T, means[ri, 1, li].T, 3 if ri == 1 else None)})
        for si, state in enumerate(STATES):
            for li, light in enumerate(LIGHTS):
                metrics["comparisons"].append({"kind": "radial_refinement", "coarse_radial_segments": 8,
                    "fine_radial_segments": 12, "state": state, "light": light,
                    **contrast(means[0, si, li].T, means[1, si, li].T, 6)})
    dump(root/"optics/optical_metrics.json", metrics)
    dump(root/"experiment_manifest.json", producer)
    ledger(root)


class VariableRadiusArtifactTests(unittest.TestCase):
    def setUp(self):
        base = ROOT/"scratch_runs"
        base.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name)/"artifact"
        fixture(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_saved_scalar_fixture_verifies_without_renderer_calls(self):
        result = verifier.run(self.root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["optics"]["verified_saved_render_count"], 48)
        self.assertFalse(result["source_input"]["external_source_inputs_rechecked"])

    def test_no_render_fixture_verifies_without_radiance(self):
        other = Path(self.temporary.name)/"skipped"
        fixture(other, rendered=False)
        result = verifier.run(other)
        self.assertEqual(result["optics"]["status"], "skipped")
        self.assertEqual(result["optics"]["verified_saved_render_count"], 0)

    def test_coherently_rehashed_wrong_radius_law_is_rejected(self):
        folder = self.root/"profiles"/STATES[1]
        p = load_variable_radius_profiles(folder)[0]
        changed = replace(p, segment_radius_mm=p.segment_radius_mm*1.08)
        for file in folder.iterdir():
            file.unlink()
        save_variable_radius_profiles(folder, (changed,))
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "radius law"):
            verifier.run(self.root)

    def test_rehashed_moved_renderer_vertex_is_rejected(self):
        folder = self.root/"meshes/radial_008"/STATES[0]
        with np.load(folder/"renderer_buffers.npz", allow_pickle=False) as stored:
            arrays = {key: stored[key] for key in stored.files}
        arrays["fiber_0000/vertices_mm"][0, 0] += .01
        np.savez_compressed(folder/"renderer_buffers.npz", **arrays)
        meta = json.loads((folder/"mesh_manifest.json").read_text())
        meta["arrays_sha256"] = sha(folder/"renderer_buffers.npz")
        meta["fibers"][0]["buffer_audit"]["vertices_float32_sha256"] = array_sha(arrays["fiber_0000/vertices_mm"])
        dump(folder/"mesh_manifest.json", meta)
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "renderer vertices"):
            verifier.run(self.root)

    def test_rehashed_nonfinite_radiance_is_rejected(self):
        path = self.root/"optics/spectral_radiance.npz"
        with np.load(path, allow_pickle=False) as stored:
            raw = stored["radiance"]
        raw[0, 0, 0, 0, 0, 0, 0] = np.nan
        np.savez_compressed(path, radiance=raw)
        metrics = json.loads((self.root/"optics/optical_metrics.json").read_text())
        metrics["spectral_radiance_sha256"] = sha(path)
        dump(self.root/"optics/optical_metrics.json", metrics)
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            verifier.run(self.root)

    def test_rehashed_fabricated_bonferroni_interval_is_rejected(self):
        path = self.root/"optics/optical_metrics.json"
        metrics = json.loads(path.read_text())
        metrics["comparisons"][-1]["paired_bonferroni"]["interval_low"][0] += .4
        dump(path, metrics)
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "Bonferroni"):
            verifier.run(self.root)

    def test_rehashed_duplicate_seed_record_is_rejected(self):
        path = self.root/"optics/optical_metrics.json"
        metrics = json.loads(path.read_text())
        metrics["records"][-1] = metrics["records"][0]
        dump(path, metrics)
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "duplicated render"):
            verifier.run(self.root)

    def test_rehashed_truncated_zip_is_rejected(self):
        folder = self.root/"meshes/radial_008"/STATES[0]
        path = folder/"renderer_buffers.npz"
        # Remove the ZIP end-of-central-directory marker, then deliberately
        # update both advertised byte ledgers: consistent checksums are not
        # evidence that the scientific array archive can be read completely.
        content = path.read_bytes()
        self.assertEqual(content[-22:-18], b"PK\x05\x06")
        path.write_bytes(content[:-22])
        meta = json.loads((folder/"mesh_manifest.json").read_text())
        meta["arrays_sha256"] = sha(path)
        dump(folder/"mesh_manifest.json", meta)
        ledger(self.root)
        with self.assertRaisesRegex(ValueError, "invalid numeric archive"):
            verifier.run(self.root)


if __name__ == "__main__":
    unittest.main()
