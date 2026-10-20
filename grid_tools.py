"""One-call API/CLI for dot art <-> Base64 <-> PNG/SVG/JSON (stdlib; Pillow/numpy optional). Python 3.11+.

    python -c "import grid_tools as g; print(g.encode(g.make('cloud', 'C01', 'shadow', 16)))"
    python -m grid_tools load 'data:image/png;base64,...' --to json

No import-time I/O; optional backends are imported only when used.
"""
from __future__ import annotations
import argparse, json, math, os, re, struct, sys, zlib

import photo_grid
import pixel_grid

__all__ = ['FORMATS', 'make', 'photo', 'encode', 'restore', 'resize', 'sparse', 'downscale_2x',
           'recolor', 'cells', 'canonical', 'main']
FORMATS = ('json', 'svg', 'png', 'base64')
_CLEAR = '#00000000'
_HEX = re.compile(r'#[0-9A-Fa-f]{8}')


def _backend(name, module):
    if name not in ('auto', 'stdlib', module):
        raise ValueError(f'backend must be auto, stdlib or {module}')
    if name == 'auto':
        try:
            __import__(module)
            return module
        except ImportError:
            return 'stdlib'
    return name


def _png_meta(data):
    """The ``ironmate`` tEXt payload written by grid_png.to_png(meta=True), or None."""
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'tEXt' and body.startswith(b'ironmate\x00'):
            if zlib.crc32(kind + body) != struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0]:
                raise ValueError('ironmate metadata chunk has a bad CRC')
            meta = json.loads(body[9:].decode('ascii'))
            if not isinstance(meta, dict) or meta.get('schema') != 'ironmate-pixel-grid/1':
                raise ValueError('ironmate metadata is not an ironmate-pixel-grid/1 header')
            for key in ('width', 'height'):
                if type(meta.get(key)) is not int or meta[key] < 1:
                    raise ValueError(f'ironmate metadata {key} must be a positive integer')
            colors = meta.get('colors')
            if (not isinstance(colors, list) or not colors
                    or not all(isinstance(c, str) and _HEX.fullmatch(c) for c in colors)):
                raise ValueError('ironmate metadata colors must be a non-empty list of #RRGGBBAA')
            from grid_png import header_info
            return header_info(meta)   # foreign/free-text fields in a header are dropped, never echoed
        if kind in (b'IDAT', b'IEND'):
            return None
        pos += 12 + length
    return None


def _decode_png(data, backend):
    if _backend(backend, 'PIL') == 'PIL':
        return photo_grid.decode_pillow(data, photo_grid.MAX_PIXELS, ('PNG',))
    return photo_grid.decode_png(data)


def _rows_to_cells(width, height, rows):
    return [['#%02X%02X%02X%02X' % tuple(row[x * 4:x * 4 + 4]) for x in range(width)] for row in rows]


def _runs_gcd(grid, backend):
    """gcd of all horizontal and vertical run lengths (and the size): the largest exact cell scale."""
    if _backend(backend, 'numpy') == 'numpy':
        import numpy as np
        codes = {c: i for i, c in enumerate(sorted({c for row in grid for c in row}))}
        a = np.array([[codes[c] for c in row] for row in grid])
        result = math.gcd(*a.shape)
        for arr in (a, a.T):
            change = np.ones((arr.shape[0], arr.shape[1] + 1), bool)
            change[:, 1:-1] = arr[:, 1:] != arr[:, :-1]
            for row in change:
                starts = np.flatnonzero(row)
                result = math.gcd(result, *np.diff(starts).tolist())
        return result
    result = math.gcd(len(grid[0]), len(grid))
    for lines in (grid, [list(col) for col in zip(*grid)]):
        for line in lines:
            run = 1
            for a, b in zip(line, line[1:]):
                if a == b:
                    run += 1
                else:
                    result, run = math.gcd(result, run), 1
            result = math.gcd(result, run)
    return result


def _reduce(grid, scale):
    """Take one cell per scale x scale block; every block must be a single color."""
    height, width = len(grid), len(grid[0])
    if width % scale or height % scale:
        raise ValueError(f'image {width}x{height} is not a multiple of scale {scale}')
    out = []
    for y in range(0, height, scale):
        row = []
        for x in range(0, width, scale):
            color = grid[y][x]
            if any(grid[yy][xx] != color for yy in range(y, y + scale) for xx in range(x, x + scale)):
                raise ValueError(f'block at ({x},{y}) is not one color: not a {scale}x nearest-neighbour image')
            row.append(color)
        out.append(row)
    return out


