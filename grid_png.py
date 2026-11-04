"""Write an ``ironmate-pixel-grid/1`` artifact as PNG (stdlib zlib+struct, no I/O on import).

Default 8-bit RGBA, optional indexed palette, non-interlaced, filter 0, fixed zlib level 9, so the
same grid and scale always give the same bytes. ``scale`` is integer nearest-neighbour.
"""
from __future__ import annotations
import argparse, base64, json, re, struct, sys, zlib

__all__ = ['MAX_PIXELS', 'to_png', 'to_base64', 'main']
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
            palette += _chunk(b'tRNS', bytes(c[3] for c in rgba))
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('input', help="pixel-grid JSON file ('-' = stdin)")
    p.add_argument('-o', '--output', help='write PNG here instead of stdout')
    p.add_argument('--indexed', action='store_true', help='lossless palette PNG; 1-256 colors')
    p.add_argument('--force', action='store_true', help='replace an existing -o file')
    p.add_argument('--scale', type=int, default=1, help='pixels per cell, 1-64 (default 1)')
    args = p.parse_args(argv)
    try:
        if args.input == '-':
            artifact = json.load(sys.stdin)
        else:
            with open(args.input, encoding='utf-8') as handle:
                artifact = json.load(handle)
        data = to_png(artifact, args.scale, indexed=args.indexed)
        if args.output:
            from grid_output import write_output
            write_output(args.output, data, args.force)
        else:
            sys.stdout.buffer.write(data)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
