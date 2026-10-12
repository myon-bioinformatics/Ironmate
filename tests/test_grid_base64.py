import base64, json, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import grid_png as gp
import photo_grid
import pixel_grid

ROOT = Path(__file__).resolve().parents[1]
PHOTO = [sys.executable, '-S', str(ROOT / 'photo_grid.py')]
PIXEL = [sys.executable, '-S', str(ROOT / 'pixel_grid.py')]


def _key(art):
    return art['colors'], art['pixels']


def _photo_art():
    def pixel(x, y):
        return [(200, 30, 30, 255), (30, 200, 30, 255), (30, 30, 200, 255), (0, 0, 0, 0)][(y >= 4) * 2 + (x >= 4)]
    raw = b''.join(b'\x00' + b''.join(bytes(pixel(x, y)) for x in range(8)) for y in range(8))
    def chunk(k, b):
        return struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return photo_grid.convert(base64.b64encode(png).decode(), size=8, colors=8)


@pytest.mark.parametrize('data_uri', [False, True])
def test_pixel_grid_round_trip_identical(data_uri):
    for mask in pixel_grid.MASKS:
        for palette in pixel_grid.PALETTES:
            art = pixel_grid.render(mask, palette, 'outline', 16)
            text = gp.to_base64(art, data_uri=data_uri)
            assert text.startswith('data:image/png;base64,') == data_uri
            back = photo_grid.convert(text, size=16, palette=palette)
            assert _key(back) == _key(art)


@pytest.mark.parametrize('data_uri', [False, True])
def test_photo_grid_round_trip_identical(data_uri):
    art = _photo_art()
    assert len(art['colors']) == 4
    back = photo_grid.convert(gp.to_base64(art, data_uri=data_uri), size=8, colors=len(art['colors']) - 1)
    assert _key(back) == _key(art)


def test_same_bytes_as_png_and_deterministic():
    art = pixel_grid.render('cloud', 'lava', 'shadow', 32)
    for scale in (1, 4):
        text = gp.to_base64(art, scale)
        assert text == gp.to_base64(art, scale)
        assert base64.b64decode(text, validate=True) == gp.to_png(art, scale)
        assert photo_grid.decode_base64(gp.to_base64(art, scale, True)) == gp.to_png(art, scale)


def test_scaled_round_trip_needs_matching_target():
    art = pixel_grid.render('diamond', 'water', 'normal', 16)
    text = gp.to_base64(art, scale=2)  # 32x32 image
    assert _key(photo_grid.convert(text, size=16, palette='water')) == _key(art)  # target = original size
    assert photo_grid.convert(text, size=32, palette='water')['width'] == 32  # different grid


def test_cli_end_to_end(tmp_path):
    out = tmp_path / 'g.b64'
    r = subprocess.run(PIXEL + ['--mask', 'rock', '--palette', 'desert', '--size', '8', '--format', 'base64',
                                '--data-uri', '-o', str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == '', r.stderr
    art = pixel_grid.render('rock', 'desert', 'normal', 8)
    assert out.read_text(encoding='ascii') == gp.to_base64(art, data_uri=True) + '\n'
    j = subprocess.run(PHOTO + [str(out), '--size', '8', '--palette', 'desert'], capture_output=True, text=True)
    assert _key(json.loads(j.stdout)) == _key(art)
    again = subprocess.run(PHOTO + [str(out), '--size', '8', '--palette', 'desert', '--format', 'base64'],
                           capture_output=True, text=True)
    assert again.stdout == gp.to_base64(art) + '\n'
    piped = subprocess.run(PHOTO + ['-', '--size', '8', '--palette', 'desert'], input=again.stdout,
                           capture_output=True, text=True)
    assert _key(json.loads(piped.stdout)) == _key(art)
    scaled = subprocess.run(PIXEL + ['--size', '8', '--format', 'base64', '--scale', '3'], capture_output=True, text=True)
    assert photo_grid.decode_png(base64.b64decode(scaled.stdout))[:2] == (24, 24)
