"""Repeated image interchange, original-pixel witnesses, subprocess boundaries.

Transport cycles are lossless PNG controls, not JPEG re-encoding or resize claims.
"""
import base64
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
import grid_tools as grid
import ironmate_image as image
import studio_ingress as ingress

ROOT = Path(__file__).resolve().parents[1]


def fixture(seed):
    rng = random.Random(seed)
    art = grid.make('cloud', 'C01', 'normal', 16)
    # Include transparent RGB, partial alpha, duplicate colors and unused entries.
    art['colors'] = ['#12345600', '#ABCDEF80', '#112233FF', '#112233FF', '#FFFFFF00']
    art['pixels'] = [[rng.randrange(4) for _ in row] for row in art['pixels']]
    return art


def rgba(art):
    return tuple(tuple(art['colors'][i].upper() for i in row) for row in art['pixels'])


@pytest.mark.parametrize('seed', [0, 1, 64, 20261026])
@pytest.mark.parametrize('meta', [False, True])
@pytest.mark.parametrize('initial_uri', [False, True])
def test_25_cycles_preserve_original_pixels(seed, meta, initial_uri, tmp_path):
    art = fixture(seed)
    expected = rgba(art)
    current = art
    for cycle in range(25):
        text = image.to_base64(current, meta=meta, data_uri=bool((cycle + initial_uri) % 2))
        mime, raw = ingress.decode(text)
        assert mime == 'image/png'
        assert base64.b64decode(text.split(',')[-1], validate=True) == raw
        # Alternate entry points: dict/JSON, bytes, filesystem, plain Base64/URI.
        mode = cycle % 5
        if mode == 0:
            current = image.load(json.dumps(image.from_base64(text)))
        elif mode == 1:
            current = image.load(raw)
        elif mode == 2:
            path = tmp_path / 'roundtrip.png'
            path.write_bytes(raw)
            current = image.load(path)
        elif mode == 3:
            current = image.from_base64(text)
        else:
            current = image.load(base64.b64encode(raw).decode('ascii'))
        assert (current['width'], current['height']) == (art['width'], art['height'])
        assert rgba(current) == expected, (seed, meta, cycle)
        if meta:
            assert current['colors'] == art['colors']
            # Identical RGBA entries cannot retain distinct indices in RGBA PNG.
            canonical = [[art['colors'].index(art['colors'][i]) for i in row]
                         for row in art['pixels']]
            assert current['pixels'] == canonical


def test_repeated_real_python_stdin_stdout_png_base64():
    art = fixture(19)
    raw = image.to_png(art)
    for cycle in range(4):
        args = ['to-base64', '-'] + (['--data-uri'] if cycle % 2 else [])
        encoded = subprocess.run([sys.executable, '-S', '-m', 'ironmate_image', *args],
                                 cwd=ROOT, input=raw, capture_output=True, timeout=30)
        assert encoded.returncode == 0, encoded.stderr
        decoded = subprocess.run([sys.executable, '-S', '-m', 'ironmate_image', 'to-png', '-'],
                                 cwd=ROOT, input=encoded.stdout, capture_output=True, timeout=30)
        assert decoded.returncode == 0, decoded.stderr
        raw = decoded.stdout
        assert raw.startswith(b'\x89PNG\r\n\x1a\n')
        assert rgba(image.load(raw)) == rgba(art)


def test_repeated_ingress_padding_whitespace_budget_and_corruption():
    original = image.to_png(fixture(3))
    # All three padding residues, using bytes after PNG only for transport tests.
    for tail in range(3):
        raw = original + bytes(tail)
        for cycle in range(12):
            encoded = base64.b64encode(raw).decode('ascii')
            wrapped = '\n'.join(encoded[i:i+17] for i in range(0, len(encoded), 17))
            uri = 'data:image/png;base64,' + wrapped
            _, decoded = ingress.decode(uri, max_bytes=len(raw))
            assert decoded == raw
            with pytest.raises(ValueError):
                ingress.decode(uri, max_bytes=len(raw)-1)
            bad = encoded[:8] + '!' + encoded[9:]
            with pytest.raises(ValueError):
                ingress.decode(bad)
            with pytest.raises(ValueError):
                ingress.decode('data:image/jpeg;base64,' + encoded)
            with pytest.raises(ValueError):
                ingress.decode(encoded[:-1])
            raw = decoded


def test_repeat_fit_after_first_selection_preserves_selected_pixels_and_budget():
    # A generous bound isolates stable repeated transport, not repeated loss.
    art = fixture(47)
    text = image.to_base64(art, data_uri=True)
    budget = len(text)
    expected = rgba(art)
    for _ in range(4):
        result = image.fit_to_limit(text, max_chars=budget, data_uri=True)
        assert result.chars == len(result.text) <= budget
        current = image.from_base64(result.text)
        assert rgba(current) == expected
        text = result.text
