"""Corruption checks for the independent reader; no scene or radiance renders."""
import unittest

import matplotlib
import numpy as np

from visualization.review_structure_figures import check_display_arrays, check_physical_arrays


def plane_arrays():
    h, w = 3, 4
    x, y = np.meshgrid(((np.arange(w)+.5)/w-.5)*2, (.5-(np.arange(h)+.5)/h)*1.5)
    p = np.stack((x, y, np.full_like(x, .25)), axis=-1).astype(np.float32)
    arrays = {"valid_mask": np.ones((h, w), dtype=bool), "position_mm": p,
        "height_mm": p[..., 2].copy(), "ray_distance_mm": np.full((h, w), 1.75, np.float32),
        "world_normal": np.broadcast_to([0., 0., 1.], p.shape).astype(np.float32).copy(),
        "world_tangent": np.broadcast_to([1., 0., 0.], p.shape).astype(np.float32).copy(),
        "object_index": np.zeros((h, w), dtype=np.int32)}
    camera = {"origin_mm": [0., 0., 2.], "right": [1., 0., 0.], "up": [0., 1., 0.],
              "view_direction": [0., 0., -1.], "width_mm": 2., "height_mm": 1.5}
    return arrays, camera


def display_fixture():
    valid = np.array([[True, False, True, True], [False, False, True, True]])
    samples = {"valid_mask": valid}
    for name, vector in (("world_normal", [0., 0., 1.]), ("world_tangent", [1., 0., 0.])):
        a = np.full((*valid.shape, 3), np.nan, np.float32)
        a[valid] = vector
        samples[name] = a
    samples["height_mm"] = np.where(valid, 0., np.nan).astype(np.float32)
    center = {"valid_mask": np.array([[False, True]]), "coverage": np.array([[.25, 1.]], np.float32),
        "height_mm": np.array([[np.nan, 0.]], np.float32),
        "world_tangent": np.array([[[np.nan]*3, [1., 0., 0.]]], np.float32),
        "material_index": np.array([[-1, 0]], np.int32)}
    encoding = {"height": {"shared_limits_um": [0., 1.], "colormap": "gray"},
        "orientation": {"projection_threshold": 1e-8, "colormap": "twilight_shifted",
            "colormap_lut_size": 8, "colormap_phase_fraction": 0., "undefined_rgb": [.45]*3},
        "background_rgb": [.9]*3,
        "material": {"palette_hex": ["#FF0000"], "mixed_proxy_rgb": [.45]*3}}
    display = {}
    constant_colors = {"normal": [.5, .5, 1.], "height": [0., 0., 0.],
                       "orientation": matplotlib.colormaps["twilight_shifted"](0.)[:3]}
    for name, color in constant_colors.items():
        rgba = np.empty((1, 2, 4), np.float32)
        rgba[..., :3] = color
        rgba[..., 3] = center["coverage"]
        display[name+"_rgba"] = rgba
    display.update({"orientation_angle_rad": np.array([[np.nan, 0.]], np.float32),
                    "orientation_defined_mask": np.array([[False, True]]),
                    "material_rgba": np.array([[[0., 0., 0., 0.], [1., 0., 0., 1.]]], np.float32)})
    return center, samples, display, encoding


class IndependentStructureReviewTests(unittest.TestCase):
    def test_height_is_world_coordinate_not_ray_distance(self):
        arrays, camera = plane_arrays()
        self.assertEqual(check_physical_arrays(arrays, camera, label="plane")["valid_count"], 12)
        arrays["height_mm"] = arrays["ray_distance_mm"].copy()
        with self.assertRaisesRegex(ValueError, "height is not actual world Z"):
            check_physical_arrays(arrays, camera, label="wrong depth")

    def test_image_row_reflection_breaks_world_ray_coordinates(self):
        arrays, camera = plane_arrays()
        arrays["position_mm"][..., 1] *= -1
        with self.assertRaisesRegex(ValueError, "world position/ray mismatch"):
            check_physical_arrays(arrays, camera, label="Y reflection")

    def test_fractional_category_is_rejected_even_if_values_look_integer(self):
        arrays, camera = plane_arrays()
        arrays["object_index"] = arrays["object_index"].astype(np.float32)
        with self.assertRaisesRegex(ValueError, "categorical integer"):
            check_physical_arrays(arrays, camera, label="averaged categories")

    def test_straight_rgba_not_double_coverage(self):
        center, samples, display, encoding = display_fixture()
        report = check_display_arrays(center, samples, display, encoding, 2, label="quarter-covered pixel")
        self.assertEqual(report["partial_coverage_pixel_count"], 1)
        display["normal_rgba"][..., :3] *= display["normal_rgba"][..., 3:4]
        with self.assertRaisesRegex(ValueError, "straight-alpha error"):
            check_display_arrays(center, samples, display, encoding, 2, label="double coverage")


if __name__ == "__main__":
    unittest.main()
