import unittest
from studio_shape_metrics import metrics


class ShapeMetricTests(unittest.TestCase):
    def test_identical_even_isolated_pixel(self):
        m = metrics(8, 8, {12}, {12})
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Symmetric_Near_Field"], 1)

    def test_symmetry(self):
        a, b = {8, 9, 10}, {9, 10, 11}
        x, y = metrics(8, 8, a, b), metrics(8, 8, b, a)
        self.assertEqual(x, y)

    def test_near_miss(self):
        m = metrics(8, 8, {8, 16}, {9, 17})
        self.assertEqual(m["IoU"], 0)
        self.assertGreater(m["Symmetric_Near_Field"], 0)

    def test_disjoint_far(self):
        m = metrics(8, 8, {0}, {63})
        self.assertEqual(m["Symmetric_Near_Field"], 0)

    def test_weighted_zero_undefined(self):
        m = metrics(8, 8, {0}, {1}, [0] * 64)
        self.assertIsNone(m["Energy_Dice"])

    def test_empty(self):
        m = metrics(8, 8, set(), set())
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Symmetric_Near_Field"], 1)


if __name__ == "__main__":
    unittest.main()
