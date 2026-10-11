"""Small numerical oracles for structure-map display semantics (no beauty rendering)."""
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np

from visualization.render_structure_figures import (
    BACKGROUND, UNDEFINED_ORIENTATION, antialias_straight_rgba,
    array_descriptor, create_display_maps, nice_scale_length_mm,
    orientation_angle, save_npz_checked,
)


def _maps(normal, tangent, height=None, valid=None):
    n, t = np.asarray(normal, float), np.asarray(tangent, float)
    shape = n.shape[:-1]
    valid = np.ones(shape, bool) if valid is None else np.asarray(valid, bool)
    return {"valid_mask": valid, "world_normal": n, "world_tangent": t,
            "height_mm": np.zeros(shape) if height is None else np.asarray(height, float),
            "coverage": valid.astype(np.float32), "material_index": np.where(valid, 0, -1)}


class StructuralDisplayOracles(unittest.TestCase):
    def test_world_normal_rgb_has_no_gamma_or_axis_permutation(self):
        normals = np.array([[[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0]]], float)
        tangents = np.broadcast_to([1, 0, 0], normals.shape)
        maps = _maps(normals, tangents)
        display, _ = create_display_maps(maps, maps, 1, [-10, 10])
        np.testing.assert_array_equal(display["normal_rgba"][..., :3], (normals + 1) / 2)

    def test_orientation_is_headless_and_uses_world_xy(self):
        angles = np.array([.0, .17, .7, math.pi / 2, math.pi - .02])
        t = np.stack((np.cos(angles), np.sin(angles), np.full_like(angles, .6)), axis=-1)[None]
        valid = np.ones((1, len(angles)), bool)
        a, d = orientation_angle(t, valid)
        b, e = orientation_angle(-t, valid)
        np.testing.assert_allclose(a, b, atol=1e-14)
        np.testing.assert_allclose(a[0], angles, atol=1e-14)
        np.testing.assert_array_equal(d, e)

    def test_vertical_tangent_is_undefined_without_inventing_angle(self):
        maps = _maps([[[0, 0, 1]]], [[[0, 0, 1]]])
        display, stats = create_display_maps(maps, maps, 1, [-10, 10])
        self.assertTrue(np.isnan(display["orientation_angle_rad"][0, 0]))
        self.assertFalse(display["orientation_defined_mask"][0, 0])
        np.testing.assert_allclose(display["orientation_rgba"][0, 0, :3], UNDEFINED_ORIENTATION)
        self.assertEqual(display["orientation_rgba"][0, 0, 3], 1)
        self.assertEqual(stats["sample_orientation_undefined_hits"], 1)

    def test_antialias_rgba_is_straight_and_composes_once(self):
        rgb = np.array([[[1, 0, 0], [0, 1, 0]], [[np.nan] * 3, [np.nan] * 3]])
        valid = np.array([[True, True], [False, False]])
        rgba = antialias_straight_rgba(rgb, valid, 2)[0, 0]
        np.testing.assert_array_equal(rgba, [.5, .5, 0, .5])
        composite = rgba[:3] * rgba[3] + BACKGROUND * (1 - rgba[3])
        expected = np.where(valid[..., None], rgb, BACKGROUND).mean(axis=(0, 1))
        np.testing.assert_allclose(composite, expected, rtol=0, atol=1e-12)

    def test_all_miss_rgba_is_zero_and_never_nan(self):
        rgba = antialias_straight_rgba(np.full((4, 4, 3), np.nan), np.zeros((4, 4), bool), 2)
        np.testing.assert_array_equal(rgba, np.zeros((2, 2, 4)))

    def test_invalid_antialias_sample_factor_rejected(self):
        for bad in (0, -1, 1.5, True):
            with self.subTest(factor=bad), self.assertRaises(ValueError):
                antialias_straight_rgba(np.zeros((2, 2, 3)), np.ones((2, 2), bool), bad)

    def test_height_range_shared_and_cannot_silently_clip(self):
        maps = _maps([[[0, 0, 1], [0, 0, 1]]], [[[1, 0, 0], [1, 0, 0]]], [[-.01, .01]])
        display, stats = create_display_maps(maps, maps, 1, [-10, 10])
        np.testing.assert_array_equal(display["height_rgba"][0, :, 0], [0, 1])
        self.assertEqual(stats["height_clipped_samples"], 0)
        with self.assertRaisesRegex(ValueError, "clips"):
            create_display_maps(maps, maps, 1, [-5, 5])

    def test_material_id_uses_integer_center_without_averaging(self):
        center = _maps([[[0, 0, 1]]], [[[1, 0, 0]]])
        center["material_index"][0, 0] = 1
        samples = {key: np.repeat(np.repeat(value, 2, axis=0), 2, axis=1) for key, value in center.items()}
        samples["material_index"][:] = 0
        display, _ = create_display_maps(center, samples, 2, [-10, 10])
        np.testing.assert_allclose(display["material_rgba"][0, 0], [213 / 255, 94 / 255, 0, 1])

    def test_inconsistent_raw_coverage_is_rejected(self):
        maps = _maps([[[0, 0, 1]]], [[[1, 0, 0]]])
        maps["coverage"][:] = .5
        with self.assertRaisesRegex(ValueError, "coverage"):
            create_display_maps(maps, maps, 1, [-10, 10])

    def test_scale_bars_use_real_mm(self):
        for width, expected in ((1.08, .2), (.22, .05), (.04, .005)):
            with self.subTest(width=width):
                self.assertAlmostEqual(nice_scale_length_mm(width), expected)
                self.assertLessEqual(nice_scale_length_mm(width), .23 * width)

    def test_saved_display_npz_roundtrip_and_crc(self):
        values = {"a": np.array([[1, np.nan]], np.float32), "mask": np.array([[True, False]])}
        temporary_root = Path(__file__).resolve().parents[1] / "scratch_runs"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            path = Path(folder) / "display.npz"
            descriptor = save_npz_checked(path, values)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
            with np.load(path, allow_pickle=False) as saved:
                for name in values:
                    self.assertEqual(descriptor["arrays"][name], array_descriptor(saved[name]))
            self.assertEqual(len(descriptor["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
