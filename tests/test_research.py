"""🔬 Research measurements: bit representation, boundary synthesis and twins, fingerprint widths, observable choice, quality experiment, robust observation, stream phases and the survey holdout."""

import ast
import gzip
import hashlib
import inspect
import io
import itertools
import json
import random
import subprocess
import sys
import unittest
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
from scripts import (
    bit_representation as r, boundary_synthesis as module, littlebit_jev_3way_survey as survey, stream_phase_report as s,
    survey_holdout as holdout,
)
from scripts.adaptive_fingerprint import masked_distance, reduce256
from scripts.boundary_twins import audit_boundary_twins, evaluate_rule
from scripts.observable_choice import ObservableChoice, Prototype
from scripts.robust_observation import BoundedErrorChoice, temporal_prediction
from scripts.stream_phase_report import csv_spins


# ═══ · bit representation ════════════════════════════════════════════════════════════════════════════════
# Independent reconstruction checks and serialization known vectors.

def test_all_bases_signed_integer_roundtrip():
    rng = random.Random(20261026)
    for base in range(2, 257):
        for value in (0, -1, 1, base-1, base, -base, rng.getrandbits(128), -rng.getrandbits(256)):
            sign, digits = r.integer_to_digits(value, base)
            independent = sign * sum(d * base**i for i, d in enumerate(reversed(digits)))
            assert independent == value
            assert r.digits_to_integer(sign, digits, base) == value
    assert r.integer_to_digits(255, 16) == (1, (15, 15))
    assert r.integer_to_digits(256, 256) == (1, (1, 0))


def test_balanced_ternary_exhaustive():
    for value in range(-4096, 4097):
        trits = r.integer_to_balanced_ternary(value)
        assert sum(t * 3**i for i,t in enumerate(reversed(trits))) == value
        assert r.balanced_ternary_to_integer(trits) == value
    assert r.integer_to_balanced_ternary(2) == (1, -1)
    assert r.integer_to_balanced_ternary(-2) == (-1, 1)


def test_fingerprint_bytes_known_order_and_roundtrip():
    assert r.fingerprint64_to_bytes(0x0123456789abcdef) == bytes.fromhex('0123456789abcdef')
    for value in (0, 1, 255, 256, (1 << 63), (1 << 64)-1):
        data = r.fingerprint64_to_bytes(value)
        assert len(data) == 8
        assert r.fingerprint64_from_bytes(data) == value
    assert r.fingerprint64_from_bytes(bytes(8)) == 0


def test_exact_rationals_all_requested_bases():
    for base in (2,3,7,8,11,13,16,17,23,32,64,128,256):
        for numerator in (-17,0,1,31):
            for denominator in (3,7,10,16,-23):
                n,d = r.rational_to_digits(numerator,denominator,base)
                assert r.rational_from_digits(n,d,base) == Fraction(numerator,denominator)


def test_symbol_tokens_preserve_boundaries():
    alphabet = ('⚪','👩‍💻','👩','ab','a')
    digits = (0,1,2,3,4,1)
    tokens = r.digits_to_tokens(digits, alphabet)
    assert r.tokens_to_digits(tokens, alphabet) == digits
    assert tokens[1] == '👩‍💻'
    # Symbols do not replace binary storage; their encoded byte lengths vary.
    assert len(alphabet[0].encode()) != len(alphabet[1].encode())


@pytest.mark.parametrize('fn,args', [
    (r.integer_to_digits,(True,3)), (r.integer_to_digits,(1,1)),
    (r.integer_to_digits,(1,257)), (r.digits_to_integer,(0,(1,),3)),
    (r.digits_to_integer,(1,(),3)), (r.digits_to_integer,(1,(3,),3)),
    (r.digits_to_integer,(True,(1,),3)), (r.balanced_ternary_to_integer,((2,),)),
    (r.balanced_ternary_to_integer,((True,),)), (r.fingerprint64_to_bytes,(-1,)),
    (r.fingerprint64_to_bytes,(1 << 64,)), (r.fingerprint64_to_bytes,(True,)),
    (r.fingerprint64_from_bytes,(bytes(7),)), (r.fingerprint64_from_bytes,(bytes(9),)),
    (r.fingerprint64_from_bytes,('00000000',)),
    (r.rational_to_digits,(1,0,3)),
    (r.rational_from_digits,((1,(1,)),(0,(0,)),3)),
    (r.digits_to_tokens,((0,),('a','a'))),
    (r.digits_to_tokens,((2,),('a','b'))),
    (r.tokens_to_digits,(('c',),('a','b'))),
])
def test_reject_invalid_data(fn,args):
    with pytest.raises(ValueError):
        fn(*args)


