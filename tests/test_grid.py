"""🟩 Grids and images: pixel/photo grids, PNG/SVG/base64 round trips, properties and matrix, preview, formats, decode limits, pixel arcade, SVG raster, size estimates, privacy, review fixes and pillow_min."""

import base64
import io
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image as PILImage, ImageChops as PILImageChops

ROOT = Path(__file__).resolve().parents[1]
import grid_png
import grid_png as gp
import grid_preview
import grid_svg
import grid_svg as s
import grid_tools as g
import grid_tools as grid
import ironmate_image as im
import ironmate_image as image
import photo_grid
import photo_grid as g_photo_grid
import photo_grid as pg
import pillow_min as pm
import pixel_grid
import pixel_grid as p
import studio_ingress as ingress
from ironlib import size_estimate as s_size_estimate, svg_raster as sr
from ironlib.grid_output import write_output
from ironlib.pixel_arcade_engine import InvaderSparseScanner, PacmanGhostProbes, ReversiblePixelGrid
from ironlib.svg_raster import SvgError, rasterize


# ═══ · grid properties ═══════════════════════════════════════════════════════════════════════════════════
# Randomized property, mutation and adversarial-input tests for the grid_tools conditions table.
#
# Seeds are fixed (reproducible). The oracle is an independent per-pixel expansion of the artifact;
# stdlib, Pillow and numpy paths are each compared against it as (x, y, RGBA) cells, not only bytes.

HAS_NUMPY = g._backend('auto', 'numpy') == 'numpy'
HAS_PIL = g._backend('auto', 'PIL') == 'PIL'
CLEAR = '#00000000'
KINDS = ('noise', 'many', 'near', 'alpha', 'checker', 'odd', 'line', 'prime', 'clear', 'flat', 'blocks')
ITER = 40       # per kind in the default suite -> 440 grids per property
HEAVY_ITER = 400


# --- generators ---------------------------------------------------------------------------
def _hex(rgba):
    return '#%02X%02X%02X%02X' % tuple(rgba)


