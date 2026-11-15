"""Write an ``ironmate-pixel-grid/1`` artifact out: PNG, SVG and safe ``-o`` files (stdlib only, no I/O on import).

PNG: default 8-bit RGBA, optional indexed palette, non-interlaced, filter 0, fixed zlib level 9, so the
same grid and scale always give the same bytes. ``scale`` is integer nearest-neighbour.

SVG: horizontal runs of the same color become one ``<rect>``; only alpha 0 is omitted.
Coordinates are grid units in ``viewBox``; ``scale`` only sets width/height.

Files: by default exclusive create, so an existing file or symlink (even a dangling one) is never truncated.
``force=True``: write a temporary file in the same directory and ``os.replace`` it onto the path,
which replaces a symlink itself instead of writing through it to its target.
"""
from __future__ import annotations
import base64, json, os, re, struct, tempfile, zlib
from xml.sax.saxutils import escape

__all__ = ['MAX_PIXELS', 'HEADER_FIELDS', 'header_info', 'to_png', 'to_base64', 'to_svg', 'write_output']
MAX_PIXELS = 4096 * 4096
_RGBA = re.compile(r'#[0-9A-Fa-f]{8}')


# Only these artifact fields ever go into the ironmate tEXt header (size, palette, generation
# parameters). Anything else, including any source-image metadata, is never written.
HEADER_FIELDS = ('schema', 'width', 'height', 'colors', 'palette', 'mask', 'effect', 'resampling', 'source',
                 'fit', 'quantize', 'restored')
_TOKEN = re.compile(r'[A-Za-z0-9_./-]{1,64}')


def header_info(artifact):
    """Whitelisted, type-checked header fields of ``artifact`` (no free text, no foreign keys)."""
    def ok(key, v):
        if key in ('width', 'height'):
            return type(v) is int
        if key == 'colors':
            return isinstance(v, list) and all(isinstance(c, str) and _RGBA.fullmatch(c) for c in v)
        if key in ('source', 'restored'):
            return isinstance(v, dict) and all(k in ('width', 'height', 'format', 'scale') and
                                               (type(x) is int or (isinstance(x, str) and _TOKEN.fullmatch(x)))
                                               for k, x in v.items())
        return v is None or (isinstance(v, str) and _TOKEN.fullmatch(v) is not None)
    return {k: artifact[k] for k in HEADER_FIELDS if k in artifact and ok(k, artifact[k])}


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def to_png(artifact, scale=1, meta=False, *, indexed=False):
    """Return deterministic PNG bytes; index 0 is written as its RGBA (normally transparent).

    ``indexed=True`` uses lossless palette indexes at 1/2/4/8 bits per pixel.
    The default remains byte-identical RGBA; palette headers can cost more for tiny images.

    ``meta=True`` adds a ``tEXt`` chunk (keyword ``ironmate``) with the artifact minus ``pixels``,
    so ``grid_tools.restore`` can recover palette order, unused colors and the grid size exactly.
    """
    if type(indexed) is not bool:
        raise ValueError('indexed must be boolean')
    if type(scale) is not int or not 1 <= scale <= 64:
        raise ValueError('scale must be an integer from 1 to 64')
    width, height, pixels, colors = (artifact['width'], artifact['height'],
                                     artifact['pixels'], artifact['colors'])
    if len(pixels) != height or any(len(row) != width for row in pixels) or not width:
        raise ValueError('pixels do not match width/height')
    if width * height * scale * scale > MAX_PIXELS:
        raise ValueError(f'output exceeds {MAX_PIXELS} pixels')
    if any(not isinstance(c, str) or not _RGBA.fullmatch(c) for c in colors):
        raise ValueError('colors must be #RRGGBBAA')
    if indexed and not 1 <= len(colors) <= 256:
        raise ValueError('indexed PNG requires 1 to 256 colors')
    rgba = [bytes.fromhex(c[1:]) for c in colors]
    depth = next(d for d in (1, 2, 4, 8) if len(colors) <= (1 << d)) if indexed else 8
    palette = b''
    if indexed:
        palette = _chunk(b'PLTE', b''.join(c[:3] for c in rgba))
        if any(c[3] != 255 for c in rgba):
            palette += _chunk(b'tRNS', bytes(c[3] for c in rgba).rstrip(b'\xff'))
    raw = bytearray()
    for row in pixels:
        if any(type(v) is not int or not 0 <= v < len(rgba) for v in row):
            raise ValueError('color index out of range')
        if indexed:
            packed = bytearray()
            value = used = 0
            for pixel in row:
                for _ in range(scale):
                    value = (value << depth) | pixel
                    used += depth
                    if used == 8:
                        packed.append(value)
                        value = used = 0
            if used:
                packed.append(value << (8 - used))
            line = b'\x00' + bytes(packed)
        else:
            line = b'\x00' + b''.join(rgba[v] * scale for v in row)
        raw += line * scale
    header = struct.pack('>IIBBBBB', width * scale, height * scale, depth, 3 if indexed else 6, 0, 0, 0)
    text = b''
    if meta:
        info = header_info(artifact)
        text = _chunk(b'tEXt', b'ironmate\x00' + json.dumps(info, sort_keys=True, separators=(',', ':'),
                                                            ensure_ascii=True).encode('ascii'))
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + palette + text
            + _chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + _chunk(b'IEND', b''))


