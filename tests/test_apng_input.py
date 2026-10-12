"""APNG opens as its default (IDAT) image on both the stdlib and the Pillow path."""
import struct, zlib

import pytest

import grid_tools as g
import photo_grid

SIG = b'\x89PNG\r\n\x1a\n'


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _frame(rgba, w=2, h=2):
    return zlib.compress(b''.join(b'\0' + bytes(rgba) * w for _ in range(h)))


def _fctl(seq, w=2, h=2):
    return _chunk(b'fcTL', struct.pack('>IIIIIHHBB', seq, w, h, 0, 0, 1, 10, 0, 0))


def apng(default_in_animation):
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
    red, green, blue = (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128)
    out = SIG + head + _chunk(b'acTL', struct.pack('>II', 2, 0))
    seq = 0
    if default_in_animation:
        out += _fctl(seq); seq += 1
    out += _chunk(b'IDAT', _frame(red))
    frames = [green] if default_in_animation else [green, blue]
    for color in frames:
        out += _fctl(seq); seq += 1
        out += _chunk(b'fdAT', struct.pack('>I', seq) + _frame(color)); seq += 1
    return out + _chunk(b'IEND', b'')


@pytest.mark.parametrize('default_in_animation', [True, False])
def test_apng_default_image(default_in_animation):
    data = apng(default_in_animation)
    want = (2, 2, [bytes((255, 0, 0, 255)) * 2] * 2)
    assert photo_grid.decode_png(data) == want
    assert g.cells(g.restore(data, size=2)) == [['#FF0000FF'] * 2] * 2
    if g._backend('auto', 'PIL') == 'PIL':
        assert photo_grid.decode_pillow(data, formats=('PNG',)) == want
    assert photo_grid.convert(data, 8, 'contain', 2)['width'] == 8