def test_u32_limb_order_and_carry_against_python_integer():
    assert r.integer_to_u32_limbs(0x123456789abcdef0) == (0x9abcdef0, 0x12345678)
    assert r.add_u32_limbs((0xffffffff, 0xffffffff), (1,)) == (0, 0, 1)
    assert r.add_u32_limbs((0, 0), (0,)) == (0,)
    rng = random.Random(32128)
    cases = [0, 1, (1 << 32)-1, 1 << 32, (1 << 64)-1, 1 << 4096]
    cases += [rng.getrandbits(rng.randrange(1, 2048)) for _ in range(150)]
    for value in cases:
        limbs = r.integer_to_u32_limbs(value)
        assert r.u32_limbs_to_integer(limbs) == value
        assert sum(limb << (32*i) for i, limb in enumerate(limbs)) == value
        other = rng.getrandbits(1024)
        added = r.add_u32_limbs(limbs, r.integer_to_u32_limbs(other))
        assert r.u32_limbs_to_integer(added) == value + other


def test_mask_batch_byte_order_and_many_masks():
    values = (0, 1, (1 << 64)-1, 0x0123456789abcdef, 0)
    packed = r.fingerprints64_to_bytes(iter(values))
    assert packed == bytes.fromhex('00000000000000000000000000000001ffffffffffffffff0123456789abcdef0000000000000000')
    assert r.fingerprints64_from_bytes(packed) == values
    assert r.fingerprints64_to_bytes(()) == b''
    assert r.fingerprints64_from_bytes(b'') == ()
    rng = random.Random(64)
    many = tuple(rng.getrandbits(64) for _ in range(10000))
    data = r.fingerprints64_to_bytes(many)
    assert len(data) == 80000
    assert r.fingerprints64_from_bytes(data) == many


def test_rgb_channel_positions_and_roundtrips():
    assert r.rgb8_to_integer(0x12, 0x34, 0x56) == 0x123456
    assert r.rgb8_to_bytes(0x12, 0x34, 0x56) == b'\x12\x34\x56'
    for channel in range(256):
        for rgb in ((channel,0,0), (0,channel,0), (0,0,channel), (channel,channel,channel)):
            assert r.integer_to_rgb8(r.rgb8_to_integer(*rgb)) == rgb
            assert r.rgb8_from_bytes(r.rgb8_to_bytes(*rgb)) == rgb


@pytest.mark.parametrize('fn,args', [
    (r.integer_to_u32_limbs,(-1,)), (r.integer_to_u32_limbs,(True,)),
    (r.u32_limbs_to_integer,((),)), (r.u32_limbs_to_integer,((-1,),)),
    (r.u32_limbs_to_integer,((1 << 32,),)), (r.u32_limbs_to_integer,((True,),)),
    (r.add_u32_limbs,((0,), (1 << 32,))),
    (r.fingerprints64_to_bytes,((0,-1),)), (r.fingerprints64_to_bytes,((True,),)),
    (r.fingerprints64_from_bytes,(bytes(9),)), (r.fingerprints64_from_bytes,('12345678',)),
    (r.rgb8_to_integer,(256,0,0)), (r.rgb8_to_integer,(0,-1,0)),
    (r.rgb8_to_bytes,(0,0,True)), (r.integer_to_rgb8,(1 << 24,)),
    (r.integer_to_rgb8,(-1,)), (r.integer_to_rgb8,(True,)),
    (r.rgb8_from_bytes,(bytes(4),)), (r.rgb8_from_bytes,('RGB',)),
])
def test_new_adapters_reject_invalid_data(fn,args):
    with pytest.raises(ValueError):
        fn(*args)


@pytest.mark.parametrize('base', range(2, 257))
def test_zero_sign_contract_and_leading_zeros(base):
    assert r.integer_to_digits(0, base) == (0, (0,))
    for digits in ((0,), (0, 0, 0), [0, 0]):
        assert r.digits_to_integer(0, digits, base) == 0
        for sign in (-1, 1):
            with pytest.raises(ValueError, match='zero value requires zero sign'):
                r.digits_to_integer(sign, digits, base)
    for digits in ((1,), (0, 0, 1), [0, base - 1, 1]):
        magnitude = sum(d * base**i for i, d in enumerate(reversed(digits)))
        for sign in (-1, 1):
            value = r.digits_to_integer(sign, digits, base)
            assert value == sign * magnitude
            assert r.integer_to_digits(value, base)[0] == sign
        with pytest.raises(ValueError, match='zero sign requires zero value'):
            r.digits_to_integer(0, digits, base)


@pytest.mark.parametrize('base', range(2, 257))
def test_rational_records_share_zero_sign_contract(base):
    zero, one = (0, (0, 0)), (1, (0, 1))
    assert r.rational_from_digits(zero, one, base) == Fraction(0)
    assert r.rational_to_digits(0, -base, base) == ((0, (0,)), (1, (1,)))
    for sign in (-1, 1):
        signed_zero = (sign, (0, 0))
        with pytest.raises(ValueError, match='zero value requires zero sign'):
            r.rational_from_digits(signed_zero, one, base)
        with pytest.raises(ValueError, match='zero value requires zero sign'):
            r.rational_from_digits(one, signed_zero, base)
    with pytest.raises(ValueError, match='denominator must not be zero'):
        r.rational_from_digits(one, zero, base)


# ═══ · boundary synthesis ════════════════════════════════════════════════════════════════════════════════
# Board enumeration is an independent existence oracle, never the solver.

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


