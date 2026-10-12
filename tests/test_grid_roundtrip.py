"""Property-style verification of PNG/Base64 output and the photo_grid round trip (fixed seeds)."""
import base64, io, math, random, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import grid_png as gp
import photo_grid as pg
import pixel_grid

ROOT = Path(__file__).resolve().parents[1]
PHOTO = [sys.executable, '-S', str(ROOT / 'photo_grid.py')]


def _random_art(rnd, width, height, count, transparent):
    colors = set()
    while len(colors) < count:
        colors.add('#%02X%02X%02XFF' % tuple(rnd.randrange(256) for _ in range(3)))
    table = (['#00000000'] if transparent else []) + sorted(colors)
    pixels = [[rnd.randrange(len(table)) for _ in range(width)] for _ in range(height)]
    return {'width': width, 'height': height, 'colors': table, 'pixels': pixels}


def _expected_rows(art, scale):
    rgba = [bytes.fromhex(c[1:]) for c in art['colors']]
    return [b''.join(rgba[v] * scale for v in row) for row in art['pixels'] for _ in range(scale)]


def _chunks(data):
    """Independent PNG structure check: signature, CRCs, IHDR first, IEND last, nothing trailing."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos, chunks = 8, []
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        assert struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0] == zlib.crc32(kind + body)
        chunks.append((kind, body))
        pos += 12 + length
    assert pos == len(data) and chunks[0][0] == b'IHDR' and chunks[-1] == (b'IEND', b'')
    return chunks


def _png(width, height, pixel):
    raw = b''.join(b'\x00' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def _key(art):
    return art['colors'], art['pixels']


def _check_random(seed, iterations):
    rnd = random.Random(seed)
    try:
        from PIL import Image
    except ImportError:
        Image = None
    for _ in range(iterations):
        width, height = rnd.choice((1, 2, 7, 8, 16, 33, 128)), rnd.choice((1, 5, 8, 16, 128))
        art = _random_art(rnd, width, height, rnd.randint(1, 16), rnd.random() < 0.5)
        scale = rnd.randint(1, 4) if width * height <= 4096 else 1
        data = gp.to_png(art, scale)
        header = struct.unpack('>IIBBBBB', _chunks(data)[0][1])
        assert header == (width * scale, height * scale, 8, 6, 0, 0, 0)
        assert pg.decode_png(data) == (width * scale, height * scale, _expected_rows(art, scale))
        if Image:
            with Image.open(io.BytesIO(data)) as image:
                assert image.mode == 'RGBA' and image.tobytes() == b''.join(_expected_rows(art, scale))
        for data_uri in (False, True):
            assert pg.decode_base64(gp.to_base64(art, scale, data_uri)) == data
        if width == height and width in pixel_grid.SIZES and art['colors'][0] == '#00000000':
            used = {v for row in art['pixels'] for v in row}
            if used >= set(range(1, len(art['colors']))):
                back = pg.convert(gp.to_base64(art, scale, rnd.random() < 0.5), size=width,
                                  colors=len(art['colors']) - 1)
                assert _key(back) == _key(art)


def test_random_grids_round_trip():
    _check_random(1234, 60)


@pytest.mark.heavy
def test_random_grids_round_trip_many():
    for seed in range(5):
        _check_random(seed, 200)


def _photos():
    rnd = random.Random(7)
    return {
        'gradient': _png(200, 150, lambda x, y: (x * 255 // 199, y * 255 // 149, (x + y) % 256, 255)),
        'noise': _png(120, 90, lambda x, y: (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255)),
        'alpha_disc': _png(100, 80, lambda x, y: (200, 100, 50, max(0, 255 - int(3 * math.hypot(x - 50, y - 40))))),
    }


@pytest.mark.parametrize('name', ['gradient', 'noise', 'alpha_disc'])
@pytest.mark.parametrize('fit', ['crop', 'contain'])
def test_photo_like_round_trip(name, fit):
    source = base64.b64encode(_photos()[name]).decode()
    for size in (16, 64):
        for colors in (1, 8, 16):
            art = pg.convert(source, size=size, fit=fit, colors=colors)
            assert {v for row in art['pixels'] for v in row} >= set(range(1, len(art['colors'])))
            for scale, uri in ((1, False), (2, True)):
                back = pg.convert(gp.to_base64(art, scale, uri), size=size, colors=len(art['colors']) - 1)
                assert _key(back) == _key(art)
        fixed = pg.convert(source, size=size, fit=fit, palette='C01')
        assert _key(pg.convert(gp.to_base64(fixed), size=size, palette='C01')) == _key(fixed)


def test_median_cut_drops_unused_colors():
    # Regression: a 200x150 gradient fitted into 16 used 7 of 8 median-cut colors.
    art = pg.convert(base64.b64encode(_photos()['gradient']).decode(), size=16, fit='contain', colors=8)
    assert {v for row in art['pixels'] for v in row} == set(range(len(art['colors'])))


PNG8 = gp.to_png(pixel_grid.render('circle', size=8))
B64 = base64.b64encode(PNG8).decode()


@pytest.mark.parametrize('text', [
    '\r\n'.join(B64[i:i + 76] for i in range(0, len(B64), 76)) + '\r\n',
    '\ufeff' + B64, 'DATA:IMAGE/PNG;BASE64,' + B64, 'data:image/png;base64,\r\n' + B64,
    'data:;base64,' + B64, B64.encode('ascii'), PNG8])
def test_accepted_inputs(text):
    assert _key(pg.convert(text, size=8, palette='C01')) == _key(pixel_grid.render('circle', size=8))


@pytest.mark.parametrize('text,match', [
    ('', 'empty'), (' \r\n', 'empty'), (B64.rstrip('='), 'padding'),
    (base64.urlsafe_b64encode(b'\xfb\xff' * 30).decode(), 'URL-safe'),
    ('data:text/plain;base64,' + B64, 'unsupported data URI type'),
    ('data:image/svg+xml;base64,' + B64, 'unsupported data URI type'),
    ('data:image/jpeg;base64,' + B64, 'not that format'),
    ('data:image/webp;base64,' + base64.b64encode(b'RIFF\0\0\0\0WAVE').decode(), 'not that format'),
    ('data:image/png,' + B64, 'base64-encoded'), (b'\xff\xfe', 'ASCII'),
    (base64.b64encode(PNG8[:-20]).decode(), 'truncated'),
    (base64.b64encode(PNG8[:40] + bytes([PNG8[40] ^ 1]) + PNG8[41:]).decode(), 'CRC'),
])
def test_rejected_inputs(text, match):
    with pytest.raises(ValueError, match=match):
        pg.convert(text, size=8)


def test_limits():
    limit = pg.MAX_BYTES
    exact = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\0' * (limit - 8)).decode()
    with pytest.raises(pg.ImageDecodeError):  # accepted by size, then rejected as a PNG
        pg.convert(exact)
    over = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\0' * (limit - 7)).decode()
    with pytest.raises(ValueError, match='exceeds'):
        pg.convert(over)
    big = pixel_grid.render(size=128)
    assert pg.decode_png(gp.to_png(big, 32))[:2] == (4096, 4096)
    with pytest.raises(ValueError, match='exceeds'):
        gp.to_png(big, 33)
    for scale in (0, 65, True, 1.0):
        with pytest.raises(ValueError, match='scale'):
            gp.to_base64(big, scale)


def test_cli_pipelines_and_crlf(tmp_path):
    art = pg.convert(base64.b64encode(_photos()['gradient']).decode(), size=16, colors=6)
    count = str(len(art['colors']) - 1)
    crlf = tmp_path / 'crlf.b64'
    text = gp.to_base64(art, data_uri=True)
    crlf.write_bytes(('\r\n'.join(text[i:i + 76] for i in range(0, len(text), 76)) + '\r\n').encode('ascii'))
    one = subprocess.run(PHOTO + [str(crlf), '--size', '16', '--colors', count, '--format', 'base64'],
                         capture_output=True)
    assert one.returncode == 0 and one.stdout == (gp.to_base64(art) + '\n').encode('ascii')
    two = subprocess.run(PHOTO + ['-', '--size', '16', '--colors', count, '--format', 'png'],
                         input=one.stdout, capture_output=True)
    assert two.returncode == 0 and two.stdout == gp.to_png(art)
    out = tmp_path / 'again.b64'
    three = subprocess.run(PHOTO + ['-', '--size', '16', '--colors', count, '--format', 'base64',
                                    '--data-uri', '-o', str(out)], input=two.stdout, capture_output=True)
    assert three.returncode == 0 and three.stdout == b''
    assert out.read_text(encoding='ascii') == text + '\n'
    bad = subprocess.run(PHOTO + ['-'], input=b'data:text/plain;base64,QUJD', capture_output=True, text=False)
    assert bad.returncode == 2 and b'unsupported data URI type' in bad.stderr and b'Traceback' not in bad.stderr