def to_base64(artifact, scale=1, data_uri=False, meta=False, *, indexed=False):
    """Base64 of ``to_png`` bytes; indexed output needs a palette-capable decoder."""
    text = base64.b64encode(to_png(artifact, scale, meta, indexed=indexed)).decode('ascii')
    return 'data:image/png;base64,' + text if data_uri else text


def _fill(value):
    if not isinstance(value, str) or not _RGBA.fullmatch(value):
        raise ValueError(f'color must be #RRGGBBAA: {value!r}')
    alpha = int(value[7:9], 16)
    if not alpha:
        return None
    attr = f'fill="#{value[1:7].lower()}"'
    return attr if alpha == 255 else f'{attr} fill-opacity="{alpha / 255:.4g}"'


def _runs(row):
    x = 0
    while x < len(row):
        end = x
        while end + 1 < len(row) and row[end + 1] == row[x]:
            end += 1
        yield x, end - x + 1, row[x]
        x = end + 1


def to_svg(artifact, scale=8, merge=True):
    """Return deterministic SVG text for a pixel-grid artifact."""
    if type(scale) is not int or not 1 <= scale <= 64:
        raise ValueError('scale must be an integer from 1 to 64')
    width, height, pixels = artifact['width'], artifact['height'], artifact['pixels']
    colors = artifact['colors']
    if len(pixels) != height or any(len(row) != width for row in pixels):
        raise ValueError('pixels do not match width/height')
    fills = [_fill(value) for value in colors]
    title = ' '.join(f'{key}={artifact[key]}' for key in ('schema', 'mask', 'palette', 'effect', 'fit', 'quantize')
                     if artifact.get(key) is not None)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width * scale}" height="{height * scale}" '
             f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges">',
             f'<title>{escape(title)}</title>',
             f'<desc>{escape(json.dumps({"colors": colors}))}</desc>']
    for y, row in enumerate(pixels):
        cells = _runs(row) if merge else ((x, 1, v) for x, v in enumerate(row))
        for x, run, index in cells:
            if type(index) is not int or not 0 <= index < len(colors):
                raise ValueError(f'color index out of range: {index!r}')
            if fills[index]:
                lines.append(f'<rect x="{x}" y="{y}" width="{run}" height="1" {fills[index]}/>')
    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


def write_output(path, data, force=False):
    """Write bytes to ``path``; raise FileExistsError (an OSError) unless ``force``."""
    if not force:
        try:
            with open(path, 'xb') as handle:
                handle.write(data)
        except FileExistsError:
            raise FileExistsError(f'refusing to overwrite existing {path} (use --force)') from None
        return
    if os.path.isdir(path):
        raise IsADirectoryError(f'{path} is a directory')
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
