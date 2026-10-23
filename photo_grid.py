"""Base64 image or image file -> indexed pixel grid (photo conversion, first milestone). Python 3.11+.

Pipeline: strict Base64/data URI decode -> image bytes -> decoder adapter
(bytes -> width, height, RGBA rows) -> crop/fit -> area-average downscale ->
deterministic quantization -> ``ironmate-pixel-grid/1`` JSON.
PNG (8-bit gray/gray+alpha/RGB/RGBA, non-interlaced) is decoded with stdlib only.
JPEG/WebP (and other PNG variants) use Pillow if installed; Pillow is never required or imported eagerly.
SVG, GIF, BMP, TIFF, ICO and HEIC/AVIF input is rejected with a clear error.
"""
from __future__ import annotations
import argparse, base64, binascii, json, re, struct, sys, zlib

from pixel_grid import PALETTES, SIZES
from pillow_min import paeth as _paeth, unfilter_scanlines as _unfilter

__all__ = ['FITS', 'MAX_BYTES', 'MAX_PIXELS', 'max_base64_chars', 'ImageDecodeError', 'decode_base64',
           'decode_png', 'decode_pillow', 'decode_image', 'convert', 'main']
FITS = ('crop', 'contain')
MAX_BYTES = 32 * 1024 * 1024  # = flutter_navigation_basic PhotoImportLimits.maxInputBytes
MAX_PIXELS = 4096 * 4096
_DATA_URI = re.compile(r'data:([\w.+-]+/[\w.+-]+)?((?:;[\w.+-]+=[\w.+-]+)*);base64,', re.ASCII | re.IGNORECASE)
_MIME_SIGNATURES = {'image/png': (b'\x89PNG\r\n\x1a\n',), 'image/jpeg': (b'\xff\xd8\xff',),
                    'image/jpg': (b'\xff\xd8\xff',), 'image/webp': (b'RIFF',)}
_BASE64 = re.compile(r'[A-Za-z0-9+/]*={0,2}', re.ASCII)
_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_PNG_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}  # gray, RGB, gray+alpha, RGBA


_UNSUPPORTED = {'gif': 'GIF', 'bmp': 'BMP', 'tiff': 'TIFF', 'ico': 'ICO', 'heif': 'HEIC/HEIF/AVIF'}


class ImageDecodeError(ValueError):
    """Input bytes could not be decoded into RGBA pixels."""


def _to_rgba(line, channels, key=None):
    """Expand one unfiltered row to RGBA; ``key`` is the tRNS color (gray or RGB) that becomes alpha 0."""
    if channels == 4:
        return bytes(line)
    out = bytearray()
    for i in range(0, len(line), channels):
        if channels == 3:
            rgb = bytes(line[i:i + 3])
            out += rgb + (b'\x00' if rgb == key else b'\xff')
        elif channels == 2:
            out += bytes((line[i], line[i], line[i], line[i + 1]))
        else:
            out += bytes((line[i], line[i], line[i], 0 if key == bytes((line[i],)) else 255))
    return bytes(out)


def _sniff(data):
    """Image kind from magic bytes, or None (e.g. Base64 text)."""
    head = data[:64]
    if head.startswith(_PNG_SIGNATURE):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if head[:2] == b'BM':
        return 'bmp'
    if head[:4] in (b'II*\x00', b'MM\x00*'):
        return 'tiff'
    if head[:4] == b'\x00\x00\x01\x00':
        return 'ico'
    if head[4:8] == b'ftyp':
        return 'heif'
    text = data[:1024].lstrip(b'\xef\xbb\xbf \t\r\n').lower()
    if text.startswith(b'<') and (b'<svg' in text or text.startswith(b'<?xml')):
        return 'svg'
    return None


def _check_size(width, height, max_pixels):
    if width <= 0 or height <= 0:
        raise ImageDecodeError('image has zero width or height')
    if width * height > max_pixels:
        raise ImageDecodeError(f'image has {width * height} pixels; limit is {max_pixels}')


