"""Rebuild Ironmate's font-free 16-cell pixel identity using existing PNG tools.

Run from the repository root: python -S scripts/build_brand.py
SVG uses integer rectangles; PNG/ICO use nearest-neighbour integer scales.
"""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grid_png import to_png

COLORS = ['#003D32FF', '#F5F9F0FF', '#00AD75FF', '#DBE442FF', '#21918CFF', '#5EC962FF']


def grid(heatmap=False):
    pixels = [[0] * 16 for _ in range(16)]
    def stamp(x, y, rows, color):
        for j, row in enumerate(rows):
            for i, cell in enumerate(row):
                if cell != '.':
                    pixels[y+j][x+i] = color(cell, i, j) if callable(color) else color
    stamp(1, 7, ['1111', '.11.', '.11.', '.11.', '.11.', '.11.', '1111'], 1)
    stamp(7, 8, ['111.111.', '11111111'] + ['11.11.11'] * 4, 1)
    stamp(6, 1, ['G...Y', 'GG.YY', 'GGGYY', 'GGGYY', '.GGY.', '..G..'],
          lambda cell, x, y: (4 + (x+y) % 2 if cell == 'G' else 3) if heatmap else (2 if cell == 'G' else 3))
    return dict(schema='ironmate-pixel-grid/1', width=16, height=16, colors=COLORS, pixels=pixels)


def app_grid(size=32):
    """Pixel 3D on an opaque square; padded content fits the maskable safe circle."""
    art = grid()
    colors = COLORS + ['#001C22FF', '#FFFFFFFF']
    pixels = [[0] * size for _ in range(size)]
    offset = (size - 16) // 2
    for j, row in enumerate(art['pixels']):
        for i, value in enumerate(row):
            if value:
                pixels[j+offset+1][i+offset+1] = 6
    for j, row in enumerate(art['pixels']):
        for i, value in enumerate(row):
            if value:
                pixels[j+offset][i+offset] = value
    for x, y in ((1, 7), (2, 7), (3, 7), (4, 7), (6, 1), (10, 1), (10, 2)):
        pixels[y+offset][x+offset] = 7
    return dict(schema='ironmate-pixel-grid/1', width=size, height=size, colors=colors, pixels=pixels)


def cells(art, x=0, y=0, scale=1, foreground=False):
    return ''.join(f'<rect x="{x+i*scale}" y="{y+j*scale}" width="{scale}" height="{scale}" fill="{art["colors"][v][:7]}"/>'
                   for j, row in enumerate(art['pixels']) for i, v in enumerate(row) if not foreground or v)


def svg(body, width, height, view_width=None, view_height=None):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {view_width or width} {view_height or height}" role="img" aria-label="Ironmate: I’m, beginner mark apostrophe" shape-rendering="crispEdges">'
            '<title>Ironmate — I’m with a beginner mark apostrophe</title>' + body + '</svg>\n')