def canonical(artifact):
    """Same cells, palette = transparent + used colors in ascending #RRGGBBAA order."""
    grid = cells(artifact)
    colors = [_CLEAR] + sorted({c for row in grid for c in row} - {_CLEAR})
    index = {c: i for i, c in enumerate(colors)}
    out = {k: v for k, v in artifact.items() if k not in ('colors', 'pixels', 'palette')}
    out.update(colors=colors, pixels=[[index[c] for c in row] for row in grid])
    return out


def cells(artifact):
    """Grid of #RRGGBBAA strings (palette-independent view used for equivalence)."""
    colors = artifact['colors']
    return [[colors[v].upper() for v in row] for row in artifact['pixels']]


def make(mask='cloud', palette='C01', effect='normal', size=16):
    """Procedural dot art (pixel_grid.render)."""
    return pixel_grid.render(mask, palette, effect, size)


def photo(source, size=32, fit='crop', colors=8, palette=None):
    """Photo (PNG; JPEG/WebP with Pillow; file bytes, Base64 or data URI) -> grid. Lossy by design."""
    return photo_grid.convert(source, size, fit, colors, palette)


def encode(artifact, fmt='base64', scale=1, data_uri=False, meta=True):
    """Artifact -> str (json/svg/base64) or bytes (png). ``meta`` embeds the palette header in PNG."""
    if fmt == 'json':
        return json.dumps(artifact, ensure_ascii=False, separators=(',', ':'))
    if fmt == 'svg':
        from grid_svg import to_svg
        return to_svg(artifact, scale if scale != 1 else 8)
    from grid_png import to_base64, to_png
    if fmt == 'png':
        return to_png(artifact, scale, meta)
    if fmt == 'base64':
        return to_base64(artifact, scale, data_uri, meta)
    raise ValueError(f'format must be one of {FORMATS}')


def restore(source, size=None, backend='auto'):
    """Dot-art PNG/SVG/JSON (file bytes, Base64, data URI or dict) -> artifact.

    With the ``ironmate`` PNG header the original artifact is returned exactly. Otherwise the
    cell scale is ``image width // size`` when ``size`` is given (SVG: 1 by default), else the largest scale that
    divides every same-color run; the palette is canonical (see ``canonical``).
    ``backend``: PNG decoding via 'stdlib' or 'PIL' (Pillow), scale detection via 'numpy'.
    """
    if isinstance(source, dict):
        return json.loads(json.dumps(source))
    if isinstance(source, str) and source.lstrip().startswith('{'):
        return json.loads(source)
    if isinstance(source, str) and source.lstrip('\ufeff \t\r\n').startswith('<'):
        source = source.encode('utf-8')
    data = source if isinstance(source, bytes) and photo_grid._sniff(source) else photo_grid.decode_base64(source)
    kind = photo_grid._sniff(data)
    meta = None
    if kind == 'png':
        meta = _png_meta(data)
        width, height, rows = _decode_png(data, 'stdlib' if backend == 'numpy' else backend)
    elif kind == 'svg':
        from svg_raster import rasterize
        width, height, rows = rasterize(data, backend='numpy' if backend == 'numpy' else
                                        'stdlib' if backend in ('stdlib', 'PIL') else 'auto')
    elif kind in ('jpeg', 'webp'):
        raise ValueError(f'{kind.upper()} is lossy and cannot be restored cell-exactly; use photo() instead')
    else:
        raise ValueError('restore needs PNG or SVG dot art (or ironmate JSON)')
    grid = _rows_to_cells(width, height, rows)
    if meta:
        scale = width // meta['width']
        if scale < 1 or width != scale * meta['width'] or height != scale * meta['height']:
            raise ValueError('image size does not match the ironmate metadata')
        small = _reduce(grid, scale)
        colors = [c.upper() for c in meta['colors']]
        index = {}
        for i, c in enumerate(colors):
            index.setdefault(c, i)
        if any(c not in index for row in small for c in row):
            raise ValueError('pixels use colors that are not in the ironmate metadata')
        return dict(meta, pixels=[[index[c] for c in row] for row in small])
    if size is None and kind == 'svg':
        size = width  # SVG pixel size comes from its viewBox (grid units for grid_svg output)
    if size is not None:
        if type(size) is not int or size < 1 or width % size:
            raise ValueError(f'size {size!r} does not divide the image width {width}')
        scale = width // size
    else:
        scale = _runs_gcd(grid, 'stdlib' if backend == 'PIL' else backend)
    small = _reduce(grid, scale)
    used = sorted({c for row in small for c in row})
    art = canonical({'schema': 'ironmate-pixel-grid/1', 'width': len(small[0]), 'height': len(small),
                     'colors': used, 'pixels': [[used.index(c) for c in row] for row in small]})
    art['restored'] = {'format': kind, 'scale': scale}
    return art


