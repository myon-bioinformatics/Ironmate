"""Verify width boundaries without truncating out-of-range fingerprints."""
import unittest
from scripts.adaptive_fingerprint import masked_distance, reduce256


class FingerprintWidthBoundaries(unittest.TestCase):
    def test_highest_bit_is_preserved_and_next_bit_is_rejected(self):
        for width in (8, 64, 256):
            top = 1 << (width - 1)
            with self.subTest(width=width):
                result = masked_distance(top, 0, top, top, width)
                self.assertEqual((result['mismatches'], result['observed']), (1, 1))
                for index in range(4):
                    values = [0, 0, 0, 0]
                    values[index] = 1 << width
                    with self.assertRaises(ValueError):
                        masked_distance(*values, width)

    def test_fine_mask_top_bit_and_out_of_range(self):
        self.assertEqual(reduce256(1 << 255), 1 << 63)
        with self.assertRaises(ValueError):
            reduce256(1 << 256)


if __name__ == '__main__':
    unittest.main()
