import base64, json, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import photo_grid as g


def _png(width, height, pixel, color_type=6, depth=8, interlace=0, filter_type=0):
    channels = {0: 1, 2: 3, 4: 2, 6: 4, 3: 1}[color_type]
    raw = b''.join(bytes([filter_type]) + b''.join(bytes(pixel(x, y)[:channels]) for x in range(width))
                   for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    header = struct.pack('>IIBBBBB', width, height, depth, color_type, 0, 0, interlace)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))


def _b64(data):
    return base64.b64encode(data).decode('ascii')


def _quadrants(x, y):
    return [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)][(y >= 10) * 2 + (x >= 10)]


@pytest.mark.parametrize('size', g.SIZES)
def test_dimensions_palette_range_and_determinism(size):
    text = _b64(_png(20, 20, _quadrants))
    a = g.convert(text, size=size, colors=4)
    assert a == g.convert(text, size=size, colors=4)
    assert a['schema'] == 'ironmate-pixel-grid/1' and a['width'] == a['height'] == size
    assert len(a['pixels']) == size and all(len(r) == size for r in a['pixels'])
    assert all(type(v) is int and 0 <= v < len(a['colors']) for r in a['pixels'] for v in r)
    assert a['colors'][0] == '#00000000' and len(a['colors']) <= 5
    assert sorted(a['colors'][1:]) == sorted(['#FF0000FF', '#00FF00FF', '#0000FFFF', '#FFFF00FF'])
    corner = {a['colors'][a['pixels'][y][x]] for y, x in ((0, 0), (0, -1), (-1, 0), (-1, -1))}
    assert len(corner) == 4


def test_area_average_and_center_crop():
    # 48x16: center crop keeps x=16..31 (black/white stripes); red sides are discarded.
    def pixel(x, y):
        if not 16 <= x < 32:
            return (255, 0, 0, 255)
        return (0, 0, 0, 255) if x % 2 else (255, 255, 255, 255)
    a = g.convert(_b64(_png(48, 16, pixel)), size=8, colors=16)
    assert a['source'] == {'width': 48, 'height': 16}
    assert a['colors'] == ['#00000000', '#808080FF']
    assert {v for r in a['pixels'] for v in r} == {1}


def test_transparency_and_contain_margin():
    half = _b64(_png(16, 16, lambda x, y: (200, 10, 10, 255 if x < 8 else 0)))
    a = g.convert(half, size=16, colors=2)
    assert all(r[0] != 0 and r[-1] == 0 for r in a['pixels'])
    assert a['colors'] == ['#00000000', '#C80A0AFF']
    wide = _b64(_png(32, 8, lambda x, y: (0, 0, 255, 255), color_type=2))
    c = g.convert(wide, size=16, fit='contain')
    assert not any(c['pixels'][0]) and not any(c['pixels'][-1])
    assert sum(1 for r in c['pixels'] if any(r)) == 4


@pytest.mark.parametrize('color_type,filter_type', [(0, 1), (2, 2), (4, 3), (6, 4)])
def test_png_color_types_and_filters(color_type, filter_type):
    data = _png(5, 4, lambda x, y: (x * 40, y * 50, 90, 255), color_type, filter_type=filter_type)
    width, height, rows = g.decode_png(data)
    assert (width, height, len(rows), len(rows[0])) == (5, 4, 4, 20)


def test_png_filters_reconstruct_exact_pixels():
    pixel = lambda x, y: (x * 30 % 256, y * 70 % 256, (x * y) % 256, 200)
    expected = g.decode_png(_png(6, 5, pixel))[2]
    raw = []
    for y in range(5):
        line = b''.join(bytes(pixel(x, y)) for x in range(6))
        prev = b''.join(bytes(pixel(x, y - 1)) for x in range(6)) if y else bytes(24)
        raw.append(b'\x02' + bytes((line[i] - prev[i]) & 255 for i in range(24)))
    body = zlib.compress(b''.join(raw))
    data = _png(6, 5, pixel)
    head = data[:33]
    idat = struct.pack('>I', len(body)) + b'IDAT' + body + struct.pack('>I', zlib.crc32(b'IDAT' + body))
    tail = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND'))
    assert g.decode_png(head + idat + tail)[2] == expected


