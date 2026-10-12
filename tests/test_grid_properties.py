"""Randomized property, mutation and adversarial-input tests for the grid_tools conditions table.

Seeds are fixed (reproducible). The oracle is an independent per-pixel expansion of the artifact;
stdlib, Pillow and numpy paths are each compared against it as (x, y, RGBA) cells, not only bytes.
"""
import base64, json, random, struct, zlib

import pytest

import grid_png
import grid_tools as g
import photo_grid

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
