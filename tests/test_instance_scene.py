import ast
from pathlib import Path
import unittest
from scripts.observable_choice import Prototype
from scripts.instance_scene import components, quorum_scene, Detection, Tracker


class InstanceSceneTests(unittest.TestCase):
    def test_components_exhaustive(self):
        for board in range(512):
            remaining = {i for i in range(9) if board & (1 << i)}
            reference = []
            while remaining:
                todo = [min(remaining)]
                found = set()
                while todo:
                    p = todo.pop()
                    if p not in remaining:
                        continue
                    remaining.remove(p)
                    found.add(p)
                    x, y = p % 3, p // 3
                    todo.extend(q for q in remaining if abs(q % 3-x)+abs(q // 3-y) == 1)
                reference.append(sum(1 << p for p in found))
            self.assertEqual(components(board, 3, 3), tuple(reference))

    def test_quorum_and_observation(self):
        ps = [Prototype('sword', 63), Prototype('shield', 3841)]
        r = quorum_scene(ps, 31 | 3841, 65535, width=16, shared=3)
        self.assertEqual(len(r['candidates']), 2)
        self.assertEqual(r['residual'], 0)
        self.assertFalse(quorum_scene(ps, 15, 65535, width=16, shared=3)['candidates'])
        # Unobserved garbage cannot manufacture quorum evidence.
        self.assertFalse(quorum_scene(ps, 63, 3, width=16, shared=3)['candidates'])
        self.assertFalse(quorum_scene([Prototype('empty', 3)], 3, 63, width=6, shared=3)['candidates'])

    def test_shared_leaf_ownership(self):
        r = quorum_scene([Prototype('a', 31), Prototype('b', 31)], 31, 31, width=5, shared=1)
        self.assertEqual(r['residual'], 30)
        self.assertEqual(r['removed'], 0)

    def test_velocity_crossing_birth_death(self):
        def d(x, cls='sword'):
            return Detection(cls, 63, x, 0)
        t = Tracker(5)
        self.assertEqual(t.update([d(0), d(10)]), (0, 1))
        self.assertEqual(t.update([d(3), d(7)]), (0, 1))
        self.assertEqual(t.update([d(4), d(6)]), (1, 0))
        self.assertEqual(t.update([d(9), d(20, 'ring')]), (0, 2))
        self.assertEqual(t.update([]), ())
        self.assertEqual(t.update([d(9)]), (3,))

    def test_core_has_no_multiply_or_float(self):
        tree = ast.parse(Path('scripts/instance_scene.py').read_text())
        self.assertFalse(any(isinstance(n, (ast.Mult, ast.Div, ast.Pow)) for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree)))

    def test_hidden_budget_and_forbidden(self):
        p = [Prototype('a', 255, 256)]
        # Two hidden leaves are allowed when six of eight are measured.
        r = quorum_scene(p, 63, 63, width=9, errors=0)
        self.assertEqual(r['candidates'][0]['hidden'], 192)
        self.assertFalse(quorum_scene(p, 63, 511, width=9, errors=1)['candidates'])
        self.assertFalse(quorum_scene(p, 511, 511, width=9)['candidates'])

    def test_validation_and_touching_limit(self):
        self.assertEqual(len(components(7, 3, 1)), 1)
        for board in (-1, 512):
            with self.assertRaises(ValueError):
                components(board, 3, 3)
        with self.assertRaises(ValueError):
            Tracker().update([Detection('a', 1 << 64, 0, 0)])

    def test_bridge(self):
        import json
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-S', '-m', 'scripts.instance_scene'],
                                input='{"frames": [[], []]}', text=True,
                                capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), {'track_ids': [[], []]})