def test_high_support_fixed_bits_and_sparse_mutable_mask():
    # Relabel three adjacent bits to sparse positions, including a high bit.
    positions = (1, 1 << 65, 1 << 200)
    def lift(board):
        return sum(bit for i, bit in enumerate(positions) if board & (1 << i))
    rule = dict(pair_tables=((positions[0], positions[1], 6),
                             (positions[1], positions[2], 14)))
    for mutable, fixed in itertools.product(range(8), repeat=2):
        expected = {positions[i] for i in range(3) if mutable & (1 << i)
                    for board in range(8)
                    if board & ~mutable == fixed & ~mutable
                    and evaluate_rule(lift(board), **rule) !=
                    evaluate_rule(lift(board ^ (1 << i)), **rule)}
        report = module.synthesize_boundary_twins(lift(mutable),
                                                  fixed_board=lift(fixed), **rule)
        assert {p['changed_bit'] for p in report['pairs']} == expected
        for pair in report['pairs']:
            assert pair['positive'] & ~lift(mutable) == lift(fixed) & ~lift(mutable)
            assert pair['negative'] & ~lift(mutable) == lift(fixed) & ~lift(mutable)


def test_subtraction_budget_exact_threshold_and_no_partial_report():
    # No clauses: all counted work is in subtraction, after a witness exists.
    kwargs = dict(mutable_mask=3, must_and=3)
    report = module.synthesize_boundary_twins(**kwargs)
    assert len(report['pairs']) == 2
    steps = report['symbolic_steps']
    assert steps == 2
    assert module.synthesize_boundary_twins(**kwargs, max_steps=steps) == report
    with pytest.raises(ValueError, match='budget exhausted'):
        module.synthesize_boundary_twins(**kwargs, max_steps=steps - 1)


# ═══ · boundary twins ════════════════════════════════════════════════════════════════════════════════════
# Independent exhaustive truth tables certify local boundaries, not causality.

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


# ═══ · fingerprint width boundaries ══════════════════════════════════════════════════════════════════════
# Verify width boundaries without truncating out-of-range fingerprints.

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


# ═══ · observable choice ═════════════════════════════════════════════════════════════════════════════════

def test_exhaustive_index_matches_linear_kleene():
    specs = [Prototype('on',1,2,(12,)), Prototype('off',2,1), Prototype('wild'), Prototype('or',0,0,(3,))]
    for budget in (1,3,31):
        e = ObservableChoice(specs,4,node_budget=budget,leaf_size=1)
        assert e.nodes <= budget
        for active in range(16):
            for obs in range(16):
                result = e.query(active,obs)
                expected = [p.name for p in specs if e.evaluate(p,active,obs) != 'false']
                assert [c['name'] for c in result['candidates']] == expected
                probe = result['next_probe']
                if probe:
                    for value, key in ((0,'zero_survivors'),(1,'one_survivors')):
                        bit=1<<probe['bit']
                        actual=e.query((active & obs & ~bit)|(bit if value else 0),obs|bit)
                        assert len(actual['candidates']) == probe[key]


def test_unknown_not_false_and_no_false_xor_guarantee():
    e=ObservableChoice([Prototype('required',1),Prototype('dontcare')],1)
    r=e.query(0,0)
    assert r['status']=='ambiguous' and r['next_probe'] is None
    assert r['candidates'][0]['truth']=='unknown'
    assert e.query(0,1)['candidates']==[{'name':'dontcare','truth':'true'}]
    assert ObservableChoice([Prototype('on',1),Prototype('off',0,1)],1).query(0,0)['next_probe']['one_survivors']==1


def test_256_exact_classes_and_all_hidden():
    e=ObservableChoice([Prototype(str(i),i,255^i) for i in range(256)],8,leaf_size=1)
    for i in range(256):
        r=e.query(i,255)
        assert r['candidates']==[{'name':str(i),'truth':'true'}]
        assert r['bit_tests']==8
    assert len(e.query(0,0)['candidates'])==256
    assert e.query(0,0)['bit_tests']==255


def test_missing_csv_neutral_observed_and_all_missing():
    rows=list(csv_spins(io.StringIO('id,x,y\na,NULL,0\nb,,0\nc,1,0\n'),'id',['x','y'],True))
    assert [r['obs_mask'] for r in rows]==[12,12,15]
    assert all(r['spin_board']==0 for r in rows)
    assert list(csv_spins(io.StringIO('id,x\na,NULL\n'),'id',['x'],True))[0]['obs_mask']==0
    with pytest.raises(ValueError):
        list(csv_spins(io.StringIO('id,x\na,NULL\n'),'id',['x']))
    with pytest.raises(ValueError): ObservableChoice([Prototype('bad',1,1)],1)


# ═══ · quality experiment ════════════════════════════════════════════════════════════════════════════════

# test_quality_experiment.py
# __all__: 0
__all__ = []

import hashlib, json, random


from scripts import quality_experiment as q
from ironlib.studio_alignment import invert_translation
from ironlib.studio_shape_metrics import metrics


