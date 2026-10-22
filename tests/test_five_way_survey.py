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
            assert not (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                        and child.func.attr in {'sin','cos','tan','atan2','sqrt'}), node.name


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


def test_probes_exhaustive_all_three_bit_boolean_functions_and_actual_queries():
    # All 256 deterministic truth tables; includes parity and interactions.
    for table in range(256):
        oracle = lambda b: bool(table & (1 << b))
        for objective in ('preserve', 'flip'):
            seen = []
            def counted(b):
                seen.append(b)
                return oracle(b)
            result = s.probe_bit_core(7, counted, objective=objective)
            assert result['queries_used'] == len(seen) == len(set(seen))
            assert result['queries_used'] == sum(result['queries_by_phase'].values())
            if result['complete']:
                witness = result['witness']
                check = (lambda m: oracle(m) == oracle(7)) if objective == 'preserve' else (lambda m: oracle(7 ^ m) != oracle(7))
                assert check(witness)
                assert all(not check(witness ^ (1 << i)) for i in range(3) if witness & (1 << i))
                assert result['guarantee'] == '1-minimal'
                assert not result['globally_minimum']
            else:
                assert objective == 'flip'
                assert result['status'] == 'no_full_deletion_flip'
                assert oracle(0) == oracle(7)
        exact = s.exact_deletion_counterfactual(7, oracle)
        candidates = [removed for removed in range(1,8) if oracle(7 ^ removed) != oracle(7)]
        if candidates:
            assert exact['complete'] and exact['globally_minimum']
            assert exact['witness_size'] == min(b.bit_count() for b in candidates)
            assert oracle(7 ^ exact['witness']) != oracle(7)
        else:
            assert exact['status'] == 'no_flip_exists'


def test_sufficient_core_is_not_the_set_whose_deletion_flips_output():
    oracle = lambda b: bool(b & 3)
    support = s.probe_bit_core(3, oracle)
    deletion = s.probe_bit_core(3, oracle, objective='flip')
    assert support['witness_size'] == 1
    assert oracle(3 ^ support['witness'])  # still True after removing one alternative
    assert deletion['witness'] == 3
    assert not oracle(3 ^ deletion['witness'])


def test_split_reduction_uses_current_context_in_crossed_interactions():
    # Supplied recursive left/right reduction picks bit 0 with old background
    # {2,3}, and bit 2 with old background {0,1}; {0,2} is NOT sufficient.
    oracle = lambda b: (b & 9 == 9) or (b & 6 == 6)
    assert oracle(15) and not oracle(5)
    result = s.probe_bit_core(15, oracle)
    assert result['complete']
    assert oracle(result['witness'])
    assert result['witness'] in (6,9)


def test_one_minimal_is_not_global_minimum_and_no_flip_endpoint_is_not_impossibility():
    oracle = lambda b: (b & 12 == 12) or bool(b & 1)
    result = s.probe_bit_core(15, oracle)
    assert result['witness'] == 12 and result['witness_size'] == 2
    assert oracle(1)  # a better cardinality-one support exists
    even = lambda b: b.bit_count() % 2 == 0
    approximate = s.probe_bit_core(3, even, objective='flip')
    assert approximate['status'] == 'no_full_deletion_flip'
    exact = s.exact_deletion_counterfactual(3, even)
    assert exact['witness_size'] == 1 and exact['globally_minimum']


def test_query_complexity_includes_endpoints_and_is_not_universally_logarithmic():
    full = (1 << 64)-1
    single = s.probe_bit_core(full, lambda b: bool(b & (1 << 63)))
    assert single['queries_by_phase']['split'] == 6
    assert single['queries_used'] == 8  # baseline and empty endpoint also counted
    all_required = s.probe_bit_core(full, lambda b: b == full)
    assert all_required['witness_size'] == 64
    assert all_required['queries_used'] > 64
    any_bit = s.probe_bit_core(full, lambda b: bool(b), objective='flip')
    assert any_bit['witness_size'] == 64
    assert any_bit['queries_used'] > 64


def test_budget_caching_validation_and_oracle_errors():
    result = s.probe_bit_core(15, lambda b: bool(b & 1), max_queries=1)
    assert result['status'] == 'budget_exhausted' and not result['complete']
    assert result['witness'] == 15 and result['guarantee'] == 'uncertified'
    assert result['queries_used'] == 1
    exact = s.exact_deletion_counterfactual(15, lambda b: b == 15, max_queries=1)
    assert not exact['complete'] and not exact['globally_minimum']
    for active in (-1, True):
        with pytest.raises(ValueError):
            s.probe_bit_core(active, bool)
    with pytest.raises(TypeError):
        s.probe_bit_core(3, lambda b: 1)
    with pytest.raises(ValueError):
        s.probe_bit_core(3, bool, objective='unknown')
    with pytest.raises(ValueError):
        s.probe_bit_core(3, bool, max_queries=0)
    with pytest.raises(ValueError):
        s.exact_deletion_counterfactual(31, bool, max_bits=4)
    def broken(b):
        raise RuntimeError('oracle failed')
    with pytest.raises(RuntimeError, match='oracle failed'):
        s.probe_bit_core(3, broken)
    meter = s.BooleanProbe(3, bool, 1)
    assert meter.ask(1,'test') is True
    assert meter.ask(1,'test') is True
    assert meter.accounting()['queries_used'] == 1
    with pytest.raises(s.QueryBudgetExceeded):
        meter.ask(2,'test')