def sparse(artifact, quota_per_frame=1):
    """Owned reversible grid + scanner. Export via scanner.grid.to_artifact()."""
    from pixel_arcade_engine import InvaderSparseScanner, ReversiblePixelGrid
    return InvaderSparseScanner(ReversiblePixelGrid.from_artifact(artifact), quota_per_frame)


def downscale_2x(artifact):
    """Opt-in lossy Pacman probe filter; even source dimensions only, stdlib backend."""
    from pixel_arcade_engine import PacmanGhostProbes, ReversiblePixelGrid
    return PacmanGhostProbes().adaptive_downscale_2x(ReversiblePixelGrid.from_artifact(artifact)).to_artifact()


def resize(artifact, width, height=None, backend='auto', *, method='nearest'):
    """Nearest-neighbour resize by cell centers: source = (2*i + 1) * old // (2 * new).

    ``height`` defaults to keeping the aspect ratio. Integer upscale is exact and reversible.
    ``method='probes'`` opts into lossy, even-dimension 2x downsampling (stdlib only).
    """
    w0, h0 = artifact['width'], artifact['height']
    if height is None:
        height = max(1, round(h0 * width / w0))
    if any(type(v) is not int or not 1 <= v <= 4096 for v in (width, height)):
        raise ValueError('width/height must be integers from 1 to 4096')
    if method == 'probes':
        if w0 != (width << 1) or h0 != (height << 1):
            raise ValueError('probes requires an exact 2x downscale of both dimensions')
        return downscale_2x(artifact)
    if method != 'nearest':
        raise ValueError('method must be nearest or probes')
    xs = [(2 * i + 1) * w0 // (2 * width) for i in range(width)]
    ys = [(2 * j + 1) * h0 // (2 * height) for j in range(height)]
    if _backend(backend, 'numpy') == 'numpy':
        import numpy as np
        pixels = np.array(artifact['pixels'])[np.array(ys)[:, None], np.array(xs)[None, :]].tolist()
    else:
        pixels = [[artifact['pixels'][y][x] for x in xs] for y in ys]
    return dict(artifact, width=width, height=height, pixels=pixels)


def recolor(artifact, palette):
    """Swap the RGBA table for a pixel_grid color ID (indices unchanged; reversible)."""
    if palette not in pixel_grid.PALETTES:
        raise ValueError('unknown color ID')
    colors = list(pixel_grid.PALETTES[palette])
    if any(v >= len(colors) for row in artifact['pixels'] for v in row):
        raise ValueError(f'grid uses color indices beyond the {len(colors)} roles of {palette}')
    return dict(artifact, palette=palette, colors=colors)


def _read(arg):
    if arg == '-':
        return sys.stdin.buffer.read(photo_grid.MAX_BYTES * 2)
    if os.path.isfile(arg):
        with open(arg, 'rb') as handle:
            return handle.read(photo_grid.MAX_BYTES * 2)
    return arg  # inline Base64, data URI, JSON or SVG text


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m grid_tools', description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='command', required=True)
    mk = sub.add_parser('make', help='procedural dot art')
    mk.add_argument('mask', choices=pixel_grid.MASKS)
    mk.add_argument('--palette', default='C01')
    mk.add_argument('--effect', default='normal', choices=pixel_grid.EFFECTS)
    mk.add_argument('--size', type=int, default=16)
    ph = sub.add_parser('photo', help='photo -> grid (lossy)')
    ph.add_argument('input')
    ph.add_argument('--size', type=int, default=32)
    ph.add_argument('--fit', default='crop', choices=photo_grid.FITS)
    ph.add_argument('--colors', type=int, default=8)
    ph.add_argument('--palette')
    ld = sub.add_parser('load', help='dot-art PNG/SVG/JSON/Base64 -> grid')
    ld.add_argument('input')
    ld.add_argument('--size', type=int, help='original grid width (skips scale detection)')
    es = sub.add_parser('estimate', help='recommend a downscale so PNG/Base64 fits a size limit')
    es.add_argument('input', nargs='?', help='image file, Base64 or data URI (optional)')
    es.add_argument('--width', type=int)
    es.add_argument('--height', type=int)
    es.add_argument('--bytes', type=int, dest='nbytes', help='current file size')
    es.add_argument('--chars', type=int, help='current Base64 length')
    es.add_argument('--limit-bytes', type=int)
    es.add_argument('--limit-chars', type=int)
    es.add_argument('--data-uri', action='store_true', help='limit includes the data:image/png;base64, prefix')
    es.add_argument('--no-meta', action='store_true', help='size output written with --no-meta (default: with header)')
    es.add_argument('--verify', action='store_true', help='encode each candidate and report the real size')
    ft = sub.add_parser('fit', help='largest verified PNG/Base64 that fits a size limit (auto ratio/meta)')
    ft.add_argument('input')
    lim = ft.add_mutually_exclusive_group(required=True)
    lim.add_argument('--limit-bytes', type=int)
    lim.add_argument('--limit-chars', type=int)
    ft.add_argument('--data-uri', action='store_true')
    ft.add_argument('--prefer', choices=('lossless', 'largest'), default='lossless')
    ft.add_argument('--to', choices=('base64', 'png'), default='base64')
    ft.add_argument('-o', '--output')
    ft.add_argument('--force', action='store_true')
    for cmd in (mk, ph, ld):
        cmd.add_argument('--to', choices=FORMATS, default='base64' if cmd is mk else 'json')
        cmd.add_argument('--scale', type=int, default=1, help='output pixels per cell (svg default 8)')
        cmd.add_argument('--data-uri', action='store_true')
        cmd.add_argument('--no-meta', action='store_true', help='omit the ironmate PNG header')
        cmd.add_argument('--resize', type=int, help='resize to this width (nearest-neighbour by default)')
        cmd.add_argument('--resize-method', choices=('nearest', 'probes'), default='nearest',
                         help='probes: experimental lossy 2x downscale; requires --resize')
        cmd.add_argument('--recolor', help='swap palette to this color ID')
        cmd.add_argument('-o', '--output')
        cmd.add_argument('--force', action='store_true', help='replace an existing -o file')
    args = p.parse_args(argv)
    if args.command == 'estimate':
        from size_estimate import estimate
        try:
            result = estimate(_read(args.input) if args.input else None, width=args.width, height=args.height,
                              nbytes=args.nbytes, chars=args.chars, limit_bytes=args.limit_bytes,
                              limit_chars=args.limit_chars, data_uri=args.data_uri, verify=args.verify,
                              meta=not args.no_meta)
        except (OSError, ValueError, ImportError) as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    if args.command == 'fit':
        import ironmate_image
        try:
            res = ironmate_image.fit_to_limit(_read(args.input), args.limit_bytes, args.limit_chars, args.data_uri,
                                              args.prefer)
        except (OSError, ValueError, ImportError) as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        info = {k: v for k, v in vars(res).items() if k not in ('data', 'text')}
        print(json.dumps(info, ensure_ascii=False), file=sys.stderr)
        data = res.data if args.to == 'png' else (res.text + '\n').encode()
        if args.output:
            from grid_output import write_output
            try:
                write_output(args.output, data, args.force)
            except OSError as exc:
                print(f'error: {exc}', file=sys.stderr)
                return 2
        else:
            sys.stdout.buffer.write(data)
            sys.stdout.flush()
        return 0
    try:
        if args.command == 'make':
            art = make(args.mask, args.palette, args.effect, args.size)
        elif args.command == 'photo':
            art = photo(_read(args.input), args.size, args.fit, args.colors, args.palette)
        else:
            art = restore(_read(args.input), args.size)
        if args.resize is not None:
            art = resize(art, args.resize, method=args.resize_method)
        elif args.resize_method != 'nearest':
            raise ValueError('--resize-method probes requires --resize')
        if args.recolor:
            art = recolor(art, args.recolor)
        result = encode(art, args.to, args.scale, args.data_uri, not args.no_meta)
    except (OSError, ValueError, KeyError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    data = result if isinstance(result, bytes) else (result + ('' if result.endswith('\n') else '\n')).encode()
    if args.output:
        from grid_output import write_output
        try:
            write_output(args.output, data, args.force)
        except OSError as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