def test_iou_dice_monotonic_equivalence_independent_counts():
    rng=random.Random(20261018)
    scores=[]
    for _ in range(100):
        a={i for i in range(64) if rng.random()<.3}; b={i for i in range(64) if rng.random()<.3}
        tp=sum(i in a and i in b for i in range(64)); fp=sum(i not in a and i in b for i in range(64)); fn=sum(i in a and i not in b for i in range(64))
        m=metrics(8,8,a,b)
        expected=tp/(tp+fp+fn) if tp+fp+fn else 1
        assert m['IoU']==expected
        assert m['Dice']==pytest.approx(2*expected/(1+expected))
        scores.append(m)
    assert sorted(range(100),key=lambda i:scores[i]['IoU'])==sorted(range(100),key=lambda i:scores[i]['Dice'])


def test_tolerance_can_reverse_area_ranking():
    # One long thin line displaced by one pixel versus sparse exact hits.
    a={y*16+4 for y in range(2,14)}
    near={i+1 for i in a}; partial=set(sorted(a)[::3])
    n=metrics(16,16,a,near); p=metrics(16,16,a,partial)
    assert n['IoU']<p['IoU']
    # Mean of exact directed hit 1 and recall 1/3 = 2/3; use a far false positive
    # population to reduce partial tolerance while retaining positive IoU.
    partial |= {y*16+14 for y in range(2,14)}
    p=metrics(16,16,a,partial)
    assert n['IoU']<p['IoU'] and n['Symmetric_Near_Field']>p['Symmetric_Near_Field']


def test_alpha_masks_cannot_judge_color_and_alignment_is_not_position_improvement():
    white=(255,255,255,255); ref=[white]*64;ref[27]=(20,30,40,255)
    _,colored,_=q.perturb(8,8,ref,'color_change')
    result=q.evaluate(8,8,ref,colored,repeats=1)
    assert result['alpha']['IoU']==result['alpha']['Aligned_IoU']==1
    assert result['rgba_similarity']<1
    _,moved,recipe=q.perturb(8,8,ref,'shift_1px')
    result=q.evaluate(8,8,ref,moved,repeats=1)
    assert result['foreground']['IoU']==0
    assert result['foreground']['Aligned_IoU']==1
    assert (result['foreground']['Alignment_dx'],result['foreground']['Alignment_dy'])==(-1,0)
    assert recipe['inverse_exact']


def test_clipped_pixels_cannot_be_recovered():
    pixels=[(255,255,255,255)]*64;pixels[7]=(1,2,3,255)
    _,out,r=q.perturb(8,8,pixels,'edge_clip')
    assert r['clipped_nonfill']==1 and not r['inverse_exact']
    assert invert_translation(8,8,out,r['dx'],0,fill=(255,255,255,255))['pixels']!=pixels


def test_undefined_energy_remains_null_and_identity_has_no_nan():
    ref=[(255,255,255,255)]*64
    value=q.evaluate(8,8,ref,ref,repeats=1)
    assert value['foreground']['Energy_Dice'] is None
    assert 'null' in json.dumps(value,allow_nan=False)
    assert value['foreground']['IoU']==value['rgba_similarity']==1


def test_seeded_perturbations_png_roundtrip_and_source_preserved():
    pixels=[(x*13,y*17,80,255) for y in range(8) for x in range(8)]
    original=list(pixels)
    for kind in ['identity','shift_1px','shrink_expand','enlarge_crop','mosaic','blur','thin_line_loss','contour_dilate','color_change','edge_clip']:
        a,b,r=q.perturb(8,8,pixels,kind)
        assert (a,b,r)==q.perturb(8,8,pixels,kind)
        assert pixels==original and len(a)==len(b)==64
        w,h,rows=q.decode_png(q._png(8,8,b))
        assert (w,h)==(8,8) and b==[tuple(row[i:i+4]) for row in rows for i in range(0,len(row),4)]
    _,_,recipe=q.perturb(8,8,pixels,'thin_line_loss')
    assert recipe['reference_variant']!='original'


