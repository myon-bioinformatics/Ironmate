"""Privacy: source metadata (EXIF/GPS, XMP, ICC, text chunks, timestamps) never reaches any output.

Every output may carry only the ironmate header (schema, size, palette, generation parameters) or nothing.
"""
import base64, io, json, re, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import grid_png
import grid_tools as g
import ironmate_image as im
import photo_grid

ROOT = Path(__file__).resolve().parents[1]
MARKERS = [b'SECRET_ARTIST', b'SECRET_GPS', b'SECRET_XMP', b'SECRET_ICC', b'SECRET_COMMENT', b'SECRET_AUTHOR',
           b'SECRET_ZTXT', b'SECRET_ITXT', b'SECRET_FORGED', b'2001:02:03', b'Exif', b'xmpmeta', b'adobe']
_ALLOWED_CHUNKS = {b'IHDR', b'tEXt', b'IDAT', b'IEND'}
_HEADER_KEYS = {'schema', 'width', 'height', 'colors', 'palette', 'mask', 'effect', 'resampling', 'source', 'fit',
                'quantize', 'restored'}


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)


def _png_with_metadata(forged_ironmate=False):
    w = h = 8
    raw = b''.join(b'\0' + bytes([(x * 30) % 256, (y * 30) % 256, 90, 255]) * 1 for y in range(h) for x in range(w)
                   for _ in [0] if x == 0) if False else b''.join(
        b'\0' + b''.join(bytes([x * 30, y * 30, 90, 255]) for x in range(w)) for y in range(h))
    exif = b'MM\0*\0\0\0\x08' + b'SECRET_GPS SECRET_ARTIST 2001:02:03'
    chunks = [_chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)),
              _chunk(b'tIME', struct.pack('>HBBBBB', 2001, 2, 3, 4, 5, 6)),
              _chunk(b'iCCP', b'icc\0\0' + zlib.compress(b'SECRET_ICC profile')),
              _chunk(b'tEXt', b'Author\0SECRET_AUTHOR'),
              _chunk(b'tEXt', b'Creation Time\x002001:02:03 04:05:06'),
              _chunk(b'zTXt', b'Comment\0\0' + zlib.compress(b'SECRET_ZTXT')),
              _chunk(b'iTXt', b'XML:com.adobe.xmp\0\0\0\0\0<x:xmpmeta>SECRET_XMP SECRET_ITXT</x:xmpmeta>'),
              _chunk(b'eXIf', exif)]
    if forged_ironmate:   # a hostile/foreign ironmate header with extra personal fields
        info = {'schema': 'ironmate-pixel-grid/1', 'width': 8, 'height': 8, 'author': 'SECRET_FORGED',
                'gps': 'SECRET_GPS', 'colors': sorted({'#%02X%02X5AFF' % (x * 30, y * 30)
                                                        for x in range(8) for y in range(8)})}
        chunks.append(_chunk(b'tEXt', b'ironmate\0' + json.dumps(info).encode()))
    return b'\x89PNG\r\n\x1a\n' + b''.join(chunks) + _chunk(b'IDAT', zlib.compress(raw)) + _chunk(b'IEND', b'')


def _pillow_with_metadata(fmt):
    Image = pytest.importorskip('PIL.Image')
    img = Image.new('RGB', (48, 40))
    img.putdata([(x * 5, y * 6, (x * y) % 256) for y in range(40) for x in range(48)])
    exif = Image.Exif()
    exif[0x013B] = 'SECRET_ARTIST'
    exif[0x0132] = '2001:02:03 04:05:06'
    gps = exif.get_ifd(0x8825)
    gps.update({1: 'N', 2: (35.0, 41.0, 7.0), 3: 'E', 4: (139.0, 41.0, 30.0), 27: b'ASCII\0\0\0SECRET_GPS'})
    xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/">SECRET_XMP</x:xmpmeta>'
    kw = dict(exif=exif.tobytes(), icc_profile=b'\0' * 128 + b'SECRET_ICC', xmp=xmp)
    if fmt == 'JPEG':
        kw['comment'] = b'SECRET_COMMENT'
    buf = io.BytesIO()
    img.save(buf, fmt, quality=90, **kw)
    data = buf.getvalue()
    assert b'SECRET_ARTIST' in data and b'SECRET_XMP' in data and b'SECRET_ICC' in data   # fixture really leaks
    return data


def _sources():
    out = [('png', _png_with_metadata()), ('png-forged-ironmate', _png_with_metadata(True))]
    try:
        out += [('jpeg', _pillow_with_metadata('JPEG')), ('webp', _pillow_with_metadata('WEBP'))]
    except pytest.skip.Exception:
        pass
    return out


