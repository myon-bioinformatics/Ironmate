"""pillow_min: PNG decode/encode, Image API, and diff helpers vs Pillow reference."""
import base64
import io
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

import pillow_min as pm

ROOT = Path(__file__).resolve().parents[1]
from PIL import Image as PILImage
from PIL import ImageChops as PILImageChops


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _png_bytes(width, height, pixels, color_type=6, depth=8, interlace=0, filter_type=0, palette=None, trns=None):
    channels = {0: 1, 2: 3, 4: 2, 6: 4, 3: 1}[color_type]
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            px = pixels(x, y)
            if color_type == 3:
                row.append(px[0] if isinstance(px, tuple) else px)
            else:
                row.extend(px[:channels])
        if color_type == 3 and depth < 8:
            packed = bytearray()
            acc = bit = 0
            for v in row:
                acc = (acc << depth) | (v & ((1 << depth) - 1))
                bit += depth
                while bit >= 8:
                    bit -= 8
                    packed.append((acc >> bit) & 255)
            row = packed
        rows.append(bytes([filter_type]) + bytes(row))
    raw = b''.join(rows)
    parts = [b'\x89PNG\r\n\x1a\n', _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color_type, 0, 0, interlace))]
    if palette is not None:
        parts.append(_chunk(b'PLTE', palette))
    if trns is not None:
        parts.append(_chunk(b'tRNS', trns))
    parts.append(_chunk(b'IDAT', zlib.compress(raw)))
    parts.append(_chunk(b'IEND', b''))
    return b''.join(parts)


def _pillow_rgba(data: bytes):
    with PILImage.open(io.BytesIO(data), formats=['PNG']) as img:
        return img.convert('RGBA')


def _pm_rgba(data: bytes):
    return pm.open_bytes(data).convert('RGBA')


def assert_pixels_match(data: bytes):
    ref = _pillow_rgba(data)
    got = _pm_rgba(data)
    assert got.size == ref.size
    assert got.tobytes() == ref.tobytes()


@pytest.mark.parametrize('color_type', [0, 2, 4, 6])
@pytest.mark.parametrize('filter_type', [0, 1, 2, 3, 4])
def test_color_types_and_filters(color_type, filter_type):
    data = _png_bytes(5, 4, lambda x, y: (x * 40, y * 50, 90, 200), color_type=color_type, filter_type=filter_type)
    assert_pixels_match(data)


@pytest.mark.parametrize('depth', [1, 2, 4, 8])
def test_palette_depths(depth):
    img = PILImage.new('P', (7, 3))
    palette = [255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]
    img.putpalette(palette + [0] * (768 - len(palette)))
    for y in range(3):
        for x in range(7):
            img.putpixel((x, y), (x + y) % 4)
    buf = io.BytesIO()
    img.save(buf, format='PNG', bits=depth, transparency=bytes([255, 128, 0, 255]))
    assert_pixels_match(buf.getvalue())


def test_grayscale_trns():
    data = _png_bytes(3, 2, lambda x, y: (x * 80,), color_type=0, trns=struct.pack('>H', 80))
    assert_pixels_match(data)


def test_rgb_trns():
    data = _png_bytes(2, 2, lambda x, y: (1, 2, 3), color_type=2, trns=struct.pack('>3H', 1, 2, 3))
    assert_pixels_match(data)


def test_adam7_interlace():
    img = PILImage.new('RGBA', (8, 8))
    px = img.load()
    for y in range(8):
        for x in range(8):
            px[x, y] = (x * 31, y * 17, 90, 255)
    buf = io.BytesIO()
    img.save(buf, format='PNG', interlace=True)
    assert_pixels_match(buf.getvalue())


def test_apng_default_frame():
    from tests.test_apng_input import apng

    data = apng(default_in_animation=False)
    assert_pixels_match(data)


def test_encode_roundtrip_rgb_rgba():
    for mode, color in (('RGB', (10, 20, 30)), ('RGBA', (1, 2, 3, 4))):
        src = pm.Image.new(mode, (3, 2), color)
        out = pm.open_bytes(pm.encode_png(src))
        assert out.mode == 'RGBA'
        assert out.tobytes() == src.convert('RGBA').tobytes()


def test_image_api_and_base64():
    img = pm.Image.new('RGB', (2, 1), (5, 6, 7))
    cropped = img.crop((0, 0, 1, 1))
    assert cropped.size == (1, 1) and cropped.getpixel((0, 0)) == (5, 6, 7)
    text = img.to_base64(data_uri=True)
    assert text.startswith('data:image/png;base64,')
    back = pm.open_bytes(pm.decode_base64(text))
    assert back.tobytes() == img.convert('RGBA').tobytes()


def test_diff_helpers_match_pillow():
    a = pm.Image.new('RGB', (4, 3), (10, 20, 30))
    b = pm.Image.new('RGB', (4, 3), (12, 18, 40))
    d = pm.ImageChops.difference(a, b)
    ref = PILImageChops.difference(PILImage.new('RGB', (4, 3), (10, 20, 30)), PILImage.new('RGB', (4, 3), (12, 18, 40)))
    assert d.convert('RGB').tobytes() == ref.tobytes()
    r, g, bl = d.split()[:3]
    hist = pm.ImageChops.lighter(pm.ImageChops.lighter(r, g), bl).histogram()
    ref_r, ref_g, ref_b = ref.split()[:3]
    ref_hist = PILImageChops.lighter(PILImageChops.lighter(ref_r, ref_g), ref_b).histogram()
    assert hist == ref_hist
    stats = pm.diff_metrics(a, b, threshold=1)
    assert stats['max_diff'] == 10
    assert stats['changed_pixels'] == 4 * 3


def test_non_png_rejected():
    with pytest.raises(pm.UnsupportedImageError):
        pm.open_bytes(b'not a png')
    with pytest.raises(ValueError, match='unsupported data URI'):
        pm.decode_base64('data:image/jpeg;base64,' + base64.b64encode(b'x').decode())


def test_decompression_bomb():
    header = struct.pack('>IIBBBBB', 4096, 4096, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(b'\x00' * 100)) + _chunk(b'IEND', b'')
    with pytest.raises(pm.ImageDecodeError):
        pm.open_bytes(png, max_pixels=1000)


def test_corrupt_crc_and_truncation():
    good = _png_bytes(2, 2, lambda x, y: (1, 2, 3, 4))
    bad = bytearray(good)
    bad[30] ^= 1
    with pytest.raises(pm.ImageDecodeError, match='CRC'):
        pm.open_bytes(bytes(bad))
    with pytest.raises(pm.ImageDecodeError):
        pm.open_bytes(bytes(good[:40]))


def test_standalone_python_s():
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'pillow_min.py')], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
