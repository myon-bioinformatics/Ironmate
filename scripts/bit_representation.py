"""Lossless representation adapters; no change to numeric inference kernels.

Digits are most-significant first tuples, not ambiguous concatenated glyphs.
The tuple format is project-specific; base 256 digits are bytes only when packed.
"""
from fractions import Fraction


def _integer(value):
    if type(value) is not int:
        raise ValueError('expected an integer (not bool)')
    return value


def _base(base):
    if type(base) is not int or not 2 <= base <= 256:
        raise ValueError('base must be an integer in 2..256')
    return base


def integer_to_digits(value, base):
    """Return (sign, digits); zero has sign 0 and digits (0,)."""
    _integer(value)
    _base(base)
    sign = (value > 0) - (value < 0)
    remaining = abs(value)
    digits = []
    while remaining:
        remaining, digit = divmod(remaining, base)
        digits.append(digit)
    return sign, tuple(reversed(digits)) if digits else (0,)


def digits_to_integer(sign, digits, base):
    """Decode explicit positional digits. Leading zero digits are accepted."""
    _base(base)
    if type(sign) is not int or sign not in (-1, 0, 1):
        raise ValueError('sign must be -1, 0 or 1')
    if not isinstance(digits, (tuple, list)) or not digits:
        raise ValueError('digits must be a nonempty tuple/list')
    value = 0
    for digit in digits:
        if type(digit) is not int or not 0 <= digit < base:
            raise ValueError('digit outside base')
        value = value * base + digit
    if sign == 0 and value != 0:
        raise ValueError('zero sign requires zero value')
    return -value if sign < 0 else value


def integer_to_balanced_ternary(value):
    """MSD-first trits in {-1,0,1}; the sign is carried by the trits."""
    _integer(value)
    trits = []
    while value:
        value, digit = divmod(value, 3)
        if digit == 2:
            digit = -1
            value += 1
        trits.append(digit)
    return tuple(reversed(trits)) if trits else (0,)


def balanced_ternary_to_integer(trits):
    if not isinstance(trits, (tuple, list)) or not trits:
        raise ValueError('trits must be a nonempty tuple/list')
    value = 0
    for trit in trits:
        if type(trit) is not int or trit not in (-1, 0, 1):
            raise ValueError('trit must be -1, 0 or 1')
        value = value * 3 + trit
    return value


def fingerprint64_to_bytes(value):
    """Exactly eight unsigned bytes, most-significant byte first (big endian)."""
    _integer(value)
    if not 0 <= value < (1 << 64):
        raise ValueError('fingerprint must fit unsigned 64 bits')
    return value.to_bytes(8, 'big')


def fingerprint64_from_bytes(data):
    if type(data) is not bytes or len(data) != 8:
        raise ValueError('fingerprint requires exactly eight bytes')
    return int.from_bytes(data, 'big')


def rational_to_digits(numerator, denominator, base):
    """Exact reduced rational as two signed digit records; no rounding decision."""
    _integer(numerator)
    _integer(denominator)
    _base(base)
    if denominator == 0:
        raise ValueError('denominator must not be zero')
    value = Fraction(numerator, denominator)
    return (integer_to_digits(value.numerator, base),
            integer_to_digits(value.denominator, base))


def rational_from_digits(numerator, denominator, base):
    n = digits_to_integer(*numerator, base)
    d = digits_to_integer(*denominator, base)
    if d == 0:
        raise ValueError('denominator must not be zero')
    return Fraction(n, d)


def _alphabet(alphabet):
    if not isinstance(alphabet, (tuple, list)) or len(alphabet) < 2:
        raise ValueError('alphabet must be a tuple/list of distinct tokens')
    if any(type(token) is not str or not token for token in alphabet):
        raise ValueError('tokens must be nonempty strings')
    if len(set(alphabet)) != len(alphabet):
        raise ValueError('tokens must be distinct')


def digits_to_tokens(digits, alphabet):
    """Display-only symbol substitution; preserve token boundaries as a tuple."""
    _alphabet(alphabet)
    if not isinstance(digits, (tuple, list)) or not digits:
        raise ValueError('digits must be a nonempty tuple/list')
    for digit in digits:
        if type(digit) is not int or not 0 <= digit < len(alphabet):
            raise ValueError('digit outside alphabet')
    return tuple(alphabet[digit] for digit in digits)


def tokens_to_digits(tokens, alphabet):
    _alphabet(alphabet)
    if not isinstance(tokens, (tuple, list)) or not tokens:
        raise ValueError('tokens must be a nonempty tuple/list')
    lookup = {token: index for index, token in enumerate(alphabet)}
    if any(type(token) is not str or token not in lookup for token in tokens):
        raise ValueError('unknown token')
    return tuple(lookup[token] for token in tokens)
