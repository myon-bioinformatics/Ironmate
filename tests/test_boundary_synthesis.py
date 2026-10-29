"""Board enumeration is an independent existence oracle, never the solver."""
import ast
import inspect
import itertools
import pytest
from scripts import boundary_synthesis as module
from scripts.boundary_twins import evaluate_rule, audit_boundary_twins


def check(width, **rule):
    mask = (1 << width) - 1
    for mutable in range(mask + 1):
        for fixed in range(mask + 1):
            fn = lambda b: evaluate_rule(b, **rule)
            expected = {1 << i for i in range(width) if mutable & (1 << i)
                        for b in range(mask + 1)
                        if b & ~mutable == fixed & ~mutable
                        and fn(b) != fn(b ^ (1 << i))}
            report = module.synthesize_boundary_twins(mutable, fixed_board=fixed, **rule)
            assert {p['changed_bit'] for p in report['pairs']} == expected
            for p in report['pairs']:
                assert fn(p['positive']) and not fn(p['negative'])
                assert p['positive'] ^ p['negative'] == p['changed_bit']
                assert p['positive'] & ~mutable == fixed & ~mutable
            assert report['complete_sensitive_bits']
            assert not report['all_boundary_edges']


def test_all_luts_and_shared_variable_interference():
    for first, second in itertools.product(range(16), repeat=2):
        check(3, pair_tables=((1, 2, first), (2, 4, second)))


def test_and_or_not_all_small_masks():
    for required, forbidden, disjunction in itertools.product(range(4), repeat=3):
        check(2, must_and=required, forbid_not=forbidden, or_masks=(disjunction,))
    check(3, must_and=2, pair_tables=((1, 2, 6),), or_masks=(5, 3, 3))
    check(3, or_masks=(3, 6, 5))


def test_high_bits_constants_and_local_fallback():
    high = 1 << 200
    result = module.synthesize_boundary_twins(1, fixed_board=high, must_and=1)
    assert result['pairs'][0]['positive'] == high | 1
    assert module.synthesize_boundary_twins(7)['pairs'] == []
    assert module.synthesize_boundary_twins(7, or_masks=(0,))['pairs'] == []
    assert audit_boundary_twins(0, 3, lambda b: evaluate_rule(b, must_and=3))['pairs'] == []
    assert len(module.synthesize_boundary_twins(3, must_and=3)['pairs']) == 2


def test_budget_and_validation():
    with pytest.raises(ValueError, match='budget'):
        module.synthesize_boundary_twins(7, or_masks=(7, 3), max_steps=1)
    for kwargs in (dict(mutable_mask=True), dict(mutable_mask=1, fixed_board=-1),
                   dict(mutable_mask=1, max_steps=True),
                   dict(mutable_mask=1, pair_tables=((1, 1, 6),))):
        with pytest.raises(ValueError):
            module.synthesize_boundary_twins(**kwargs)


def test_integer_bit_kernel():
    tree = ast.parse(inspect.getsource(module))
    assert not any(isinstance(n, (ast.Mult, ast.Div, ast.Pow)) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree))
