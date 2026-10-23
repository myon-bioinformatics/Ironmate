"""Deterministic pixel-grid prototype: procedural masks, color-ID palettes, indexed colors.

Stdlib only; importing this module performs no I/O.
"""
from __future__ import annotations
import argparse
import json
import sys

__all__ = ['MASKS', 'MASK_BOUNDS', 'PALETTE_BASE', 'PALETTE_LABELS', 'PALETTES', 'SIZES', 'EFFECTS',
           'derive_palette', 'mask_problem', 'silhouette', 'render', 'filename', 'emoji', 'main']
# Canonical canvas sizes shared with photo_grid.py. render() accepts any size in MASK_BOUNDS.
SIZES = (8, 16, 32, 64, 128)
EFFECTS = ('normal', 'shadow', 'highlight', 'outline')
MASKS = ('triangle', 'diamond', 'cloud', 'circle', 'rock')
# Inclusive (min, max) canvas size per mask. Every size in range passes mask_problem() (scanned 3..256);
# below min a mask fails the rule or is not recognizable. 256 is a policy cap, not a quality limit.
MASK_BOUNDS = {
    'triangle': (5, 256), 'diamond': (9, 256), 'cloud': (16, 256), 'circle': (6, 256), 'rock': (7, 256),
}
# Color ID -> (main, shadow). IDs are fixed and never reused; labels are informational only.
PALETTE_BASE = {
    'C01': ('#5BBD3E', '#418A2D'), 'C02': ('#63B3FF', '#3F75CC'), 'C03': ('#FF6A00', '#CC3D00'),
    'C04': ('#A84DFF', '#7520B8'), 'C05': ('#FFFFFF', '#CFD8E6'), 'C06': ('#E0C072', '#B08D45'),
    'C07': ('#9EA4AB', '#6D737B'), 'C08': ('#A8693A', '#744423'), 'C09': ('#FFD23F', '#C99A17'),
    'C10': ('#FF86C0', '#C9568F'),
}
PALETTE_LABELS = {
    'C01': 'grass', 'C02': 'water', 'C03': 'lava', 'C04': 'poison', 'C05': 'snow',
    'C06': 'sand', 'C07': 'stone', 'C08': 'wood', 'C09': 'gold', 'C10': 'blossom',
}
_EMOJI_RGB = {
    '🟥': (221, 46, 68), '🟧': (244, 144, 12), '🟨': (253, 203, 88), '🟩': (120, 177, 89),
    '🟦': (85, 172, 238), '🟪': (170, 142, 214), '🟫': (193, 105, 79), '⬛': (49, 55, 61), '⬜': (230, 231, 232),
}


def _rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return '#%02X%02X%02XFF' % rgb


