"""Independent pixel-graph oracles; no production topology/ring code in oracle."""
import ast
import copy
import json
import random
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

from scripts import littlebit_jev_5way_survey as s
from scripts import littlebit_jev_3way_survey as legacy


def oracle(board, w, h):
    points = {(x, y) for y in range(h) for x in range(w) if board & (1 << (y*w+x))}
    def components(points, diagonal):
        rem, groups = set(points), []
        while rem:
            seed = rem.pop()
            group, todo = {seed}, deque([seed])
            while todo:
                x, y = todo.popleft()
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                               *(((-1, -1), (-1, 1), (1, -1), (1, 1)) if diagonal else ())):
                    nb = x+dx, y+dy
                    if nb in rem:
                        rem.remove(nb)
                        group.add(nb)
                        todo.append(nb)
            groups.append(group)
        return groups
    foreground = components(points, True)
    background = components({(x, y) for x in range(-1, w+1) for y in range(-1, h+1)} - points, False)
    return len(foreground), len(background)-1


def test_exhaustive_4x4_topology_against_independent_foreground8_background4_bfs():
    for board in range(1 << 16):
        result = s.compute_bitboard_topology_and_betti(board, 4, 4)
        b0, b1 = oracle(board, 4, 4)
        assert (result['b0_clusters'], result['b1_holes'], result['chi']) == (b0, b1, b0-b1), board


@pytest.mark.parametrize('w,h', [(1, 1), (1, 9), (9, 1), (3, 7), (17, 5)])
def test_random_rectangular_topology_boundaries(w, h):
    rng = random.Random(66)
    for _ in range(60):
        board = rng.getrandbits(w*h)
        result = s.compute_bitboard_topology_and_betti(board, w, h)
        assert (result['b0_clusters'], result['b1_holes']) == oracle(board, w, h)


def test_l_shape_must_not_gain_false_diagonal_cycle():
    result = s.compute_bitboard_topology_and_betti(0b0111, 2, 2)
    assert (result['V'], result['E'], result['F'], result['chi'], result['b1_holes']) == (3, 2, 0, 1, 0)


@pytest.mark.parametrize('board,w,h', [(-1, 2, 2), (16, 2, 2), (True, 1, 1), (0, 0, 2), (0, 2, -1)])
def test_invalid_topology_inputs(board, w, h):
    with pytest.raises(ValueError):
        s.compute_bitboard_topology_and_betti(board, w, h)


def test_known_fixture_topologies_are_separate_from_reconstruction_accuracy():
    expected = [(1, 0), (1, 0), (1, 1), (1, 2), (1, 0), (1, 0), (3, 0), (2, 0)]
    for name, target in zip(s.SCENARIOS, expected):
        _, truth = s.scenario_data(name, random.Random(1))
        board = s.pack_to_bitboard(truth, 32, 32)
        result = s.compute_bitboard_topology_and_betti(board, 32, 32)
        assert (result['b0_clusters'], result['b1_holes']) == target


def test_legacy_fwht_equivalence_and_ternary_distance():
    rng = random.Random(9)
    for _ in range(40):
        values = [rng.randint(-500, 500) for _ in range(8)]
        assert s.fwht8_add_only(values) == legacy.fwht8_add_only(values)
        for _ in range(10):
            a, b = [[rng.choice((-1, 0, 1)) for _ in range(7)] for _ in range(2)]
            ap, an, bp, bn = [sum(1 << i for i, value in enumerate(v) if value == sign)
                              for v in (a, b) for sign in (1, -1)]
            assert s.ternary_diff(ap, an, bp, bn) == sum(abs(x-y) for x, y in zip(a, b))


def test_all_integer_kernel_definitions_have_no_mult_float_div_power():
    tree = ast.parse(Path(s.__file__).read_text())
    for node in tree.body:
        if getattr(node, 'name', None) == 'evaluation':
            break
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        for child in ast.walk(node):
            assert not (isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Mult, ast.Div, ast.Pow))), node.name
            assert not (isinstance(child, ast.Constant) and isinstance(child.value, float)), node.name