def test_fixed_palette_and_data_uri():
    data = _png(4, 4, lambda x, y: (91, 189, 62, 255))
    uri = 'data:image/png;base64,' + _b64(data)
    a = g.convert(uri, size=8, palette='C01')
    assert a['colors'] == list(g.PALETTES['C01'])
    assert {v for r in a['pixels'] for v in r} == {1}
    wrapped = '\n'.join(_b64(data)[i:i + 10] for i in range(0, len(_b64(data)), 10))
    assert g.decode_base64(wrapped) == data


@pytest.mark.parametrize('text', ['', '   ', 'abc', 'a!==', 'data:image/png,abcd', 'AAAA====', 'éé'])
def test_invalid_base64(text):
    with pytest.raises(ValueError):
        g.decode_base64(text)


def test_size_limits():
    data = _png(4, 4, lambda x, y: (1, 2, 3, 255))
    with pytest.raises(ValueError, match='exceeds'):
        g.decode_base64(_b64(data), max_bytes=len(data) - 1)
    with pytest.raises(g.ImageDecodeError, match='pixels'):
        g.convert(_b64(data), max_pixels=15)


@pytest.mark.parametrize('kwargs,match', [
    ({'depth': 16}, 'unsupported'), ({'color_type': 3}, 'unsupported'), ({'interlace': 1}, 'interlaced')])
def test_unsupported_png(kwargs, match):
    data = _png(2, 2, lambda x, y: (0, 0, 0, 0), **kwargs)
    with pytest.raises(g.ImageDecodeError, match=match):
        g.decode_png(data)


def test_corrupt_png():
    data = bytearray(_png(2, 2, lambda x, y: (0, 0, 0, 255)))
    data[20] ^= 1
    with pytest.raises(g.ImageDecodeError, match='CRC'):
        g.decode_png(bytes(data))
    with pytest.raises(g.ImageDecodeError):
        g.decode_png(bytes(data[:30]))


@pytest.mark.parametrize('kwargs', [{'size': 17}, {'size': True}, {'fit': 'stretch'},
                                    {'colors': 0}, {'colors': 17}, {'palette': 'unknown'}])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        g.convert(_b64(_png(2, 2, lambda x, y: (0, 0, 0, 255))), **kwargs)


def test_non_png_without_pillow_has_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    with pytest.raises(g.ImageDecodeError, match='Pillow'):
        g.convert(_b64(b'\xff\xd8\xff\xe0 not really a jpeg'))


def test_pillow_adapter_jpeg():
    pil = pytest.importorskip('PIL.Image')
    import io
    buffer = io.BytesIO()
    pil.new('RGB', (24, 12), (250, 20, 20)).save(buffer, 'JPEG', quality=95)
    a = g.convert(_b64(buffer.getvalue()), size=8, colors=1)
    r, gg, b = g._hex_rgb(a['colors'][1])
    assert r > 200 and gg < 60 and b < 60
    assert {v for row in a['pixels'] for v in row} == {1}


def test_cli_and_inert_import(tmp_path):
    file = Path(g.__file__).resolve()
    src = tmp_path / 'in.b64'
    src.write_text(_b64(_png(8, 8, _quadrants)), encoding='ascii')
    result = subprocess.run([sys.executable, '-S', str(file), str(src), '--size', '8'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['width'] == 8
    bad = subprocess.run([sys.executable, '-S', str(file), '-'], input='not base64!',
                         cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode == 2 and 'invalid Base64' in bad.stderr
    probe = ('import sys;sys.path.insert(0,sys.argv[1]);import photo_grid;'
             'assert "PIL" not in sys.modules')
    result = subprocess.run([sys.executable, '-S', '-c', probe, str(file.parent)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0 and result.stdout == result.stderr == b''
    assert sorted(p.name for p in tmp_path.iterdir()) == ['in.b64']
