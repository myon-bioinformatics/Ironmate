"""Downscale / size estimator for PNG and Base64 payloads (stdlib; Pillow optional). Python 3.11+.

    python -c "import size_estimate as s; print(s.estimate(width=1024, height=768, nbytes=900000, limit_chars=200000))"
    python -m grid_tools estimate photo.png --limit-chars 100000 --data-uri --verify

Output PNGs are modelled as 8-bit RGBA written by grid_png (filter 0, zlib level 9), the format
grid_tools produces. Without ``verify`` the size is an estimate with explicit bounds and a
confidence level; ``verify`` encodes the candidate and reports the actual size.
"""
from __future__ import annotations
import base64, binascii, math, struct, zlib
from fractions import Fraction

__all__ = ['CANDIDATES', 'DATA_URI_PREFIX', 'base64_chars', 'bytes_for_chars', 'inspect', 'estimate']
CANDIDATES = tuple(Fraction(f) for f in ('1', '5/6', '4/5', '3/4', '2/3', '3/5', '1/2', '2/5', '1/3', '1/4',
                                          '1/5', '1/6', '1/8', '1/10', '1/12', '1/16', '1/24', '1/32', '1/64'))
DATA_URI_PREFIX = len('data:image/png;base64,')
PNG_OVERHEAD = 8 + 25 + 12 + 12  # signature, IHDR, IDAT and IEND framing
_ANALYZE_LIMIT = 2048 * 2048     # pixel statistics above this are skipped (signal reported)


def base64_chars(nbytes, data_uri=False):
    """Exact Base64 length (with = padding) for ``nbytes`` bytes."""
    return 4 * math.ceil(nbytes / 3) + (DATA_URI_PREFIX if data_uri else 0)