def test_fixed_point_cycle_lock_and_reciprocity():
    cycle = {0: 2|8, 1: 1|8, 4: 2|4, 5: 1|4}
    result = s.reconstruct_fixed_point(cycle, 4, 4)
    assert result['nodes'] == {0, 1, 4, 5}
    assert result['converged']
    # Remove one reciprocal direction; no cycle lock, cascade to empty.
    broken = dict(cycle)
    broken[1] = 1
    assert s.reconstruct_fixed_point(broken, 4, 4)['nodes'] == set()
    assert s.reconstruct_fixed_point({3: 2, 4: 1}, 4, 4)['nodes'] == set()
    assert s.reconstruct_fixed_point({0: 2, 1: 2}, 4, 4)['nodes'] == set()


def test_true_convergence_can_take_more_than_three_passes():
    # Weighted degree threshold peels a 1D chain; no unit-square lock.
    w = 20
    history = {i: (1 if i else 0) | (2 if i+1 < w else 0) for i in range(w)}
    result = s.reconstruct_fixed_point(history, w, 1, anisotropy_x_shift=1)
    assert result['nodes'] == set()
    assert result['iterations'] > 3
    assert result['converged']



@pytest.mark.parametrize('slots', [8, 16])
def test_phase_ring_exact_quarter_turn_and_translation(slots):
    rng = random.Random(6)
    w = 19
    for _ in range(80):
        nodes = {rng.randrange(w*w) for _ in range(40)}
        rotated = {(i % w)*w + w-1-i//w for i in nodes}
        a = s.phase_ring_signature(s.pack_to_bitboard(nodes, w, w), w, w, slots)
        b = s.phase_ring_signature(s.pack_to_bitboard(rotated, w, w), w, w, slots)
        assert b['rings'] == tuple(s.rotate_ring(r, slots//4, slots) for r in a['rings'])
        match = s.match_phase_rings(a, b)
        assert match['numerator'] == match['denominator']
        assert (slots - slots//4) in match['shifts']
    nodes = {3*w+4, 3*w+5, 5*w+7, 7*w+8}
    moved = {i + w + 2 for i in nodes}
    assert s.phase_ring_signature(s.pack_to_bitboard(nodes,w,w),w,w,slots) == s.phase_ring_signature(s.pack_to_bitboard(moved,w,w),w,w,slots)


def test_rotation_oracle_returns_ambiguity_and_distractor_does_not_prove_identity():
    result = s.rotation_experiment()
    for row in result['rotations']:
        if row['degrees'] in (0, 90, 180, 270):
            assert row['numerator'] == row['denominator']
    a = s.phase_ring_signature(1, 3, 3)
    assert s.match_phase_rings(a, a)['ambiguous']
    empty = s.phase_ring_signature(0, 3, 3)
    assert s.match_phase_rings(empty, empty)['shifts'] == []
    # Occupancy-only ring signatures are lossy by construction: two concentric
    # squares with different radii have identical support after normalization.
    a = s.phase_ring_signature(s.pack_to_bitboard({0,2,6,8},3,3),3,3)
    b = s.phase_ring_signature(s.pack_to_bitboard({0,4,20,24},5,5),5,5)
    assert s.match_phase_rings(a,b)['numerator'] == s.match_phase_rings(a,b)['denominator']


def test_ring_validation():
    for args in ((1,0,7), (-1,1,8), (256,1,8)):
        with pytest.raises(ValueError):
            s.rotate_ring(*args)
    with pytest.raises(ValueError):
        s.match_phase_rings(s.phase_ring_signature(1,2,2,8), s.phase_ring_signature(1,2,2,16))


def test_venn_partition_exact_vs_approximate_and_no_causal_claim():
    rng = random.Random(4)
    for _ in range(50):
        boards = [rng.getrandbits(25) for _ in range(3)]
        result = s.analyze_venn_and_implication_bitboard(*boards, (1 << 25)-1)
        expected = {format(flags,'03b'): sum(all(bool(b & (1<<i)) == bool(flags & (1<<j))
                                               for j,b in enumerate(boards)) for i in range(25)) for flags in range(8)}
        assert result['venn_counts'] == expected
        assert sum(expected.values()) == 25
        assert result['causal_claim'] is False
    assert s.analyze_venn_and_implication_bitboard(3,7,0,15)['relation_AB'] == 'A_subset_B'
    assert s.analyze_venn_and_implication_bitboard(7,3,0,15)['relation_AB'] == 'B_subset_A'
    assert s.analyze_venn_and_implication_bitboard(3,12,0,15)['relation_AB'] == 'mutually_exclusive'
    result = s.analyze_venn_and_implication_bitboard(511,4094,0,4095)
    assert result['relation_AB'] == 'approximate_A_in_B'
    assert result['counterexamples_AB'] == 1
    assert s.analyze_venn_and_implication_bitboard(0,7,0,15)['relation_AB'] == 'empty_antecedent'
    with pytest.raises(ValueError):
        s.analyze_venn_and_implication_bitboard(16,0,0,15)


def test_metrics_identity_bounds_and_exact_shift():
    patches = [s.CalibratedTernaryPatch([0]*8, [0]*8) for _ in range(16)]
    rng = random.Random(4)
    for _ in range(50):
        a,b = [{i for i in range(16) if rng.randrange(2)} for _ in range(2)]
        assert all(v == 1 for v in s.evaluation(a,a,patches,4,4).values())
        assert all(0 <= v <= 1 for v in s.evaluation(a,b,patches,4,4).values())
        assert s.evaluation(a,b,patches,4,4) == s.evaluation(b,a,patches,4,4)
        moved = s.shift_nodes(a,4,4,2,2)
        assert len(moved) == len(a)
        assert s.shift_nodes(moved,4,4,-2,-2) == a


def test_temporal_xor_equals_full_reference_even_when_spins_change():
    patches, _ = s.scenario_data('Thin_Skeleton', random.Random(1))
    first = s.FiveWaySurveyEngine(patches,32,32).execute_5way_survey()
    patches, _ = s.scenario_data('High_Noise_Dark', random.Random(2))
    second = s.FiveWaySurveyEngine(copy.deepcopy(patches),32,32).execute_5way_survey(prev_frame_bitboard=first['bitboard'])
    full = s.FiveWaySurveyEngine(patches,32,32).execute_5way_survey()
    assert second['nodes'] == full['nodes']
    assert second['temporal_delta'] == first['bitboard'] ^ second['bitboard']
    unchanged = s.FiveWaySurveyEngine(patches,32,32).execute_5way_survey(prev_frame_bitboard=full['bitboard'])
    assert unchanged['temporal_delta'] == 0
    assert unchanged['nodes'] == full['nodes']


def test_benchmark_is_deterministic_except_measurements_and_records_observed_failures():
    first, second = s.run_benchmark(1), s.run_benchmark(1)
    for result in (first, second):
        del result['measurements']
    assert first == second
    assert len(first['records']) == 8
    assert any(not r['topology_match'] for r in first['records'])
    assert all(r['tp'] + r['fn'] == len(r['truth']) for r in first['records'])


def test_standalone_cli_stdlib_and_reports(tmp_path):
    script = Path(s.__file__)
    result = subprocess.run([sys.executable, '-S', str(script), '--trials', '1', '--output', str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    report = json.loads((tmp_path/'results.json').read_text())
    assert len(report['records']) == 8
    assert '# TP, + FP, - FN' in result.stdout
    assert 'causal_claim' in result.stdout
    assert (tmp_path/'report.md').read_text() == result.stdout
    bad = subprocess.run([sys.executable, '-S', str(script), '--trials', '0'],capture_output=True)
    assert bad.returncode != 0