def test_shells_are_sufficient_disjoint_not_ranked_and_residual_is_unclassified():
    oracle = lambda b: b & 3 == 3 or b & 12 == 12
    result = s.core_shell_decomposition(31, oracle)
    assert len(result['layers']) == 2
    union = 0
    for layer in result['layers']:
        assert oracle(layer['board'])
        assert not (union & layer['board'])
        assert all(not oracle(layer['board'] ^ (1 << i)) for i in range(5) if layer['board'] & (1 << i))
        union |= layer['board']
    assert union == 15 and result['residual_unclassified'] == 16
    assert result['status'] == 'residual_false_unclassified'
    assert not result['graph_k_core']
    partial = s.core_shell_decomposition(31, oracle, max_queries=1)
    assert partial['status'] == 'budget_exhausted'
    assert partial['queries_used'] == 1
    assert s.core_shell_decomposition(31, lambda b: True)['status'] == 'true_on_empty'
    # Residual bit 1 can be useful with bit 0, despite being False by itself.
    interaction = s.core_shell_decomposition(7, lambda b: bool(b & 4) or b & 3 == 3)
    assert all(layer['guarantee'] == '1-minimal' for layer in interaction['layers'])


def test_integer_lookup_rotation_and_component_descriptors():
    nodes = {2*15+4, 2*15+5, 3*15+4, 8*15+10, 9*15+10, 9*15+11}
    board = s.pack_to_bitboard(nodes,15,15)
    components = s.component_phase_rings(board,15,15)
    assert len(components) == 2
    assert sum(c['board'].bit_count() for c in components) == len(nodes)
    assert components[0]['board'] & components[1]['board'] == 0
    for comp in components:
        rotated = s.rotate_support_slots(comp['board'],15,15,4)
        # These centroids have thirds, so rasterization is measured, not assumed exact.
        assert rotated['input_count'] == (rotated['output_count'] + rotated['cropped_points'] + rotated['merged_points'])
        assert s.rotate_support_slots(comp['board'],15,15,0)['board'] == comp['board']
    exact = s.pack_to_bitboard({5*15+4, 5*15+5, 5*15+6},15,15)
    rotated = s.rotate_support_slots(exact,15,15,4)
    assert s.unpack(rotated['board']) == {4*15+5, 5*15+5, 6*15+5}
    assert s.rotate_support_slots(0,15,15,3)['board'] == 0


def test_nearest_sector_axes_symmetry_and_uniform_angle_reference():
    import math
    for dx,dy,slot in ((1,0,0), (1,1,2), (0,1,4), (-1,0,8), (0,-1,12)):
        assert s.direction_slot(dx,dy,16) == slot
    rng = random.Random(89)
    for _ in range(300):
        # Exclude vectors extremely near an irrational quantization boundary.
        angle = rng.random()*math.tau
        dx,dy = round(10000*math.cos(angle)), round(10000*math.sin(angle))
        ref = int(math.floor((math.atan2(dy,dx) % math.tau)*16/math.tau + 0.5)) % 16
        assert s.direction_slot(dx,dy,16) == ref


def test_probe_and_rotation_control_reports_preserve_failures_and_semantics():
    report = s.counterfactual_experiment()
    assert len(report['cases']) == 8
    failed = report['supplied_counterexample']
    assert failed['result'] == 5
    assert not failed['result_output'] and failed['expected_output']
    assert report['nonmonotone_exact']['witness_size'] == 1
    rotations = s.rotation_pipeline_experiment()
    assert len(rotations['cases']) == 8
    assert rotations['local_components']['detected_components'] == 3
    assert len(rotations['local_components']['all_to_all']) == 3
    l_shape = rotations['cases'][1]
    assert l_shape['ring']['shifts'] == [12]
    assert l_shape['aligned_candidates'][0]['metrics']['Flux_Field'] == 1
    ring = rotations['cases'][2]
    assert ring['ring']['ambiguous']
    scores = [a['metrics']['Flux_Field'] for a in ring['aligned_candidates']]
    assert min(scores) < max(scores)


def test_kernel_helpers_reject_infinite_negative_bit_loops_and_bad_reduction_start():
    with pytest.raises(ValueError):
        s.unpack(-1)
    with pytest.raises(ValueError):
        s.integer_scale(2,-1)
    with pytest.raises(ValueError):
        s.reduce_bit_subset(7, lambda mask,phase: False)
    assert s.integer_scale(-12,31) == -372


def test_ring_similarity_does_not_reward_shared_zero_background_slots():
    a = dict(slots=16, rings=(1,0), center=0, count=1)
    b = dict(slots=16, rings=(0,2), center=0, count=1)
    match = s.match_phase_rings(a,b)
    assert match['numerator'] == 0 and match['denominator'] == 2