def bytes_for_chars(chars, data_uri=False):
    """Largest byte count whose Base64 fits in ``chars`` characters."""
    return max(0, (chars - (DATA_URI_PREFIX if data_uri else 0)) // 4 * 3)


# --- header signals -------------------------------------------------------------------------
def _png_signals(data):
    out, pos, idat, other = {'format': 'png'}, 8, 0, 0
    while pos + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR' and length == 13:
            w, h, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', body)
            out.update(width=w, height=h, bit_depth=depth, color_type=color, interlaced=bool(interlace))
        elif kind == b'PLTE':
            out['palette_size'] = length // 3
        elif kind == b'tRNS':
            out['trns'] = True
        elif kind == b'tEXt' and body.startswith(b'ironmate\x00'):
            out['ironmate_meta'] = True
        if kind == b'IDAT':
            idat += length
        else:
            other += 12 + length
        pos += 12 + length
        if kind == b'IEND':
            break
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(out.get('color_type'), 4)
    if 'width' in out:
        raw = out['height'] * (1 + math.ceil(out['width'] * channels * out['bit_depth'] / 8))
        out.update(idat_bytes=idat, raw_bytes=raw, compression_ratio=round(idat / raw, 4) if raw else None,
                   chunk_overhead_bytes=other + 8)
    return out


def _jpeg_signals(data):
    out, i = {'format': 'jpeg'}, 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        seg = data[i + 4:i + 2 + length]
        if marker == 0xE1 and seg.startswith(b'Exif\0\0'):
            out['exif_bytes'] = length
        elif marker == 0xDB and len(seg) >= 65 and seg[0] == 0 and 'quality_estimate' not in out:
            # libjpeg-style quality from the luminance table average vs the standard table (avg 57.6)
            avg = sum(seg[1:65]) / 64
            scale = avg / 57.6250 * 100
            out['quality_estimate'] = max(1, min(100, round(100 - scale / 2 if scale <= 100 else 5000 / scale)))
        elif marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w, n = struct.unpack('>HHB', seg[1:6])
            factors = [seg[7 + 3 * c] for c in range(n)]
            out.update(width=w, height=h, components=n, progressive=marker in (0xC2, 0xC6, 0xCA, 0xCE))
            if n == 3:
                out['subsampling'] = {0x11: '4:4:4', 0x21: '4:2:2', 0x22: '4:2:0', 0x12: '4:4:0'}.get(factors[0], hex(factors[0]))
        elif marker == 0xDA:
            break
        i += 2 + length
    return out


def _webp_signals(data):
    out = {'format': 'webp'}
    kind = data[12:16]
    if kind == b'VP8 ' and len(data) >= 30:
        w, h = struct.unpack('<HH', data[26:30])
        out.update(width=w & 0x3FFF, height=h & 0x3FFF, lossless=False, alpha=False)
    elif kind == b'VP8L' and len(data) >= 25:
        b = int.from_bytes(data[21:25], 'little')
        out.update(width=(b & 0x3FFF) + 1, height=((b >> 14) & 0x3FFF) + 1, lossless=True, alpha=bool(b >> 28 & 1))
    elif kind == b'VP8X' and len(data) >= 30:
        out.update(width=int.from_bytes(data[24:27], 'little') + 1, height=int.from_bytes(data[27:30], 'little') + 1,
                   alpha=bool(data[20] & 0x10), animated=bool(data[20] & 0x02))
    return out


def _pixels(data, kind):
    import photo_grid
    if kind == 'png':
        try:
            return photo_grid.decode_png(data)
        except ValueError:
            pass
    return photo_grid.decode_pillow(data, photo_grid.MAX_PIXELS, ('PNG', 'JPEG', 'WEBP'))


def inspect(source):
    """Header + pixel signals of image bytes, Base64 or a data URI."""
    import photo_grid
    text_len = None
    if isinstance(source, str) or not photo_grid._sniff(source):
        text = source if isinstance(source, str) else source.decode('ascii', 'replace')
        text_len = len(''.join(text.split()))
        source = photo_grid.decode_base64(source)
    kind = photo_grid._sniff(source)
    sig = {'png': _png_signals, 'jpeg': _jpeg_signals, 'webp': _webp_signals}.get(kind)
    if sig is None:
        raise ValueError(f'cannot estimate {kind or "unknown"} input; use PNG, JPEG or WebP')
    out = sig(source)
    out['bytes'] = len(source)
    out['base64_chars'] = text_len if text_len is not None else base64_chars(len(source))
    try:
        w, h, rows = _pixels(source, kind)
    except (ImportError, ValueError) as exc:
        out['pixels'] = f'not analysed: {exc}'
        return out, None
    out.update(width=w, height=h)
    if w * h > _ANALYZE_LIMIT:
        out['pixels'] = f'not analysed: over {_ANALYZE_LIMIT} pixels'
        return out, (w, h, rows)
    px = [row[i:i + 4] for row in rows for i in range(0, len(row), 4)]
    counts = {}
    for p in px:
        counts[p] = counts.get(p, 0) + 1
    alphas = {p[3] for p in counts}
    runs = sum(1 for row in rows for i in range(0, len(row), 4) if i == 0 or row[i:i + 4] != row[i - 4:i])
    entropy = -sum(c / len(px) * math.log2(c / len(px)) for c in counts.values())
    import grid_tools
    grid = [[row[i:i + 4] for i in range(0, len(row), 4)] for row in rows]
    out.update(unique_colors=len(counts), alpha='none' if alphas == {255} else
               'binary' if alphas <= {0, 255} else 'partial', mean_run=round(w * h / runs, 2),
               entropy_bits=round(entropy, 3), cell_scale=grid_tools._runs_gcd(grid, 'stdlib'))
    return out, (w, h, rows)


# --- size model -----------------------------------------------------------------------------
def _encode_rgba(w, h, rows):
    raw = b''.join(b'\0' + r for r in rows)
    return PNG_OVERHEAD + len(zlib.compress(raw, 9))


def _nearest(w, h, rows, nw, nh):
    xs = [(2 * i + 1) * w // (2 * nw) for i in range(nw)]
    return [b''.join(rows[(2 * j + 1) * h // (2 * nh)][4 * x:4 * x + 4] for x in xs) for j in range(nh)]


def _size(dim, r):
    return max(1, round(dim * r))


def estimate(source=None, *, width=None, height=None, nbytes=None, chars=None, limit_bytes=None,
             limit_chars=None, data_uri=False, verify=False):
    """Recommend a reduction so the output PNG (or its Base64) fits a limit.

    Give ``source`` (bytes, Base64 or data URI) for full signals, or just ``width``/``height`` with
    ``nbytes`` or ``chars``. ``limit_chars`` counts the ``data:image/png;base64,`` prefix when
    ``data_uri`` is true. Returns a JSON-able dict with signals used, bounds and confidence.
    """
    signals, pixels, used = {}, None, []
    if source is not None:
        signals, pixels = inspect(source)
        used.append(f"{signals['format']} header")
        if 'unique_colors' in signals:
            used.append('pixel statistics')
        width, height = signals['width'], signals['height']
        nbytes = signals['bytes']
    if not width or not height:
        raise ValueError('need width and height (or an image)')
    if nbytes is None and chars is not None:
        nbytes = bytes_for_chars(chars)
        used.append('bytes from Base64 length')
    if (limit_bytes is None) == (limit_chars is None):
        raise ValueError('give exactly one of limit_bytes or limit_chars')
    target = limit_bytes if limit_bytes is not None else bytes_for_chars(limit_chars, data_uri)
    raw_full = height * (1 + 4 * width)

    # Content cost at scale 1: our own RGBA encoding when pixels are available (measured),
    # else the source's compressed size (other encoders/filters differ, so lower confidence).
    fmt = signals.get('format')
    cell = signals.get('cell_scale', 1)
    if pixels and width * height <= _ANALYZE_LIMIT:
        base, conf = _encode_rgba(*pixels) - PNG_OVERHEAD, 'medium'
        used.append('measured RGBA re-encode at full size')
    elif fmt == 'png' and signals.get('idat_bytes'):
        factor = {6: 1.0, 2: 1.75, 4: 1.5, 0: 2.0, 3: 1.5}.get(signals.get('color_type'), 2.0)
        base, conf = signals['idat_bytes'] * factor, 'low'
        used.append(f'PNG IDAT size x{factor} for colour type {signals.get("color_type")}')
    elif nbytes and fmt in ('jpeg', 'webp'):
        base, conf = min(raw_full, nbytes * 4), 'low'
        used.append('lossy source size x4 (photos usually grow when stored as PNG)')
    elif nbytes:
        base, conf = nbytes, 'low'
        used.append('input byte size only')
    else:
        raise ValueError('need nbytes, chars or an image')
    if cell > 1:
        used.append(f'cell scale {cell} (block-uniform pixel art)')

    def model(r):
        w2, h2 = _size(width, r), _size(height, r)
        stored = h2 * (1 + 4 * w2)
        upper = PNG_OVERHEAD + stored + 5 * math.ceil(stored / 65535) + 6   # hard: deflate stored blocks
        # Photos scale with pixel count (r^2). Block art keeps detail until blocks reach 1 px (~r).
        point = base * (r * min(1.0, math.sqrt(cell * r)) if cell > 1 else r * r)
        point = PNG_OVERHEAD + int(min(point, upper - PNG_OVERHEAD))
        low = PNG_OVERHEAD + int(min(point - PNG_OVERHEAD, upper) * 0.5)          # heuristic
        return w2, h2, point, low, upper

    def lossless(r):
        k = 1 / r
        return bool(cell > 1 and k == int(k) and cell % int(k) == 0) or r == 1

    def option(r):
        w2, h2, point, low, upper = model(r)
        out = {'ratio': str(r), 'width': w2, 'height': h2, 'est_bytes': point,
               'typical_low_bytes': low, 'upper_bytes': upper,
               'est_chars': base64_chars(point, data_uri), 'nearest_lossless': lossless(r)}
        if verify and pixels:
            actual = _encode_rgba(w2, h2, _nearest(*pixels, w2, h2))
            out.update(actual_bytes=actual, actual_chars=base64_chars(actual, data_uri))
        return out

    def fits(o):
        return o.get('actual_bytes', o['est_bytes']) <= target

    options = [option(r) for r in CANDIDATES if _size(width, r) >= 1 and (r == 1 or round(width * r) >= 1)]
    rec = next((o for o in options if fits(o)), None)
    integer = next((o for o in options if Fraction(o['ratio']).numerator == 1 and fits(o)), None)
    lossless_fit = next((o for o in options if o['nearest_lossless'] and fits(o)), None)
    if verify and pixels:
        conf = 'verified'
    result = {
        'target_bytes': target, 'target_chars': base64_chars(target, data_uri) if limit_chars is None else limit_chars,
        'input': {k: v for k, v in signals.items()} or {'width': width, 'height': height, 'bytes': nbytes},
        'signals_used': used, 'confidence': conf,
        'raw_rgba_upper_bytes': PNG_OVERHEAD + raw_full + 5 * math.ceil(raw_full / 65535) + 6,
        'fits_now': bool(nbytes is not None and nbytes <= target),
        'achievable': rec is not None, 'recommended': rec, 'integer_option': integer,
        'lossless_option': lossless_fit,
        'smallest': options[-1], 'options': options,
    }
    if rec is None:
        result['note'] = 'even the smallest candidate exceeds the limit'
    elif cell > 1 and not rec['nearest_lossless']:
        result['note'] = f'pixel art with cell scale {cell}: ratios 1/k with k dividing {cell} are lossless'
    return result
