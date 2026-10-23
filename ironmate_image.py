"""Ironmate image facade: one call for the fiddly decisions (stdlib only; Pillow optional for JPEG/WebP).

    python -c "import ironmate_image as im; print(im.fit_to_limit('a.png', max_chars=20000).text)"
    python -m grid_tools fit a.png --limit-chars 20000 -o out.b64

``src`` is anything: a path, PNG/JPEG/WebP bytes, Base64, a data URI, ironmate JSON or a grid dict.
Output is always the default grid_tools PNG (8-bit RGBA, ironmate metadata when it fits).
"""
from __future__ import annotations
import base64, json, os, sys
from dataclasses import dataclass, field
from fractions import Fraction

import grid_tools
import photo_grid
import size_estimate
import studio_ingress

__all__ = ['FitError', 'FitResult', 'fit_to_limit', 'load', 'to_base64', 'from_base64', 'to_png', 'resize', 'parse_shelf']


def parse_shelf(items):
    """Parse clipboard shelf payload array into validated items."""
    return studio_ingress.parse_shelf(items)


class FitError(ValueError):
    """The image cannot be made to fit the limit (even the smallest candidate without metadata)."""


@dataclass
class FitResult:
    data: bytes                 # PNG bytes
    text: str                   # Base64 (with data: prefix when data_uri)
    ratio: str                  # e.g. '1', '1/2', '2/3'
    width: int
    height: int
    bytes: int                  # len(data)
    chars: int                  # len(text)
    meta_used: bool
    lossless: bool              # nearest-neighbour ratio that loses no dot-art cells
    command: str                # equivalent grid_tools CLI
    warnings: list = field(default_factory=list)


def _bytes(src):
    if isinstance(src, os.PathLike) or (isinstance(src, str) and len(src) < 4096 and os.path.isfile(src)):
        with open(src, 'rb') as fh:
            return fh.read(photo_grid.MAX_BYTES * 2)
    return src


def _image(src):
    """-> raw image bytes (PNG/JPEG/WebP/SVG) from any accepted form."""
    src = _bytes(src)
    if isinstance(src, bytes) and photo_grid._sniff(src):
        return src
    return photo_grid.decode_base64(src)


def load(src):
    """Anything -> ironmate grid artifact (dict). PNG/SVG dot art exactly; JPEG/WebP at full size, 1 cell = 1 px."""
    src = _bytes(src)
    if isinstance(src, dict) or (isinstance(src, (str, bytes)) and (src.lstrip()[:1] in ('{', b'{'))):
        return grid_tools.restore(json.loads(src) if isinstance(src, (str, bytes)) else src)
    data = _image(src)
    kind = photo_grid._sniff(data)
    if kind in ('png', 'svg'):
        return grid_tools.restore(data)
    _, pixels = size_estimate.inspect(data)
    if pixels is None:
        raise ValueError(f'cannot decode {kind}: install Pillow for JPEG/WebP')
    return size_estimate._candidate_artifact(None, kind, pixels[0], pixels, pixels[0])


def to_png(src, meta=True):
    return grid_tools.encode(load(src), 'png', 1, meta=meta)


def to_base64(src, data_uri=False, meta=True):
    """Anything -> Base64 PNG (reversible: from_base64(to_base64(x)) == load(x))."""
    return grid_tools.encode(load(src), 'base64', 1, data_uri, meta)


def from_base64(text):
    """Base64 / data URI -> grid artifact (exact when it carries ironmate metadata)."""
    return load(photo_grid.decode_base64(text) if isinstance(text, str) else text)


def resize(src, width, height=None):
    """Nearest-neighbour resize of the grid (height keeps the aspect ratio)."""
    return grid_tools.resize(load(src), width, height)


def fit_to_limit(src, max_bytes=None, max_chars=None, data_uri=False, prefer='lossless'):
    """Largest verified PNG/Base64 of ``src`` that fits ``max_bytes`` or ``max_chars``.

    ``prefer='lossless'`` takes the largest dot-art-lossless ratio that fits (else the largest ratio);
    ``prefer='largest'`` takes the largest ratio. Metadata is kept when it fits and dropped (with a
    warning) only if nothing fits with it. Raises FitError when nothing fits.
    """
    if prefer not in ('lossless', 'largest'):
        raise ValueError("prefer must be 'lossless' or 'largest'")
    if (max_bytes is None) == (max_chars is None):
        raise ValueError('give exactly one of max_bytes or max_chars')
    data = _image(src)
    warnings, picks = [], []
    for meta in (True, False):
        r = size_estimate.estimate(data, limit_bytes=max_bytes, limit_chars=max_chars, data_uri=data_uri,
                                   verify=True, meta=meta)
        if r['confidence'] != 'verified':
            raise ValueError('could not decode pixels to verify (install Pillow for JPEG/WebP)')
        picks += [(bool(o['nearest_lossless']) if prefer == 'lossless' else False, Fraction(o['ratio']), meta, o, r)
                  for o in r['options'] if o['actual_bytes'] <= r['target_bytes']]
    if not picks:
        raise FitError(f"cannot fit: smallest candidate is {r['smallest']['actual_bytes']} bytes "
                       f"({r['smallest']['actual_chars']} chars) without metadata > limit")
    # Pixels first (lossless, then larger ratio); metadata only breaks ties.
    _, _, meta, pick, r = max(picks, key=lambda t: t[:3])
    if not meta:
        warnings.append('ironmate metadata dropped to fit (palette order/size header not embedded; '
                        'pixels still exact)')
    if prefer == 'lossless' and not pick['nearest_lossless']:
        warnings.append(f"no lossless ratio fits; using {pick['ratio']} (dot-art cells may be dropped)")
    png = grid_tools.encode(size_estimate._candidate_artifact(
        data if r['input']['format'] == 'png' else None, r['input']['format'], r['input']['width'],
        size_estimate.inspect(data)[1], pick['width']), 'png', 1, meta=meta)
    text = ('data:image/png;base64,' if data_uri else '') + base64.b64encode(png).decode('ascii')
    assert len(png) == pick['actual_bytes'] and len(text) == pick['actual_chars']
    assert (len(png) <= max_bytes) if max_bytes is not None else (len(text) <= max_chars)
    h = grid_tools.restore(png)['height'] if meta else pick['height']
    return FitResult(png, text, pick['ratio'], pick['width'], h, len(png), len(text), meta,
                     pick['nearest_lossless'], pick['command'], warnings)