def main():
    target = ROOT / 'studio/brand'
    target.mkdir(exist_ok=True)
    art = grid()
    palettes = {
        'mono': ['#FFFFFF', '#10201C', '#10201C', '#10201C', '#10201C', '#10201C'],
        'dark-green': [color[:7] for color in COLORS],
        'famicom': ['#F7EFDF', '#651D2D', '#009967', '#DED43C', '#009967', '#DED43C'],
        'gameboy': ['#D8E6A3', '#244D36', '#77994C', '#ABC65E', '#77994C', '#ABC65E'],
        'heatmap': [color[:7] for color in COLORS],
        'pixel-3d': [color[:7] for color in COLORS],
    }
    for style, palette in palettes.items():
        variant = grid(style == 'heatmap')
        variant['colors'] = palette
        if style in ('famicom', 'gameboy', 'pixel-3d'):
            body = f'<rect width="20" height="20" fill="{palette[0]}"/>'
            if style == 'pixel-3d':
                body += ''.join(f'<rect x="{i+3}" y="{j+3}" width="1" height="1" fill="#001C22"/>'
                                for j, row in enumerate(variant['pixels']) for i, v in enumerate(row) if v)
            else:
                body += f'<path d="M2 0h16v1h1v1h1v16h-1v1h-1v1H2v-1H1v-1H0V2h1V1h1z M2 2v16h16V2z" fill="{palette[1]}" fill-rule="evenodd"/>'
            body += cells(variant, 2, 2, foreground=True)
            if style == 'pixel-3d':
                body += '<path d="M3 9h4v1H3z M8 3h1v1H8z M12 3h1v2h-1z" fill="#FFFFFF"/>'
            (target / f'{style}.svg').write_text(svg(body, 320, 320, 20, 20))
        else:
            (target / f'{style}.svg').write_text(svg(cells(variant), 256, 256, 16, 16))
    (target / 'icon.svg').write_text(svg(cells(art), 32, 32, 16, 16))
    payloads = [to_png(art, scale) for scale in (1, 2, 3)]
    for size, payload in zip((16, 32, 48), payloads):
        (target / f'favicon-{size}.png').write_bytes(payload)
    (target / 'icon-192.png').write_bytes(to_png(art, 12))
    for filename, base, scale in (('app-192.png', 32, 6), ('app-512.png', 32, 16),
                                  ('app-maskable-512.png', 32, 16), ('apple-touch-icon.png', 30, 6)):
        (target / filename).write_bytes(to_png(app_grid(base), scale))
    manifest = dict(id='../', name='Ironmate', short_name='Ironmate', lang='ja',
                    start_url='../', scope='../', display='standalone',
                    theme_color='#003D32', background_color='#EDF0EC',
                    icons=[dict(src='app-192.png', sizes='192x192', type='image/png', purpose='any'),
                           dict(src='app-512.png', sizes='512x512', type='image/png', purpose='any'),
                           dict(src='app-maskable-512.png', sizes='512x512', type='image/png', purpose='maskable')],
                    shortcuts=[dict(name='画像を作る', url='../'),
                               dict(name='スライドを作る', url='../slides/'),
                               dict(name='ドット絵・画像一覧', url='../tools/')])
    (target / 'manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    offset = 6 + 16 * len(payloads)
    entries = []
    for size, payload in zip((16, 32, 48), payloads):
        entries.append(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(payload), offset))
        offset += len(payload)
    (target / 'favicon.ico').write_bytes(struct.pack('<HHH', 0, 1, 3) + b''.join(entries) + b''.join(payloads))
    glyphs = {
        'I': ['11111', '..1..', '..1..', '..1..', '..1..', '..1..', '11111'],
        'r': ['.....', '.....', '1.11.', '11..1', '1....', '1....', '1....'],
        'o': ['.....', '.....', '.111.', '1...1', '1...1', '1...1', '.111.'],
        'n': ['.....', '.....', '1111.', '1...1', '1...1', '1...1', '1...1'],
        'm': ['.....', '.....', '11.1.', '1.1.1', '1.1.1', '1.1.1', '1.1.1'],
        'a': ['.....', '.....', '.111.', '....1', '.1111', '1...1', '.1111'],
        't': ['..1..', '..1..', '11111', '..1..', '..1..', '..1..', '...11'],
        'e': ['.....', '.....', '.111.', '1...1', '11111', '1....', '.111.'],
    }
    for filename, style in (('readme.svg', 'famicom'), ('hero.svg', 'heatmap')):
        palette = palettes[style]
        variant = grid(style == 'heatmap')
        variant['colors'] = palette
        body = f'<rect width="280" height="80" fill="{palette[0]}"/>' + cells(variant, 8, 8, 4)
        if style == 'famicom':
            body += f'<path d="M6 2h268v2h2v2h2v68h-2v2h-2v2H6v-2H4v-2H2V6h2V4h2z M6 6v68h268V6z" fill="{palette[1]}" fill-rule="evenodd"/>'
        for k, letter in enumerate('Ironmate'):
            body += ''.join(f'<rect x="{84+k*23+i*3}" y="{28+j*3}" width="3" height="3" fill="{palette[1]}"/>'
                            for j, row in enumerate(glyphs[letter]) for i, v in enumerate(row) if v == '1')
        (target / filename).write_text(svg(body, 560, 160, 280, 80))


if __name__ == '__main__':
    main()
