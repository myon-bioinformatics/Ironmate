"""Deterministic README preview sheet of pixel_grid output (stdlib only). Python 3.11+.

    python -S grid_preview.py -o docs/pixel-grid-preview.png --force

Rows: 5 masks x 10 color IDs (effect ``shadow``), a strip of the 4 effects, and odd sizes.
The sheet is itself an ``ironmate-pixel-grid/1`` artifact encoded by grid_png, so the bytes are
reproducible; tests/test_grid_preview.py asserts the committed PNG matches.
"""
from __future__ import annotations
import argparse, sys

import pixel_grid

__all__ = ['CELL', 'SCALE', 'build', 'png', 'main']
CELL, SCALE, GAP, LABEL_W = 24, 3, 4, 44
BG, INK = '#D5DCE4FF', '#2B2B2BFF'  # tinted so white (C05 snow) stays visible
ODD_SIZES = (('triangle', 5), ('diamond', 9), ('circle', 7), ('rock', 13), ('cloud', 17), ('circle', 31))
_FONT = {  # 3x5 glyphs, rows top to bottom
    'A': '010101111101101', 'C': '011100100100011', 'D': '110101101101110', 'E': '111100110100111',
    'G': '011100101101011', 'H': '101101111101101', 'I': '111010010010111', 'K': '101101110101101',
    'L': '100100100100111', 'M': '101111111101101', 'N': '110101101101101', 'O': '010101101101010',
    'R': '110101110101101', 'S': '011100010001110', 'T': '111010010010010', 'U': '101101101101111',
    'W': '101101111111101', '0': '111101101101111', '1': '010110010010111', '2': '110001010100111',
    '3': '110001010001110', '4': '101101111001001', '5': '111100110001110', '6': '011100111101111',
    '7': '111001010010010', '8': '111101111101111', '9': '111101111001110', ' ': '000000000000000',
}


class _Canvas:
    def __init__(self, width, height):
        self.colors = [BG]
        self.index = {BG: 0}
        self.width, self.height = width, height
        self.pixels = [[0] * width for _ in range(height)]

    def color(self, rgba):
        if rgba not in self.index:
            self.index[rgba] = len(self.colors)
            self.colors.append(rgba)
        return self.index[rgba]

    def paste(self, art, x0, y0):
        for y, row in enumerate(art['pixels']):
            for x, v in enumerate(row):
                c = art['colors'][v]
                if c[7:] != '00':
                    self.pixels[y0 + y][x0 + x] = self.color(c)

    def text(self, s, x0, y0):
        ink = self.color(INK)
        for n, ch in enumerate(s.upper()):
            bits = _FONT[ch]
            for i, b in enumerate(bits):
                if b == '1':
                    self.pixels[y0 + i // 3][x0 + n * 4 + i % 3] = ink


def build():
    """The preview sheet as an ironmate-pixel-grid/1 artifact (1 cell = 1 sheet pixel)."""
    ids = list(pixel_grid.PALETTES)
    pitch = CELL + GAP
    rows = len(pixel_grid.MASKS) + 2
    width = LABEL_W + pitch * len(ids)
    height = 8 + pitch * rows + 8 * 2 + 40
    cv = _Canvas(width, height)
    for i, pid in enumerate(ids):
        cv.text(pid, LABEL_W + i * pitch + 6, 1)
    y = 8
    for mask in pixel_grid.MASKS:
        cv.text(mask[:10], 0, y + CELL // 2 - 2)
        for i, pid in enumerate(ids):
            cv.paste(pixel_grid.render(mask, pid, 'shadow', CELL), LABEL_W + i * pitch, y)
        y += pitch
    for i, effect in enumerate(pixel_grid.EFFECTS):   # effects strip, 2 columns per effect
        x = LABEL_W + i * pitch * 2
        cv.text(effect, x, y)
        cv.paste(pixel_grid.render('cloud', 'C02', effect, CELL), x, y + 7)
        cv.paste(pixel_grid.render('rock', 'C07', effect, CELL), x + pitch, y + 7)
    y += pitch + 7
    x = LABEL_W
    for mask, size in ODD_SIZES:
        cv.text(str(size), x, y)
        cv.paste(pixel_grid.render(mask, 'C09', 'outline', size), x, y + 7)
        x += size + GAP * 2
    used = y + 7 + max(s for _, s in ODD_SIZES) + 2
    pixels = cv.pixels[:used]
    return {'schema': 'ironmate-pixel-grid/1', 'width': width, 'height': len(pixels),
            'colors': cv.colors, 'pixels': pixels}


def png():
    from grid_png import to_png
    return to_png(build(), SCALE)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('-o', '--output', required=True)
    p.add_argument('--force', action='store_true', help='replace an existing file')
    args = p.parse_args(argv)
    from grid_output import write_output
    try:
        write_output(args.output, png(), args.force)
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
