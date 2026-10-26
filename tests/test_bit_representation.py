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
