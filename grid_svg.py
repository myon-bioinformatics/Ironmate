"""Write an ``ironmate-pixel-grid/1`` artifact as SVG (stdlib only, no I/O on import).

Horizontal runs of the same color become one ``<rect>``; index 0 (or alpha 0) is omitted.
Coordinates are grid units in ``viewBox``; ``scale`` only sets width/height.
"""
from __future__ import annotations
import argparse, json, re, sys
from xml.sax.saxutils import escape, quoteattr

__all__ = ['to_svg', 'main']
_RGBA = re.compile(r'#[0-9A-Fa-f]{8}')


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
    fills = [None] + [_fill(value) for value in colors[1:]]
    _fill(colors[0])
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('input', help="pixel-grid JSON file ('-' = stdin)")
    p.add_argument('-o', '--output', help='write SVG here instead of stdout')
    p.add_argument('--scale', type=int, default=8, help='output pixels per cell, 1-64 (default 8)')
    p.add_argument('--no-merge', action='store_true', help='one rect per cell')
    args = p.parse_args(argv)
    try:
        if args.input == '-':
            artifact = json.load(sys.stdin)
        else:
            with open(args.input, encoding='utf-8') as handle:
                artifact = json.load(handle)
        svg = to_svg(artifact, args.scale, not args.no_merge)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as handle:
                handle.write(svg)
        else:
            sys.stdout.write(svg)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
