import unittest
from studio_image_quality import compare_rgba


def grid(coords, width=8, height=8, color=(255, 0, 0, 255)):
    pixels = [(0, 0, 0, 0)] * (width * height)
    for x, y in coords:
        pixels[y * width + x] = color
    return pixels


class ImageQualityTests(unittest.TestCase):
    def test_identical(self):
        a = grid({(1, 1), (1, 2)})
        m = compare_rgba(8, 8, a, a)
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Aligned_IoU"], 1)
        self.assertEqual(m["RGBA_L1_Similarity"], 1)
        self.assertEqual((m["Alignment_dx"], m["Alignment_dy"]), (0, 0))

    def test_shift_and_realign(self):
        a = grid({(1, 1), (1, 2)})
        b = grid({(2, 1), (2, 2)})
        m = compare_rgba(8, 8, a, b)
        self.assertEqual(m["IoU"], 0)
        self.assertEqual(m["Aligned_IoU"], 1)
        self.assertEqual((m["Alignment_dx"], m["Alignment_dy"]), (-1, 0))
        self.assertGreater(m["RGBA_L1_Similarity"], 0)

    def test_missing_pixel(self):
        a = grid({(1, 1), (1, 2)})
        b = grid({(1, 1)})
        m = compare_rgba(8, 8, a, b)
        self.assertLess(m["IoU"], 1)
        self.assertLess(m["Aligned_IoU"], 1)

    def test_color_difference_not_hidden_by_mask(self):
        a = grid({(1, 1)}, color=(255, 0, 0, 255))
        b = grid({(1, 1)}, color=(0, 0, 255, 255))
        m = compare_rgba(8, 8, a, b)
        self.assertEqual(m["IoU"], 1)
        self.assertLess(m["RGBA_L1_Similarity"], 1)


if __name__ == "__main__":
    unittest.main()
