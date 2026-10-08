"""Deterministic pixel-grid prototype: indexed colors first, emoji as preview."""
from __future__ import annotations
import argparse
import json

__all__ = ['MASKS', 'PALETTES', 'SIZES', 'EFFECTS', 'render', 'emoji', 'main']
SIZES = (8, 16, 32, 64, 128)
EFFECTS = ('normal', 'shadow', 'highlight', 'outline')
MASKS = {
    'triangle': ('0001000', '0011100', '0111110', '1111111'),
    'diamond': ('0001000', '0011100', '0111110', '1111111', '0111110', '0011100', '0001000'),
    'cloud': ('0011100011100', '0111110111110', '1111111111111', '1111111111111', '0111111111110'),
    'circle': ('0011100', '0111110', '1111111', '1111111', '1111111', '0111110', '0011100'),
    'rock': ('0011110', '0111111', '1111111', '1111111', '0111110'),
}
# Transparent / main / shadow / highlight / outline, with fixed RGBA values.
# Emoji mapping is only an approximate, device-dependent view of those values.
PALETTES = {
    'nature': ('#00000000', '#67B84AFF', '#2D6B35FF', '#BFE889FF', '#1C3028FF'),
    'water': ('#00000000', '#398ACBFF', '#24539BFF', '#A3DBEFFF', '#183348FF'),
    'lava': ('#00000000', '#EC5A31FF', '#A32C37FF', '#FFD36AFF', '#39232FFF'),
    'poison': ('#00000000', '#A65BC3FF', '#603C8FFF', '#E8A9ECFF', '#30263FFF'),
    'desert': ('#00000000', '#D7AF63FF', '#95653FFF', '#F6DEA0FF', '#44352FFF'),
    'snow': ('#00000000', '#EAF3F5FF', '#8BAEC8FF', '#FFFFFFFF', '#344C68FF'),
}
_EMOJI = {
    'nature': ('⬜', '🟩', '🟫', '🟨', '⬛'),
    'water': ('⬜', '🟦', '⬛', '🟩', '⬛'),
    'lava': ('⬜', '🟥', '🟫', '🟨', '⬛'),
    'poison': ('⬜', '🟪', '⬛', '🟥', '⬛'),
    'desert': ('⬜', '🟨', '🟫', '⬜', '⬛'),
    'snow': ('⬜', '⬜', '🟦', '🟨', '⬛'),
}


def render(mask='cloud', palette='nature', effect='normal', size=16):
    """Fit a binary seed into a square grid without stretching its aspect ratio.

    This is nearest-neighbor seed enlargement, not size-specific art synthesis.
    Index 0 is transparent, never an outline/background color.
    """
    if mask not in MASKS or palette not in PALETTES or effect not in EFFECTS:
        raise ValueError('unknown mask, palette or effect')
    if type(size) is not int or size not in SIZES:
        raise ValueError('size must be 8, 16, 32, 64 or 128')
    seed = MASKS[mask]
    width, height = len(seed[0]), len(seed)
    if not width or any(len(row) != width or set(row) - {'0', '1'} for row in seed):
        raise ValueError('mask must be a rectangular binary grid')
    span = size - 2  # preserve transparent margin, including outline variants
    scale = min(span / width, span / height)
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    left, top = (size - w) // 2, (size - h) // 2
    grid = [[0] * size for _ in range(size)]
    for y in range(h):
        for x in range(w):
            grid[top + y][left + x] = int(seed[y * height // h][x * width // w])
    occupied = [(y, x) for y in range(size) for x in range(size) if grid[y][x]]
    if not occupied:
        raise ValueError('mask became empty at requested size')
    y0, y1 = min(y for y, x in occupied), max(y for y, x in occupied)
    band = max(1, (y1 - y0 + 1) // 3)
    for y, x in occupied:
        if effect == 'shadow' and y > y1 - band:
            grid[y][x] = 2
        elif effect == 'highlight' and y < y0 + band:
            grid[y][x] = 3
        elif effect == 'outline' and any(not (0 <= yy < size and 0 <= xx < size) or not grid[yy][xx]
                                       for yy, xx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1))):
            grid[y][x] = 4
    return {'schema': 'ironmate-pixel-grid/1', 'mask': mask, 'palette': palette,
            'effect': effect, 'width': size, 'height': size,
            'colors': list(PALETTES[palette]), 'pixels': grid,
            'resampling': 'nearest_seed_fit'}


def emoji(artifact):
    """Approximate square emoji preview; JSON grid/RGBA remain authoritative."""
    cells = _EMOJI[artifact['palette']]
    return '\n'.join(''.join(cells[index] for index in row) for row in artifact['pixels'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mask', choices=MASKS, default='cloud')
    p.add_argument('--palette', choices=PALETTES, default='nature')
    p.add_argument('--effect', choices=EFFECTS, default='normal')
    p.add_argument('--size', type=int, choices=SIZES, default=16)
    p.add_argument('--format', choices=('emoji', 'json'), default='emoji')
    args = p.parse_args(argv)
    artifact = render(args.mask, args.palette, args.effect, args.size)
    print(emoji(artifact) if args.format == 'emoji' else json.dumps(artifact, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