def gen(rnd, kind):
    """One adversarial artifact. Palette entries are unique unless noted."""
    w, h = rnd.randint(1, 24), rnd.randint(1, 24)
    colors = [CLEAR]
    if kind == 'many':                       # up to w*h distinct colors
        w, h = rnd.randint(8, 40), rnd.randint(8, 40)
        colors += list(dict.fromkeys(_hex([rnd.randrange(256) for _ in range(3)] + [rnd.randrange(1, 256)])
                                     for _ in range(w * h)))
    elif kind == 'near':                     # differ by 1 in one channel
        base = [rnd.randrange(1, 255) for _ in range(4)]
        for ch in range(4):
            for d in (-1, 1):
                c = list(base); c[ch] += d
                colors.append(_hex(c))
        colors.append(_hex(base))
    elif kind == 'alpha':                    # every alpha 1..255 (alpha 0 is index 0)
        rgb = [rnd.randrange(256) for _ in range(3)]
        colors += [_hex(rgb + [a]) for a in range(1, 256)]
        w, h = 16, 16
    else:
        colors += list(dict.fromkeys(_hex([rnd.randrange(256) for _ in range(3)] + [rnd.choice([255, rnd.randrange(1, 256)])])
                                     for _ in range(rnd.randint(1, 6))))
    n = len(colors)
    if kind == 'line':
        w, h = rnd.choice([(1, rnd.randint(1, 300)), (rnd.randint(1, 300), 1)])
    if kind == 'prime':
        w, h = rnd.choice([2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]), rnd.choice([3, 7, 13, 31, 61])
    if kind == 'alpha':
        pixels = [[1 + (y * 16 + x) % 255 if y * 16 + x < 255 else 0 for x in range(w)] for y in range(h)]
    elif kind == 'checker':
        a, b = rnd.sample(range(n), 2) if n > 1 else (0, 0)
        k = rnd.randint(1, 3)
        pixels = [[a if (x // k + y // k) % 2 else b for x in range(w)] for y in range(h)]
    elif kind in ('odd', 'flat'):
        c = rnd.randrange(n)
        pixels = [[c] * w for _ in range(h)]
        if kind == 'odd':
            pixels[rnd.randrange(h)][rnd.randrange(w)] = (c + 1) % n
    elif kind == 'clear':
        pixels = [[0] * w for _ in range(h)]
    elif kind == 'blocks':                   # coincidentally uniform k x k blocks (scale trap)
        k = rnd.randint(2, 4)
        sw, sh = rnd.randint(1, 6), rnd.randint(1, 6)
        small = [[rnd.randrange(n) for _ in range(sw)] for _ in range(sh)]
        pixels = [[v for v in row for _ in range(k)] for row in small for _ in range(k)]
        w, h = len(pixels[0]), len(pixels)
    else:
        pixels = [[rnd.randrange(n) for _ in range(w)] for _ in range(h)]
    return {'schema': 'ironmate-pixel-grid/1', 'width': w, 'height': h, 'colors': colors, 'pixels': pixels}


def cases(seed, iterations=ITER):
    rnd = random.Random(seed)
    for kind in KINDS:
        for i in range(iterations):
            yield kind, i, gen(rnd, kind)


# --- oracle and comparison ------------------------------------------------------------------
def oracle(art, scale=1):
    """{(x, y): (r, g, b, a)} expanded independently of grid_png/grid_tools."""
    out = {}
    for y, row in enumerate(art['pixels']):
        for x, v in enumerate(row):
            rgba = tuple(bytes.fromhex(art['colors'][v][1:]))
            for dy in range(scale):
                for dx in range(scale):
                    out[(x * scale + dx, y * scale + dy)] = rgba
    return out


def from_rows(width, height, rows):
    assert len(rows) == height and all(len(r) == width * 4 for r in rows)
    return {(x, y): tuple(rows[y][x * 4:x * 4 + 4]) for y in range(height) for x in range(width)}


def mismatches(a, b):
    """Per-pixel differences; also catches size differences."""
    return sorted((k, a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k))


def visible(cells_map):
    return {k: (v if v[3] else (0, 0, 0, 0)) for k, v in cells_map.items()}


# --- properties -----------------------------------------------------------------------------
def test_png_decoders_match_oracle_per_pixel():
    for kind, i, art in cases(1):
        scale = 1 + i % 3
        data = grid_png.to_png(art, scale, meta=i % 2 == 0)
        want = oracle(art, scale)
        assert not mismatches(from_rows(*photo_grid.decode_png(data)), want), (kind, i)
        if HAS_PIL:
            assert not mismatches(from_rows(*g._decode_png(data, 'PIL')), want), (kind, i)


def test_meta_restore_exact_and_base64_whitespace():
    for kind, i, art in cases(2):
        scale = 1 + i % 4
        b64 = g.encode(art, 'base64', scale, data_uri=i % 2 == 1)
        noisy = '\ufeff' + '\r\n '.join(b64[j:j + 61] for j in range(0, len(b64), 61)) + '\n\t'
        for src in (b64, noisy, g.encode(art, 'png', scale)):
            assert g.restore(src) == art, (kind, i)


def test_no_meta_with_size_hint_cells_exact():
    for kind, i, art in cases(3):
        scale = 1 + i % 4
        back = g.restore(g.encode(art, 'png', scale, meta=False), size=art['width'])
        assert not mismatches(oracle(back), oracle(art)), (kind, i)
        assert back['colors'] == g.canonical(art)['colors']


@pytest.mark.parametrize('backend', ['stdlib', 'numpy', 'PIL'])
def test_no_meta_auto_scale_explains_image(backend):
    """Auto scale = the largest exact one: restored grid re-expanded equals the image per pixel."""
    if backend == 'numpy' and not HAS_NUMPY or backend == 'PIL' and not HAS_PIL:
        pytest.skip(f'{backend} not installed')
    for kind, i, art in cases(4):
        scale = 1 + i % 3
        data = g.encode(art, 'png', scale, meta=False)
        back = g.restore(data, backend=backend)
        k = back['restored']['scale']
        assert k % scale == 0 and k * back['width'] == art['width'] * scale, (kind, i)
        assert not mismatches(oracle(back, k), oracle(art, scale)), (kind, i)
        if kind in ('noise', 'many', 'alpha', 'odd', 'prime') and art['width'] * art['height'] > 4:
            pass  # no claim: random grids may still coincide
        if kind in ('flat', 'clear'):
            assert (back['width'], back['height']) in {(1, art['height'] // (k // scale) if art['height'] else 1),
                                                       (1, 1)} or back['width'] * k == art['width'] * scale


def test_resize_up_then_back_exact_both_backends():
    rnd = random.Random(5)
    for kind, i, art in cases(5):
        w = art['width'] * rnd.randint(1, 4) + rnd.randint(0, 3)
        h = art['height'] * rnd.randint(1, 4) + rnd.randint(0, 3)
        w, h = min(w, 4096), min(h, 4096)
        for be in ('stdlib', 'numpy') if HAS_NUMPY else ('stdlib',):
            up = g.resize(art, w, h, backend=be)
            assert g.resize(up, art['width'], art['height'], backend=be) == art, (kind, i, be)


def test_recolor_round_trip():
    ids = [f'C{n:02d}' for n in range(1, 11)]
    for kind, i, art in cases(6):
        small = dict(art, colors=art['colors'][:5], pixels=[[v % min(5, len(art['colors'])) for v in r]
                                                             for r in art['pixels']])
        a, b = ids[i % 10], ids[(i * 3 + 1) % 10]
        start = g.recolor(small, a)
        assert g.recolor(g.recolor(start, b), a) == start, (kind, i)


def test_svg_load_visible_cells():
    for kind, i, art in cases(7, ITER // 4):
        back = g.restore(g.encode(art, 'svg'))
        assert not mismatches(oracle(back), visible(oracle(art))), (kind, i)
        if HAS_NUMPY:
            assert g.restore(g.encode(art, 'svg'), backend='numpy') == back


@pytest.mark.heavy
def test_heavy_properties():
    for kind, i, art in cases(100, HEAVY_ITER):
        scale = 1 + i % 5
        assert g.restore(g.encode(art, 'base64', scale)) == art
        back = g.restore(g.encode(art, 'png', scale, meta=False))
        assert not mismatches(oracle(back, back['restored']['scale']), oracle(art, scale))
    big = gen(random.Random(9), 'many')
    big = g.resize(big, 1024, 1024)
    assert g.restore(g.encode(big)) == big
    assert g.restore(g.encode(g.resize(big, 64, 64), 'png', 64)) == g.resize(big, 64, 64)  # 4096x4096 limit


# --- mutation / sensitivity -----------------------------------------------------------------
def _mutations(art, rnd):
    px = art['pixels']
    w, h = art['width'], art['height']
    cols = art['colors']
    out = {}
    pos = [(x, y) for y in range(h) for x in range(w)]
    pairs = [(p, q) for p in pos[:30] for q in pos[-30:] if cols[px[p[1]][p[0]]] != cols[px[q[1]][q[0]]]]
    if pairs:
        (x1, y1), (x2, y2) = pairs[0]
        m = [r[:] for r in px]
        m[y1][x1], m[y2][x2] = m[y2][x2], m[y1][x1]
        out['swap'] = dict(art, pixels=m)
    x, y = rnd.choice(pos)
    c = bytearray(bytes.fromhex(cols[px[y][x]][1:]))
    ch = rnd.randrange(4)
    c[ch] = c[ch] + 1 if c[ch] < 255 else 254
    m = [r[:] for r in px]
    m[y][x] = len(cols)
    out['channel+1'] = dict(art, colors=cols + [_hex(c)], pixels=m)
    rows = [j for j, r in enumerate(px) if len({cols[v] for v in r}) > 1]
    if rows:
        m = [r[:] for r in px]
        m[rows[0]] = m[rows[0]][1:] + m[rows[0]][:1]
        out['shift-row'] = dict(art, pixels=m)
    t = [list(r) for r in zip(*px)]
    if w != h or any(px[a][b] != px[b][a] for a in range(h) for b in range(w)):
        out['transpose'] = dict(art, width=h, height=w, pixels=t)
    out['flip'] = dict(art, pixels=px[::-1])
    out['palette-order'] = dict(art, colors=cols[1:] + cols[:1])
    return out


def test_mutations_are_detected():
    rnd = random.Random(8)
    detected, total, noops = {}, {}, {}
    for kind, i, art in cases(8, 10):
        want = oracle(art)
        for name, mut in _mutations(art, rnd).items():
            changed = bool(mismatches(oracle(mut), want))
            if not changed:          # e.g. flipping a symmetric picture is a true no-op
                noops[name] = noops.get(name, 0) + 1
                continue
            total[name] = total.get(name, 0) + 1
            back = g.restore(g.encode(mut))
            if mismatches(oracle(back), want) and back != art:
                detected[name] = detected.get(name, 0) + 1
    assert set(total) == {'swap', 'channel+1', 'shift-row', 'transpose', 'flip', 'palette-order'}
    assert detected == total, (detected, total)
    print('\nmutations detected:', total, 'visual no-ops skipped:', noops)


def _set_meta(data, meta):
    body = b'ironmate\x00' + json.dumps(meta).encode()
    start = data.index(b'tEXtironmate') - 4
    end = start + 12 + struct.unpack('>I', data[start:start + 4])[0]
    return data[:start] + struct.pack('>I', len(body)) + b'tEXt' + body + \
        struct.pack('>I', zlib.crc32(b'tEXt' + body)) + data[end:]


@pytest.mark.parametrize('change, match', [
    (lambda m: m.update(width=m['width'] + 1), 'does not match'),
    (lambda m: m.update(height=m['height'] * 2), 'does not match'),
    (lambda m: m.update(width='8'), 'width'),
    (lambda m: m.update(width=0), 'width'),
    (lambda m: m.update(colors=m['colors'][:1]), 'not in the ironmate metadata'),
    (lambda m: m.update(colors=[c[:-2] + '7F' for c in m['colors']]), 'not in the ironmate metadata'),
    (lambda m: m.update(colors='#00000000'), 'colors'),
    (lambda m: m.pop('colors'), 'colors'),
    (lambda m: m.update(schema='other/1'), 'header'),
])
def test_tampered_meta_with_valid_crc_errors(change, match):
    art = gen(random.Random(11), 'noise')
    art = dict(art, width=8, height=6, pixels=[[(x + y) % len(art['colors']) for x in range(8)] for y in range(6)])
    meta = json.loads(json.dumps({k: v for k, v in art.items() if k != 'pixels'}))
    change(meta)
    with pytest.raises(ValueError, match=match):
        g.restore(_set_meta(g.encode(art, 'png', 2), meta))


def test_tampered_meta_palette_permutation_keeps_cells():
    """A consistent permutation with a valid CRC is a different but equivalent artifact (never wrong cells)."""
    art = gen(random.Random(12), 'noise')
    meta = {k: v for k, v in art.items() if k != 'pixels'}
    meta['colors'] = meta['colors'][:1] + meta['colors'][1:][::-1]
    back = g.restore(_set_meta(g.encode(art, 'png'), meta))
    assert not mismatches(oracle(back), oracle(art))


def test_corrupt_meta_byte_is_bad_crc():
    data = bytearray(g.encode(gen(random.Random(13), 'noise'), 'png'))
    data[data.index(b'tEXtironmate') + 15] ^= 0x20
    with pytest.raises(ValueError, match='CRC'):
        g.restore(bytes(data))


# --- adversarial PNGs -----------------------------------------------------------------------
def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def craft_png(width, height, rows, filters, idat_parts=1, extra=(), trailing=b''):
    raw, prev = bytearray(), bytes(width * 4)
    for y, row in enumerate(rows):
        f = filters[y % len(filters)]
        line = bytearray()
        for i, v in enumerate(row):
            a = row[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            pred = (0, a, b, (a + b) // 2, _paeth(a, b, c))[f]
            line.append((v - pred) & 255)
        raw += bytes([f]) + line
        prev = row
    z = zlib.compress(bytes(raw))
    size = -(-len(z) // idat_parts)
    idats = b''.join(_chunk(b'IDAT', z[j:j + size]) for j in range(0, len(z), size))
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    return b'\x89PNG\r\n\x1a\n' + head + b''.join(extra) + idats + _chunk(b'IEND', b'') + trailing


def _rand_rows(rnd, w, h):
    return [bytes(rnd.randrange(256) for _ in range(w * 4)) for _ in range(h)]


@pytest.mark.parametrize('filters', [[0], [1], [2], [3], [4], [0, 1, 2, 3, 4]])
def test_crafted_png_filters_split_idat_extra_chunks(filters):
    rnd = random.Random(sum(filters) + len(filters))
    for _ in range(20):
        w, h = rnd.randint(1, 17), rnd.randint(1, 9)
        rows = _rand_rows(rnd, w, h)
        data = craft_png(w, h, rows, filters, rnd.randint(1, 5),
                         [_chunk(b'tEXt', b'Comment\x00x'), _chunk(b'gAMA', b'\0\0\xb1\x8f')])
        want = from_rows(w, h, rows)
        assert not mismatches(from_rows(*photo_grid.decode_png(data)), want)
        if HAS_PIL:
            assert not mismatches(from_rows(*g._decode_png(data, 'PIL')), want)
        back = g.restore(data, size=w)
        assert not mismatches(oracle(back), want)


def test_crafted_png_errors():
    rnd = random.Random(21)
    rows = _rand_rows(rnd, 4, 3)
    good = craft_png(4, 3, rows, [4])
    bad_crc = bytearray(good)
    bad_crc[good.index(b'IDAT') + 6] ^= 1
    with pytest.raises(ValueError, match='CRC'):
        photo_grid.decode_png(bytes(bad_crc))
    with pytest.raises(ValueError, match='trailing'):
        photo_grid.decode_png(good + b'junk')
    with pytest.raises(ValueError):
        photo_grid.decode_png(craft_png(4, 3, rows, [4])[:-20])
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 3, 8, 6, 0, 0, 0))
    raw = b''.join(b'\0' + r for r in rows)
    for idat, match in ((zlib.compress(raw) + b'xx', 'extra bytes'), (zlib.compress(raw + b'\0' * 40), 'length')):
        with pytest.raises(ValueError, match=match):
            photo_grid.decode_png(b'\x89PNG\r\n\x1a\n' + head + _chunk(b'IDAT', idat) + _chunk(b'IEND', b''))
    raw_bad_filter = good.replace(good[33:good.index(b'IEND') - 4], b'')  # drop IDAT -> missing data
    with pytest.raises(ValueError):
        photo_grid.decode_png(raw_bad_filter)
    z = zlib.compress(bytes([5]) + bytes(16) + (bytes([0]) + bytes(16)) * 2)
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 3, 8, 6, 0, 0, 0))
    with pytest.raises(ValueError, match='filter'):
        photo_grid.decode_png(b'\x89PNG\r\n\x1a\n' + head + _chunk(b'IDAT', z) + _chunk(b'IEND', b''))


def test_meta_after_idat_is_ignored_not_trusted():
    art = gen(random.Random(30), 'noise')
    plain = g.encode(art, 'png', meta=False)
    meta = g.encode(art, 'png', meta=True)
    text = meta[meta.index(b'tEXtironmate') - 4:meta.index(b'IDAT') - 4]
    late = plain[:-12] + text + plain[-12:]
    back = g.restore(late, size=art['width'])
    assert 'restored' in back and not mismatches(oracle(back), oracle(art))


def test_scale_trap_uniform_blocks():
    """Pictures built from uniform k x k blocks are indistinguishable from k-times upscales without hints."""
    rnd = random.Random(31)
    for _ in range(50):
        art = gen(rnd, 'blocks')
        data = g.encode(art, 'png', 2, meta=False)
        auto = g.restore(data)
        assert auto['restored']['scale'] >= 2 * 2 and auto['width'] < art['width']
        assert not mismatches(oracle(auto, auto['restored']['scale']), oracle(art, 2))
        assert not mismatches(oracle(g.restore(data, size=art['width'])), oracle(art))
        assert g.restore(g.encode(art, 'png', 2)) == art   # the header removes the ambiguity


# ═══ · grid matrix ═══════════════════════════════════════════════════════════════════════════════════════
# Pixel grids as per-channel matrices (numpy), after the SVD / sign+scale ideas in Aoi.
#
# Idea credit: myon-bioinformatics/Aoi ``pythdragoras/littlebit_prune.py`` (SVD residual stages,
# sign(U) / sign(V) with scales) and ``queryu/ask/suggest.py`` (SVD + binary sign index). Re-implemented
# here in a few lines; nothing is imported from Aoi.
#
# Findings encoded below: the exact residual R = restored - original (all four channels) is the
# primary check and must be zero on lossless paths. Singular values alone are blind to row/column
# permutations and transposition, so they are only a secondary fingerprint; adding the sign pattern of
# the leading singular vectors (Aoi's sign index) recovers most of those cases but not all.

np = pytest.importorskip('numpy')


def channels(art):
    """(4, H, W) float matrix stack: R, G, B, A."""
    pal = np.array([list(bytes.fromhex(c[1:])) for c in art['colors']], dtype=np.float64)
    return pal[np.array(art['pixels'])].transpose(2, 0, 1)


def residual(a, b):
    ca, cb = channels(a), channels(b)
    if ca.shape != cb.shape:
        return None
    return cb - ca


def singular_values(art):
    return [np.linalg.svd(m, compute_uv=False) for m in channels(art)]


def sign_scale(art, rank=2):
    """Aoi-style fingerprint: per channel, singular values + sign(U[:, :r]) and sign(V[:, :r])."""
    out = []
    for m in channels(art):
        u, s, vt = np.linalg.svd(m - m.mean(), full_matrices=False)
        r = min(rank, len(s))
        su, sv = np.sign(u[:, :r]), np.sign(vt[:r].T)
        flip = np.where(np.sign(su[0]) == 0, 1, np.sign(su[0]))  # fix SVD's sign ambiguity
        out.append((np.round(s, 6), (su * flip).astype(int), (sv * flip).astype(int)))
    return out


def same_fingerprint(fa, fb):
    return all(a[0].shape == b[0].shape and np.allclose(a[0], b[0]) and np.array_equal(a[1], b[1])
               and np.array_equal(a[2], b[2]) for a, b in zip(fa, fb))


def test_residual_is_exactly_zero_on_lossless_paths():
    count = 0
    for kind, i, art in cases(40, 15):
        scale = 1 + i % 3
        paths = {
            'meta': g.restore(g.encode(art, 'base64', scale)),
            'size-hint': g.restore(g.encode(art, 'png', scale, meta=False), size=art['width']),
            'resize-back': g.resize(g.resize(art, art['width'] * 3 + 1, art['height'] * 2 + 1),
                                    art['width'], art['height']),
        }
        for name, back in paths.items():
            r = residual(art, back)
            assert r is not None and not np.any(r), (kind, i, name)
            count += 1
    assert count == len(KINDS) * 15 * 3


def test_fingerprints_vs_exact_residual_on_mutations(capsys):
    rnd = random.Random(41)
    stats = {}
    for kind, i, art in cases(42, 10):
        for name, mut in _mutations(art, rnd).items():
            r = residual(art, mut)
            if r is not None and not np.any(r):
                continue                     # visual no-op (e.g. symmetric flip)
            s = stats.setdefault(name, [0, 0, 0, 0])
            s[0] += 1
            s[1] += 1                        # exact residual / per-pixel check: always detects
            sva, svb = singular_values(art), singular_values(mut)
            s[2] += not all(a.shape == b.shape and np.allclose(a, b) for a, b in zip(sva, svb))
            s[3] += not same_fingerprint(sign_scale(art), sign_scale(mut))
    for name, (n, exact, sv, signs) in stats.items():
        assert exact == n
    # Singular values are invariant under row permutation / transpose: provably blind.
    assert stats['flip'][2] == 0 and stats['transpose'][2] == 0
    assert stats['flip'][3] > 0.8 * stats['flip'][0]
    with capsys.disabled():
        print('\nmutation: n / exact / singular-values / sign+scale')
        for name, row in sorted(stats.items()):
            print(f'  {name:14s}', *row)


def test_lossy_paths_report_error_norms(capsys):
    lines = []
    rnd = random.Random(43)
    for kind in ('noise', 'checker', 'blocks', 'flat'):
        art = gen(rnd, kind)
        w, h = art['width'], art['height']
        if w < 2 or h < 2:
            continue
        back = g.resize(g.resize(art, max(1, w // 2), max(1, h // 2)), w, h)
        r = residual(art, back)
        rms = float(np.sqrt((r ** 2).mean()))
        changed = float((np.abs(r).sum(0) > 0).mean())
        assert rms <= 255 and float(np.abs(r).max()) <= 255
        if kind == 'flat':
            assert rms == 0                   # uniform blocks: the lossless exception
        lines.append(f'  down2-up {kind:8s} rms={rms:6.2f} changed={changed:.0%}')
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image:
        img = Image.new('RGB', (64, 64))
        img.putdata([(x * 4, y * 4, (x + y) * 2) for y in range(64) for x in range(64)])
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=90)
        art = g.photo(buf.getvalue(), 32, colors=16)
        ref = np.asarray(img.resize((32, 32), Image.BOX), dtype=np.float64).transpose(2, 0, 1)
        rms = float(np.sqrt(((channels(art)[:3] - ref) ** 2).mean()))
        assert rms < 30                       # lossy but bounded: JPEG + 16-color median cut
        lines.append(f'  jpeg->32x32x16 rms vs box-downscale={rms:.2f}')
        assert g.restore(g.encode(art)) == art    # lossless from the grid onward
    with capsys.disabled():
        print('\n' + '\n'.join(lines))


def test_low_rank_is_not_a_storage_format():
    """A rank-k sign+scale approximation (LittleBit-style) is lossy for dot art; documented, not used."""
    art = gen(random.Random(44), 'noise')
    m = channels(art)[0]
    u, s, vt = np.linalg.svd(m, full_matrices=False)
    k = max(1, len(s) // 4)
    approx = (np.sign(u[:, :k]) * np.abs(u[:, :k]).mean(0) * s[:k]) @ (np.sign(vt[:k]) * np.abs(vt[:k]).mean(1)[:, None])
    assert np.abs(np.rint(approx) - m).max() > 0


# ═══ · apng input ════════════════════════════════════════════════════════════════════════════════════════
# APNG opens as its default (IDAT) image on both the stdlib and the Pillow path.

SIG = b'\x89PNG\r\n\x1a\n'


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


# ═══ · base64 bridge cases ═══════════════════════════════════════════════════════════════════════════════
# Clipboard/Base64 import cases mirroring bugs found in flutter_navigation_basic's Base64ImageBridge.
#
# The literal cases live in tests/fixtures/base64_bridge_cases.json so another implementation (e.g.
# the Flutter app's Dart tests) can load the same inputs and expectations.

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


# ═══ · decode limit ══════════════════════════════════════════════════════════════════════════════════════
# Decode-size limit: same boundary semantics as flutter_navigation_basic Base64ImageBridge (#178).

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


# ═══ · grid base64 ═══════════════════════════════════════════════════════════════════════════════════════

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
    art = pixel_grid.render('cloud', 'C03', 'shadow', 32)
    for scale in (1, 4):
        text = gp.to_base64(art, scale)
        assert text == gp.to_base64(art, scale)
        assert base64.b64decode(text, validate=True) == gp.to_png(art, scale)
        assert photo_grid.decode_base64(gp.to_base64(art, scale, True)) == gp.to_png(art, scale)


def test_scaled_round_trip_needs_matching_target():
    art = pixel_grid.render('diamond', 'C02', 'normal', 16)
    text = gp.to_base64(art, scale=2)  # 32x32 image
    assert _key(photo_grid.convert(text, size=16, palette='C02')) == _key(art)  # target = original size
    assert photo_grid.convert(text, size=32, palette='C02')['width'] == 32  # different grid


def test_cli_end_to_end(tmp_path):
    out = tmp_path / 'g.b64'
    r = subprocess.run(PIXEL + ['--mask', 'rock', '--palette', 'C06', '--size', '8', '--format', 'base64',
                                '--data-uri', '-o', str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == '', r.stderr
    art = pixel_grid.render('rock', 'C06', 'normal', 8)
    assert out.read_text(encoding='ascii') == gp.to_base64(art, data_uri=True) + '\n'
    j = subprocess.run(PHOTO + [str(out), '--size', '8', '--palette', 'C06'], capture_output=True, text=True)
    assert _key(json.loads(j.stdout)) == _key(art)
    again = subprocess.run(PHOTO + [str(out), '--size', '8', '--palette', 'C06', '--format', 'base64'],
                           capture_output=True, text=True)
    assert again.stdout == gp.to_base64(art) + '\n'
    piped = subprocess.run(PHOTO + ['-', '--size', '8', '--palette', 'C06'], input=again.stdout,
                           capture_output=True, text=True)
    assert _key(json.loads(piped.stdout)) == _key(art)
    scaled = subprocess.run(PIXEL + ['--mask', 'circle', '--size', '8', '--format', 'base64', '--scale', '3'], capture_output=True, text=True)
    assert photo_grid.decode_png(base64.b64decode(scaled.stdout))[:2] == (24, 24)


# ═══ · grid png ══════════════════════════════════════════════════════════════════════════════════════════

def _cells(art, scale=1):
    rgba = [bytes.fromhex(c[1:]) for c in art['colors']]
    return [b''.join(rgba[v] * scale for v in row) for row in art['pixels'] for _ in range(scale)]


@pytest.mark.parametrize('scale', [1, 3])
def test_round_trip_through_stdlib_decoder(scale):
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'C02', 'shadow', 16)
        data = gp.to_png(art, scale)
        assert data == gp.to_png(art, scale)
        w, h, rows = photo_grid.decode_png(data)
        assert (w, h) == (16 * scale, 16 * scale)
        assert rows == _cells(art, scale)
        assert rows[0][3] == 0  # index 0 stays transparent


def test_png_grid_png_round_trip_is_identical():
    art = pixel_grid.render('circle', 'C03', 'outline', 32)
    back = photo_grid.convert(base64.b64encode(gp.to_png(art)).decode(), size=32, colors=16)
    assert _cells(back) == _cells(art)
    raw = photo_grid.convert(gp.to_png(art), size=32, colors=16)  # plain PNG bytes, no Base64
    assert raw == back


@pytest.mark.parametrize('art,kw', [
    (pixel_grid.render('circle', size=8), {'scale': 0}), (pixel_grid.render('circle', size=8), {'scale': 65}),
    (pixel_grid.render('circle', size=8) | {'width': 9}, {}), (pixel_grid.render('circle', size=8) | {'colors': ['#000']}, {}),
    (pixel_grid.render(size=128), {'scale': 64})])
def test_invalid(art, kw):
    with pytest.raises(ValueError):
        gp.to_png(art, **kw)


def test_plain_png_file_and_oversize():
    data = gp.to_png(pixel_grid.render('circle', size=8))
    with pytest.raises(ValueError, match='exceeds'):
        photo_grid.convert(data, size=8, max_bytes=len(data) - 1)


def test_cli_png_outputs(tmp_path):
    art = pixel_grid.render('rock', 'C05', 'normal', 8)
    png = tmp_path / 'in.png'
    png.write_bytes(gp.to_png(art))
    b64 = tmp_path / 'in.b64'
    b64.write_text('data:image/png;base64,' + base64.b64encode(png.read_bytes()).decode(), encoding='ascii')
    photo = [sys.executable, '-S', str(ROOT / 'photo_grid.py')]
    outs = []
    for src in (png, b64):
        out = tmp_path / f'{src.suffix[1:]}-out.png'
        r = subprocess.run(photo + [str(src), '--size', '8', '--format', 'png', '--scale', '2', '-o', str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == '', r.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    assert photo_grid.decode_png(outs[0])[:2] == (16, 16)
    j = subprocess.run(photo + [str(png), '--size', '8'], capture_output=True, text=True)
    assert _cells(json.loads(j.stdout)) == _cells(art)
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'pixel_grid.py'), '--mask', 'rock', '--palette', 'C05',
                        '--size', '8', '--format', 'png'], capture_output=True)
    assert r.returncode == 0 and r.stdout == gp.to_png(art)
    jf = tmp_path / 'a.json'
    jf.write_text(json.dumps(art), encoding='utf-8')
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'grid_png.py'), str(jf)], capture_output=True)
    assert r.returncode == 0 and r.stdout == gp.to_png(art)


def test_inert_import(tmp_path):
    probe = 'import sys;sys.path.insert(0,sys.argv[1]);import grid_png'
    r = subprocess.run([sys.executable, '-S', '-c', probe, str(ROOT)], cwd=tmp_path, capture_output=True)
    assert r.returncode == 0 and r.stdout == r.stderr == b'' and list(tmp_path.iterdir()) == []


# ═══ · grid preview ══════════════════════════════════════════════════════════════════════════════════════
# The committed README preview must be exactly what grid_preview.py generates (no drift).

SHEET = ROOT / 'docs' / 'pixel-grid-preview.png'


def test_committed_preview_matches_generator():
    data = grid_preview.png()
    assert data == grid_preview.png()
    assert SHEET.read_bytes() == data, 'regenerate: python -S grid_preview.py -o docs/pixel-grid-preview.png --force'


def test_preview_is_small_and_decodes():
    w, h, rows = photo_grid.decode_png(SHEET.read_bytes())
    assert (w, h) == (grid_preview.build()['width'] * 3, grid_preview.build()['height'] * 3)
    assert SHEET.stat().st_size < 64 * 1024


def test_cli_refuses_overwrite(tmp_path):
    out = tmp_path / 'p.png'
    run = lambda *a: subprocess.run([sys.executable, '-S', 'grid_preview.py', '-o', str(out), *a],
                                    cwd=ROOT, capture_output=True)
    assert run().returncode == 0 and out.read_bytes() == SHEET.read_bytes()
    assert run().returncode == 2
    assert run('--force').returncode == 0


# ═══ · grid roundtrip ════════════════════════════════════════════════════════════════════════════════════
# Property-style verification of PNG/Base64 output and the photo_grid round trip (fixed seeds).

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
    limit = 1000  # small stand-in for MAX_BYTES (boundary semantics are size-independent)
    exact = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\0' * (limit - 8)).decode()
    with pytest.raises(pg.ImageDecodeError):  # accepted by size, then rejected as a PNG
        pg.convert(exact, max_bytes=limit)
    over = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\0' * (limit - 7)).decode()
    with pytest.raises(ValueError, match='exceeds'):
        pg.convert(over, max_bytes=limit)
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


# ═══ · grid svg ══════════════════════════════════════════════════════════════════════════════════════════

NS = '{http://www.w3.org/2000/svg}'


def _art(pixels, colors=('#00000000', '#FF0000FF', '#0000FF80')):
    return {'schema': 'ironmate-pixel-grid/1', 'width': len(pixels[0]), 'height': len(pixels),
            'colors': list(colors), 'pixels': pixels}


def _cover(svg):
    root = ET.fromstring(svg)
    cells = {}
    for r in root.iter(NS + 'rect'):
        x, y, w = int(r.get('x')), int(r.get('y')), int(r.get('width'))
        assert r.get('height') == '1'
        for i in range(w):
            assert (y, x + i) not in cells
            cells[(y, x + i)] = (r.get('fill'), r.get('fill-opacity'))
    return root, cells


def _expected(art):
    out = {}
    for y, row in enumerate(art['pixels']):
        for x, v in enumerate(row):
            c = art['colors'][v]
            if int(c[7:], 16):
                a = int(c[7:], 16)
                out[(y, x)] = ('#' + c[1:7].lower(), None if a == 255 else f'{a / 255:.4g}')
    return out


def test_cells_colors_transparency_and_runs():
    art = _art([[0, 1, 1, 2], [2, 2, 0, 1]])
    svg = s.to_svg(art, scale=4)
    root, cells = _cover(svg)
    assert root.get('viewBox') == '0 0 4 2' and root.get('width') == '16' and root.get('height') == '8'
    assert root.get('shape-rendering') == 'crispEdges'
    assert cells == _expected(art)
    assert len(list(root.iter(NS + 'rect'))) == 4
    assert cells[(0, 3)] == ('#0000ff', '0.502')
    assert (0, 0) not in cells and (1, 2) not in cells


@pytest.mark.parametrize('merge', [True, False])
def test_opaque_zero_and_nonzero_transparency_follow_alpha(merge):
    art = _art([[0, 0, 1, 2], [3, 2, 0, 1]],
               ('#FF0000FF', '#12345600', '#0000FF80', '#00000000'))
    assert _cover(s.to_svg(art, merge=merge))[1] == _expected(art)


def test_merge_equivalence_on_real_grids():
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'C03', 'outline', 32)
        merged, single = s.to_svg(art), s.to_svg(art, merge=False)
        assert _cover(merged)[1] == _cover(single)[1] == _expected(art)
        assert len(merged) < len(single)
        assert merged == s.to_svg(art)


def test_metadata_is_escaped():
    art = _art([[1]]) | {'palette': '<&"x">'}
    root = ET.fromstring(s.to_svg(art))
    assert '<&"x">' in root.find(NS + 'title').text


@pytest.mark.parametrize('art,kw', [
    (_art([[3]]), {}), (_art([[1, 1]]) | {'width': 3}, {}),
    (_art([[1]], ('#000000', '#FF0000FF')), {}), (_art([[1]]), {'scale': 0}), (_art([[1]]), {'scale': 65})])
def test_invalid_grid_svg(art, kw):
    with pytest.raises(ValueError):
        s.to_svg(art, **kw)


def _png_b64():
    raw = b''.join(b'\x00' + b''.join(bytes((255 * (x < 2), 0, 255 * (x >= 2), 255 * (y < 3))) for x in range(4))
                   for y in range(4))

    def chunk(k, b):
        return struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return base64.b64encode(data).decode()


def test_cli_end_to_end_from_base64_png(tmp_path):
    src = tmp_path / 'in.b64'
    src.write_text(_png_b64(), encoding='ascii')
    out = tmp_path / 'out.svg'
    cmd = [sys.executable, '-S', str(ROOT / 'photo_grid.py'), str(src), '--size', '8', '--colors', '2']
    r = subprocess.run(cmd + ['--format', 'svg', '--scale', '3', '-o', str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == '', r.stderr
    j = subprocess.run(cmd, capture_output=True, text=True)
    art = json.loads(j.stdout)
    root, cells = _cover(out.read_text(encoding='utf-8'))
    assert root.get('width') == '24' and cells == _expected(art)
    assert any(v == 0 for row in art['pixels'] for v in row)
    assert out.read_text(encoding='utf-8') == s.to_svg(art, 3)
    jf = tmp_path / 'a.json'
    jf.write_text(j.stdout, encoding='utf-8')
    r2 = subprocess.run([sys.executable, '-S', str(ROOT / 'grid_svg.py'), str(jf), '--scale', '3'],
                        capture_output=True, text=True)
    assert r2.returncode == 0 and r2.stdout == s.to_svg(art, 3)


def test_pixel_grid_cli_svg_and_inert_imports(tmp_path):
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'pixel_grid.py'), '--mask', 'circle', '--size', '8', '--format', 'svg'],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == s.to_svg(pixel_grid.render('circle', size=8))
    probe = ('import sys;sys.path.insert(0,sys.argv[1]);import pixel_grid, grid_svg;'
             'import photo_grid;assert "PIL" not in sys.modules')
    r = subprocess.run([sys.executable, '-S', '-c', probe, str(ROOT)], cwd=tmp_path, capture_output=True)
    assert r.returncode == 0 and r.stdout == r.stderr == b''
    assert list(tmp_path.iterdir()) == []


# ═══ · grid tools ════════════════════════════════════════════════════════════════════════════════════════
# Reversibility contract of grid_tools: where round trips are exact and where they are not.

needs_numpy = pytest.mark.skipif(not HAS_NUMPY, reason='numpy not installed')
needs_pil = pytest.mark.skipif(not HAS_PIL, reason='Pillow not installed')


def _random_art_grid_tools(w, h, ncolors, seed, alpha=True):
    rnd = random.Random(seed)
    colors = ['#00000000'] + ['#%02X%02X%02X%02X' % (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256),
                                                     rnd.randrange(1, 256) if alpha else 255)
                              for _ in range(ncolors)]
    colors = list(dict.fromkeys(colors))
    return {'schema': 'ironmate-pixel-grid/1', 'width': w, 'height': h, 'colors': colors,
            'pixels': [[rnd.randrange(len(colors)) for _ in range(w)] for _ in range(h)]}


ALL_ART = [pixel_grid.render(m, pid, e, s) for m in pixel_grid.MASKS for pid in ('C01', 'C07')
           for e in pixel_grid.EFFECTS for s in (16, 33)]


# --- PNG / Base64 with metadata: exact JSON -------------------------------------------------
@pytest.mark.parametrize('scale', [1, 2, 5])
def test_png_base64_with_meta_is_exact(scale):
    for art in ALL_ART:
        assert g.restore(g.encode(art, 'png', scale)) == art
        assert g.restore(g.encode(art, 'base64', scale)) == art
        assert g.restore(g.encode(art, 'base64', scale, data_uri=True)) == art


@pytest.mark.parametrize('ncolors', [1, 16, 300])
def test_semi_transparent_many_colors_exact(ncolors):
    art = _random_art_grid_tools(23, 17, ncolors, ncolors)
    assert len(art['colors']) > ncolors * 0.9
    assert g.restore(g.encode(art, scale=3)) == art
    plain = g.restore(g.encode(art, scale=3, meta=False), size=23)
    assert g.cells(plain) == g.cells(art)          # alpha 1..255 survives PNG exactly


def test_meta_default_png_bytes_unchanged():
    art = ALL_ART[0]
    assert grid_png.to_png(art) == grid_png.to_png(art, meta=False)
    assert b'ironmate\x00' in grid_png.to_png(art, meta=True)


def test_duplicate_palette_rgba_is_the_one_meta_exception():
    art = dict(ALL_ART[0], colors=ALL_ART[0]['colors'] + [ALL_ART[0]['colors'][1]])
    art['pixels'] = [[len(art['colors']) - 1 if v == 1 else v for v in row] for row in art['pixels']]
    back = g.restore(g.encode(art))
    assert back != art and g.cells(back) == g.cells(art)   # first matching index wins


def test_tampered_meta_and_pixels_fail_clearly():
    art = ALL_ART[0]
    data = bytearray(g.encode(art, 'png'))
    i = data.index(b'ironmate\x00') + 12
    data[i] ^= 1
    with pytest.raises(ValueError, match='bad CRC'):
        g.restore(bytes(data))
    other = dict(art, colors=['#00000000', '#123456FF', '#123457FF', '#123458FF', '#123459FF'])
    foreign = grid_png.to_png(art)  # no meta; splice meta of a different palette
    meta = grid_png.to_png(other, meta=True)
    spliced = meta[:meta.index(b'IDAT') - 4] + foreign[foreign.index(b'IDAT') - 4:]
    with pytest.raises(ValueError, match='not in the ironmate metadata'):
        g.restore(spliced)


# --- PNG without metadata: scale detection ---------------------------------------------------
def test_scale_auto_detect_64_to_32():
    art = pixel_grid.render('circle', 'C03', 'outline', 32)
    back = g.restore(grid_png.to_png(art, 2))
    assert back['width'] == 32 and back['restored']['scale'] == 2
    assert g.cells(back) == g.cells(art)
    assert back['colors'] == g.canonical(art)['colors']


def test_gcd_detection_limit_is_documented():
    """Without a hint the scale is the largest exact one: a 2x2-checker 8x8 grid looks like 4x4 at 2x."""
    art = {'schema': 'ironmate-pixel-grid/1', 'width': 8, 'height': 8, 'colors': ['#00000000', '#FF0000FF'],
           'pixels': [[((x // 2) + (y // 2)) % 2 for x in range(8)] for y in range(8)]}
    data = grid_png.to_png(art, 3)
    assert g.restore(data)['width'] == 4                    # ambiguous: smaller grid also explains it
    assert g.cells(g.restore(data, size=8)) == g.cells(art)  # size hint restores exactly


def test_canonical_palette_gives_exact_json_without_meta():
    art = g.canonical(_random_art_grid_tools(12, 9, 7, 3))
    back = g.restore(g.encode(art, scale=4, meta=False), size=12)
    back.pop('restored')
    assert back == art


def test_non_nearest_images_rejected():
    art = pixel_grid.render('rock', 'C01', 'shadow', 16)
    with pytest.raises(ValueError, match='does not divide'):
        g.restore(grid_png.to_png(art, 2), size=7)
    smoothed = g.resize(g.restore(grid_png.to_png(art, 4)), 50)  # 64 -> 50: uneven blocks
    with pytest.raises(ValueError, match='not one color'):
        g.restore(grid_png.to_png(smoothed), size=25)


def test_lossy_inputs_point_to_photo():
    with pytest.raises(ValueError, match='lossy'):
        g.restore(b'\xff\xd8\xff\xe0' + b'\0' * 20)


# --- resize / recolor -----------------------------------------------------------------------
@pytest.mark.parametrize('k', [2, 3, 7])
def test_resize_up_then_down_exact(k):
    for art in ALL_ART[::5]:
        up = g.resize(art, art['width'] * k)
        assert up['height'] == art['height'] * k
        assert g.resize(up, art['width']) == art
        w, h, rows = photo_grid.decode_png(grid_png.to_png(art, k))
        assert g.cells(up) == g._rows_to_cells(w, h, rows)              # resize == PNG --scale


def test_resize_down_then_up_needs_uniform_blocks():
    art = pixel_grid.render('cloud', 'C01', 'normal', 32)
    blocky = g.resize(g.resize(art, 16), 32)
    assert g.resize(g.resize(blocky, 16), 32) == blocky       # uniform 2x2 blocks: exact
    assert g.resize(g.resize(art, 16), 32) != art              # detail lost


def test_any_upscale_then_back_is_exact_even_non_integer():
    """Cell-center sampling: every upscale (also 10->15) keeps every source cell, so down again is exact."""
    for a in range(1, 40):
        art = _random_art_grid_tools(a, 3, 6, a)
        for b in range(a, 3 * a + 2):
            assert g.resize(g.resize(art, b, 3), a, 3) == art
    art = _random_art_grid_tools(10, 10, 5, 9)
    assert g.resize(g.resize(art, 7), 10) != art                      # downscale drops cells


def test_recolor_round_trip_and_limits():
    art = pixel_grid.render('diamond', 'C01', 'outline', 21)
    there = g.recolor(art, 'C09')
    assert there['pixels'] == art['pixels'] and there['colors'] == list(pixel_grid.PALETTES['C09'])
    assert g.recolor(there, 'C01') == art
    with pytest.raises(ValueError, match='unknown color ID'):
        g.recolor(art, 'lava')
    with pytest.raises(ValueError, match='beyond the 5 roles'):
        g.recolor(_random_art_grid_tools(4, 4, 9, 1), 'C01')


# --- SVG -----------------------------------------------------------------------------------
def test_svg_output_loads_back_to_same_visible_cells():
    for art in ALL_ART[::3] + [_random_art_grid_tools(9, 7, 20, 5)]:
        back = g.restore(g.encode(art, 'svg'))
        want = [[c if c[7:] != '00' else '#00000000' for c in row] for row in g.cells(art)]
        assert g.cells(back) == want


# --- JPEG/WebP chain -----------------------------------------------------------------------
@needs_pil
@pytest.mark.parametrize('fmt', ['JPEG', 'WEBP'])
def test_photo_to_png_base64_to_svg_chain(fmt):
    from PIL import Image
    img = Image.new('RGB', (90, 60))
    img.putdata([(x * 3 % 256, y * 4 % 256, 120) for y in range(60) for x in range(90)])
    buf = io.BytesIO()
    img.save(buf, fmt, quality=85)
    art = g.photo(buf.getvalue(), 32, colors=6)
    assert art == g.photo(buf.getvalue(), 32, colors=6)                      # deterministic
    assert g.photo(base64.b64encode(buf.getvalue()).decode(), 32, colors=6) == art
    b64 = g.encode(art, data_uri=True)
    assert g.restore(b64) == art                                             # lossless from here
    svg = g.encode(art, 'svg')
    assert svg.startswith('<svg') and g.cells(g.restore(svg)) == g.cells(art)


# --- backend cross-checks (stdlib is the oracle) ---------------------------------------------
@needs_pil
def test_png_decode_stdlib_matches_pillow():
    for art in ALL_ART[::4] + [_random_art_grid_tools(31, 5, 50, 2)]:
        data = g.encode(art, 'png', 3, meta=False)
        assert g._decode_png(data, 'stdlib') == g._decode_png(data, 'PIL')
        assert g.restore(data, backend='stdlib') == g.restore(data, backend='PIL')


@needs_numpy
def test_scale_detect_and_resize_stdlib_matches_numpy():
    for i, art in enumerate(ALL_ART[::4]):
        grid = g.cells(g.resize(art, art['width'] * (i % 4 + 1)))
        assert g._runs_gcd(grid, 'stdlib') == g._runs_gcd(grid, 'numpy')
        for w in (1, 7, 40, art['width'] * 3):
            assert g.resize(art, w, backend='stdlib') == g.resize(art, w, backend='numpy')


@needs_pil
def test_integer_resize_matches_pillow_nearest():
    from PIL import Image
    art = _random_art_grid_tools(13, 11, 9, 4)
    w, h, rows = photo_grid.decode_png(grid_png.to_png(art))
    img = Image.frombytes('RGBA', (w, h), b''.join(rows)).resize((39, 33), Image.NEAREST)
    assert img.tobytes() == b''.join(photo_grid.decode_png(grid_png.to_png(g.resize(art, 39)))[2])


def test_without_optional_backends(monkeypatch):
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name.split('.')[0] in ('numpy', 'PIL'):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, '__import__', blocked)
    art = ALL_ART[7]
    assert g._backend('auto', 'numpy') == 'stdlib' and g._backend('auto', 'PIL') == 'stdlib'
    assert g.restore(g.encode(art, scale=2)) == art
    assert g.cells(g.restore(g.encode(art, 'svg'))) == g.cells(art)
    assert g.resize(g.resize(art, 99), art['width']) == art


@needs_numpy
@needs_pil
def test_relative_timing_report(capsys):
    art = pixel_grid.render('circle', 'C02', 'outline', 128)
    data = g.encode(art, 'png', 4, meta=False)
    times = {}
    for be in ('stdlib', 'PIL', 'numpy'):
        t = time.perf_counter()
        out = g.restore(data, backend=be)
        times[be] = time.perf_counter() - t
        assert g.cells(out) == g.cells(art)
    with capsys.disabled():
        print('\nrestore 512x512 PNG ->128:', {k: f'{v * 1000:.0f}ms' for k, v in times.items()})


# --- one-liners -----------------------------------------------------------------------------
def _run(*args, stdin=None):
    return subprocess.run([sys.executable, *args], cwd=ROOT, input=stdin, capture_output=True, timeout=120)


def test_python_c_one_liner():
    r = _run('-c', "import grid_tools as g;print(g.encode(g.make('cloud','C01','shadow',16),data_uri=True))")
    assert r.returncode == 0, r.stderr
    uri = r.stdout.decode().strip()
    assert uri.startswith('data:image/png;base64,')
    assert g.restore(uri) == pixel_grid.render('cloud', 'C01', 'shadow', 16)


def test_python_m_pipeline(tmp_path):
    r = _run('-m', 'grid_tools', 'make', 'circle', '--palette', 'C04', '--size', '32', '--scale', '2', '--no-meta')
    assert r.returncode == 0, r.stderr
    b64 = r.stdout.decode().strip()
    r = _run('-m', 'grid_tools', 'load', b64, '--to', 'json')
    art = json.loads(r.stdout)
    assert art['width'] == 32 and art['restored']['scale'] == 2
    out = tmp_path / 'x.png'
    r = _run('-m', 'grid_tools', 'load', '-', '--resize', '64', '--recolor', 'C05', '--to', 'png', '-o', str(out),
             stdin=b64.encode())
    assert r.returncode == 0 and out.read_bytes().startswith(b'\x89PNG')
    assert g.restore(out.read_bytes())['palette'] == 'C05'
    r = _run('-m', 'grid_tools', 'load', str(out), '--to', 'svg')
    assert r.stdout.startswith(b'<svg')


@pytest.mark.parametrize('args, message', [
    (['load', 'not base64!'], b'invalid Base64'),
    (['load', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0"/></svg>'], b'path'),
    (['make', 'cloud', '--size', '8'], b'16 to 256'),
    (['load', '{"width": 1}', '--recolor', 'C01'], b'error'),
])
def test_cli_errors_exit_2(args, message):
    r = _run('-m', 'grid_tools', *args)
    assert r.returncode == 2 and message in r.stderr, r.stderr


# ═══ · image base64 cycles ═══════════════════════════════════════════════════════════════════════════════
# Repeated image interchange, original-pixel witnesses, subprocess boundaries.
#
# Transport cycles are lossless PNG controls, not JPEG re-encoding or resize claims.

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


# ═══ · image formats ═════════════════════════════════════════════════════════════════════════════════════
# Input-format matrix for photo_grid: raw file bytes, Base64 and data URI (matches README table).

def _png_image_formats(color_type=6, depth=8, interlace=0):
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
            pg.convert(f'data:{mime};base64,' + base64.b64encode(_png_image_formats()).decode(), size=8)


@pytest.mark.parametrize('form', ['raw', 'base64', 'data_uri'])
def test_png_works_without_pillow(form, monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    data = _png_image_formats()
    text = {'raw': data, 'base64': base64.b64encode(data).decode(),
            'data_uri': 'data:image/png;base64,' + base64.b64encode(data).decode()}[form]
    assert pg.convert(text, size=8)['colors'][1] == '#C8C8C8FF'


@pytest.mark.parametrize('kwargs,message', [({'depth': 16}, 'bit depth 16'), ({'interlace': 1}, 'interlaced')])
def test_png_variants_without_pillow(kwargs, message, monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    with pytest.raises(pg.ImageDecodeError, match=message):
        pg.convert(_png_image_formats(**kwargs), size=8)


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


# ═══ · photo grid ════════════════════════════════════════════════════════════════════════════════════════

def _png_photo_grid(width, height, pixel, color_type=6, depth=8, interlace=0, filter_type=0):
    channels = {0: 1, 2: 3, 4: 2, 6: 4, 3: 1}[color_type]
    raw = b''.join(bytes([filter_type]) + b''.join(bytes(pixel(x, y)[:channels]) for x in range(width))
                   for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    header = struct.pack('>IIBBBBB', width, height, depth, color_type, 0, 0, interlace)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))


def _b64_photo_grid(data):
    return base64.b64encode(data).decode('ascii')


def _quadrants(x, y):
    return [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)][(y >= 10) * 2 + (x >= 10)]


@pytest.mark.parametrize('size', g_photo_grid.SIZES)
def test_dimensions_palette_range_and_determinism(size):
    text = _b64_photo_grid(_png_photo_grid(20, 20, _quadrants))
    a = g_photo_grid.convert(text, size=size, colors=4)
    assert a == g_photo_grid.convert(text, size=size, colors=4)
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
    a = g_photo_grid.convert(_b64_photo_grid(_png_photo_grid(48, 16, pixel)), size=8, colors=16)
    assert a['source'] == {'width': 48, 'height': 16}
    assert a['colors'] == ['#00000000', '#808080FF']
    assert {v for r in a['pixels'] for v in r} == {1}


def test_transparency_and_contain_margin():
    half = _b64_photo_grid(_png_photo_grid(16, 16, lambda x, y: (200, 10, 10, 255 if x < 8 else 0)))
    a = g_photo_grid.convert(half, size=16, colors=2)
    assert all(r[0] != 0 and r[-1] == 0 for r in a['pixels'])
    assert a['colors'] == ['#00000000', '#C80A0AFF']
    wide = _b64_photo_grid(_png_photo_grid(32, 8, lambda x, y: (0, 0, 255, 255), color_type=2))
    c = g_photo_grid.convert(wide, size=16, fit='contain')
    assert not any(c['pixels'][0]) and not any(c['pixels'][-1])
    assert sum(1 for r in c['pixels'] if any(r)) == 4


@pytest.mark.parametrize('color_type,filter_type', [(0, 1), (2, 2), (4, 3), (6, 4)])
def test_png_color_types_and_filters(color_type, filter_type):
    data = _png_photo_grid(5, 4, lambda x, y: (x * 40, y * 50, 90, 255), color_type, filter_type=filter_type)
    width, height, rows = g_photo_grid.decode_png(data)
    assert (width, height, len(rows), len(rows[0])) == (5, 4, 4, 20)


def test_png_filters_reconstruct_exact_pixels():
    pixel = lambda x, y: (x * 30 % 256, y * 70 % 256, (x * y) % 256, 200)
    expected = g_photo_grid.decode_png(_png_photo_grid(6, 5, pixel))[2]
    raw = []
    for y in range(5):
        line = b''.join(bytes(pixel(x, y)) for x in range(6))
        prev = b''.join(bytes(pixel(x, y - 1)) for x in range(6)) if y else bytes(24)
        raw.append(b'\x02' + bytes((line[i] - prev[i]) & 255 for i in range(24)))
    body = zlib.compress(b''.join(raw))
    data = _png_photo_grid(6, 5, pixel)
    head = data[:33]
    idat = struct.pack('>I', len(body)) + b'IDAT' + body + struct.pack('>I', zlib.crc32(b'IDAT' + body))
    tail = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND'))
    assert g_photo_grid.decode_png(head + idat + tail)[2] == expected


def test_fixed_palette_and_data_uri():
    data = _png_photo_grid(4, 4, lambda x, y: (91, 189, 62, 255))
    uri = 'data:image/png;base64,' + _b64_photo_grid(data)
    a = g_photo_grid.convert(uri, size=8, palette='C01')
    assert a['colors'] == list(g_photo_grid.PALETTES['C01'])
    assert {v for r in a['pixels'] for v in r} == {1}
    wrapped = '\n'.join(_b64_photo_grid(data)[i:i + 10] for i in range(0, len(_b64_photo_grid(data)), 10))
    assert g_photo_grid.decode_base64(wrapped) == data


@pytest.mark.parametrize('text', ['', '   ', 'abc', 'a!==', 'data:image/png,abcd', 'AAAA====', 'éé'])
def test_invalid_base64(text):
    with pytest.raises(ValueError):
        g_photo_grid.decode_base64(text)


def test_size_limits():
    data = _png_photo_grid(4, 4, lambda x, y: (1, 2, 3, 255))
    with pytest.raises(ValueError, match='exceeds'):
        g_photo_grid.decode_base64(_b64_photo_grid(data), max_bytes=len(data) - 1)
    with pytest.raises(g_photo_grid.ImageDecodeError, match='pixels'):
        g_photo_grid.convert(_b64_photo_grid(data), max_pixels=15)


@pytest.mark.parametrize('kwargs,match', [
    ({'depth': 16}, 'unsupported'), ({'color_type': 3}, 'unsupported'), ({'interlace': 1}, 'interlaced')])
def test_unsupported_png(kwargs, match):
    data = _png_photo_grid(2, 2, lambda x, y: (0, 0, 0, 0), **kwargs)
    with pytest.raises(g_photo_grid.ImageDecodeError, match=match):
        g_photo_grid.decode_png(data)


def test_corrupt_png():
    data = bytearray(_png_photo_grid(2, 2, lambda x, y: (0, 0, 0, 255)))
    data[20] ^= 1
    with pytest.raises(g_photo_grid.ImageDecodeError, match='CRC'):
        g_photo_grid.decode_png(bytes(data))
    with pytest.raises(g_photo_grid.ImageDecodeError):
        g_photo_grid.decode_png(bytes(data[:30]))


@pytest.mark.parametrize('kwargs', [{'size': 17}, {'size': True}, {'fit': 'stretch'},
                                    {'colors': 0}, {'colors': 17}, {'palette': 'unknown'}])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        g_photo_grid.convert(_b64_photo_grid(_png_photo_grid(2, 2, lambda x, y: (0, 0, 0, 255))), **kwargs)


def test_non_png_without_pillow_has_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, 'PIL', None)
    with pytest.raises(g_photo_grid.ImageDecodeError, match='Pillow'):
        g_photo_grid.convert(_b64_photo_grid(b'\xff\xd8\xff\xe0 not really a jpeg'))


def test_pillow_adapter_jpeg():
    pil = pytest.importorskip('PIL.Image')
    import io
    buffer = io.BytesIO()
    pil.new('RGB', (24, 12), (250, 20, 20)).save(buffer, 'JPEG', quality=95)
    a = g_photo_grid.convert(_b64_photo_grid(buffer.getvalue()), size=8, colors=1)
    r, gg, b = g_photo_grid._hex_rgb(a['colors'][1])
    assert r > 200 and gg < 60 and b < 60
    assert {v for row in a['pixels'] for v in row} == {1}


def test_cli_and_inert_import(tmp_path):
    file = Path(g_photo_grid.__file__).resolve()
    src = tmp_path / 'in.b64'
    src.write_text(_b64_photo_grid(_png_photo_grid(8, 8, _quadrants)), encoding='ascii')
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


# ═══ · pixel grid ════════════════════════════════════════════════════════════════════════════════════════

ODD = (13, 15, 17, 23, 29, 31)


def _shape(grid):
    return [[bool(v) for v in row] for row in grid]


def _independent_quality(grid, vertical_symmetry, notch=False):
    """Re-check the core rule without pixel_grid helpers: margin, symmetry, 4-connected,
    no column gaps, and no 2x2 stairs on the top/bottom/left edges."""
    size = len(grid)
    cells = {(y, x) for y in range(size) for x in range(size) if grid[y][x]}
    assert cells and not any(grid[0]) and not any(grid[-1]) and all(r[0] == r[-1] == 0 for r in grid)
    assert all(row == row[::-1] for row in grid)
    if vertical_symmetry:
        assert grid == grid[::-1]
    stack, seen = [min(cells)], {min(cells)}
    while stack:
        y, x = stack.pop()
        for n in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if n in cells and n not in seen:
                seen.add(n)
                stack.append(n)
    assert seen == cells
    cols = sorted({x for _, x in cells})
    tops, bottoms = [], []
    for x in cols:
        ys = [y for y in range(size) if grid[y][x]]
        assert ys == list(range(ys[0], ys[-1] + 1))
        tops.append(ys[0])
        bottoms.append(ys[-1])
    lefts = [row.index(1) for row in grid if any(row)]
    if notch:  # cloud: the puff notch is a deliberate concave corner; check the edge below it
        drops = [a - b for a, b in zip(lefts, lefts[1:])]
        lefts = lefts[drops.index(max(drops)) + 1:]
    for profile in (tops, bottoms, lefts):
        steps = [b - a for a, b in zip(profile, profile[1:])]
        for i in range(len(steps) - 1):
            assert not (abs(steps[i]) >= 2 and steps[i + 1] == 0), (profile, i)
            assert not (steps[i] == 0 and abs(steps[i + 1]) >= 2), (profile, i)


@pytest.mark.parametrize('mask', p.MASKS)
def test_quality_rule_over_default_range(mask):
    low, high = p.MASK_BOUNDS[mask]
    for size in list(range(low, 97)) + [128, 160, 199, 256]:
        grid = p.silhouette(mask, size)
        assert p.mask_problem(mask, grid) is None
        _independent_quality(grid, mask in ('circle', 'diamond'), mask == 'cloud')


@pytest.mark.heavy
@pytest.mark.parametrize('mask', p.MASKS)
def test_quality_rule_over_whole_range(mask):
    low, high = p.MASK_BOUNDS[mask]
    for size in range(low, high + 1):
        _independent_quality(p.silhouette(mask, size), mask in ('circle', 'diamond'), mask == 'cloud')


def test_bounds_are_tight_below_and_reject_cleanly():
    for mask, (low, high) in p.MASK_BOUNDS.items():
        for bad in (low - 1, high + 1, 0, -3, True, 16.0, '16'):
            with pytest.raises(ValueError, match=f'{mask} needs an integer size from {low} to {high}'):
                p.silhouette(mask, bad)
    assert p.MASK_BOUNDS == {'triangle': (5, 256), 'diamond': (9, 256), 'cloud': (16, 256),
                             'circle': (6, 256), 'rock': (7, 256)}


def test_masks_are_distinct_and_recognizable():
    for size in range(16, 65):
        shapes = [p.silhouette(m, size) for m in p.MASKS]
        assert len({json.dumps(s) for s in shapes}) == len(p.MASKS)
    tri = p.silhouette('triangle', 31)
    widths = [sum(r) for r in tri if any(r)]
    assert widths == list(range(widths[0], widths[-1] + 1, 2)) and widths[0] <= 2
    cloud = p.silhouette('cloud', 31)
    tops = [min(y for y in range(31) if cloud[y][x]) for x in range(31) if any(cloud[y][x] for y in range(31))]
    assert sum(1 for i in range(1, len(tops) - 1) if tops[i] > tops[i - 1] and tops[i] >= tops[i + 1]) >= 2


@pytest.mark.parametrize('grid,reason', [
    ([[0, 0, 0, 0, 0], [0, 1, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], 'not 4-connected'),
    ([[0] * 6, [0, 1, 1, 0, 0, 0], [0, 1, 1, 1, 1, 0], [0] * 6, [0] * 6, [0] * 6], 'symmetric'),
    ([[1, 1, 1]] + [[0, 0, 0]] * 2, 'margin'),
    ([[0] * 9, [0, 0, 0, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0, 0], [0, 1, 1, 1, 1, 1, 1, 1, 0],
      [0, 1, 1, 1, 1, 1, 1, 1, 0], [0] * 9, [0] * 9, [0] * 9, [0] * 9], 'jagged edge'),
])
def test_quality_rule_rejects_artifacts(grid, reason):
    assert reason in p.mask_problem('rock', grid)


def test_old_nearest_neighbour_seed_fit_is_rejected_at_odd_sizes():
    # The previous fixed 13x5 cloud seed, enlarged by nearest neighbour, shows the 2x2 stairs
    # this rule forbids at most odd sizes.
    seed = ('0011100011100', '0111110111110', '1111111111111', '1111111111111', '0111111111110')
    rejected = 0
    for size in ODD:
        span = size - 2
        scale = min(span / 13, span / 5)
        w, h = max(1, round(13 * scale)), max(1, round(5 * scale))
        left, top = (size - w) // 2, (size - h) // 2
        grid = [[0] * size for _ in range(size)]
        for y in range(h):
            for x in range(w):
                grid[top + y][left + x] = int(seed[y * 5 // h][x * 13 // w])
        rejected += p.mask_problem('cloud', grid) is not None
    assert rejected >= len(ODD) - 1


def test_palettes_are_color_ids_with_derived_roles():
    assert list(p.PALETTES) == [f'C{i:02d}' for i in range(1, 11)]
    assert all(re.fullmatch(r'C\d\d', k) for k in p.PALETTE_BASE)
    assert p.PALETTE_BASE['C01'] == ('#5BBD3E', '#418A2D') and p.PALETTE_LABELS['C01'] == 'grass'
    assert p.PALETTES['C01'] == ('#00000000', '#5BBD3EFF', '#418A2DFF', '#9DD78BFF', '#214517FF')
    assert p.derive_palette('#FFFFFF', '#000000') == ('#00000000', '#FFFFFFFF', '#000000FF', '#FFFFFFFF', '#000000FF')
    assert p.derive_palette('#000000', '#010101')[3:] == ('#666666FF', '#010101FF')  # 102 = 2*255/5; 0.5 -> 1
    for pid, (main, shadow) in p.PALETTE_BASE.items():
        assert p.PALETTES[pid][0] == '#00000000' and p.PALETTES[pid][1:3] == (main + 'FF', shadow + 'FF')
    with pytest.raises(ValueError):
        p.render('circle', 'grass', 'normal', 16)


@pytest.mark.parametrize('size', ODD + p.SIZES[1:])
def test_render_effects_and_determinism(size):
    for mask in p.MASKS:
        if size < p.MASK_BOUNDS[mask][0]:
            continue
        plain = p.render(mask, 'C02', 'normal', size)
        for effect in p.EFFECTS:
            a = p.render(mask, 'C02', effect, size)
            assert a == p.render(mask, 'C02', effect, size)
            assert a['width'] == a['height'] == size and len(a['pixels']) == size
            assert _shape(a['pixels']) == _shape(plain['pixels'])
            assert all(0 <= v < 5 for r in a['pixels'] for v in r)
            assert len(p.emoji(a).splitlines()) == size
        points = [(y, x) for y, row in enumerate(plain['pixels']) for x, v in enumerate(row) if v]
        mid = (min(y for y, _ in points) + max(y for y, _ in points)) / 2
        shadow = p.render(mask, 'C02', 'shadow', size)['pixels']
        highlight = p.render(mask, 'C02', 'highlight', size)['pixels']
        outline = p.render(mask, 'C02', 'outline', size)['pixels']
        assert all(y > mid for y, x in points if shadow[y][x] == 2)
        assert all(y < mid for y, x in points if highlight[y][x] == 3)
        for y, x in points:
            edge = any(not plain['pixels'][yy][xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
            assert (outline[y][x] == 4) == edge


def test_filename_uses_color_id():
    assert p.filename(p.render('triangle', 'C01', 'shadow', 32)) == 'triangle_C01_shadow_32.png'
    assert p.filename(p.render('cloud', 'C10', 'normal', 17), 'svg') == 'cloud_C10_normal_17.svg'


@pytest.mark.parametrize('kwargs', [{'size': True}, {'size': 13}, {'mask': 'unknown'}, {'palette': 'unknown'},
                                    {'effect': 'unknown'}])
def test_invalid_selections(kwargs):
    with pytest.raises(ValueError):
        p.render(**kwargs)


def test_cli_and_inert_import_pixel_grid(tmp_path):
    file = Path(p.__file__).resolve()
    result = subprocess.run([sys.executable, '-S', str(file), '--mask', 'circle', '--size', '23', '--format', 'json'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['width'] == 23
    bad = subprocess.run([sys.executable, '-S', str(file), '--mask', 'cloud', '--size', '8'],
                         cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode == 2 and 'cloud needs an integer size from 16 to 256' in bad.stderr
    result = subprocess.run([sys.executable, '-S', '-c', 'import sys;sys.path.insert(0,sys.argv[1]);import pixel_grid',
                             str(file.parent)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0 and result.stdout == result.stderr == b''
    assert list(tmp_path.iterdir()) == []


# ═══ · pixel arcade engine ═══════════════════════════════════════════════════════════════════════════════
# Arcade engine invariants, reference target vectors, and existing export integration.

def artifact(rows, colors=None):
    return {'schema': 'ironmate-pixel-grid/1', 'width': len(rows[0]), 'height': len(rows),
            'colors': colors or ['#00000000', '#FF0000FF', '#0000FFFF'], 'pixels': rows}


def assert_mask(grid):
    assert grid.active_mask == sum(1 << i for i, v in enumerate(grid.pixels) if grid.is_active(v))


@pytest.mark.parametrize('seed', range(10))
def test_random_swaps_restore_exact_pixels_mask_and_metadata(seed):
    rnd = random.Random(seed)
    art = artifact([[rnd.randrange(3) for _ in range(13)] for _ in range(9)])
    art['source'] = {'format': 'png', 'width': 13, 'height': 9}
    original = deepcopy(art)
    scanner = g.sparse(art)
    grid = scanner.grid
    before, mask = grid.pixels, grid.active_mask
    for _ in range(200):
        y, x = rnd.randrange(9), rnd.randrange(12)
        grid.swap_pixels_reversible(y * 13 + x, y * 13 + x + 1)
        assert_mask(grid)
        assert Counter(grid.pixels) == Counter(before)
    assert grid.rollback_all() > 0
    assert grid.pixels == before and grid.active_mask == mask
    assert grid.to_artifact() == original == art
    assert grid.rollback_all() == 0


def test_sparse_and_sentinel_do_not_read_pixel_array():
    grid = ReversiblePixelGrid(100, 100, [1 if i in (101, 5050, 9999) else 0 for i in range(10000)])

    class NoRead(list):
        def __iter__(self):
            raise AssertionError('full pixel scan')

        def __getitem__(self, key):
            raise AssertionError('pixel access')

    grid._pixels = NoRead(grid._pixels)
    hits = list(InvaderSparseScanner(grid).iter_active_coords())
    assert hits == [(101, 1, 1), (5050, 50, 50), (9999, 99, 99)]
    assert len(hits) == grid.active_count == 3
    assert grid.check_sentinel_collision()
    assert grid.check_sentinel_collision(1 << 5050)
    assert not grid.check_sentinel_collision(1 << 202)


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_formation_moves_once_per_active_cell_and_rolls_back(direction):
    rows = [[0] * 7 for _ in range(7)]
    rows[2][2:5], rows[3][2:5] = [1, 2, 1], [2, 1, 2]
    scanner = g.sparse(artifact(rows), quota_per_frame=4)
    grid, (dx, dy) = scanner.grid, direction
    before = grid.to_artifact()
    result = scanner.shift_formation_step_by_step(dx, dy)
    expected = [[0] * 7 for _ in range(7)]
    for y in range(7):
        for x in range(7):
            if rows[y][x]:
                expected[y + dy][x + dx] = rows[y][x]
    assert grid.to_artifact()['pixels'] == expected
    assert result['active_dots'] == 6 and result['frames_for_one_step'] == 2
    assert_mask(grid)
    grid.rollback_all()
    assert grid.to_artifact() == before


def test_frame_quota_changes_and_partial_step_can_be_rolled_back():
    art = artifact([[0] * 8, [0, 1, 2, 1, 2, 1, 0, 0], [0] * 8])
    scanner = g.sparse(art)
    frames = scanner.iter_shift_frames(1, 0)
    assert next(frames)['processed'] == 1
    scanner.quota_per_frame = 2
    assert next(frames)['processed'] == 3
    frames.close()
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == art
    assert scanner.shift_formation_step_by_step(1, 0)['frames_for_one_step'] == 3
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == art


@pytest.mark.parametrize('dx,dy,index', [(1, 0, 5), (-1, 0, 3), (0, 1, 7), (0, -1, 1)])
def test_overflow_is_atomic_and_distinct_from_border_contact(dx, dy, index):
    values = [0] * 9
    values[index] = 1
    grid = ReversiblePixelGrid(3, 3, values)
    scanner = InvaderSparseScanner(grid)
    assert grid.check_sentinel_collision()
    with pytest.raises(ValueError, match='outside'):
        scanner.shift_formation_step_by_step(dx, dy)
    assert grid.pixels == tuple(values) and grid.rollback_all() == 0
    # Touching an unrelated edge does not block a legal horizontal/vertical move.
    scanner.shift_formation_step_by_step(-dx, -dy)
    assert_mask(grid)
    grid.rollback_all()
    assert grid.pixels == tuple(values)


def test_empty_grid_and_invalid_inputs():
    scanner = InvaderSparseScanner(ReversiblePixelGrid(2, 2))
    assert list(scanner.iter_active_coords()) == []
    assert scanner.shift_formation_step_by_step(1, 0)['frames_for_one_step'] == 0
    for quota in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match='quota'):
            InvaderSparseScanner(scanner.grid, quota)
    for move in ((0, 0), (1, 1), (-1, 1), (2, 0), (True, 0)):
        with pytest.raises(ValueError, match='cardinal'):
            scanner.shift_formation_step_by_step(*move)
    for args in ((0, 2), (2, -1), (True, 2), (4097, 1), (2, 2, []), (1, 1, [-1])):
        with pytest.raises(ValueError):
            ReversiblePixelGrid(*args)
    for index in (-1, 4, True):
        with pytest.raises(ValueError):
            scanner.grid.swap_pixels_reversible(0, index)


def test_exact_probe_targets_and_guzuta_distance_boundary():
    probes = PacmanGhostProbes(corner_pos=(-2, -3))
    targets = probes.compute_targets(10, 20, -1, 1, (2, 4), (13, 24))
    assert targets.akabei == (2, 4)
    assert targets.pinky == (6, 24)
    assert targets.aosuke == (14, 40)
    assert targets.guzuta == (-2, -3)  # Manhattan 7: retreat
    assert probes.compute_targets(10, 20, -1, 1, (2, 4), (14, 24)).guzuta == (14, 24)  # 8


def test_guzuta_thins_dense_blocks_but_keeps_isolated_feature():
    dense = artifact([[1] * 4 for _ in range(2)])
    naive = g.resize(dense, 2, 1, backend='stdlib')
    adaptive = g.downscale_2x(dense)
    assert naive['pixels'] == [[1, 1]]
    assert adaptive['pixels'] == [[1, 0]]
    assert dense['pixels'] == [[1] * 4 for _ in range(2)]
    isolated = artifact([[0, 0], [0, 2]])
    assert g.downscale_2x(isolated)['pixels'] == [[2]]
    assert g.downscale_2x(artifact([[0, 0], [0, 0]]))['pixels'] == [[0]]


def test_palette_permutation_preserves_visible_output_and_transparent_indices():
    art = artifact([[0, 1, 1, 2], [1, 2, 1, 0], [2, 1, 2, 1], [1, 2, 0, 2]])
    permutation = [2, 0, 1]
    renamed = deepcopy(art)
    renamed['colors'] = [art['colors'][1], art['colors'][2], art['colors'][0]]
    renamed['pixels'] = [[permutation[v] for v in row] for row in art['pixels']]
    assert g.cells(g.downscale_2x(art)) == g.cells(g.downscale_2x(renamed))
    more = artifact([[0, 1], [2, 3]], ['#FF0000FF', '#01020300', '#00000000', '#12345601'])
    scanner = g.sparse(more)
    assert list(scanner.iter_active_coords()) == [(0, 0, 0), (3, 1, 1)]
    scanner.grid.swap_pixels_reversible(0, 1)
    assert_mask(scanner.grid)
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == more


def test_opaque_zero_is_active_and_background_is_appended_only_if_needed():
    art = artifact([[0] * 4 for _ in range(2)], ['#FF0000FF'])
    scanner = g.sparse(art)
    assert scanner.grid.active_count == 8
    assert scanner.grid.to_artifact() == art
    out = g.downscale_2x(art)
    assert out['colors'] == ['#FF0000FF', '#00000000']
    assert out['pixels'] == [[0, 1]]


def test_adapter_copies_and_rejects_invalid_palette_or_shape():
    art = artifact([[0, 1], [2, 0]])
    grid = ReversiblePixelGrid.from_artifact(art)
    art['pixels'][0][0] = 2
    out = grid.to_artifact()
    out['colors'][0] = '#FFFFFFFF'
    assert grid.to_artifact()['pixels'][0][0] == 0
    assert grid.to_artifact()['colors'][0] == '#00000000'
    for changes in ({'schema': 'other'}, {'width': 3}, {'colors': []}, {'colors': ['red']},
                    {'pixels': [[0, -1], [0, 0]]}, {'pixels': [[0, 3], [0, 0]]},
                    {'pixels': [[0, True], [0, 0]]}):
        with pytest.raises(ValueError):
            ReversiblePixelGrid.from_artifact(dict(art, **changes))


@pytest.mark.parametrize('width,height', [(1, 2), (2, 1), (3, 4), (4, 3)])
def test_odd_or_tiny_dimensions_are_rejected_without_cropping(width, height):
    with pytest.raises(ValueError, match='even'):
        PacmanGhostProbes().adaptive_downscale_2x(ReversiblePixelGrid(width, height))


def test_existing_png_base64_svg_pipeline_after_filter_and_rollback():
    original = g.make('circle', 'C02', 'outline', 16)
    scanner = g.sparse(original, 10)
    scanner.shift_formation_step_by_step(1, 0)
    scanner.grid.rollback_all()
    assert g.restore(g.encode(scanner.grid.to_artifact()), backend='stdlib') == original
    small = g.resize(original, 8, method='probes')
    assert small == g.downscale_2x(original)
    assert small['resampling'] == 'pacman_probes_2x_lossy'
    for fmt in ('base64', 'png'):
        assert g.restore(g.encode(small, fmt, scale=3), backend='stdlib') == small
    assert g.cells(g.restore(g.encode(small, 'svg'), backend='stdlib')) == g.cells(small)
    # Existing default resize still has its existing round-trip behavior.
    assert g.resize(g.resize(original, 32), 16) == original
    with pytest.raises(ValueError, match='exact 2x'):
        g.resize(original, 7, method='probes')
    with pytest.raises(ValueError, match='method'):
        g.resize(original, 8, method='other')


def test_cli_stdlib_probe_png_round_trip_and_invalid_resize():
    cli = [sys.executable, '-S', '-m', 'grid_tools', 'make', 'circle', '--size', '16']
    result = subprocess.run(cli + ['--resize', '8', '--resize-method', 'probes', '--to', 'png'],
                            cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    restored = g.restore(result.stdout, backend='stdlib')
    assert restored == g.downscale_2x(g.make('circle', size=16))
    load = subprocess.run([sys.executable, '-S', '-m', 'grid_tools', 'load', '-', '--to', 'json'],
                          cwd=ROOT, input=result.stdout, capture_output=True)
    assert load.returncode == 0 and json.loads(load.stdout) == restored
    for args in (['--resize-method', 'probes'], ['--resize', '7', '--resize-method', 'probes'], ['--resize', '0']):
        bad = subprocess.run(cli + args, cwd=ROOT, capture_output=True)
        assert bad.returncode == 2 and b'Traceback' not in bad.stderr


@pytest.mark.parametrize('colors', [
    ['#FF0000FF'],
    ['#FF000080', '#12345600', '#00000000', '#FF000080'],
    ['#FF0000FF', '#00000000', '#00FF00FF'],
])
def test_rectangular_exports_preserve_palette_and_visible_rgba(colors):
    # Opaque index zero, partial alpha, multiple transparent/duplicate/unused colors.
    art = artifact([[0] * 6 for _ in range(4)], colors)
    art.update(mask='custom', palette='custom', effect='normal',
               source={'format': 'png', 'width': 6, 'height': 4},
               custom_metadata={'nested': ['owned', 1]})
    before = deepcopy(art)
    grid = g.sparse(art).grid
    grid.swap_pixels_reversible(0, 23)
    grid.rollback_all()
    assert grid.to_artifact() == art == before
    small = g.downscale_2x(art)
    assert (small['width'], small['height']) == (3, 2)
    assert small['colors'][:len(colors)] == colors
    assert small['custom_metadata'] == art['custom_metadata']
    assert g.restore(g.encode(small, 'json')) == small
    from grid_png import header_info
    for fmt in ('png', 'base64'):
        restored = g.restore(g.encode(small, fmt, scale=2, data_uri=True), backend='stdlib')
        # Existing PNG header whitelist and first-index rule for duplicate RGBA.
        assert header_info(restored) == header_info(small)
        assert g.cells(restored) == g.cells(small)
    rgba = lambda a: [[c if c[-2:] != '00' else '#00000000' for c in row] for row in g.cells(a)]
    assert rgba(g.restore(g.encode(small, 'svg'), backend='stdlib')) == rgba(small)
    small['custom_metadata']['nested'].append('changed')
    assert art == before


# ═══ · svg raster ════════════════════════════════════════════════════════════════════════════════════════
# SVG input subset: what rasterizes exactly, what is rejected and why.

SVG_RASTER_NS = 'xmlns="http://www.w3.org/2000/svg"'


def _svg(body, box='0 0 4 4', extra=''):
    return f'<svg {SVG_RASTER_NS} viewBox="{box}"{extra}>{body}</svg>'


def _px(rows, x, y):
    return tuple(rows[y][x * 4:x * 4 + 4])


def test_rect_flat_fill_exact():
    w, h, rows = rasterize(_svg('<rect x="1" y="1" width="2" height="1" fill="#f00"/>'))
    assert (w, h) == (4, 4)
    assert _px(rows, 1, 1) == (255, 0, 0, 255) and _px(rows, 0, 0) == (0, 0, 0, 0)


def test_fill_opacity_and_group_inheritance():
    svg = _svg('<g fill="#00ff00" fill-opacity="0.5" transform="translate(1,0)"><rect width="1" height="1"/></g>')
    assert _px(rasterize(svg)[2], 1, 0) == (0, 255, 0, 128)


def test_grid_svg_output_rasterizes_exactly():
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'C06', 'outline', 20)
        w, h, rows = rasterize(grid_svg.to_svg(art))
        want = [b''.join(bytes.fromhex(art['colors'][v][1:]) for v in row) for row in art['pixels']]
        assert rows == want


@pytest.mark.parametrize('body', [
    '<circle cx="2" cy="2" r="1.5" fill="#123456"/>',
    '<ellipse cx="2" cy="2" rx="2" ry="1" fill="#abc" opacity="0.7"/>',
    '<polygon points="0,0 4,0 2,4" fill="#0f0" fill-opacity="0.3"/>',
])
def test_curved_shapes_supersampled_stdlib_equals_numpy(body):
    pytest.importorskip('numpy')
    svg = _svg(body, '0 0 9 9')
    assert rasterize(svg, backend='stdlib') == rasterize(svg, backend='numpy')


def test_width_scales_output():
    w, h, rows = rasterize(_svg('<rect width="4" height="2"/>', '0 0 4 2'), width=8)
    assert (w, h) == (8, 4)


@pytest.mark.parametrize('body, match', [
    ('<path d="M0 0L4 4"/>', 'path'),
    ('<line x1="0" y1="0" x2="4" y2="4"/>', 'line'),
    ('<polyline points="0,0 1,1"/>', 'polyline'),
    ('<defs><linearGradient id="a"/></defs>', 'defs|linearGradient'),
    ('<rect width="1" height="1" fill="url(#a)"/>', 'gradient'),
    ('<rect width="1" height="1" style="fill:red"/>', 'CSS'),
    ('<rect width="1" height="1" class="x"/>', 'CSS'),
    ('<script>alert(1)</script>', 'script'),
    ('<image href="http://example.com/x.png"/>', 'image'),
    ('<text>hi</text>', 'text'),
    ('<rect width="1" height="1" rx="0.2"/>', 'rx'),
    ('<rect width="1" height="1" stroke="#000"/>', 'stroke'),
    ('<rect width="1em" height="1"/>', 'number'),
    ('<g transform="rotate(45)"><rect width="1" height="1"/></g>', 'translate'),
    ('<rect width="1" height="1" fill="red"/>', 'unsupported fill'),
    ('<blink/>', 'unsupported'),
])
def test_unsupported_features_fail_with_reason(body, match):
    with pytest.raises(SvgError, match=match):
        rasterize(_svg(body))


@pytest.mark.parametrize('data, match', [
    ('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg/>', 'DOCTYPE|ENTITY'),
    ('<!doctype svg><svg/>', 'DOCTYPE'),
    ('<html/>', 'svg'),
    (f'<svg {SVG_RASTER_NS}/>', 'viewBox'),
    ('<svg', 'XML'),
    (f'<svg {SVG_RASTER_NS} viewBox="0 0 5000 5000"/>', 'pixels'),
])
def test_unsafe_or_malformed_documents_rejected(data, match):
    with pytest.raises(SvgError, match=match):
        rasterize(data)


def test_size_limit():
    with pytest.raises(SvgError, match='bytes'):
        rasterize(b' ' * (sr.MAX_BYTES + 1))


# ═══ · size estimate ═════════════════════════════════════════════════════════════════════════════════════
# Downscale / size estimator: exact Base64 math, signals, bounds, lossless detection, CLI.

@pytest.mark.parametrize('n', range(0, 40))
def test_base64_char_math_is_exact(n):
    import base64
    assert s_size_estimate.base64_chars(n) == len(base64.b64encode(bytes(n)))
    assert s_size_estimate.base64_chars(n, True) == len('data:image/png;base64,' + base64.b64encode(bytes(n)).decode())
    assert s_size_estimate.base64_chars(s_size_estimate.bytes_for_chars(s_size_estimate.base64_chars(n))) <= s_size_estimate.base64_chars(n)
    assert s_size_estimate.bytes_for_chars(s_size_estimate.base64_chars(n)) >= n


def test_header_only_estimate():
    r = s_size_estimate.estimate(width=1024, height=768, nbytes=900000, limit_chars=200000, data_uri=True)
    assert r['confidence'] == 'low' and r['achievable'] and not r['fits_now']
    rec = r['recommended']
    assert rec['est_chars'] <= 200000 and Fraction(rec['ratio']) < 1
    assert Fraction(r['integer_option']['ratio']).numerator == 1
    assert r['signals_used'] == ['input byte size only',
                                 'ironmate metadata chunk (default output; --no-meta to omit)']


def test_pixel_art_signals_and_lossless_options():
    data = g.encode(g.make('cloud', 'C01', 'shadow', 32), 'png', 8)
    r = s_size_estimate.estimate(data, limit_bytes=10 ** 6, verify=True)
    sig = r['input']
    assert sig['cell_scale'] == 8 and sig['ironmate_meta'] and sig['color_type'] == 6 and sig['alpha'] == 'binary'
    assert sig['unique_colors'] <= 4
    lossless = {o['ratio'] for o in r['options'] if o['nearest_lossless']}
    assert lossless == {'1', '1/2', '1/4', '1/8'}
    small = g.restore(data)['width']
    assert small == 32
    tight = s_size_estimate.estimate(data, limit_bytes=200, verify=True)
    assert tight['confidence'] == 'verified'
    for o in tight['options']:
        assert o['actual_bytes'] <= o['upper_bytes']


def _photo(fmt, **kw):
    Image = pytest.importorskip('PIL.Image')
    rnd = random.Random(3)
    img = Image.new('RGB', (160, 120))
    img.putdata([(x % 256, (y * 2) % 256, (x * y + rnd.randrange(30)) % 256) for y in range(120) for x in range(160)])
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


@pytest.mark.parametrize('fmt, kw', [('JPEG', {'quality': 50}), ('JPEG', {'quality': 85}), ('WEBP', {'quality': 80}),
                                     ('PNG', {})])
def test_photo_signals_and_estimate_accuracy(fmt, kw):
    data = _photo(fmt, **kw)
    r = s_size_estimate.estimate(data, limit_chars=20000, data_uri=True, verify=True, meta=False)
    with_meta = s_size_estimate.estimate(data, limit_chars=20000, data_uri=True, verify=True)
    assert with_meta['recommended'] is None and '--no-meta' in with_meta['note']   # 1 header entry per color
    sig = r['input']
    if fmt == 'JPEG':
        assert sig['quality_estimate'] == kw['quality'] and sig['subsampling'] == '4:2:0'
    if fmt == 'WEBP':
        assert sig['lossless'] is False
    for o in r['options']:
        assert o['actual_bytes'] <= o['upper_bytes']                    # hard bound holds
        assert 0.5 <= o['actual_bytes'] / o['est_bytes'] <= 2.0          # measured model accuracy
    rec = r['recommended']
    assert rec['actual_chars'] <= 20000


def test_unreachable_limit():
    data = g.encode(g.make('cloud'), 'png')
    r = s_size_estimate.estimate(data, limit_bytes=10, verify=True)
    assert not r['achievable'] and r['recommended'] is None and 'smallest' in r


@pytest.mark.parametrize('kwargs, match', [
    ({'width': 10, 'height': 10, 'limit_bytes': 5}, 'need nbytes'),
    ({'width': 10, 'nbytes': 5, 'limit_bytes': 5}, 'width and height'),
    ({'width': 10, 'height': 10, 'nbytes': 5}, 'exactly one'),
])
def test_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        s_size_estimate.estimate(**kwargs)


def test_cli_one_liners(tmp_path):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', '--width', '800', '--height', '600',
                          '--bytes', '500000', '--limit-chars', '100000'], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)['recommended']['est_chars'] <= 100000
    png = tmp_path / 'a.png'
    png.write_bytes(g.encode(g.make('circle', 'C02', 'normal', 40), 'png', 4))
    out = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', str(png), '--limit-bytes', '400', '--verify'],
                         cwd=ROOT, capture_output=True, timeout=60)
    r = json.loads(out.stdout)
    assert r['confidence'] == 'verified' and r['input']['cell_scale'] == 4
    one = subprocess.run([sys.executable, '-c', "from ironlib import size_estimate as s;print(s.estimate(width=64,height=64,"
                          "nbytes=3000,limit_chars=2000)['recommended']['ratio'])"], cwd=ROOT, capture_output=True)
    assert one.returncode == 0 and Fraction(one.stdout.decode().strip()) < 1
    bad = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', '--width', '5'], cwd=ROOT, capture_output=True)
    assert bad.returncode == 2 and b'error' in bad.stderr


# --- review #92 Blocking: verification must measure the real default grid_tools output -------
def _cli(*args):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', *args], cwd=ROOT, capture_output=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _real(src_path, opt, data_uri, meta):
    """Length of what the verified command actually prints (Base64 text, newline stripped)."""
    args = ['load', str(src_path), '--size', str(opt and SRC_W[src_path]), '--resize', str(opt['width']),
            '--to', 'base64'] + (['--data-uri'] if data_uri else []) + ([] if meta else ['--no-meta'])
    return len(_cli(*args).rstrip(b'\n'))


SRC_W = {}


def _sources(tmp_path):
    rnd = random.Random(92)
    art = g.make('circle', 'C03', 'shadow', 24)
    plain = tmp_path / 'plain.png'          # header-less PNG (e.g. from another tool)
    plain.write_bytes(g.encode(art, 'png', 3, meta=False))
    noisy = dict(art, colors=art['colors'] + ['#%08X' % rnd.getrandbits(32) for _ in range(40)])
    noisy['pixels'] = [[rnd.randrange(len(noisy['colors'])) for _ in row] for row in art['pixels']]
    noise = tmp_path / 'noise.png'
    noise.write_bytes(g.encode(noisy, 'png', 1, meta=False))
    withmeta = tmp_path / 'meta.png'        # default grid_tools output (ironmate header)
    withmeta.write_bytes(g.encode(art, 'png', 3))
    for p in (plain, noise, withmeta):
        SRC_W[p] = s_size_estimate.inspect(p.read_bytes())[0]['width']
    return plain, noise, withmeta


@pytest.mark.parametrize('meta', [True, False])
@pytest.mark.parametrize('data_uri', [False, True])
def test_verify_matches_real_cli_output_at_the_boundary(tmp_path, meta, data_uri):
    for src in _sources(tmp_path):
        data = src.read_bytes()
        probe = s_size_estimate.estimate(data, limit_chars=10 ** 7, data_uri=data_uri, verify=True, meta=meta)
        for opt in probe['options'][:6]:
            real = _real(src, opt, data_uri, meta) if opt['ratio'] in ('1', '1/2', '2/3') else None
            if real is not None:
                assert opt['actual_chars'] == real, (src.name, opt['ratio'])
            assert opt['actual_bytes'] == len(g.encode(s_size_estimate._candidate_artifact(
                data, 'png', SRC_W[src], s_size_estimate.inspect(data)[1], opt['width']), 'png', 1, meta=meta))
            assert opt['actual_bytes'] <= opt['upper_bytes']
        full = probe['options'][0]
        real = _real(src, full, data_uri, meta)
        # limit exactly at the real output size -> full size verified as fitting
        at = s_size_estimate.estimate(data, limit_chars=real, data_uri=data_uri, verify=True, meta=meta)
        assert at['recommended']['ratio'] == '1' and at['recommended']['actual_chars'] == real
        # one Base64 quantum below -> full size must be rejected (no fail-open)
        below = s_size_estimate.estimate(data, limit_chars=real - 1, data_uri=data_uri, verify=True, meta=meta)
        assert below['recommended'] is None or below['recommended']['ratio'] != '1'
        if below['recommended']:
            rec = below['recommended']
            assert _real(src, rec, data_uri, meta) == rec['actual_chars'] <= real - 1
        # byte limits: exact and 1 byte below
        nb = full['actual_bytes']
        assert s_size_estimate.estimate(data, limit_bytes=nb, verify=True, meta=meta)['recommended']['ratio'] == '1'
        assert s_size_estimate.estimate(data, limit_bytes=nb - 1, verify=True, meta=meta)['recommended']['ratio'] != '1' \
            if s_size_estimate.estimate(data, limit_bytes=nb - 1, verify=True, meta=meta)['recommended'] else True


def test_bare_fits_but_default_meta_exceeds(tmp_path):
    """The review's fixture: header-less size fits, the default (meta) output does not."""
    plain, _, _ = _sources(tmp_path)
    data = plain.read_bytes()
    bare = _real(plain, {'width': SRC_W[plain]}, False, False)
    withm = _real(plain, {'width': SRC_W[plain]}, False, True)
    assert withm > bare
    r = s_size_estimate.estimate(data, limit_chars=bare, verify=True)                # default meta=True
    assert r['options'][0]['actual_chars'] == withm > bare
    if r['recommended']:
        assert r['recommended']['ratio'] != '1'
        assert _real(plain, r['recommended'], False, True) <= bare
    r = s_size_estimate.estimate(data, limit_chars=bare, verify=True, meta=False)
    assert r['recommended']['ratio'] == '1'
    out = json.loads(_cli('estimate', str(plain), '--limit-chars', str(bare), '--verify'))
    assert out['meta'] is True and (out['recommended'] or {}).get('ratio') != '1'
    out = json.loads(_cli('estimate', str(plain), '--limit-chars', str(bare), '--verify', '--no-meta'))
    assert out['recommended']['ratio'] == '1' and '--no-meta' in out['recommended']['command']


def test_estimate_without_verify_includes_meta_overhead(tmp_path):
    plain, noise, withmeta = _sources(tmp_path)
    for src in (plain, noise, withmeta):
        data = src.read_bytes()
        on = s_size_estimate.estimate(data, limit_bytes=10 ** 7, verify=True)
        off = s_size_estimate.estimate(data, limit_bytes=10 ** 7, verify=True, meta=False)
        for a, b in zip(on['options'], off['options']):
            assert a['est_bytes'] > b['est_bytes'] and a['upper_bytes'] > b['upper_bytes']
            assert a['actual_bytes'] <= a['upper_bytes']
    hdr_on = s_size_estimate.estimate(width=64, height=64, nbytes=3000, limit_bytes=10 ** 6)
    hdr_off = s_size_estimate.estimate(width=64, height=64, nbytes=3000, limit_bytes=10 ** 6, meta=False)
    assert hdr_on['recommended']['upper_bytes'] > hdr_off['recommended']['upper_bytes']


@pytest.mark.parametrize('n', [2**53-1, 2**53, 2**53+1, 2**64-1, 10**400])
@pytest.mark.parametrize('data_uri', [False, True])
def test_large_base64_length_without_float_rounding_or_overflow(n, data_uri):
    groups, remainder = divmod(n, 3)
    expected = 4 * (groups + bool(remainder))
    prefix = s_size_estimate.DATA_URI_PREFIX if data_uri else 0
    assert s_size_estimate.base64_chars(n, data_uri) == expected + prefix
    budget = expected + prefix
    capacity = s_size_estimate.bytes_for_chars(budget, data_uri)
    assert capacity >= n
    assert s_size_estimate.base64_chars(capacity, data_uri) <= budget
    assert s_size_estimate.base64_chars(capacity + 1, data_uri) > budget


@pytest.mark.parametrize('data_uri', [False, True])
def test_base64_budget_boundary_matches_actual_encoded_bytes(data_uri):
    import base64
    prefix = s_size_estimate.DATA_URI_PREFIX if data_uri else 0
    for budget in range(prefix, prefix + 80):
        capacity = s_size_estimate.bytes_for_chars(budget, data_uri)
        assert len(base64.b64encode(bytes(capacity))) + prefix <= budget
        assert len(base64.b64encode(bytes(capacity + 1))) + prefix > budget


# ═══ · privacy ═══════════════════════════════════════════════════════════════════════════════════════════
# Privacy: source metadata (EXIF/GPS, XMP, ICC, text chunks, timestamps) never reaches any output.
#
# Every output may carry only the ironmate header (schema, size, palette, generation parameters) or nothing.

MARKERS = [b'SECRET_ARTIST', b'SECRET_GPS', b'SECRET_XMP', b'SECRET_ICC', b'SECRET_COMMENT', b'SECRET_AUTHOR',
           b'SECRET_ZTXT', b'SECRET_ITXT', b'SECRET_FORGED', b'2001:02:03', b'Exif', b'xmpmeta', b'adobe']
_ALLOWED_CHUNKS = {b'IHDR', b'tEXt', b'IDAT', b'IEND'}
_HEADER_KEYS = {'schema', 'width', 'height', 'colors', 'palette', 'mask', 'effect', 'resampling', 'source', 'fit',
                'quantize', 'restored'}


def _chunk_privacy(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)


def _png_with_metadata(forged_ironmate=False):
    w = h = 8
    raw = b''.join(b'\0' + bytes([(x * 30) % 256, (y * 30) % 256, 90, 255]) * 1 for y in range(h) for x in range(w)
                   for _ in [0] if x == 0) if False else b''.join(
        b'\0' + b''.join(bytes([x * 30, y * 30, 90, 255]) for x in range(w)) for y in range(h))
    exif = b'MM\0*\0\0\0\x08' + b'SECRET_GPS SECRET_ARTIST 2001:02:03'
    chunks = [_chunk_privacy(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)),
              _chunk_privacy(b'tIME', struct.pack('>HBBBBB', 2001, 2, 3, 4, 5, 6)),
              _chunk_privacy(b'iCCP', b'icc\0\0' + zlib.compress(b'SECRET_ICC profile')),
              _chunk_privacy(b'tEXt', b'Author\0SECRET_AUTHOR'),
              _chunk_privacy(b'tEXt', b'Creation Time\x002001:02:03 04:05:06'),
              _chunk_privacy(b'zTXt', b'Comment\0\0' + zlib.compress(b'SECRET_ZTXT')),
              _chunk_privacy(b'iTXt', b'XML:com.adobe.xmp\0\0\0\0\0<x:xmpmeta>SECRET_XMP SECRET_ITXT</x:xmpmeta>'),
              _chunk_privacy(b'eXIf', exif)]
    if forged_ironmate:   # a hostile/foreign ironmate header with extra personal fields
        info = {'schema': 'ironmate-pixel-grid/1', 'width': 8, 'height': 8, 'author': 'SECRET_FORGED',
                'gps': 'SECRET_GPS', 'colors': sorted({'#%02X%02X5AFF' % (x * 30, y * 30)
                                                        for x in range(8) for y in range(8)})}
        chunks.append(_chunk_privacy(b'tEXt', b'ironmate\0' + json.dumps(info).encode()))
    return b'\x89PNG\r\n\x1a\n' + b''.join(chunks) + _chunk_privacy(b'IDAT', zlib.compress(raw)) + _chunk_privacy(b'IEND', b'')


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


def _sources_privacy():
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


def _cli_privacy(mod, *args):
    r = subprocess.run([sys.executable, '-m', mod, *args], cwd=ROOT, capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout


SOURCES = _sources_privacy()


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
        _check(_cli_privacy('grid_tools', 'photo', str(src), '--size', '16', '--to', fmt), f'cli photo {fmt}')
        _check(_cli_privacy('photo_grid', str(src), '--format', fmt), f'photo_grid {fmt}')
        if name.startswith('png'):
            _check(_cli_privacy('grid_tools', 'load', str(src), '--size', '8', '--to', fmt), f'cli load {fmt}')
    _check(_cli_privacy('grid_tools', 'fit', str(src), '--limit-chars', '1000000'), 'cli fit')
    _check(_cli_privacy('grid_tools', 'fit', str(src), '--limit-bytes', '1000000', '--to', 'png'), 'cli fit png')
    _check(_cli_privacy('grid_tools', 'photo', str(src), '--size', '16', '--to', 'base64', '--data-uri'), 'data uri')


def test_ironmate_header_contains_only_size_and_palette_fields():
    art = g.make('cloud', 'C02', 'shadow', 16)
    info = json.loads(dict(_png_chunks(g.encode(art, 'png')))[b'tEXt'].split(b'\0', 1)[1])
    assert set(info) == {'schema', 'width', 'height', 'colors', 'palette', 'mask', 'effect', 'resampling'}
    assert not any(k == b'tEXt' for k, _ in _png_chunks(g.encode(art, 'png', meta=False)))


# ═══ · review fixes ══════════════════════════════════════════════════════════════════════════════════════
# Review fixes on PR #90: PNG tRNS, strict zlib termination, and non-destructive -o output.

def _png_review_fixes(width, height, color, samples, extra=b'', stream=None, depth=8):
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = b''.join(b'\0' + bytes(samples[y * width * channels:(y + 1) * width * channels]) for y in range(height))
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0))
    return SIG + head + extra + _chunk(b'IDAT', zlib.compress(raw) if stream is None else stream) + _chunk(b'IEND', b'')


def _cells_review_fixes(width, height, rows):
    return {(x, y): tuple(rows[y][4 * x:4 * x + 4]) for y in range(height) for x in range(width)}


def _pillow_cells(data):
    Image = pytest.importorskip('PIL.Image')
    img = Image.open(io.BytesIO(data)).convert('RGBA')
    raw = img.tobytes()
    w, h = img.size
    return _cells_review_fixes(w, h, [raw[y * w * 4:(y + 1) * w * 4] for y in range(h)])


def _cases():
    rnd = random.Random(90)
    for _ in range(25):
        w, h = rnd.randint(1, 9), rnd.randint(1, 7)
        gray = [rnd.choice([7, 7, rnd.randrange(256)]) for _ in range(w * h)]
        yield 'gray', w, h, _png_review_fixes(w, h, 0, gray, _chunk(b'tRNS', struct.pack('>H', 7))), {
            (i % w, i // w): (v, v, v, 0 if v == 7 else 255) for i, v in enumerate(gray)}
        key = (10, 20, 30)
        rgb = [rnd.choice([key, key, tuple(rnd.randrange(256) for _ in range(3))]) for _ in range(w * h)]
        yield 'rgb', w, h, _png_review_fixes(w, h, 2, [c for p in rgb for c in p], _chunk(b'tRNS', struct.pack('>3H', *key))), {
            (i % w, i // w): p + ((0,) if p == key else (255,)) for i, p in enumerate(rgb)}


def test_trns_gray_and_rgb_stdlib_matches_expected_and_pillow():
    pil = g._backend('auto', 'PIL') == 'PIL'
    n = 0
    for kind, w, h, data, want in _cases():
        got = _cells_review_fixes(*photo_grid.decode_png(data))
        assert got == want, kind
        if pil:
            assert _pillow_cells(data) == got, kind
        n += 1
    assert n == 50


def test_trns_reaches_the_grid():
    data = _png_review_fixes(2, 1, 2, [10, 20, 30, 200, 0, 0], _chunk(b'tRNS', struct.pack('>3H', 10, 20, 30)))
    art = photo_grid.convert(data, 8, 'contain', 2)
    assert {art['colors'][v] for row in art['pixels'] for v in row} >= {'#00000000'}
    back = g.restore(data, size=2)
    assert g.cells(back) == [['#0A141E00', '#C80000FF']]  # RGB kept, alpha 0 (same as Pillow)


def test_palette_with_trns_via_pillow_matches_rgba_reference():
    Image = pytest.importorskip('PIL.Image')
    img = Image.new('P', (4, 2))
    img.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * 759)
    img.putdata([0, 1, 2, 0, 2, 1, 0, 1])
    buf = io.BytesIO()
    img.save(buf, 'PNG', transparency=bytes([0, 128, 255]))
    w, h, rows = photo_grid.decode_image(buf.getvalue()) if hasattr(photo_grid, 'decode_image') else (None,) * 3
    alpha = {0: 0, 1: 128, 2: 255}
    rgb = {0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255)}
    want = {(i % 4, i // 4): rgb[v] + (alpha[v],) for i, v in enumerate([0, 1, 2, 0, 2, 1, 0, 1])}
    assert _cells_review_fixes(w, h, rows) == want == _pillow_cells(buf.getvalue())
    with pytest.raises(photo_grid.ImageDecodeError, match='color type 3'):
        photo_grid.decode_png(buf.getvalue())   # stdlib: explicit, Pillow fallback handles it


@pytest.mark.parametrize('extra, match', [
    (_chunk(b'tRNS', b'\0\7') * 2, 'once'),
    (_chunk(b'tRNS', b'\0\7\0'), 'length'),
    (_chunk(b'tRNS', b'\1\0'), '8-bit'),
])
def test_invalid_trns_rejected(extra, match):
    with pytest.raises(photo_grid.ImageDecodeError, match=match):
        photo_grid.decode_png(_png_review_fixes(1, 1, 0, [7], extra))


def test_trns_on_alpha_types_and_after_idat_rejected():
    with pytest.raises(photo_grid.ImageDecodeError, match='not allowed'):
        photo_grid.decode_png(_png_review_fixes(1, 1, 6, [1, 2, 3, 4], _chunk(b'tRNS', b'\0\1')))
    good = _png_review_fixes(1, 1, 0, [7])
    late = good[:-12] + _chunk(b'tRNS', b'\0\7') + good[-12:]
    with pytest.raises(photo_grid.ImageDecodeError, match='before IDAT'):
        photo_grid.decode_png(late)


def test_zlib_stream_must_terminate():
    raw = b'\0' + bytes(12) + b'\0' + bytes(12)
    full = zlib.compress(raw)
    cases = {
        'no checksum': full[:-4],             # all rows present, Adler-32 missing
        'half checksum': full[:-2],
        'flush only': (lambda c: c.compress(raw) + c.flush(zlib.Z_SYNC_FLUSH))(zlib.compressobj()),
    }
    for name, stream in cases.items():
        with pytest.raises(photo_grid.ImageDecodeError, match='truncated|length|corrupt'):
            photo_grid.decode_png(_png_review_fixes(3, 2, 6, list(raw.replace(b'\0' + bytes(12), bytes(12))), stream=stream))
    with pytest.raises(photo_grid.ImageDecodeError, match='extra bytes'):
        photo_grid.decode_png(_png_review_fixes(3, 2, 6, [0] * 24, stream=full + zlib.compress(b'')))
    assert photo_grid.decode_png(_png_review_fixes(3, 2, 6, [0] * 24, stream=full))[:2] == (3, 2)


CLIS = [
    ['pixel_grid.py', '--mask', 'cloud', '--format', 'png'],
    ['photo_grid.py', 'SRC', '--size', '8', '--format', 'png'],
    ['grid_png.py', 'JSON'],
    ['grid_svg.py', 'JSON'],
    ['-m', 'grid_tools', 'make', 'cloud'],
]


def _cli_review_fixes(args, tmp_path, out, *extra):
    src = tmp_path / 'src.png'
    src.write_bytes(g.encode(g.make('cloud'), 'png'))
    js = tmp_path / 'g.json'
    js.write_text(g.encode(g.make('cloud'), 'json'))
    args = [str(src) if a == 'SRC' else str(js) if a == 'JSON' else a for a in args]
    return subprocess.run([sys.executable, *args, '-o', str(out), *extra], cwd=ROOT, capture_output=True, timeout=60)


@pytest.mark.parametrize('args', CLIS, ids=lambda a: a[0] if a[0] != '-m' else a[1])
def test_cli_output_does_not_clobber(tmp_path, args):
    out = tmp_path / 'out'
    out.write_bytes(b'keep')
    r = _cli_review_fixes(args, tmp_path, out)
    assert r.returncode == 2 and b'refusing to overwrite' in r.stderr and out.read_bytes() == b'keep'
    target = tmp_path / 'target'
    target.write_bytes(b'precious')
    link = tmp_path / 'link'
    link.symlink_to(target)
    r = _cli_review_fixes(args, tmp_path, link)
    assert r.returncode == 2 and target.read_bytes() == b'precious' and link.is_symlink()
    dangling = tmp_path / 'dangling'
    dangling.symlink_to(tmp_path / 'missing')
    assert _cli_review_fixes(args, tmp_path, dangling).returncode == 2 and not (tmp_path / 'missing').exists()
    r = _cli_review_fixes(args, tmp_path, link, '--force')            # replaces the link, not its target
    assert r.returncode == 0, r.stderr
    assert target.read_bytes() == b'precious' and not link.is_symlink() and link.read_bytes() != b'precious'
    fresh = tmp_path / 'fresh'
    assert _cli_review_fixes(args, tmp_path, fresh).returncode == 0 and fresh.stat().st_size > 0


def test_write_output_api(tmp_path):
    p = tmp_path / 'a'
    write_output(p, b'1')
    with pytest.raises(FileExistsError):
        write_output(p, b'2')
    write_output(p, b'3', force=True)
    assert p.read_bytes() == b'3' and sorted(os.listdir(tmp_path)) == ['a']
    with pytest.raises(IsADirectoryError):
        write_output(tmp_path, b'x', force=True)


# ═══ · pillow min ════════════════════════════════════════════════════════════════════════════════════════
# pillow_min: PNG decode/encode, Image API, and diff helpers vs Pillow reference.

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


# ═══ · pillow min parity ═════════════════════════════════════════════════════════════════════════════════
# pillow_min vs Pillow: seeded randomized parity for the API surface consumers use.
#
# Pillow is a dev-only reference here; pillow_min itself never imports it.

PIL = pytest.importorskip('PIL')
from PIL import Image as PILImage  # noqa: E402
from PIL import ImageChops as PILImageChops  # noqa: E402

SEEDS = range(6)
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
COMBOS = [(1, 0), (2, 0), (4, 0), (8, 0), (16, 0), (8, 2), (16, 2), (1, 3), (2, 3), (4, 3), (8, 3),
          (8, 4), (16, 4), (8, 6), (16, 6)]


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _filter(rows, bpp, rng):
    """Apply random PNG filters (0-4) to raw scanlines, as a real encoder might."""
    out, prev = [], bytes(len(rows[0])) if rows else b''
    for row in rows:
        kind = rng.randrange(5)
        enc = bytearray(len(row))
        for i, v in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = (0, a, b, (a + b) >> 1, pm.paeth(a, b, c))[kind]
            enc[i] = (v - pred) & 255
        out.append(bytes([kind]) + bytes(enc))
        prev = row
    return b''.join(out)


def _rows(w, h, depth, color, rng):
    bits = depth * CHANNELS[color]
    stride = (w * bits + 7) // 8
    rows = []
    for _ in range(h):
        row = bytearray(rng.randrange(256) for _ in range(stride))
        tail = stride * 8 - w * bits
        if tail:
            row[-1] &= (0xFF << tail) & 0xFF
        rows.append(bytes(row))
    return rows, max(1, bits // 8)


def _adam7(w, h, depth, color, rng):
    starts = ((0, 0), (4, 0), (0, 4), (2, 0), (0, 2), (1, 0), (0, 1))
    steps = ((8, 8), (8, 8), (4, 8), (4, 4), (2, 4), (2, 2), (1, 2))
    raw = b''
    for (sx, sy), (ix, iy) in zip(starts, steps):
        pw = 0 if sx >= w else (w - sx + ix - 1) // ix
        ph = 0 if sy >= h else (h - sy + iy - 1) // iy
        if pw and ph:
            rows, bpp = _rows(pw, ph, depth, color, rng)
            raw += _filter(rows, bpp, rng)
    return raw


def random_png(rng, depth, color, interlace=False, with_trns=True):
    w, h = rng.randint(1, 19), rng.randint(1, 13)
    if interlace:
        raw = _adam7(w, h, depth, color, rng)
    else:
        rows, bpp = _rows(w, h, depth, color, rng)
        raw = _filter(rows, bpp, rng)
    extra = b''
    if color == 3:
        entries = rng.randint(1, 1 << depth)  # short palettes are legal; Pillow pads with black
        extra += chunk(b'PLTE', bytes(rng.randrange(256) for _ in range(entries * 3)))
        if with_trns and rng.random() < 0.7:
            extra += chunk(b'tRNS', bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(rng.randint(1, entries))))
    elif color in (0, 2) and with_trns and rng.random() < 0.7:
        top = (1 << depth) - 1
        n = 1 if color == 0 else 3
        # out-of-range keys too: Pillow compares only their low 8 bits
        extra += chunk(b'tRNS', struct.pack(f'>{n}H', *(rng.choice((rng.randint(0, top), rng.randint(0, 65535)))
                                                          for _ in range(n))))
    header = struct.pack('>IIBBBBB', w, h, depth, color, 0, 0, 1 if interlace else 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + extra
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def assert_same_image(ours, ref):
    assert ours.mode == ref.mode
    assert ours.size == ref.size
    assert ours.tobytes() == ref.tobytes()


@pytest.mark.parametrize('seed', SEEDS)
@pytest.mark.parametrize('depth,color', COMBOS)
@pytest.mark.parametrize('interlace', [False, True])
def test_decode_matches_pillow(seed, depth, color, interlace):
    rng = random.Random(seed * 1000 + depth * 10 + color)
    data = random_png(rng, depth, color, interlace)
    with PILImage.open(io.BytesIO(data)) as ref:
        ours = pm.Image.open(io.BytesIO(data))
        assert_same_image(ours, ref)
        assert ours.info.get('transparency') == ref.info.get('transparency')
        for mode in ('RGBA', 'RGB', 'L', 'LA'):
            assert_same_image(ours.convert(mode), ref.convert(mode))


def _pil_apng(rng, n_frames, default_image):
    """RGBA APNG written by Pillow itself (frames cropped to changed regions by its encoder)."""
    w, h = rng.randint(2, 9), rng.randint(2, 7)
    frames = []
    for _ in range(n_frames):
        im = PILImage.new('RGBA', (w, h))
        # partial alpha exercises Pillow's paste-with-mask blending
        im.putdata([tuple(rng.randrange(256) for _ in range(3)) + (rng.choice((0, 255, rng.randrange(256))),)
                    for _ in range(w * h)])
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, 'PNG', save_all=True, append_images=frames[1:], loop=rng.randint(0, 3),
                   duration=[rng.randint(1, 500) for _ in frames], default_image=default_image,
                   disposal=[rng.randint(0, 2) for _ in frames], blend=[rng.randint(0, 1) for _ in frames])
    return buf.getvalue()


def _hand_apng(rng, depth, color, n_frames, default_image, interlace):
    """APNG of any colour type / depth with random sub-region frames, disposal and blending."""
    W, H = rng.randint(1, 11), rng.randint(1, 9)
    out = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, depth, color, 0, 0, int(interlace)))
    if color == 3:
        entries = rng.randint(1, 1 << depth)
        out += chunk(b'PLTE', bytes(rng.randrange(256) for _ in range(entries * 3)))
        out += chunk(b'tRNS', bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(entries)))
    elif color in (0, 2) and rng.random() < 0.5:
        n = 1 if color == 0 else 3
        out += chunk(b'tRNS', struct.pack(f'>{n}H', *(rng.randint(0, (1 << depth) - 1) for _ in range(n))))
    out += chunk(b'acTL', struct.pack('>II', n_frames, rng.randint(0, 3)))
    seq = 0

    def data_for(w, h):
        raw = _adam7(w, h, depth, color, rng) if interlace else _filter(*_rows(w, h, depth, color, rng), rng)
        return zlib.compress(raw)

    if default_image:
        out += chunk(b'IDAT', data_for(W, H))
    for i in range(n_frames):
        if i == 0:
            x, y, w, h = 0, 0, W, H  # the first frame covers the canvas
        else:
            w, h = rng.randint(1, W), rng.randint(1, H)
            x, y = rng.randint(0, W - w), rng.randint(0, H - h)
        out += chunk(b'fcTL', struct.pack('>IIIIIHHBB', seq, w, h, x, y, rng.randint(1, 900),
                                          rng.choice((0, 10, 100, 1000)), rng.randint(0, 2), rng.randint(0, 1)))
        seq += 1
        payload = data_for(w, h)
        if i == 0 and not default_image:
            out += chunk(b'IDAT', payload)
            continue
        cut = rng.randint(0, len(payload))
        for piece in (payload[:cut], payload[cut:]) if cut else (payload,):  # frame data split over fdAT
            out += chunk(b'fdAT', struct.pack('>I', seq) + piece)
            seq += 1
    return out + chunk(b'IEND', b'')


class _PillowCrash(Exception):
    pass


def _pillow_frames(data, index, read_each):
    """Frame ``index`` of a freshly opened Pillow image.

    Pillow's result can depend on whether earlier frames were read: "dispose to previous" is
    captured before the previous frame is lazily loaded. ``read_each`` reads every frame while
    iterating (the usual ``seek(i); convert()`` loop); otherwise it seeks straight to ``index``.
    """
    ref = PILImage.open(io.BytesIO(data))
    try:
        for k in (range(index + 1) if read_each else (index,)):
            ref.seek(k)
            ref.load()
    except (ValueError, TypeError) as exc:
        # Pillow 13 crashes where pillow_min decodes: the OVER-blend mask of 16-bit grayscale
        # ("conversion from I;16 to RGBA"), and frames after the first of an interlaced APNG
        # (its decoderconfig grows by one interlace flag per frame).
        assert 'I;16' in str(exc) or 'arguments' in str(exc), exc
        raise _PillowCrash() from exc
    return ref


def _same_frame(ours, ref):
    assert ours.tell() == ref.tell()
    assert_same_image(ours, ref)
    assert ours.convert('RGBA').tobytes() == ref.convert('RGBA').tobytes()
    for key in ('loop', 'duration', 'disposal', 'blend', 'bbox', 'default_image', 'transparency'):
        assert ours.info.get(key) == ref.info.get(key), key


def _assert_frames_match(data):
    with PILImage.open(io.BytesIO(data)) as ref:
        n_frames, animated = ref.n_frames, ref.is_animated
    assert pm.Image.open(data).n_frames == n_frames
    assert pm.Image.open(data).is_animated == animated
    walked = pm.Image.open(data)
    expected = []
    for i in range(n_frames):
        walked.seek(i)  # path A: read every frame while iterating
        direct = pm.Image.open(data)
        direct.seek(i)  # path B: seek straight to frame i
        try:
            ref_a = _pillow_frames(data, i, read_each=True)
            ref_b = _pillow_frames(data, i, read_each=False)
        except _PillowCrash:
            walked.tobytes()
            direct.tobytes()
            break
        _same_frame(walked, ref_a)
        _same_frame(direct, ref_b)
        expected.append(ref_a.convert('RGBA').tobytes())
    else:
        # rewinding replays the frames without reading them, i.e. path B
        walked.seek(0)
        _same_frame(walked, _pillow_frames(data, 0, read_each=False))
        walked.seek(n_frames - 1)
        _same_frame(walked, _pillow_frames(data, n_frames - 1, read_each=False))
        assert [f.tobytes() for f in pm.iter_apng_frames(data)] == expected


@pytest.mark.parametrize('seed', range(10))
@pytest.mark.parametrize('default_image', [False, True])
def test_apng_written_by_pillow_matches(seed, default_image):
    rng = random.Random(seed * 2 + default_image)
    _assert_frames_match(_pil_apng(rng, rng.randint(2, 5), default_image))


@pytest.mark.parametrize('seed', range(4))
@pytest.mark.parametrize('depth,color', COMBOS)
@pytest.mark.parametrize('default_image', [False, True])
@pytest.mark.parametrize('interlace', [False, True])
def test_apng_any_colour_type_matches(seed, depth, color, default_image, interlace):
    rng = random.Random(hash((seed, depth, color, default_image, interlace)) & 0xFFFFFFFF)
    _assert_frames_match(_hand_apng(rng, depth, color, rng.randint(2, 5), default_image, interlace))


def _random_image(rng, mode, size):
    w, h = size
    n = w * h * {'L': 1, 'LA': 2, 'RGB': 3, 'RGBA': 4}[mode]
    data = bytes(rng.choice((0, 0, 255, rng.randrange(256))) for _ in range(n))
    return pm.Image(mode, size, data), PILImage.frombytes(mode, size, data)


@pytest.mark.parametrize('seed', SEEDS)
@pytest.mark.parametrize('mode', ['L', 'LA', 'RGB', 'RGBA'])
def test_image_operations_match_pillow(seed, mode):
    rng = random.Random(seed + 7 * len(mode))
    size = (rng.randint(1, 17), rng.randint(1, 11))
    a, ra = _random_image(rng, mode, size)
    b, rb = _random_image(rng, mode, size)
    assert_same_image(pm.ImageChops.difference(a, b), PILImageChops.difference(ra, rb))
    assert_same_image(pm.ImageChops.lighter(a, b), PILImageChops.lighter(ra, rb))
    assert_same_image(pm.ImageChops.darker(a, b), PILImageChops.darker(ra, rb))
    for ours, ref in zip(a.split(), ra.split()):
        assert_same_image(ours, ref)
    assert a.getextrema() == ra.getextrema()
    assert a.histogram() == ra.histogram()
    assert a.getbbox() == ra.getbbox()
    assert a.getbbox(alpha_only=False) == ra.getbbox(alpha_only=False)
    threshold = rng.randrange(256)
    assert_same_image(a.point(lambda v: 255 if v > threshold else 0),
                      ra.point(lambda v: 255 if v > threshold else 0))
    assert_same_image(a.point(lambda v: v * 0.7 + 3.5), ra.point(lambda v: v * 0.7 + 3.5))
    box = (rng.randint(-3, size[0]), rng.randint(-3, size[1]), 0, 0)
    box = (box[0], box[1], box[0] + rng.randint(0, 8), box[1] + rng.randint(0, 8))
    assert_same_image(a.crop(box), ra.crop(box))
    for target in ('L', 'LA', 'RGB', 'RGBA'):
        assert_same_image(a.convert(target), ra.convert(target))
    x, y = rng.randrange(size[0]), rng.randrange(size[1])
    assert a.getpixel((x, y)) == ra.getpixel((x, y))
    value = b.getpixel((x, y))
    a.putpixel((x, y), value)
    ra.putpixel((x, y), value)
    assert_same_image(a, ra)
    a.putpixel((-1, -1), value)
    ra.putpixel((-1, -1), value)
    assert_same_image(a, ra)
    assert (a.width, a.height) == (ra.width, ra.height)


def test_image_diff_pipeline_matches_pillow():
    """The exact call chain of browser-test-kit scripts/image_diff.py compare()."""
    rng = random.Random(5)
    for _ in range(25):
        size = (rng.randint(1, 30), rng.randint(1, 20))
        a, ra = _random_image(rng, 'RGBA', size)
        b, rb = _random_image(rng, 'RGBA', size)
        tolerance = rng.randrange(256)
        for mod, x, y in ((pm, a, b), (None, ra, rb)):
            chops = pm.ImageChops if mod else PILImageChops
            diff = chops.difference(x, y)
            bands = diff.split()
            max_band = bands[0]
            for band in bands[1:]:
                max_band = chops.lighter(max_band, band)
            mask = max_band.point(lambda value: 255 if value > tolerance else 0, mode='L')
            result = (mask.histogram()[255], mask.getbbox(), max(hi for _lo, hi in diff.getextrema()),
                      mask.width * mask.height)
            if mod:
                ours = result
            else:
                assert ours == result


@pytest.mark.parametrize('seed', SEEDS)
def test_constructors_and_save_roundtrip(seed, tmp_path):
    rng = random.Random(seed)
    for mode, color in (('RGB', 5), ('RGBA', 0x01020304), ('RGBA', (1, 2, 3)), ('RGBA', None), ('L', 300),
                        ('LA', (1, 2)), ('P', 3), ('RGB', (9, 8, 7))):
        args = (mode, (3, 2)) if color is None else (mode, (3, 2), color)
        assert_same_image(pm.Image.new(*args), PILImage.new(*args))
    for mode in ('L', 'LA', 'RGB', 'RGBA'):
        bands = {'L': 1, 'LA': 2, 'RGB': 3, 'RGBA': 4}[mode]
        values = [rng.randrange(-20, 300) if bands == 1 else tuple(rng.randrange(256) for _ in range(bands))
                  for _ in range(12)]
        ours, ref = pm.Image.new(mode, (4, 3)), PILImage.new(mode, (4, 3))
        ours.putdata(values)
        ref.putdata(values)
        assert_same_image(ours, ref)
        path = tmp_path / f'{mode}.png'
        ours.save(path)
        with PILImage.open(path) as back:
            assert_same_image(ours, back)  # pillow_min writes, Pillow reads
        buf = io.BytesIO()
        ref.save(buf, 'PNG')
        assert_same_image(pm.Image.open(io.BytesIO(buf.getvalue())), ref)  # Pillow writes, pillow_min reads
    palette = [rng.randrange(256) for _ in range(12)]
    for bits in (1, 2, 4, 8):
        for transparency in (0, 2, bytes([255, 128, 0])):
            ours, ref = pm.Image.new('P', (5, 2)), PILImage.new('P', (5, 2))
            idx = [rng.randrange(min(4, 1 << bits)) for _ in range(10)]
            for im in (ours, ref):
                im.putdata(idx)
                im.putpalette(palette)
            path = tmp_path / f'p{bits}.png'
            ours.save(path, bits=bits, transparency=transparency)
            with PILImage.open(path) as back:
                assert back.convert('RGBA').tobytes() == ref.convert('RGBA').tobytes() if transparency is None else True
                expected = io.BytesIO()
                ref.save(expected, 'PNG', bits=bits, transparency=transparency)
                with PILImage.open(io.BytesIO(expected.getvalue())) as want:
                    assert back.convert('RGBA').tobytes() == want.convert('RGBA').tobytes()
                    assert_same_image(pm.Image.open(expected.getvalue()).convert('RGBA'), want.convert('RGBA'))


def test_limits_follow_pillow(monkeypatch):
    data = random_png(random.Random(0), 8, 2, with_trns=False)
    monkeypatch.setattr(pm, 'MAX_IMAGE_PIXELS', 4)
    w, h = struct.unpack('>II', data[16:24])
    if w * h > 8:
        with pytest.raises(pm.DecompressionBombError):
            pm.Image.open(data)
    monkeypatch.setattr(pm, 'MAX_IMAGE_PIXELS', None)
    pm.Image.open(data)  # no limit, as with PIL.Image.MAX_IMAGE_PIXELS = None


def test_tall_screenshot_beyond_old_4096_limit():
    im = PILImage.new('RGB', (64, 5000), (1, 2, 3))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    assert_same_image(pm.Image.open(buf.getvalue()), im)


def test_errors_are_value_and_os_errors():
    for bad in (b'GIF89a....', b'\x89PNG\r\n\x1a\n' + b'\0' * 4):
        with pytest.raises(OSError):
            pm.Image.open(bad)
        with pytest.raises(ValueError):
            pm.Image.open(bad)


def test_non_png_save_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        pm.Image.new('RGB', (1, 1)).save(tmp_path / 'x.jpg')
    with pytest.raises(ValueError):
        pm.Image.new('RGB', (1, 1)).save(io.BytesIO(), 'JPEG')