def _png_chunks(data):
    pos, out = 8, []
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        out.append((kind, data[pos + 8:pos + 8 + n]))
        pos += 12 + n
    return out


def _check(out, label):
    """Assert ``out`` (bytes/str/dict) carries no source metadata."""
    if isinstance(out, dict):
        out = json.dumps(out)
    if isinstance(out, str):
        out = out.encode()
    text = out.strip()
    if text.startswith(b'data:'):
        text = text.split(b',', 1)[1]
    if re.fullmatch(rb'[A-Za-z0-9+/=\s]+', text) and len(text) > 40:
        out = base64.b64decode(text)
    for m in MARKERS:
        assert m.lower() not in out.lower(), (label, m)
    if out.startswith(b'\x89PNG'):
        for kind, body in _png_chunks(out):
            assert kind in _ALLOWED_CHUNKS, (label, kind)
            if kind == b'tEXt':
                key, _, value = body.partition(b'\0')
                assert key == b'ironmate', (label, key)
                assert set(json.loads(value)) <= _HEADER_KEYS, (label, set(json.loads(value)) - _HEADER_KEYS)
    elif out.lstrip().startswith(b'{'):
        assert set(json.loads(out)) <= _HEADER_KEYS | {'pixels'}, label


def _cli(mod, *args):
    r = subprocess.run([sys.executable, '-m', mod, *args], cwd=ROOT, capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout


SOURCES = _sources()


@pytest.mark.parametrize('name, data', SOURCES, ids=[n for n, _ in SOURCES])
def test_python_apis_drop_source_metadata(name, data):
    b64 = base64.b64encode(data).decode()
    for src in (data, b64, f'data:image/{name.split("-")[0]};base64,{b64}'):
        art = im.load(src)
        _check(art, 'load')
        for meta in (True, False):
            _check(im.to_png(src, meta=meta), 'to_png')
            _check(im.to_base64(src, data_uri=True, meta=meta), 'to_base64')
        _check(im.from_base64(b64), 'from_base64')
        _check(im.resize(src, 4), 'resize')
        for prefer in ('lossless', 'largest'):
            r = im.fit_to_limit(src, max_chars=10 ** 6, prefer=prefer)
            _check(r.data, 'fit'); _check(r.text, 'fit text')
        for fmt in g.FORMATS:
            _check(g.encode(art, fmt), f'encode {fmt}')
    photo = g.photo(data, 16)
    _check(photo, 'photo')
    for fmt in g.FORMATS:
        for meta in (True, False):
            _check(g.encode(photo, fmt, meta=meta), f'photo {fmt}')
    photo2 = photo_grid.convert(b64, 16)
    _check(photo2, 'photo_grid.convert')
    _check(grid_png.to_png(photo2, 1, True), 'grid_png meta')
    if name.startswith('png'):
        _check(g.restore(data), 'restore')


@pytest.mark.parametrize('name, data', SOURCES, ids=[n for n, _ in SOURCES])
def test_clis_drop_source_metadata(tmp_path, name, data):
    src = tmp_path / f'in.{name[:4]}'
    src.write_bytes(data)
    for fmt in g.FORMATS:
        _check(_cli('grid_tools', 'photo', str(src), '--size', '16', '--to', fmt), f'cli photo {fmt}')
        _check(_cli('photo_grid', str(src), '--format', fmt), f'photo_grid {fmt}')
        if name.startswith('png'):
            _check(_cli('grid_tools', 'load', str(src), '--size', '8', '--to', fmt), f'cli load {fmt}')
    _check(_cli('grid_tools', 'fit', str(src), '--limit-chars', '1000000'), 'cli fit')
    _check(_cli('grid_tools', 'fit', str(src), '--limit-bytes', '1000000', '--to', 'png'), 'cli fit png')
    _check(_cli('grid_tools', 'photo', str(src), '--size', '16', '--to', 'base64', '--data-uri'), 'data uri')


def test_ironmate_header_contains_only_size_and_palette_fields():
    art = g.make('cloud', 'C02', 'shadow', 16)
    info = json.loads(dict(_png_chunks(g.encode(art, 'png')))[b'tEXt'].split(b'\0', 1)[1])
    assert set(info) == {'schema', 'width', 'height', 'colors', 'palette', 'mask', 'effect', 'resampling'}
    assert not any(k == b'tEXt' for k, _ in _png_chunks(g.encode(art, 'png', meta=False)))