def derive_palette(main, shadow):
    """Index palette (transparent, main, shadow, highlight, outline) from main/shadow.

    Per RGB channel with integer round-half-up:
    highlight = round((3 * main + 2 * 255) / 5)  (main mixed 40% toward white)
    outline   = round(shadow / 2)                (shadow mixed 50% toward black)
    """
    m, s = _rgb(main), _rgb(shadow)
    highlight = tuple((2 * (3 * c + 510) + 5) // 10 for c in m)
    outline = tuple((c + 1) // 2 for c in s)
    return ('#00000000', _hex(m), _hex(s), _hex(highlight), _hex(outline))


PALETTES = {pid: derive_palette(*pair) for pid, pair in PALETTE_BASE.items()}


def _fill(size, inside):
    return [[1 if inside(x + 0.5, y + 0.5) else 0 for x in range(size)] for y in range(size)]


def _center(grid):
    """Move the filled rows so the shape is vertically centered (top gets the smaller margin)."""
    size = len(grid)
    rows = [y for y in range(size) if any(grid[y])]
    if not rows:
        return grid
    shift = (size - (rows[-1] - rows[0] + 1)) // 2 - rows[0]
    out = [[0] * size for _ in range(size)]
    for y in rows:
        out[y + shift] = grid[y]
    return out


def _triangle(size, variant):
    if variant:
        return None
    span = size - 2
    grid = [[0] * size for _ in range(size)]
    for y in range((span + 1) // 2):  # every row widens by exactly one cell per side
        width = (1 if span % 2 else 2) + 2 * y
        left = (size - width) // 2
        grid[y][left:left + width] = [1] * width
    return _center(grid)


def _diamond(size, variant):
    if variant >= 10:
        return None
    c, r = size / 2, (size - 2) / 2 - 0.05 * variant
    return _fill(size, lambda x, y: abs(x - c) + abs(y - c) <= r + 1e-9)


def _circle(size, variant):
    if variant >= 10:
        return None
    c, r = size / 2, (size - 2) / 2 - 0.05 * variant
    return _fill(size, lambda x, y: (x - c) ** 2 + (y - c) ** 2 <= r * r)


def _rock(size, variant):
    if variant >= 10:
        return None
    # Superellipse (exponent 2.6, height 0.7 x width) with the bottom quarter cut flat.
    c, a = size / 2, (size - 2) / 2 - 0.05 * variant
    b = 0.7 * a
    return _center(_fill(size, lambda x, y: abs(y - c) <= 0.75 * b
                         and (abs(x - c) / a) ** 2.6 + (abs(y - c) / b) ** 2.6 <= 1))


def _cloud(size, variant):
    # Three puffs on a flat base (W = drawable width): side puffs r=0.16W centered +-0.34W and
    # resting on the base line; center puff r=0.2W whose center is 0.27W above the base line.
    # Fallback variants: drawable width -0.1*a, side puffs lifted 0.15*b, center radius -0.15*d cells.
    a, b, d = variant % 5, variant // 5 % 4, variant // 20
    width, c, bottom = size - 2 - 0.1 * a, size / 2, size - 1.0
    side_y, center_y = bottom - 0.16 * width - 0.15 * b, bottom - 0.27 * width
    r, big, off = 0.16 * width, 0.2 * width - 0.15 * d, 0.34 * width

    def inside(x, y):
        if y > bottom:
            return False
        if any((x - cx) ** 2 + (y - side_y) ** 2 <= r * r for cx in (c - off, c + off)):
            return True
        return (x - c) ** 2 + (y - center_y) ** 2 <= big * big or (abs(x - c) <= off and y >= side_y)
    grid = _fill(size, inside)
    for x in range(size):  # close pin holes where puffs meet: fill each column top..bottom
        ys = [y for y in range(size) if grid[y][x]]
        for y in range(ys[0], ys[-1] + 1) if ys else ():
            grid[y][x] = 1
    return _center(grid)


_BUILDERS = {'triangle': _triangle, 'diamond': _diamond, 'cloud': _cloud, 'circle': _circle, 'rock': _rock}


def _runs(cells):
    out, start = [], None
    for i, v in enumerate(list(cells) + [0]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def _pieces(values):
    """Split a profile into monotone pieces at its turning points (shared flats go to both)."""
    out, start, direction = [], 0, 0
    for i in range(1, len(values)):
        step = (values[i] > values[i - 1]) - (values[i] < values[i - 1])
        if step and direction and step != direction:
            j = i - 1
            while j > start and values[j - 1] == values[j]:
                j -= 1
            out.append(values[start:i])
            start = j
        if step:
            direction = step
    out.append(values[start:])
    return out


def _clean_piece(values):
    """Edge rule for one monotone stretch of a boundary profile.

    1. No 2x2 stair: a jump of >=2 cells never touches a flat (zero) step.
    2. Neighbouring segments of the same kind (jump sizes; flat-run lengths + 1) differ by at most 2x.
       The first and last segment of the stretch are cut by the turning point and are excluded.
    """
    steps = [abs(b - a) for a, b in zip(values, values[1:])]
    for i, s in enumerate(steps):
        if s >= 2 and ((i and not steps[i - 1]) or (i + 1 < len(steps) and not steps[i + 1])):
            return False
    tokens, i = [], 0
    while i < len(steps):
        if steps[i]:
            tokens.append(('jump', steps[i]))
            i += 1
            continue
        j = i
        while j < len(steps) and not steps[j]:
            j += 1
        tokens.append(('flat', j - i + 1))
        i = j
    inner = tokens[1:-1]
    for kind in ('jump', 'flat'):
        seq = [n for k, n in inner if k == kind]
        if any(a > 2 * b or b > 2 * a for a, b in zip(seq, seq[1:])):
            return False
    return True


def _profile_ok(values):
    return all(len(p) < 2 or _clean_piece(p) for p in _pieces(values))


def mask_problem(name, grid):
    """Return None if ``grid`` passes the quality rule for mask ``name``, else a short reason."""
    size = len(grid)
    cells = {(y, x) for y in range(size) for x in range(size) if grid[y][x]}
    if not cells:
        return 'empty'
    if any(grid[0]) or any(grid[-1]) or any(row[0] or row[-1] for row in grid):
        return 'no transparent margin'
    first = min(cells)
    seen, stack = {first}, [first]
    while stack:
        y, x = stack.pop()
        for n in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if n in cells and n not in seen:
                seen.add(n)
                stack.append(n)
    if len(seen) != len(cells):
        return 'not 4-connected'
    if any(row != row[::-1] for row in grid):
        return 'not left-right symmetric'
    if name in ('circle', 'diamond') and grid != grid[::-1]:
        return 'not top-bottom symmetric'
    cols = [x for x in range(size) if any(grid[y][x] for y in range(size))]
    rows = [y for y in range(size) if any(grid[y])]
    tops, bottoms, lefts, widths = [], [], [], []
    for x in cols:
        runs = _runs(grid[y][x] for y in range(size))
        if len(runs) != 1:
            return 'column has a gap'
        tops.append(runs[0][0])
        bottoms.append(runs[0][1])
    for y in rows:
        runs = _runs(grid[y])
        if name != 'cloud' and len(runs) != 1:
            return 'row has a gap'
        lefts.append(runs[0][0])
        widths.append(sum(b - a + 1 for a, b in runs))
    if name == 'cloud' and len(lefts) > 1:  # left edge below the puff notch (largest inward jump)
        drops = [a - b for a, b in zip(lefts, lefts[1:])]
        lefts = lefts[drops.index(max(drops)) + 1:]
    if not all(_profile_ok(p) for p in (tops, bottoms, lefts)):
        return 'jagged edge'
    w, h = len(cols), len(rows)
    corners = (grid[rows[0]][cols[0]], grid[rows[0]][cols[-1]], grid[rows[-1]][cols[0]], grid[rows[-1]][cols[-1]])
    ratio = len(cells) / (w * h)
    if name == 'triangle' and not (widths[0] <= 2 and widths[-1] == w and h >= 2):
        return 'not a triangle'
    if name == 'diamond' and not (widths[0] <= 2 and max(widths) == w and ratio <= 0.65 and h >= 3):
        return 'not a diamond'
    if name == 'circle' and not (w == h and not any(corners) and 0.68 <= ratio <= 0.9):
        return 'not round'
    if name == 'rock' and not (w > h and not any(corners) and widths[-1] * 2 >= w and widths[0] * 5 >= w * 2):
        return 'not a rock'
    if name == 'cloud':
        valleys = sum(1 for i in range(1, len(tops) - 1) if tops[i] > tops[i - 1] and tops[i] >= tops[i + 1]
                      and min(tops[:i]) < tops[i] and min(tops[i + 1:]) < tops[i])
        peaks = [x for x in range(1, len(tops) - 1) if tops[x] < tops[x - 1] and tops[x] <= tops[x + 1]]
        narrow = any(tops[x + 1] > tops[x] for x in peaks) or (tops and tops[0] == min(tops))
        if valleys < 2 or widths[-1] * 2 < w or narrow:
            return 'not a cloud'
    return None


def silhouette(name, size):
    """0/1 grid for ``name`` at ``size``; raises ValueError outside the clean range."""
    if name not in _BUILDERS:
        raise ValueError('unknown mask')
    low, high = MASK_BOUNDS[name]
    if type(size) is not int or not low <= size <= high:
        raise ValueError(f'{name} needs an integer size from {low} to {high}')
    reason = 'no variant'
    for variant in range(60):  # deterministic fallback, first clean variant wins
        grid = _BUILDERS[name](size, variant)
        if grid is None:
            break
        reason = mask_problem(name, grid)
        if reason is None:
            return grid
    raise ValueError(f'{name} cannot be drawn cleanly at size {size}: {reason}')


def render(mask='cloud', palette='C01', effect='normal', size=16):
    """Square indexed grid from a procedural mask; index 0 is transparent.

    Effects recolor inside the silhouette only: shadow = lower third -> index 2,
    highlight = upper third -> index 3, outline = cells touching transparency -> index 4.
    """
    if palette not in PALETTES or effect not in EFFECTS:
        raise ValueError('unknown palette or effect')
    grid = [row[:] for row in silhouette(mask, size)]
    occupied = [(y, x) for y in range(size) for x in range(size) if grid[y][x]]
    y0, y1 = min(y for y, x in occupied), max(y for y, x in occupied)
    band = max(1, (y1 - y0 + 1) // 3)
    for y, x in occupied:
        if effect == 'shadow' and y > y1 - band:
            grid[y][x] = 2
        elif effect == 'highlight' and y < y0 + band:
            grid[y][x] = 3
        elif effect == 'outline' and any(not grid[yy][xx]
                                         for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))):
            grid[y][x] = 4
    return {'schema': 'ironmate-pixel-grid/1', 'mask': mask, 'palette': palette,
            'effect': effect, 'width': size, 'height': size,
            'colors': list(PALETTES[palette]), 'pixels': grid,
            'resampling': 'procedural_mask'}


def filename(artifact, ext='png'):
    """``{mask}_{colorID}_{effect}_{size}.{ext}``, e.g. ``triangle_C01_shadow_32.png``."""
    return f"{artifact['mask']}_{artifact['palette']}_{artifact['effect']}_{artifact['width']}.{ext}"


def emoji(artifact):
    """Approximate emoji preview (nearest emoji color); JSON grid/RGBA remain authoritative."""
    def cell(value):
        if value[7:] == '00':
            return '⬜'
        rgb = _rgb(value)
        return min(_EMOJI_RGB, key=lambda e: (sum((a - b) ** 2 for a, b in zip(rgb, _EMOJI_RGB[e])), e))
    cells = [cell(value) for value in artifact['colors']]
    return '\n'.join(''.join(cells[index] for index in row) for row in artifact['pixels'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--mask', choices=MASKS, default='cloud')
    p.add_argument('--palette', choices=PALETTES, default='C01', help='color ID (C01-C10)')
    p.add_argument('--effect', choices=EFFECTS, default='normal')
    p.add_argument('--size', type=int, default=16, help='canvas size; per-mask range in MASK_BOUNDS')
    p.add_argument('--format', choices=('emoji', 'json', 'svg', 'png', 'base64'), default=None,
                   help='emoji (default), json, svg, png, or base64')
    p.add_argument('--json', action='store_true', help='write the grid as JSON (same as --format json)')
    p.add_argument('--scale', type=int, help='pixels per cell for svg (default 8) / png, base64 (default 1)')
    p.add_argument('--data-uri', action='store_true', help='base64: emit data:image/png;base64,...')
    p.add_argument('-o', '--output', help='write the result here instead of stdout')
    p.add_argument('--force', action='store_true', help='replace an existing -o file')
    args = p.parse_args(argv)
    if args.json and args.format not in (None, 'json'):
        print('pixel_grid.py: --json cannot be combined with a different --format', file=sys.stderr)
        print('hint: pass only --json, or only --format json', file=sys.stderr)
        return 2
    args.format = 'json' if args.json else (args.format or 'emoji')

    def fail(exc):
        from ironmate_cli import emit_error, hint_for
        if args.json:
            return emit_error('pixel_grid.py', exc, json_mode=True)
        print(f'error: {exc}', file=sys.stderr)
        hint = hint_for(exc)
        if hint:
            print(f'hint: {hint}', file=sys.stderr)
        return 2

    try:
        artifact = render(args.mask, args.palette, args.effect, args.size)
    except ValueError as exc:
        return fail(exc)
    if args.format == 'base64':
        from grid_png import to_base64  # lazy: keeps import of this module inert
        data = (to_base64(artifact, args.scale or 1, args.data_uri) + '\n').encode('ascii')
    elif args.format == 'png':
        from grid_png import to_png
        data = to_png(artifact, args.scale or 1)
    elif args.format == 'svg':
        from grid_svg import to_svg
        data = to_svg(artifact, args.scale or 8).encode('utf-8')
    else:
        text = emoji(artifact) if args.format == 'emoji' else json.dumps(artifact, ensure_ascii=False)
        data = (text + '\n').encode('utf-8')
    if args.output:
        from grid_output import write_output
        try:
            write_output(args.output, data, args.force)
        except OSError as exc:
            return fail(exc)
    else:
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
