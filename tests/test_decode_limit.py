"""Decode-size limit: same boundary semantics as flutter_navigation_basic Base64ImageBridge (#178)."""
import base64

import pytest

import photo_grid as pg

PNG_SIG = b'\x89PNG\r\n\x1a\n'
LIMIT = 100  # small stand-in; real 32 MiB data is never used in CI


def _b64(n):
    return base64.b64encode(PNG_SIG + b'\0' * (n - len(PNG_SIG))).decode()


def test_default_is_32_mib():
    assert pg.MAX_BYTES == 32 * 1024 * 1024 == 33_554_432
    assert pg.max_base64_chars() == 44_739_244
    assert pg.decode_base64.__defaults__ == (pg.MAX_BYTES,)


@pytest.mark.parametrize('prefix', ['', 'data:image/png;base64,'])
def test_exact_limit_accepted(prefix):
    assert len(pg.decode_base64(prefix + _b64(LIMIT), max_bytes=LIMIT)) == LIMIT


@pytest.mark.parametrize('prefix', ['', 'data:image/png;base64,'])
def test_plus_one_same_length_rejected_after_decode(prefix):
    text = _b64(LIMIT + 1)
    assert len(text) == len(_b64(LIMIT)) == pg.max_base64_chars(LIMIT)  # passes the early length check
    with pytest.raises(ValueError, match=f'exceeds {LIMIT} bytes'):
        pg.decode_base64(prefix + text, max_bytes=LIMIT)


def test_plus_three_rejected_by_length_check():
    text = _b64(LIMIT + 3)
    assert len(text) > pg.max_base64_chars(LIMIT)
    with pytest.raises(ValueError, match=f'exceeds {LIMIT} bytes'):
        pg.decode_base64(text, max_bytes=LIMIT)


def test_length_check_runs_before_alphabet_check():
    # same order as Dart: an oversize string is reported as oversize, even if it is not valid Base64
    with pytest.raises(ValueError, match='exceeds'):
        pg.decode_base64('!' * (pg.max_base64_chars(LIMIT) + 1), max_bytes=LIMIT)


@pytest.mark.parametrize('limit', [1, 2, 3, 4, 99, 100, 101, 102])
def test_max_base64_chars_matches_dart_formula(limit):
    assert pg.max_base64_chars(limit) == 4 * ((limit + 2) // 3) == len(base64.b64encode(b'\0' * limit))