def test_checked_in_evidence_recomputes_scores_without_timing_assertions():
    folder=ROOT/'docs/evidence/studio-quality'
    report=json.loads((folder/'results.json').read_text())
    assert len(report['cases'])==110
    for c in report['cases']:
        def read(name):
            w,h,rows=q.decode_png((folder/c[name]).read_bytes())
            assert (w,h)==(c['width'],c['height'])
            return [tuple(row[i:i+4]) for row in rows for i in range(0,len(row),4)]
        a,b=read('reference_png'),read('candidate_png')
        assert hashlib.sha256(bytes(x for p in a for x in p)).hexdigest()==c['reference_sha256']
        assert hashlib.sha256(bytes(x for p in b for x in p)).hexdigest()==c['candidate_sha256']
        fixture=next(f for f in json.loads((folder/'fixtures.json').read_text())['fixtures'] if f['name']==c['scenario'] and f['seed']==c['seed'])
        source=(folder/fixture['file']).read_bytes()
        assert hashlib.sha256(source).hexdigest()==c['source_sha256']
        sw,sh,srows=q.decode_png(source)
        original=[tuple(row[i:i+4]) for row in srows for i in range(0,len(row),4)]
        scaled=q._resize(original,sw,sh,c['width'],c['height'])
        ra,rb,recipe=q.perturb(c['width'],c['height'],scaled,c['recipe']['kind'],c['seed'])
        assert (ra,rb,recipe)==(a,b,c['recipe'])
        m=metrics(c['width'],c['height'],q._mask(a),q._mask(b),q._energy(a,c['width'],c['height']))
        for k,v in m.items(): assert c['foreground'][k]==v
        expected=1-sum(abs(x-y) for p,r in zip(a,b) for x,y in zip(p,r))/(len(a)*1020)
        assert c['rgba_similarity']==expected
        assert c['png_bytes']==(folder/c['candidate_png']).stat().st_size
        for group in c['cost'].values():
            assert len(group['cpu_ms_samples'])==3 and group['cpu_ms_median']>=0
            assert group['python_peak_allocated_bytes']>=0
        if c['recipe']['kind']=='identity':
            assert c['foreground']['IoU']==c['foreground']['Aligned_IoU']==c['rgba_similarity']==1
            assert c['foreground']['Alignment_L1_Pixels']==0
    # Recompute expensive registration on a representative saved case only.
    c=next(c for c in report['cases'] if c['scenario']=='shapes' and c['recipe']['kind']=='shift_1px')
    a,b=read('reference_png'),read('candidate_png')
    fresh=q.evaluate(c['width'],c['height'],a,b,repeats=1)
    assert fresh['foreground']==c['foreground'] and fresh['alpha']==c['alpha']


# ═══ · robust observation ════════════════════════════════════════════════════════════════════════════════

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


# ═══ · stream phase report ═══════════════════════════════════════════════════════════════════════════════

