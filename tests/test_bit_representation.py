"""Independent reconstruction checks and serialization known vectors."""
from fractions import Fraction
import random
import pytest
from scripts import bit_representation as r


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
