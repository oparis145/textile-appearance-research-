"""Independent topology/endpoint checks for the v2 rectangular draft module."""
import unittest

import numpy as np

from textile_sim.weave_draft import WeaveDraft, cyclic_run_lengths, periodic_crossing_height


class WeaveDraftTests(unittest.TestCase):
    def test_rectangular_periodic_indexing_including_negative_padding(self):
        matrix = ((1, 0, 1, 0, 0, 1), (0, 1, 0, 1, 1, 0), (1, 1, 0, 0, 1, 0))
        draft = WeaveDraft(matrix)
        self.assertEqual(draft.shape, (3, 6))
        self.assertEqual(draft.crossing(-1, -1), False)
        self.assertEqual(draft.crossing(6, 3), True)
        for i in range(-9, 12):
            for j in range(-12, 18):
                self.assertEqual(draft.crossing(j, i), bool(matrix[i % 3][j % 6]))
        np.testing.assert_array_equal(draft.expanded(6, 12), np.tile(matrix, (2, 2)))

    def test_invalid_matrix_does_not_silently_cast(self):
        for invalid in ([], [[]], [[0, 1], [1]], [[0, 2]], [[0., 1.]], [[0, float("nan")]], [["0", "1"]]):
            with self.subTest(matrix=invalid):
                with self.assertRaises(ValueError):
                    WeaveDraft(invalid)
        with self.assertRaises(ValueError):
            WeaveDraft.from_dict({"matrix": [[0, 1]], "row_axis": "warp"})

    def test_family_exchange_preserves_physical_over_under(self):
        draft = WeaveDraft(((1, 0, 1), (0, 1, 1)))
        other = draft.transposed()
        for i in range(2):
            for j in range(3):
                self.assertNotEqual(draft.crossing(j, i), other.crossing(i, j))
        np.testing.assert_array_equal(other.transposed().as_array(), draft.as_array())

    def test_liftplan_exact_and_groups_identical_warp_schedules(self):
        threading = [0, 1, 0, 2, 1, 2]
        liftplan = [[1, 0, 1], [0, 1, 0], [1, 1, 0], [0, 0, 1]]
        draft = WeaveDraft.from_liftplan(threading, liftplan)
        expected = [[1, 0, 1, 1, 0, 1], [0, 1, 0, 0, 1, 0],
                    [1, 1, 1, 0, 1, 0], [0, 0, 0, 1, 0, 1]]
        np.testing.assert_array_equal(draft.as_array(), expected)
        factored = draft.to_liftplan()
        self.assertEqual(factored["shaft_count"], 3)
        recovered = WeaveDraft.from_liftplan(factored["threading"], factored["liftplan"])
        np.testing.assert_array_equal(recovered.as_array(), expected)
        with self.assertRaises(ValueError):
            WeaveDraft.from_liftplan([0, 3], liftplan)

    def test_circular_float_lengths_handle_seam_and_unbound_yarns(self):
        self.assertEqual(cyclic_run_lengths([1, 1, 0, 0, 1], 1), (3,))
        self.assertEqual(cyclic_run_lengths([1, 1, 0, 0, 1], 0), (2,))
        self.assertEqual(cyclic_run_lengths([1, 1, 1], 1), (3,))
        self.assertEqual(cyclic_run_lengths([1, 1, 1], 0), ())
        diag = WeaveDraft(((1, 0, 1), (1, 1, 0))).diagnostics()
        self.assertEqual(diag["unbound_warp_indices"], [0])
        self.assertFalse(diag["every_yarn_interlaces_in_repeat"])
        self.assertTrue(WeaveDraft.plain().diagnostics()["every_yarn_interlaces_in_repeat"])

    def test_known_draft_structure(self):
        self.assertEqual(WeaveDraft.plain().diagnostics()["run_lengths"]["warp_value_1_max_run_in_repeat"], 1)
        self.assertEqual(WeaveDraft.twill(2, 2).diagnostics()["run_lengths"]["warp_value_1_max_run_in_repeat"], 2)
        satin = WeaveDraft.satin(5, 2).as_array()
        np.testing.assert_array_equal(np.sum(1-satin, axis=0), np.ones(5))
        np.testing.assert_array_equal(np.sum(1-satin, axis=1), np.ones(5))
        self.assertEqual(WeaveDraft.basket(3, 2).shape, (4, 6))
        with self.assertRaises(ValueError):
            WeaveDraft.satin(6, 2)

    def test_rectangular_crossing_heights_are_exact_for_both_families(self):
        draft = WeaveDraft(((1, 0, 1), (0, 1, 0)))
        for family, pitch, amplitude in (("warp", .13, .025), ("weft", .21, .04)):
            for j in range(7):
                k = np.arange(-8, 9)
                z = periodic_crossing_height(k*pitch, draft=draft, family=family,
                    yarn_index=j, crossing_pitch_mm=pitch, amplitude_mm=amplitude)
                expected = [amplitude*(1 if draft.crossing(j, i) else -1) if family == "warp"
                            else amplitude*(-1 if draft.crossing(i, j) else 1) for i in k]
                np.testing.assert_allclose(z, expected, atol=1e-14)
                for order in (1, 2):
                    derivative = periodic_crossing_height(k*pitch, draft=draft, family=family,
                        yarn_index=j, crossing_pitch_mm=pitch, amplitude_mm=amplitude, derivative=order)
                    np.testing.assert_allclose(derivative, 0., atol=2e-11)

    def test_crimp_is_c2_bounded_and_periodic_with_different_axis_lengths(self):
        draft = WeaveDraft(((1, 0, 1), (0, 1, 0)))
        pitch, amplitude = .17, .036
        for family, period in (("warp", 2), ("weft", 3)):
            kwargs = dict(draft=draft, family=family, yarn_index=0,
                          crossing_pitch_mm=pitch, amplitude_mm=amplitude)
            x = np.linspace(-3*pitch, 7*pitch, 1513)
            y = periodic_crossing_height(x, **kwargs)
            self.assertLessEqual(np.max(np.abs(y)), amplitude+1e-14)
            for derivative in (0, 1, 2):
                a = periodic_crossing_height(x, derivative=derivative, **kwargs)
                b = periodic_crossing_height(x+period*pitch, derivative=derivative, **kwargs)
                np.testing.assert_allclose(a, b, atol=3e-11)
            eps = 1e-7
            # Numerical derivatives supply an independent check of published derivatives.
            center = .371*pitch
            yplus = periodic_crossing_height(center+eps, **kwargs)
            yminus = periodic_crossing_height(center-eps, **kwargs)
            dnum = (yplus-yminus)/(2*eps)
            dexact = periodic_crossing_height(center, derivative=1, **kwargs)
            self.assertAlmostEqual(float(dnum), float(dexact), places=8)
            dplus = periodic_crossing_height(center+eps, derivative=1, **kwargs)
            dminus = periodic_crossing_height(center-eps, derivative=1, **kwargs)
            d2num = (dplus-dminus)/(2*eps)
            d2exact = periodic_crossing_height(center, derivative=2, **kwargs)
            self.assertAlmostEqual(float(d2num), float(d2exact), places=7)


if __name__ == "__main__":
    unittest.main()