def test_pixels_borrowed_and_projection():
    buf = bytearray(range(64))
    p = next(s.image_patches(buf, 8, 8))
    assert p.dc_level == s.CalibratedTernaryPatch([sum(buf[y*8:y*8+8])//8 for y in range(8)], [sum(buf[x::8])//8 for x in range(8)]).dc_level
    buf[:] = bytes([100])*64
    assert next(s.image_patches(buf, 8, 8)).dc_level != p.dc_level
    rgb = bytes([255, 0, 0])*64
    assert next(s.image_patches(rgb, 8, 8, 3)).dc_level == next(s.image_patches(bytes([63])*64, 8, 8)).dc_level
    for w, h, c, data in [(7,8,1,buf), (8,8,4,buf), (8,8,1,b'')]:
        with pytest.raises(ValueError):
            list(s.image_patches(data,w,h,c))


def test_pgm_binary_separator():
    for first in (10,32,35,0):
        original = bytearray(b'P5\n# comment\n8 8\n255\n' + bytes([first])*64)
        mv,w,h = s.pgm_view(original)
        assert (w,h,len(mv),mv[0]) == (8,8,64,first)
        original[-1] = 9
        assert mv[-1] == 9
    with pytest.raises(ValueError):
        s.pgm_view(b'P5 8 8 65535\n')


def test_csv_exact_and_neutral():
    assert s.fixed100('-0.25') == -25
    assert s.fixed100('3.45') == 345
    for bad in ('NaN','1e2','1.234','','.5'):
        with pytest.raises(ValueError): s.fixed100(bad)
    rows = list(s.csv_spins(io.StringIO('id,x,c\na,-1,2\nb,0,2\nc,1,2\n'),'id',['x','c']))
    assert [(r['pos_mask'],r['neg_mask']) for r in rows] == [(0,1),(0,0),(1,0)]
    for text in ('id,x\na,\n','id,x\na\n','id,x,x\na,1,2\n'):
        with pytest.raises(ValueError): list(s.csv_spins(io.StringIO(text),'id',['x']))


def test_bfs_matches_exhaustive_overlapping_or_and_winner():
    def choose(b):
        if b & 8: return 'rival'
        return 'target' if b & 3 and b & 6 else 'source'
    for board in range(16):
        result = s.shortest_ladder(board,'target',choose,4,max_distance=4)
        exact = min((board^b).bit_count() for b in range(16) if choose(b)=='target')
        assert result['distance'] == exact
        assert choose(result['path'][-1]) == 'target'
    assert s.shortest_ladder(0,'target',choose,4,max_states=1)['status'] == 'resource_limit'
    assert s.shortest_ladder(0,'target',choose,4,max_distance=0)['status'] == 'not_found_within_bound'
    assert s.shortest_ladder(0,'target',choose,4)['distance'] == 1


def test_render_escapes():
    text = s.render_ladder([0,1],lambda b: 'x"\n``` <tag>',{0:'a"|\n```'})
    assert '&quot;' in text and '&lt;tag&gt;' in text
    assert text.count('```') == 4
    with pytest.raises(ValueError): s.render_ladder([0,3],str,{})


def test_csv_ladder_multiple_rows_reuses_setup(tmp_path, monkeypatch, capsys):
    csv_path = tmp_path / 'rows.csv'
    csv_path.write_text('id,x\na,-1\nb,0\nc,1\n', encoding='utf-8')
    spec_path = tmp_path / 'ladder.json'
    spec_path.write_text(json.dumps({'target': 'high', 'classes': [
        {'name': 'high', 'must_and': 1, 'forbid_not': 2, 'or_masks': [1]},
        {'name': 'low', 'must_and': 2}, {'name': 'neutral'}]}), encoding='utf-8')
    read_text, loads = Path.read_text, s.json.loads
    reads, parses, callbacks, mappings = [], [], [], []
    def read(path, *args, **kwargs):
        reads.append(path)
        return read_text(path, *args, **kwargs)
    def load(text, *args, **kwargs):
        parses.append(text)
        return loads(text, *args, **kwargs)
    shortest, render = s.shortest_ladder, s.render_ladder
    def search(board, target, choose, bits, **kwargs):
        callbacks.append((choose, kwargs['valid']))
        assert not kwargs['valid'](3)
        return shortest(board, target, choose, bits, **kwargs)
    def draw(path, choose, names):
        mappings.append(names)
        return render(path, choose, names)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(s.json, 'loads', load)
    monkeypatch.setattr(s, 'shortest_ladder', search)
    monkeypatch.setattr(s, 'render_ladder', draw)
    s.main(['--csv', str(csv_path), '--id-col', 'id', '--columns', 'x',
            '--ladder-spec', str(spec_path)])
    assert reads == [spec_path]
    assert len(parses) == 1
    assert len(callbacks) == len(mappings) == 3
    assert all(c[0] is callbacks[0][0] and c[1] is callbacks[0][1] for c in callbacks)
    assert all(m is mappings[0] for m in mappings)
    expected = []
    for ident, pos, neg, board, path in [('a', 0, 1, 2, [2, 0, 1]),
                                        ('b', 0, 0, 0, [0, 1]),
                                        ('c', 1, 0, 1, [1])]:
        expected.append(json.dumps(dict(id=ident, pos_mask=pos, neg_mask=neg,
                                        spin_board=board, obs_mask=3)) + '\n')
        expected.append(json.dumps(dict(status='found', path=path, distance=len(path)-1)) + '\n')
        expected.append(render(path, lambda b: {0: 'neutral', 1: 'high', 2: 'low'}[b],
                               {0: 'x_High', 1: 'x_Low'}) + '\n')
    assert capsys.readouterr().out == ''.join(expected)


@pytest.mark.parametrize('rows', ['id,x\n', 'id,x\na,0\nb,1\n'])
def test_csv_invalid_ladder_json_fails_before_output(tmp_path, capsys, rows):
    csv_path, spec_path = tmp_path / 'rows.csv', tmp_path / 'bad.json'
    csv_path.write_text(rows, encoding='utf-8')
    spec_path.write_text('{bad', encoding='utf-8')
    with pytest.raises(SystemExit) as exc:
        s.main(['--csv', str(csv_path), '--columns', 'x', '--ladder-spec', str(spec_path)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'error:' in captured.err and 'property name' in captured.err


@pytest.mark.parametrize('missing', ['', 'NULL'])
def test_csv_missing_candidates_stay_unknown_and_ladder_rejected(tmp_path, capsys, missing):
    csv_path, spec_path = tmp_path / 'rows.csv', tmp_path / 'classes.json'
    csv_path.write_text(f'id,x\na,0\nb,{missing}\nc,0\n', encoding='utf-8')
    spec_path.write_text(json.dumps({'target': 'on', 'classes': [
        {'name': 'on', 'must_and': 1}, {'name': 'off', 'forbid_not': 1}]}), encoding='utf-8')
    args = ['--csv', str(csv_path), '--id-col', 'id', '--columns', 'x',
            '--allow-missing', '--observable-spec', str(spec_path)]
    s.main(args)
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r['obs_mask'] for r in records[::2]] == [3, 0, 3]
    assert records[1]['candidates'] == records[5]['candidates'] == [{'name': 'off', 'truth': 'true'}]
    assert records[3]['candidates'] == [{'name': 'on', 'truth': 'unknown'},
                                        {'name': 'off', 'truth': 'unknown'}]
    with pytest.raises(SystemExit) as exc:
        s.main(args + ['--ladder-spec', str(spec_path)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert 'ladder requires complete observations' in captured.err
    # The complete first row is still processed before rejecting the missing row.
    assert '"status": "found"' in captured.out


# ═══ · survey holdout ════════════════════════════════════════════════════════════════════════════════════
# Frozen observations and independent fixture/metric checks, not accuracy gates.

SNAPSHOT = ROOT / "docs/evidence/survey-holdout/summary.json"


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def _scalar_metrics(truth, prediction):
    # Deliberately do not call the engine's set-based metrics implementation.
    counts = dict.fromkeys(("tp", "fp", "fn", "tn"), 0)
    for idx in range(1024):
        key = ("tp" if idx in prediction else "fn") if idx in truth else ("fp" if idx in prediction else "tn")
        counts[key] += 1
    union = counts["tp"] + counts["fp"] + counts["fn"]
    counts["iou"] = counts["tp"] / union if union else 1.0
    return counts


@pytest.fixture(scope="module")
def report():
    return holdout.evaluate()


def test_settings_are_frozen_from_prior_evidence_and_seeds_are_new(monkeypatch):
    prior = json.loads((ROOT / "docs/evidence/three-way-survey/summary.json").read_text())
    assert asdict(holdout.FROZEN_CONFIG) == prior["config"] == {
        "deadzone_shift": 3, "ub_threshold": 64, "min_links": 2, "max_diff": 4,
    }
    assert set(holdout.SEEDS).isdisjoint({20261017, *prior["test_seeds"]})
    def no_tuning(*args, **kwargs):
        pytest.fail("held-out evaluator must not tune")
    monkeypatch.setattr(survey, "tune", no_tuning)
    assert len(holdout.evaluate(trials=1, seeds=(20261020,))["records"]) == 20


def test_factorial_panels_and_frozen_observations(report):
    expected = json.loads(SNAPSHOT.read_text())
    assert len(report["records"]) == 120
    assert {p: sum(r["panel"] == p for r in report["records"]) for p in
            ("reference", "shape_only", "signal_only", "shape_and_signal")} == {
                "reference": 6, "shape_only": 18, "signal_only": 24, "shape_and_signal": 72,
            }
    assert report["summary"] == expected["summary"]
    for key in ("engine_sha256", "harness_sha256", "records_sha256", "config", "strides", "seeds"):
        assert report[key] == expected[key], key
    actual_records = [{k: v for k, v in r.items() if k not in ("profiles", "truth", "prediction")}
                      for r in report["records"]]
    assert actual_records == expected["records"]
    # Poor accuracy must remain visible, not be xfailed, discarded or made 100%.
    assert any(r["iou"] == 0 and r["outcome"] == "observed_mismatch" for r in report["records"])
    assert any(r["fp"] > 0 and r["fn"] > 0 for r in report["records"])


def test_new_shape_families_are_not_old_masks_or_each_other():
    old_masks = [survey.generate_test_scenario(32, 32, name, random.Random(0))[1]
                 for name in survey.SCENARIOS]
    for trial in range(3):
        new = []
        for shape in holdout.HELDOUT_SHAPES:
            _, truth = holdout.generate_case(20261020, shape, "reference", trial)
            assert truth not in old_masks and truth not in new
            new.append(truth)
        assert [len(mask) for mask in new] == [232, 595, 149]
    # Specific geometric controls: reentrant bay, nine holes, and border turns.
    _, comb = holdout.generate_case(20261020, "concave_comb", "reference", 0)
    assert 7 * 32 + 6 in comb and 7 * 32 + 7 not in comb
    _, slab = holdout.generate_case(20261020, "perforated_slab", "reference", 0)
    for x in (8, 16, 24):
        for y in (8, 16, 24):
            assert y * 32 + x not in slab and y * 32 + x - 1 in slab
    _, path = holdout.generate_case(20261020, "border_serpentine", "reference", 0)
    assert {0, 31, 8 * 32, 8 * 32 + 31, 16 * 32, 24 * 32 + 31} <= path


def test_control_signal_exactly_matches_original_distribution():
    seed = holdout._case_seed(20261020, "dense_reference", "reference", 0)
    expected = survey.generate_test_scenario(32, 32, "Dense_Object", random.Random(seed))
    assert holdout.generate_case(20261020, "dense_reference", "reference", 0) == expected


def test_signal_families_have_intended_distinct_support():
    low, truth = holdout.generate_case(20261020, "dense_reference", "quantized_low_contrast", 0)
    assert {abs(v - 50) for idx in truth for vector in low[idx] for v in vector} == {1, 2, 3, 4, 6, 8}
    phase, _ = holdout.generate_case(20261020, "dense_reference", "phase_mixture", 0)
    assert any(phase[idx][0][0] < phase[idx][0][1] for idx in truth)
    impulsive, _ = holdout.generate_case(20261020, "dense_reference", "impulsive_tail", 0)
    for cells in (truth, set(range(1024)) - truth):
        assert {0, 255} <= {v for idx in cells for vector in impulsive[idx] for v in vector}
    walks, _ = holdout.generate_case(20261020, "dense_reference", "correlated_walk", 0)
    differences = {b - a for idx in truth for vector in walks[idx] for a, b in zip(vector, vector[1:])}
    assert differences == {-12, -6, 6, 12}


def test_fixture_and_outcome_oracles_for_every_case(report):
    truths = {}
    for row in report["records"]:
        profiles, truth, prediction = row["profiles"], set(row["truth"]), set(row["prediction"])
        assert len(profiles) == 1024
        assert len(prediction) == len(row["prediction"])
        assert truth <= set(range(1024)) and prediction <= set(range(1024))
        assert all(len(pair) == 2 and all(len(vector) == 8 and all(type(v) is int and 0 <= v <= 255
                   for v in vector) for vector in pair) for pair in profiles)
        assert row["input_sha256"] == _fingerprint(profiles)
        assert row["truth_sha256"] == _fingerprint(sorted(truth))
        assert row["prediction_sha256"] == _fingerprint(sorted(prediction))
        for key, value in _scalar_metrics(truth, prediction).items():
            assert row[key] == value
        assert row["candidate_count"] + row["skipped"] == 1024
        assert (row["outcome"] == "exact") == (prediction == truth)
        # Signal/seed changes never move the labels in a shape panel.
        key = (row["shape"], row["trial"])
        assert truths.setdefault(key, truth) == truth
        if not prediction:
            assert row["precision"] is None and row["com_error_patch"] is None


def test_seed_and_order_independence():
    cases = [(20261020, "concave_comb", "phase_mixture", 0),
             (20261021, "perforated_slab", "impulsive_tail", 2)]
    forward = {case: holdout.generate_case(*case) for case in cases}
    reverse = {case: holdout.generate_case(*case) for case in reversed(cases)}
    assert forward == reverse
    changed = holdout.generate_case(20261021, "concave_comb", "phase_mixture", 0)
    assert forward[cases[0]][0] != changed[0]
    assert forward[cases[0]][1] == changed[1]


def test_h8_integer_loss_and_isolated_legitimate_support_remain_counterexamples():
    assert survey.fwht8_add_only([1, 0, 0, 0, 0, 0, 0, 0]) == [0] * 8
    config = holdout.FROZEN_CONFIG
    profiles = [([50] * 8, [50] * 8) for _ in range(64)]
    profiles[27] = ([130, 25] * 4, [120, 120, 30, 30] * 2)
    result = survey.ThreeWaySurveyEngine(survey.encode_profiles(profiles, config), 8, 8).execute_survey(config)
    assert result["normal_set"] == set()
    # The identical measurement cannot decide whether an isolated patch is truth or noise.
    assert survey.metrics({27}, result["normal_set"], 8, 8)["fn"] == 1
    assert survey.metrics(set(), result["normal_set"], 8, 8)["fp"] == 0


@pytest.mark.parametrize("kwargs", [{"trials": 0}, {"trials": 21}, {"trials": True},
                                    {"seeds": ()}, {"seeds": (1, 1)}, {"seeds": (True,)}])
def test_evaluator_rejects_invalid_requests(kwargs):
    with pytest.raises(ValueError):
        holdout.evaluate(**kwargs)


def test_invalid_fixtures_and_engine_errors_fail_instead_of_becoming_accuracy_results(monkeypatch):
    with pytest.raises(ValueError, match="unknown shape"):
        holdout.generate_case(1, "not_a_shape", "reference", 0)
    with pytest.raises(ValueError, match="unknown signal"):
        holdout.generate_case(1, "dense_reference", "not_a_signal", 0)
    original = holdout.generate_case
    def invalid_fixture(*args):
        profiles, truth = original(*args)
        profiles[0][0][0] = 300
        return profiles, truth
    monkeypatch.setattr(holdout, "generate_case", invalid_fixture)
    with pytest.raises(ValueError, match="invalid holdout integer profile"):
        holdout.evaluate(trials=1)
    monkeypatch.setattr(holdout, "generate_case", original)
    def broken_engine(*args, **kwargs):
        raise RuntimeError("engine error must propagate")
    monkeypatch.setattr(survey.ThreeWaySurveyEngine, "execute_survey", broken_engine)
    with pytest.raises(RuntimeError, match="must propagate"):
        holdout.evaluate(trials=1)


def test_stdlib_cli_preserves_full_replayable_inputs_and_rejects_invalid_trial_count(tmp_path):
    command = [sys.executable, "-S", str(Path(holdout.__file__).resolve()), "--trials", "1", "--output", str(tmp_path)]
    run = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    raw_bytes = gzip.decompress((tmp_path / "results.json.gz").read_bytes())
    raw, summary = json.loads(raw_bytes), json.loads((tmp_path / "summary.json").read_text())
    assert hashlib.sha256(raw_bytes).hexdigest() == summary["raw_results_sha256"]
    assert _fingerprint(raw["records"]) == raw["records_sha256"]
    assert len(raw["records"]) == 40
    # Replay the persisted inputs, rather than regenerating from a seed.
    config = survey.Config(**raw["config"])
    for row in raw["records"]:
        result = survey.ThreeWaySurveyEngine(survey.encode_profiles(row["profiles"], config),
                                             raw["width"], raw["height"]).execute_survey(config)
        assert sorted(result["normal_set"]) == row["prediction"]
    assert (tmp_path / "report.md").read_text() == run.stdout
    assert "observed_mismatch" in raw_bytes.decode()
    invalid = subprocess.run(command + ["--trials", "0"], capture_output=True, text=True)
    assert invalid.returncode != 0 and "trials must be 1..20" in invalid.stderr


def test_import_does_not_execute_experiment(tmp_path):
    code = f"import sys; sys.path.insert(0, {str(ROOT)!r}); from scripts import survey_holdout"
    run = subprocess.run([sys.executable, "-S", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "" and list(tmp_path.iterdir()) == []


if __name__ == "__main__":
    unittest.main()
