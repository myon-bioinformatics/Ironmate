"""Independent exhaustive truth tables certify local boundaries, not causality."""
import pytest
from scripts.boundary_twins import audit_boundary_twins, evaluate_rule


def test_every_three_bit_function_at_every_board():
    for table in range(256):
        fn = lambda board: bool(table & (1 << board))
        for board in range(8):
            report = audit_boundary_twins(board, 7, fn)
            expected = {other for other in range(8)
                        if (board ^ other).bit_count() == 1 and fn(other) != fn(board)}
            actual = {r['negative'] if fn(board) else r['positive'] for r in report['pairs']}
            assert actual == expected
            assert report['predicate_queries'] == 4
            for row in report['pairs']:
                assert fn(row['positive']) and not fn(row['negative'])
                assert (row['positive'] ^ row['negative']).bit_count() == 1
                assert row['oracle_verified'] is None


def test_all_pair_tables_with_independent_bit_order():
    for code in range(16):
        for board in range(4):
            assert evaluate_rule(board, pair_tables=((1,2,code),)) == bool(code & (1 << (0, 2, 1, 3)[board]))


def test_joint_overlapping_clauses_and_unsatisfiable_rules():
    # The supplied canonical OR assembly would set both XOR operands and fail.
    fn = lambda b: evaluate_rule(b, must_and=2, pair_tables=((1,2,6),))
    assert not fn(3) and fn(2)
    report = audit_boundary_twins(3, 3, fn)
    assert [(r['positive'],r['negative']) for r in report['pairs']] == [(2,3)]
    impossible = lambda b: evaluate_rule(b, must_and=1, forbid_not=1)
    assert audit_boundary_twins(0,7,impossible)['pairs'] == []
    # Two missing AND conditions cannot be fixed by any one-bit change.
    assert audit_boundary_twins(0,3,lambda b: evaluate_rule(b,must_and=3))['pairs'] == []
    assert evaluate_rule(2, or_masks=(3,))
    assert not evaluate_rule(0, or_masks=(3,))
    assert not evaluate_rule(1, or_masks=(0,))


def test_oracle_mismatch_caching_and_query_accounting():
    calls = []
    def oracle(b):
        calls.append(b)
        return True  # deliberately disagrees with parity on negative endpoints
    report = audit_boundary_twins(0,7,lambda b: bool(b.bit_count() % 2),oracle=oracle)
    assert len(report['pairs']) == 3
    assert report['oracle_queries'] == len(calls) == len(set(calls)) == 4
    assert all(row['oracle_verified'] is False for row in report['pairs'])
    fn = lambda b: bool(b & 1)
    verified = audit_boundary_twins(0,1,fn,oracle=fn,max_queries=4)
    assert verified['pairs'][0]['oracle_verified'] is True
    with pytest.raises(ValueError, match='budget'):
        audit_boundary_twins(0,1,fn,oracle=fn,max_queries=3)


def test_mutable_mask_preserves_unselected_and_high_bits():
    report = audit_boundary_twins(1 << 200,1,lambda b: bool(b & 1))
    assert report['pairs'][0]['positive'] == (1 << 200) | 1
    assert audit_boundary_twins(0,0,lambda b: False)['predicate_queries'] == 1


@pytest.mark.parametrize('args', [(-1,1), (True,1), (0,-1), (0,True)])
def test_bad_masks(args):
    with pytest.raises(ValueError):
        audit_boundary_twins(*args,lambda b: False)


def test_errors_and_invalid_rule_inputs():
    with pytest.raises(TypeError):
        audit_boundary_twins(0,1,lambda b: 1)
    def broken(b):
        raise RuntimeError('failed')
    with pytest.raises(RuntimeError):
        audit_boundary_twins(0,1,broken)
    for pair in ((1,1,6),(3,4,6),(1,2,16),(True,2,6)):
        with pytest.raises(ValueError):
            evaluate_rule(0,pair_tables=(pair,))