def _box_weights(start, length, cells, limit):
    """Per output cell, the overlapping source indices and their area weights."""
    step = length / cells
    table = []
    for c in range(cells):
        a, b = start + c * step, start + (c + 1) * step
        items, i = [], int(a)
        while i < b and i < limit:
            w = min(b, i + 1) - max(a, i)
            if w > 1e-12:
                items.append((i, w))
            i += 1
        table.append(items)
    return table


def _downscale(width, height, rows, size, fit):
    """Area-average into a size x size canvas; returns RGBA tuples or None (outside image)."""
    if fit == 'crop':
        side = min(width, height)
        xs = _box_weights((width - side) / 2, side, size, width)
        ys = _box_weights((height - side) / 2, side, size, height)
        left = top = 0
        cw = ch = size
    else:
        scale = min(size / width, size / height)
        cw, ch = max(1, round(width * scale)), max(1, round(height * scale))
        left, top = (size - cw) // 2, (size - ch) // 2
        xs, ys = _box_weights(0, width, cw, width), _box_weights(0, height, ch, height)
    canvas = [[None] * size for _ in range(size)]
    for cy, yitems in enumerate(ys):
        for cx, xitems in enumerate(xs):
            total = r = g = b = a = 0.0
            for sy, wy in yitems:
                row = rows[sy]
                for sx, wx in xitems:
                    w = wy * wx
                    o = sx * 4
                    alpha = row[o + 3] * w  # premultiplied: transparent pixels add no color
                    r += row[o] * alpha
                    g += row[o + 1] * alpha
                    b += row[o + 2] * alpha
                    a += alpha
                    total += w
            if a:
                rgb = (round(r / a), round(g / a), round(b / a))
            else:
                rgb = (0, 0, 0)
            canvas[top + cy][left + cx] = rgb + (round(a / total),)
    return canvas


def _median_cut(colors, count):
    """Deterministic median cut over (rgb, weight) pairs; returns <= count RGB tuples."""
    boxes = [sorted(colors)]
    while len(boxes) < count:
        best = None
        for index, box in enumerate(boxes):
            if len(box) < 2:
                continue
            spans = [max(c[0][k] for c in box) - min(c[0][k] for c in box) for k in range(3)]
            span = max(spans)
            if span and (best is None or span > best[0]):
                best = (span, index, spans.index(span))
        if best is None:
            break
        _, index, channel = best
        box = sorted(boxes[index], key=lambda c: (c[0][channel], c[0]))
        half, acc, cut = sum(w for _, w in box) / 2, 0, 1
        for i, (_, w) in enumerate(box[:-1]):
            acc += w
            cut = i + 1
            if acc >= half:
                break
        boxes[index:index + 1] = [box[:cut], box[cut:]]
    result = []
    for box in boxes:
        weight = sum(w for _, w in box)
        result.append(tuple(round(sum(c[k] * w for c, w in box) / weight) for k in range(3)))
    return sorted(set(result))


def _nearest(rgb, palette):
    return min(range(len(palette)),
               key=lambda i: (sum((rgb[k] - palette[i][k]) ** 2 for k in range(3)), i))


