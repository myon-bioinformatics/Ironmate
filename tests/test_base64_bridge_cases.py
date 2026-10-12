"""Clipboard/Base64 import cases mirroring bugs found in flutter_navigation_basic's Base64ImageBridge.

The literal cases live in tests/fixtures/base64_bridge_cases.json so another implementation (e.g.
the Flutter app's Dart tests) can load the same inputs and expectations.
"""
import base64, json
from pathlib import Path

import pytest

import grid_tools as g
import photo_grid

CASES = json.loads((Path(__file__).parent / 'fixtures' / 'base64_bridge_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES['cases'], ids=lambda c: c['id'])
def test_case(case):
    if case['expect'] == 'ok':
        data = photo_grid.decode_base64(case['text'])
        assert photo_grid._sniff(data) == case['result']
        photo_grid.decode_image(data)
        if case['result'] == 'png':
            assert g.restore(case['text'], size=2)['width'] == 2
    else:
        with pytest.raises(ValueError, match=case['messageContains']):
            photo_grid.decode_image(photo_grid.decode_base64(case['text']))


def test_every_flutter_bug_is_covered():
    assert {c['flutterBug'] for c in CASES['cases']} >= {1, 2, 3, 4}


def test_unified_limit_bytes_and_chars():
    """One byte limit; the Base64 char limit is derived from it, for raw and data URI alike."""
    limit = 3000
    exact = base64.b64encode(b'\x89PNG\r\n\x1a\n' + bytes(limit - 8)).decode()
    over = base64.b64encode(b'\x89PNG\r\n\x1a\n' + bytes(limit - 7)).decode()
    for prefix in ('', 'data:image/png;base64,'):
        assert len(photo_grid.decode_base64(prefix + exact, max_bytes=limit)) == limit
        with pytest.raises(ValueError, match=f'exceeds {limit} bytes'):
            photo_grid.decode_base64(prefix + over, max_bytes=limit)
    wrapped = '\r\n'.join(exact[i:i + 76] for i in range(0, len(exact), 76))
    assert len(photo_grid.decode_base64(wrapped, max_bytes=limit)) == limit  # whitespace is not counted
    assert CASES['limits']['maxBase64Chars'] == 4 * -(-photo_grid.MAX_BYTES // 3)
    assert CASES['limits']['maxInputBytes'] == photo_grid.MAX_BYTES


def test_repeated_two_thirds_downscale_loses_but_png_round_trip_does_not():
    """Flutter bug 5: re-encoding at 2/3 on every paste compounds; a PNG/Base64 round trip is exact."""
    art = g.make('circle', 'C04', 'outline', 48)
    current = art
    sizes = []
    for _ in range(3):  # paste -> copy -> paste ...
        current = g.restore(g.encode(g.resize(current, max(1, round(current['width'] * 2 / 3)))))
        sizes.append(current['width'])
    assert sizes == [32, 21, 14]
    assert g.cells(g.resize(current, 48)) != g.cells(art)
    same = art
    for _ in range(10):
        same = g.restore(g.encode(same, data_uri=True))
    assert same == art