def _read_input(path):
    """Path, stdin, or an inline Base64/data URI/JSON string."""
    if path == '-':
        if sys.stdin.isatty():
            raise ValueError('pass a file or pipe bytes; stdin is a terminal')
        return sys.stdin.buffer.read(photo_grid.MAX_BYTES * 2)
    if os.path.isfile(path):
        with open(path, 'rb') as handle:
            return handle.read(photo_grid.MAX_BYTES * 2)
    return path


def _emit(data, output, force):
    if output:
        from grid_output import write_output
        write_output(output, data if isinstance(data, bytes) else data.encode('utf-8'), force)
    elif isinstance(data, bytes):
        sys.stdout.buffer.write(data)
    else:
        sys.stdout.write(data if data.endswith('\n') else data + '\n')


def _output_flags(command, *, data_uri=False):
    if data_uri:
        command.add_argument('--data-uri', action='store_true', help='prefix Base64 with data:image/png;base64,')
    command.add_argument('--no-meta', action='store_true', help='omit the ironmate PNG header')
    command.add_argument('-o', '--output')
    command.add_argument('--force', action='store_true', help='replace an existing -o file')


def main(argv=None):
    """CLI for load / to-png / to-base64 / resize. Size fitting stays ``python -m grid_tools fit``."""
    from ironmate_cli import ToolParser, guard

    parser = ToolParser(prog='ironmate_image.py', description=__doc__.splitlines()[0])
    parser.add_json_flag()
    commands = parser.add_subparsers(dest='command', required=True)
    for name, help_text in (
        ('load', 'anything -> grid JSON'),
        ('from-base64', 'Base64 or data URI -> grid JSON'),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument('input', help='path, or - for stdin')
    png_cmd = commands.add_parser('to-png', help='anything -> PNG bytes')
    png_cmd.add_argument('input', help='path, or - for stdin')
    _output_flags(png_cmd)
    b64_cmd = commands.add_parser('to-base64', help='anything -> Base64 PNG text')
    b64_cmd.add_argument('input', help='path, or - for stdin')
    _output_flags(b64_cmd, data_uri=True)
    resize_cmd = commands.add_parser('resize', help='nearest-neighbour resize, then JSON, PNG, or Base64')
    resize_cmd.add_argument('input', help='path, or - for stdin')
    resize_cmd.add_argument('width', type=int)
    resize_cmd.add_argument('--height', type=int)
    resize_cmd.add_argument('--to', '--format', dest='to', choices=('json', 'png', 'base64'), default='json')
    _output_flags(resize_cmd, data_uri=True)
    parser.epilog = 'To fit a size limit: python -m grid_tools fit INPUT --limit-chars N'
    args = parser.parse_args(argv)

    def work():
        src = _read_input(args.input)
        meta = not getattr(args, 'no_meta', False)
        if args.command == 'load':
            payload = json.dumps(load(src), ensure_ascii=False) + '\n'
        elif args.command == 'from-base64':
            payload = json.dumps(from_base64(src), ensure_ascii=False) + '\n'
        elif args.command == 'to-png':
            payload = to_png(src, meta=meta)
        elif args.command == 'to-base64':
            payload = to_base64(src, data_uri=args.data_uri, meta=meta) + '\n'
        else:
            art = resize(src, args.width, args.height)
            if args.to == 'png':
                payload = grid_tools.encode(art, 'png', 1, meta=meta)
            elif args.to == 'base64':
                payload = grid_tools.encode(art, 'base64', 1, args.data_uri, meta) + '\n'
            else:
                payload = json.dumps(art, ensure_ascii=False) + '\n'
        _emit(payload, getattr(args, 'output', None), getattr(args, 'force', False))
        return 0

    return guard('ironmate_image.py', work, json_mode=args.json)


if __name__ == '__main__':
    raise SystemExit(main())
