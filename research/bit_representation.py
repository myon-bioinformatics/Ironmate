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
    """Decode positional digits; leading zeros are accepted, signed zero is not.

    A zero magnitude requires sign 0; a nonzero magnitude requires -1 or 1.
    """
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
    if value == 0 and sign != 0:
        raise ValueError('zero value requires zero sign')
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


def _u32_limbs(limbs):
    if not isinstance(limbs, (tuple, list)) or not limbs:
        raise ValueError('limbs must be a nonempty tuple/list')
    for limb in limbs:
        if type(limb) is not int or not 0 <= limb < (1 << 32):
            raise ValueError('limbs must be unsigned 32-bit integers')


def integer_to_u32_limbs(value):
    """Unsigned base-2**32 digits, least-significant limb first; zero -> (0,)."""
    _integer(value)
    if value < 0:
        raise ValueError('value must be unsigned')
    limbs = []
    while value:
        limbs.append(value & 0xffffffff)
        value >>= 32
    return tuple(limbs) if limbs else (0,)


def u32_limbs_to_integer(limbs):
    _u32_limbs(limbs)
    value = 0
    for limb in reversed(limbs):
        value = (value << 32) | limb
    return value


def add_u32_limbs(left, right):
    """Exact unsigned addition with explicit carry; canonical result, no wrap."""
    _u32_limbs(left)
    _u32_limbs(right)
    result, carry = [], 0
    for i in range(max(len(left), len(right))):
        total = (left[i] if i < len(left) else 0) + (right[i] if i < len(right) else 0) + carry
        result.append(total & 0xffffffff)
        carry = total >> 32
    if carry:
        result.append(carry)
    while len(result) > 1 and result[-1] == 0:
        result.pop()
    return tuple(result)


def fingerprints64_to_bytes(values):
    """Concatenated eight-byte big-endian records, preserving order/duplicates."""
    packed = bytearray()
    for value in values:
        packed.extend(fingerprint64_to_bytes(value))
    return bytes(packed)


def fingerprints64_from_bytes(data):
    """Decode a raw record batch; empty bytes -> empty tuple."""
    if type(data) is not bytes or len(data) % 8:
        raise ValueError('batch requires bytes with length divisible by eight')
    return tuple(fingerprint64_from_bytes(data[i:i+8]) for i in range(0, len(data), 8))


def rgb8_to_integer(red, green, blue):
    """Three raw channels -> 0xRRGGBB; no color-space conversion or clipping."""
    for channel in (red, green, blue):
        if type(channel) is not int or not 0 <= channel <= 255:
            raise ValueError('RGB channels must be integers in 0..255')
    return (red << 16) | (green << 8) | blue


def integer_to_rgb8(value):
    _integer(value)
    if not 0 <= value < (1 << 24):
        raise ValueError('RGB value must fit unsigned 24 bits')
    return value >> 16, (value >> 8) & 255, value & 255


def rgb8_to_bytes(red, green, blue):
    return rgb8_to_integer(red, green, blue).to_bytes(3, 'big')


def rgb8_from_bytes(data):
    if type(data) is not bytes or len(data) != 3:
        raise ValueError('RGB requires exactly three bytes')
    return integer_to_rgb8(int.from_bytes(data, 'big'))