def _hex_rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def max_base64_chars(max_bytes=MAX_BYTES):
    """Most Base64 characters (padding included) that can decode to ``max_bytes`` bytes."""
    return 4 * ((max_bytes + 2) // 3)


def decode_base64(text, max_bytes=MAX_BYTES):
    """Strictly decode raw Base64 or a ``data:...;base64,`` URI into the original bytes."""
    if isinstance(text, bytes):
        try:
            text = text.decode('ascii')
        except UnicodeDecodeError:
            raise ValueError('Base64 input must be ASCII') from None
    text = text.lstrip('\ufeff').strip()  # tolerate a UTF-8 BOM from Windows editors
    match = _DATA_URI.match(text)
    mime = (match.group(1) or '').lower() if match else ''
    if mime and mime not in _MIME_SIGNATURES:
        raise ValueError(f'unsupported data URI type {mime!r}; use image/png, image/jpeg or image/webp')
    if match:
        text = text[match.end():]
    elif text[:5].lower() == 'data:':
        raise ValueError('data URI must be base64-encoded (data:<type>;base64,...)')
    text = ''.join(text.split())
    if not text:
        raise ValueError('Base64 input is empty')
    if len(text) > max_base64_chars(max_bytes):  # same early check as Dart Base64ImageBridge
        raise ValueError(f'decoded input exceeds {max_bytes} bytes')
    if len(text) % 4 or not _BASE64.fullmatch(text):
        raise ValueError('invalid Base64 input (standard alphabet A-Z a-z 0-9 + / with = padding; '
                         'URL-safe -_ and unpadded input are rejected)')
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('invalid Base64 input') from None
    if len(data) > max_bytes:
        raise ValueError(f'decoded input exceeds {max_bytes} bytes')
    if mime and not data.startswith(_MIME_SIGNATURES[mime]):
        raise ValueError(f'data URI says {mime} but the decoded bytes are not that format')
    if mime == 'image/webp' and data[8:12] != b'WEBP':
        raise ValueError('data URI says image/webp but the decoded bytes are not that format')
    return data


def decode_png(data, max_pixels=MAX_PIXELS):
    """Stdlib-only PNG adapter: bytes -> (width, height, RGBA rows as bytes)."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ImageDecodeError('not a PNG file')
    pos, header, idat, trns = 8, None, [], None
    while True:
        if pos + 8 > len(data):
            raise ImageDecodeError('truncated PNG (missing IEND)')
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise ImageDecodeError('truncated PNG chunk')
        if zlib.crc32(kind + body) != struct.unpack('>I', crc)[0]:
            raise ImageDecodeError(f'PNG chunk {kind!r} has a bad CRC')
        pos += 12 + length
        if header is None and kind != b'IHDR':
            raise ImageDecodeError('PNG must start with IHDR')
        if kind == b'IHDR':
            if length != 13:
                raise ImageDecodeError('invalid IHDR')
            header = struct.unpack('>IIBBBBB', body)
            width, height, depth, color, compression, filtering, interlace = header
            if depth != 8 or color not in _PNG_CHANNELS:
                raise ImageDecodeError(
                    f'unsupported PNG (bit depth {depth}, color type {color}); stdlib decoder '
                    'supports 8-bit gray, gray+alpha, RGB and RGBA only. Install Pillow for others')
            if interlace:
                raise ImageDecodeError('interlaced PNG is not supported by the stdlib decoder')
            if compression or filtering:
                raise ImageDecodeError('invalid PNG compression/filter method')
            _check_size(width, height, max_pixels)
        elif kind == b'tRNS':
            # PNG spec 11.3.2.1: gray uses one 16-bit sample, RGB three; alpha types must not carry it.
            if idat or trns is not None:
                raise ImageDecodeError('tRNS must appear once, before IDAT')
            if header[3] not in (0, 2):
                raise ImageDecodeError(f'tRNS is not allowed for PNG color type {header[3]}')
            if length != (2 if header[3] == 0 else 6):
                raise ImageDecodeError('invalid tRNS length')
            samples = struct.unpack(f'>{length // 2}H', body)
            if any(v > 255 for v in samples):
                raise ImageDecodeError('tRNS value exceeds the 8-bit sample range')
            trns = bytes(samples)
        elif kind == b'IDAT':
            idat.append(body)
        elif kind == b'IEND':
            if pos != len(data):
                raise ImageDecodeError(f'{len(data) - pos} bytes of trailing data after PNG IEND')
            break
    if not idat:
        raise ImageDecodeError('PNG has no image data')
    channels = _PNG_CHANNELS[header[3]]
    expected = header[1] * (header[0] * channels + 1)
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(b''.join(idat), expected + 1)
        if len(raw) == expected and not inflater.eof:
            raw += inflater.decompress(inflater.unconsumed_tail, 1)
    except zlib.error:
        raise ImageDecodeError('PNG image data is corrupt') from None
    if len(raw) != expected:
        raise ImageDecodeError('PNG image data has unexpected length')
    if not inflater.eof:
        raise ImageDecodeError('PNG image data is truncated (zlib stream not terminated)')
    if inflater.unused_data:
        raise ImageDecodeError('PNG image data has extra bytes after the zlib stream')
    rows = _unfilter(raw, header[0], header[1], channels)
    return header[0], header[1], [_to_rgba(line, channels, trns) for line in rows]


def decode_pillow(data, max_pixels=MAX_PIXELS, formats=('JPEG', 'WEBP', 'PNG')):
    """Optional Pillow adapter (JPEG/WebP, and PNG variants): bytes -> (width, height, RGBA rows).

    Only ``formats`` are opened; animated images use their first frame.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise ImageDecodeError('this image format needs the optional Pillow package '
                               '(pip install Pillow); only PNG works without it') from None
    import io
    try:
        with Image.open(io.BytesIO(data), formats=list(formats)) as image:
            _check_size(image.width, image.height, max_pixels)
            image = ImageOps.exif_transpose(image).convert('RGBA')
    except ImageDecodeError:
        raise
    except Exception as exc:  # Pillow raises several types for unreadable input
        raise ImageDecodeError('unrecognized or corrupt image (PNG with stdlib; JPEG/WebP with Pillow; '
                               f'Pillow reported {type(exc).__name__})') from None
    raw, stride = image.tobytes(), image.width * 4
    return image.width, image.height, [raw[y * stride:(y + 1) * stride] for y in range(image.height)]


def decode_image(data, max_pixels=MAX_PIXELS):
    """Dispatch by magic bytes.

    PNG: stdlib adapter; palette/16-bit/interlaced PNG fall back to Pillow when it is installed.
    JPEG/WebP: Pillow only. SVG, GIF, BMP, TIFF, ICO, HEIC/AVIF: rejected.
    """
    kind = _sniff(data)
    if kind == 'png':
        try:
            return decode_png(data, max_pixels)
        except ImageDecodeError as exc:
            if not str(exc).startswith(('unsupported PNG', 'interlaced PNG')):
                raise
            try:
                import PIL  # noqa: F401  (only to decide whether a fallback exists)
            except ImportError:
                raise exc from None
            return decode_pillow(data, max_pixels, ('PNG',))
    if kind in ('jpeg', 'webp'):
        return decode_pillow(data, max_pixels, ('JPEG',) if kind == 'jpeg' else ('WEBP',))
    if kind == 'svg':
        raise ImageDecodeError('SVG input is not supported: it is vector data and needs a renderer '
                               '(SVG is an output format only)')
    if kind in _UNSUPPORTED:
        raise ImageDecodeError(f'{_UNSUPPORTED[kind]} input is not supported '
                               '(PNG with stdlib; JPEG/WebP with Pillow)')
    raise ImageDecodeError('unrecognized image format (PNG with stdlib; JPEG/WebP with Pillow)')


def convert(text, size=16, fit='crop', colors=8, palette=None, decoder=decode_image,
            max_bytes=MAX_BYTES, max_pixels=MAX_PIXELS):
    """Base64 text (or raw PNG bytes) -> ``ironmate-pixel-grid/1`` artifact. Index 0 is always transparent.

    ``palette`` names a fixed pixel_grid palette; otherwise ``colors`` (1-16) opaque colors
    are chosen by deterministic median cut (unused colors dropped). Cells with averaged alpha < 128 become index 0.
    """
    if type(size) is not int or size not in SIZES:
        raise ValueError('size must be 8, 16, 32, 64 or 128')
    if fit not in FITS:
        raise ValueError('fit must be crop or contain')
    if palette is not None and palette not in PALETTES:
        raise ValueError('unknown palette')
    if palette is None and (type(colors) is not int or not 1 <= colors <= 16):
        raise ValueError('colors must be an integer from 1 to 16')
    if isinstance(text, str) and text.lstrip('\ufeff \t\r\n').startswith('<'):
        text = text.encode('utf-8')  # markup such as SVG, not Base64
    if isinstance(text, bytes) and _sniff(text):
        if len(text) > max_bytes:
            raise ValueError(f'input exceeds {max_bytes} bytes')
        data = text  # plain image file bytes (not Base64)
    else:
        data = decode_base64(text, max_bytes)
    width, height, rows = decoder(data, max_pixels)
    canvas = _downscale(width, height, rows, size, fit)
    opaque = [cell[:3] for row in canvas for cell in row if cell and cell[3] >= 128]
    if palette:
        rgb = [_hex_rgb(value) for value in PALETTES[palette][1:]]
    else:
        counts = {}
        for value in opaque:
            counts[value] = counts.get(value, 0) + 1
        rgb = _median_cut(list(counts.items()), colors) if counts else []
    pixels = [[0 if not cell or cell[3] < 128 else 1 + _nearest(cell[:3], rgb) for cell in row]
              for row in canvas]
    if not palette:  # drop median-cut colors no cell maps to, so the palette is canonical
        used = sorted({v for row in pixels for v in row} - {0})
        remap = {old: new for new, old in enumerate(used, 1)}
        pixels = [[remap.get(v, 0) for v in row] for row in pixels]
        rgb = [rgb[old - 1] for old in used]
    table = ['#00000000'] + ['#%02X%02X%02XFF' % value for value in rgb]
    return {'schema': 'ironmate-pixel-grid/1', 'source': {'width': width, 'height': height},
            'fit': fit, 'palette': palette, 'quantize': 'fixed' if palette else 'median_cut',
            'width': size, 'height': size, 'colors': table, 'pixels': pixels,
            'resampling': 'area_average'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('input', help="PNG file, or file with Base64 / a data: URI ('-' = stdin)")
    p.add_argument('--size', type=int, choices=SIZES, default=16)
    p.add_argument('--fit', choices=FITS, default='crop')
    p.add_argument('--colors', type=int, default=8, help='median-cut colors, 1-16 (default 8)')
    p.add_argument('--palette', choices=PALETTES, help='use a fixed pixel_grid palette instead')
    p.add_argument('--format', choices=('json', 'svg', 'png', 'base64'), default=None,
                   help='json (default), svg, png, or base64')
    p.add_argument('--json', action='store_true', help='write JSON (the default; rejects a different --format)')
    p.add_argument('--data-uri', action='store_true', help='base64: emit data:image/png;base64,...')
    p.add_argument('--scale', type=int, help='pixels per cell, 1-64 (default svg 8, png/base64 1)')
    p.add_argument('-o', '--output', help='write the result here instead of stdout')
    p.add_argument('--force', action='store_true', help='replace an existing -o file')
    args = p.parse_args(argv)
    if args.json and args.format not in (None, 'json'):
        print('photo_grid.py: --json cannot be combined with a different --format', file=sys.stderr)
        print('hint: pass only --json, or only --format json', file=sys.stderr)
        return 2
    args.format = args.format or 'json'
    try:
        if args.input == '-':
            text = sys.stdin.buffer.read(MAX_BYTES * 2)
        else:
            with open(args.input, 'rb') as handle:
                text = handle.read(MAX_BYTES * 2)
        artifact = convert(text, args.size, args.fit, args.colors, args.palette)
        if args.format == 'base64':
            from grid_png import to_base64
            result = (to_base64(artifact, args.scale or 1, args.data_uri) + '\n').encode('ascii')
        elif args.format == 'png':
            from grid_png import to_png
            result = to_png(artifact, args.scale or 1)
        elif args.format == 'svg':
            from grid_svg import to_svg
            result = to_svg(artifact, args.scale or 8).encode('utf-8')
        else:
            result = (json.dumps(artifact, ensure_ascii=False) + '\n').encode('utf-8')
        if args.output:
            from grid_output import write_output
            write_output(args.output, result, args.force)
        else:
            sys.stdout.buffer.write(result)
            sys.stdout.flush()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        from ironmate_cli import emit_error, hint_for
        if args.json:
            return emit_error('photo_grid.py', exc, json_mode=True)
        print(f'error: {exc}', file=sys.stderr)
        hint = hint_for(exc)
        if hint:
            print(f'hint: {hint}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
