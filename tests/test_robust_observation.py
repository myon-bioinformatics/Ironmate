import ast
import itertools
from pathlib import Path

import pytest
from scripts.observable_choice import Prototype
from scripts.robust_observation import BoundedErrorChoice, temporal_prediction


def engine(width, codes):
    return BoundedErrorChoice([Prototype(str(c), c, ((1 << width)-1) ^ c)
                               for c in codes], width)


@pytest.mark.parametrize('width,budget', [(3, 1), (5, 2)])
def test_all_masks_and_bounded_flip_patterns(width, budget):
    e = engine(width, [0, (1 << width)-1])
    for truth in (0, e.universe):
        for observed in range(1 << width):
            for noise in range(1 << width):
                if noise & ~observed or noise.bit_count() > budget:
                    continue
                r = e.query(truth ^ noise, observed, budget)
                assert str(truth) in [c['name'] for c in r['candidates']]
                if r['status'] == 'unique':
                    assert r['candidates'][0]['name'] == str(truth)
                if observed == e.universe:
                    assert r['status'] == 'unique'


def test_abstention_and_distance_three_does_not_correct_two():
    e = engine(3, [0, 7])
    assert e.query(0, 0)['status'] == 'ambiguous'
    assert e.query(3, 7, 2)['status'] == 'ambiguous'
    assert e.query(3, 7, 1)['candidates'][0]['name'] == '7'
    assert e.query(7, 0) == e.query(0, 0)
    assert engine(3, [0]).query(7, 7)['status'] == 'rejected'


def test_zero_error_matches_existing_index_exhaustively():
    e = engine(4, range(16))
    for active, observed in itertools.product(range(16), repeat=2):
        expected = e.index.query(active, observed)
        actual = e.query(active, observed, 0)
        assert actual['status'] == expected['status']
        assert [c['name'] for c in actual['candidates']] == [
            c['name'] for c in expected['candidates']]


def test_probe_cost_distance_and_branch_counts():
    e = engine(4, [0, 15])
    assert e.next_probe(0, 0, 0, grid_width=4, fovea=3)['bit'] == 3
    assert e.next_probe(0, 0, 0, grid_width=4, fovea=3,
                        costs={3: 100})['bit'] == 2
    assert e.next_probe(0, 0, 1, grid_width=4) is None
    for active, observed in itertools.product(range(16), repeat=2):
        p = e.next_probe(active, observed, 0, grid_width=2)
        if p:
            bit = 1 << p['bit']
            for v, key in [(0, 'zero_survivors'), (1, 'one_survivors')]:
                assert p[key] == len(e.query((active & ~bit) | (bit if v else 0),
                                            observed | bit, 0)['candidates'])


def test_temporal_measured_zero_unknown_and_current_priority():
    r = temporal_prediction(0, 2, 7, 7, width=4, height=1)
    assert r == dict(board=5, observed_mask=2, prediction_mask=5)
    r = temporal_prediction(0, 0, 0, 1, width=4, height=1, dx=1)
    assert r['board'] == 0 and r['prediction_mask'] == 2
    assert temporal_prediction(0, 0, 15, 0, width=4, height=1)['board'] == 0


def test_temporal_all_single_pixels_and_translations():
    for b in range(12):
        for dx, dy in itertools.product(range(-4, 5), range(-3, 4)):
            r = temporal_prediction(0, 0, 1 << b, 1 << b,
                                    width=4, height=3, dx=dx, dy=dy)
            x, y = b % 4 + dx, b // 4 + dy
            expected = 1 << (y * 4 + x) if 0 <= x < 4 and 0 <= y < 3 else 0
            assert r['board'] == r['prediction_mask'] == expected


def test_validation_and_integer_core():
    for p in [Prototype('partial', 1), Prototype('or', 0, 3, (4,))]:
        with pytest.raises(ValueError): BoundedErrorChoice([p], 3)
    with pytest.raises(ValueError): engine(3, [0, 0])
    e = engine(3, [0, 7])
    with pytest.raises(ValueError): e.query(8, 0)
    with pytest.raises(ValueError): e.query(0, 0, -1)
    with pytest.raises(ValueError): e.next_probe(0, 0, grid_width=0)
    with pytest.raises(ValueError): e.next_probe(0, 0, grid_width=3, costs={0: -1})
    with pytest.raises(ValueError): temporal_prediction(0, 0, 0, 0, width=0, height=1)
    source = Path('scripts/robust_observation.py').read_text()
    assert not any(isinstance(n, ast.Mult) for n in ast.walk(ast.parse(source)))
