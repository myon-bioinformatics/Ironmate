import ast, random, unittest
from pathlib import Path
from scripts import adaptive_fingerprint as f


class AdaptiveTests(unittest.TestCase):
    def test_lazy_gate(self):
        def forbidden():
            self.fail('fine encoder called on easy negative')
        self.assertFalse(f.adaptive_match(0, (1 << 64) - 1, forbidden)['escalated'])

    def test_collision_and_ties(self):
        a, b = 1, 1 << 32  # separate fine shells, same coarse cell
        r = f.adaptive_match(f.reduce256(a), f.reduce256(b), lambda: (a, b))
        self.assertEqual(r['coarse']['distance'], 0)
        self.assertEqual(r['fine']['distance'], 2)
        r = f.adaptive_match(0, 0, lambda: (0, 0))
        self.assertEqual(len(r['fine']['shifts']), 32)
        self.assertEqual(len(r['local_candidates']), 32)

    def test_exhaustive_reference_random(self):
        rng = random.Random(1301)
        for _ in range(100):
            a, b = rng.getrandbits(256), rng.getrandbits(256)
            r = f.adaptive_match(f.reduce256(a), f.reduce256(b), lambda: (a,b), 64)
            scores = []
            for shift in range(32):
                # Independent bit-index permutation, no ring rotation helper.
                moved = sum(1 << ((i // 32) * 32 + (i + shift) % 32)
                            for i in range(256) if b & (1 << i))
                scores.append((a ^ moved).bit_count())
            self.assertEqual(r['fine']['distance'], min(scores))
            self.assertEqual(r['fine']['shifts'], tuple(i for i,v in enumerate(scores) if v == min(scores)))

    def test_masks_and_fusion(self):
        self.assertEqual(f.masked_distance(0, 3, 1, 2)['defined'], False)
        self.assertEqual(f.masked_distance(0, 3, 1, 1)['mismatches'], 1)
        self.assertEqual(f.fuse64(3, 5), 39)
        for bad in (-1, True, 1 << 256):
            with self.assertRaises(ValueError):
                f.reduce256(bad)
        with self.assertRaises(ValueError):
            f.adaptive_match(0, 0, lambda: (1, 0))

    def test_operator_contract(self):
        tree = ast.parse(Path(f.__file__).read_text())
        self.assertFalse(any(isinstance(n, (ast.Mult, ast.Div, ast.Pow)) for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n, ast.Constant) and type(n.value) is float for n in ast.walk(tree)))
