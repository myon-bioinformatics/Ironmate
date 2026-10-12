"""Input-format matrix for photo_grid: raw file bytes, Base64 and data URI (matches README table)."""
import base64, io, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import photo_grid as pg

ROOT = Path(__file__).resolve().parents[1]


def _png(color_type=6, depth=8, interlace=0):
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    raw = b''.join(b'\x00' + bytes([200]) * (4 * channels) for _ in range(4))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, depth, color_type, 0, 0, interlace))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


SIGNATURES = {  # headers only: these are rejected before any decoding
    'gif': (b'GIF89a' + bytes(20), 'GIF input is not supported'),
    'bmp': (b'BM' + bytes(30), 'BMP input is not supported'),
    'tiff': (b'II*\x00' + bytes(20), 'TIFF input is not supported'),
    'ico': (b'\x00\x00\x01\x00' + bytes(20), 'ICO input is not supported'),
    'avif': (b'\x00\x00\x00\x1cftypavif' + bytes(16), 'HEIC/HEIF/AVIF input is not supported'),
    'heic': (b'\x00\x00\x00\x18ftypheic' + bytes(16), 'HEIC/HEIF/AVIF input is not supported'),
    'svg': (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>', 'SVG input is not supported'),
}


@pytest.mark.parametrize('kind', SIGNATURES)
@pytest.mark.parametrize('form', ['raw', 'base64'])
def test_unsupported_formats_are_rejected_clearly(kind, form):
    data, message = SIGNATURES[kind]
    with pytest.raises(pg.ImageDecodeError, match=message):
        pg.convert(data if form == 'raw' else base64.b64encode(data).decode(), size=8)


def test_svg_text_and_data_uri_types():
    with pytest.raises(pg.ImageDecodeError, match='SVG input'):
        pg.convert('  <svg xmlns="http://www.w3.org/2000/svg"></svg>', size=8)
    for mime in ('image/gif', 'image/bmp', 'image/tiff', 'image/svg+xml', 'image/avif', 'image/heic'):
        with pytest.raises(ValueError, match='unsupported data URI type'):
            pg.convert(f'data:{mime};base64,' + base64.b64encode(_png()).decode(), size=8)


@pytest.mark.parametrize('form', ['raw', 'base64', 'data_uri'])
def test_png_works_without_pillow(form, monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    data = _png()
    text = {'raw': data, 'base64': base64.b64encode(data).decode(),
            'data_uri': 'data:image/png;base64,' + base64.b64encode(data).decode()}[form]
    assert pg.convert(text, size=8)['colors'][1] == '#C8C8C8FF'


@pytest.mark.parametrize('kwargs,message', [({'depth': 16}, 'bit depth 16'), ({'interlace': 1}, 'interlaced')])
def test_png_variants_without_pillow(kwargs, message, monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    with pytest.raises(pg.ImageDecodeError, match=message):
        pg.convert(_png(**kwargs), size=8)


@pytest.mark.parametrize('kind', ['jpeg', 'webp'])
def test_jpeg_webp_need_pillow(kind, monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    data = b'\xff\xd8\xff\xe0' + bytes(20) if kind == 'jpeg' else b'RIFF\x00\x00\x00\x00WEBPVP8 ' + bytes(20)
    for text in (data, base64.b64encode(data).decode()):
        with pytest.raises(pg.ImageDecodeError, match='needs the optional Pillow'):
            pg.convert(text, size=8)


def _pillow_bytes(fmt, mode='RGB', **kw):
    Image = pytest.importorskip('PIL.Image')
    buffer = io.BytesIO()
    Image.new(mode, (20, 12), (200, 30, 30) if mode == 'RGB' else 300).save(buffer, fmt, **kw)
    return buffer.getvalue()


@pytest.mark.parametrize('fmt,mime', [('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')])
def test_jpeg_webp_with_pillow_all_forms(fmt, mime):
    data = _pillow_bytes(fmt)
    for text in (data, base64.b64encode(data).decode(), f'data:{mime};base64,' + base64.b64encode(data).decode()):
        r, g, b = (int(pg.convert(text, size=8, colors=1)['colors'][1][i:i + 2], 16) for i in (1, 3, 5))
        assert r > 170 and g < 70 and b < 70


def test_png_variants_fall_back_to_pillow():
    pytest.importorskip('PIL.Image')
    palette = _pillow_bytes('PNG', 'P')
    deep = _pillow_bytes('PNG', 'I;16')
    for data in (palette, deep):
        assert pg.convert(data, size=8)['width'] == 8


@pytest.mark.parametrize('fmt', ['GIF', 'BMP', 'TIFF', 'ICO'])
def test_real_files_pillow_could_read_are_still_rejected(fmt):
    data = _pillow_bytes(fmt)
    with pytest.raises(pg.ImageDecodeError, match='input is not supported'):
        pg.convert(data, size=8)


@pytest.mark.parametrize('kind', ['jpeg', 'gif'])
def test_cli_raw_files(tmp_path, kind):
    path = tmp_path / f'in.{kind}'
    if kind == 'gif':
        path.write_bytes(SIGNATURES['gif'][0])
        r = subprocess.run([sys.executable, '-S', str(ROOT / 'photo_grid.py'), str(path), '--size', '8'],
                           capture_output=True, text=True)
        assert r.returncode == 2 and 'GIF input is not supported' in r.stderr and 'Traceback' not in r.stderr
        return
    path.write_bytes(_pillow_bytes('JPEG'))
    r = subprocess.run([sys.executable, str(ROOT / 'photo_grid.py'), str(path), '--size', '8'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
