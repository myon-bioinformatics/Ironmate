import unittest
from studio_alignment import translate_rgba, invert_translation

CLEAR = (0, 0, 0, 0)
RED = (255, 0, 0, 255)


class AlignmentTests(unittest.TestCase):
    def test_roundtrip_when_content_stays_inside(self):
        src = [CLEAR] * 64
        src[2 * 8 + 2] = RED
        shifted = translate_rgba(8, 8, src, 1, -1)
        self.assertEqual(shifted["clipped_nonfill"], 0)
        restored = invert_translation(8, 8, shifted["pixels"], 1, -1)
        self.assertEqual(restored["pixels"], src)

    def test_clipped_content_cannot_be_recovered(self):
        src = [CLEAR] * 64
        src[3 * 8 + 7] = RED
        shifted = translate_rgba(8, 8, src, 1, 0)
        self.assertEqual(shifted["clipped_nonfill"], 1)
        restored = invert_translation(8, 8, shifted["pixels"], 1, 0)
        self.assertNotEqual(restored["pixels"], src)

    def test_zero_translation_is_identity(self):
        src = [CLEAR] * 64
        src[0] = RED
        self.assertEqual(translate_rgba(8, 8, src, 0, 0)["pixels"], src)


if __name__ == "__main__":
    unittest.main()
