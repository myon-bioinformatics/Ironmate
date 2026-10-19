"""Screenshots of the same pages in many browsers -> one comparison sheet, tiles and a report.

Reads a browser-test-kit ``platform-apps`` result tree (any depth), where each
screenshot sits at ``.../<page>/<OS>-<browser>-<profile>/<shot>.png``, and writes:

- ``sheet.png``: rows = pages, columns = environments, one tile each (empty = gray);
- ``tiles/<page>/<env>.png`` and ``index.html``: the same grid with labels;
- ``report.json`` (``ironmate-browser-matrix/1``): source path, SHA-256 and size per
  cell, plus the tile difference from the reference environment.

Tiles are area-sampled to a common width and cropped or padded (white) to a common
height, because device pixel ratios differ (iPhone 3x, Pixel 2.625x). The difference
is RGB MAE/RMSE between tiles, a screen-level hint for "this engine draws the page
differently", not a pixel-exact regression gate. Standard library only.

    python -S browser_matrix.py app-results --out matrix [--shot width-390] [--reference Linux-chromium-desktop]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import struct
import sys
import zlib
from pathlib import Path

from image_compare import metrics
from photo_grid import decode_png

SCHEMA = 'ironmate-browser-matrix/1'
MAX_INPUT_BYTES = 32 * 1024 * 1024
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}')
GAP, BACKGROUND, EMPTY = 4, (255, 255, 255, 255), (224, 224, 224, 255)


def find_shots(root, shot='width-390'):
    """{(page, env): path} for every ``<page>/<env>/<shot>.png`` under ``root``."""
    if not _NAME.fullmatch(shot):
        raise ValueError('shot must be a plain file stem such as width-390')
    found = {}
    for path in sorted(Path(root).rglob(shot + '.png')):
        page, env = path.parent.parent.name, path.parent.name
        if not (_NAME.fullmatch(page) and _NAME.fullmatch(env)) or path.is_symlink():
            continue
        if (page, env) in found:
            raise ValueError(f'two screenshots for {page} / {env}: {found[page, env]} and {path}')
        found[page, env] = path
    return found


def tile(width, height, rows, tile_w, tile_h):
    """Area-sample to ``tile_w`` wide (aspect kept), then crop/pad to ``tile_h`` (white)."""
    scaled_h = max(1, round(height * tile_w / width))
    out = bytearray(bytes(BACKGROUND) * (tile_w * tile_h))
    for ty in range(min(tile_h, scaled_h)):
        y0, y1 = ty * height // scaled_h, max(ty * height // scaled_h + 1, (ty + 1) * height // scaled_h)
        ys = range(y0, y1, max(1, (y1 - y0) // 4))  # at most ~4 rows per tile pixel
        for tx in range(tile_w):
            x0, x1 = tx * width // tile_w, max(tx * width // tile_w + 1, (tx + 1) * width // tile_w)
            xs = range(x0, x1, max(1, (x1 - x0) // 4))
            total, n = [0, 0, 0, 0], 0
            for y in ys:
                row = rows[y]
                for x in xs:
                    i = x * 4
                    for c in range(4):
                        total[c] += row[i + c]
                    n += 1
            o = (ty * tile_w + tx) * 4
            out[o:o + 4] = bytes((v + n // 2) // n for v in total)
    return tile_w, tile_h, bytes(out)


def encode_png(width, height, rgba):
    """8-bit RGBA PNG (filter 0); deterministic for the same pixels."""
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    stride = width * 4
    raw = b''.join(b'\x00' + rgba[y * stride:(y + 1) * stride] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def _blank(width, height, color):
    return width, height, bytes(color) * (width * height)


def build(shots, *, tile_w=160, tile_h=320, reference=None):
    """(report, sheet image, {(page, env): tile image}) from ``find_shots`` output."""
    if type(tile_w) is not int or type(tile_h) is not int or not (16 <= tile_w <= 640 and 16 <= tile_h <= 1280):
        raise ValueError('tile size must be 16..640 x 16..1280 pixels')
    if not shots:
        raise ValueError('no screenshots found')
    pages = sorted({p for p, _ in shots})
    envs = sorted({e for _, e in shots})
    if reference is None:
        reference = 'Linux-chromium-desktop' if 'Linux-chromium-desktop' in envs else envs[0]
    elif reference not in envs:
        raise ValueError(f'reference environment {reference!r} has no screenshots')
    tiles, cells = {}, []
    for (page, env), path in sorted(shots.items()):
        data = path.read_bytes()
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError(f'{path}: larger than 32MiB')
        width, height, rows = decode_png(data, max_pixels=4096 * 4096)
        tiles[page, env] = tile(width, height, rows, tile_w, tile_h)
        cells.append({'page': page, 'env': env, 'source': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                      'width': width, 'height': height})
    for cell in cells:
        base = tiles.get((cell['page'], reference))
        cell['difference'] = None if base is None else {
            k: round(v, 3) if isinstance(v, float) else v
            for k, v in metrics(base, tiles[cell['page'], cell['env']]).items()}
    sheet_w = len(envs) * tile_w + (len(envs) + 1) * GAP
    sheet_h = len(pages) * tile_h + (len(pages) + 1) * GAP
    sheet = bytearray(bytes(BACKGROUND) * (sheet_w * sheet_h))
    empty = _blank(tile_w, tile_h, EMPTY)
    for r, page in enumerate(pages):
        for c, env in enumerate(envs):
            _, _, rgba = tiles.get((page, env), empty)
            left, top = GAP + c * (tile_w + GAP), GAP + r * (tile_h + GAP)
            for y in range(tile_h):
                o = ((top + y) * sheet_w + left) * 4
                sheet[o:o + tile_w * 4] = rgba[y * tile_w * 4:(y + 1) * tile_w * 4]
    report = {'schema': SCHEMA, 'pages': pages, 'envs': envs, 'reference': reference,
              'tile': {'width': tile_w, 'height': tile_h, 'gap': GAP, 'fit': 'width, then crop or pad white'},
              'difference_definition': 'RGB MAE/RMSE (0-255) between tiles of the same page against the '
                                       'reference environment; a screen-level hint, not a pixel-exact gate',
              'missing': [{'page': p, 'env': e} for p in pages for e in envs if (p, e) not in tiles],
              'cells': cells}
    return report, (sheet_w, sheet_h, bytes(sheet)), tiles


def _index(report):
    head = ''.join(f'<th scope="col">{html.escape(e)}</th>' for e in report['envs'])
    cells = {(c['page'], c['env']): c for c in report['cells']}
    body = []
    for page in report['pages']:
        row = [f'<th scope="row">{html.escape(page)}</th>']
        for env in report['envs']:
            cell = cells.get((page, env))
            if cell is None:
                row.append('<td class="missing">no screenshot</td>')
                continue
            diff = cell['difference']
            note = 'reference' if env == report['reference'] else (
                'no reference' if diff is None else f"MAE {diff['rgb_mae']:.1f}")
            row.append(f'<td><img src="tiles/{html.escape(page)}/{html.escape(env)}.png" alt="{html.escape(page)} on '
                       f'{html.escape(env)}" width="{report["tile"]["width"]}"><br>{note}<br>'
                       f'{cell["width"]}x{cell["height"]}</td>')
        body.append('<tr>' + ''.join(row) + '</tr>')
    return ('<!doctype html><meta charset="utf-8"><title>Browser matrix</title><style>'
            'body{font:13px system-ui,sans-serif;margin:16px}table{border-collapse:collapse}'
            'th,td{border:1px solid #ccc;padding:4px;vertical-align:top;text-align:center}'
            '.missing{background:#eee;color:#666}</style>'
            f'<p>Reference: {html.escape(report["reference"])}. Differences are tile-level hints.</p>'
            f'<table><tr><th></th>{head}</tr>{"".join(body)}</table>\n')


def write(out, report, sheet, tiles):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'{out} must be a new or empty directory')
    for (page, env), image in tiles.items():
        target = out / 'tiles' / page / f'{env}.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode_png(*image))
    (out / 'sheet.png').write_bytes(encode_png(*sheet))
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'index.html').write_text(_index(report), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('root', type=Path, help='browser-test-kit app-results tree')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--shot', default='width-390', help='screenshot stem (initial, width-320, width-390, ...)')
    parser.add_argument('--reference', help='environment id to compare against (default Linux-chromium-desktop)')
    parser.add_argument('--tile', default='160x320', help='tile WIDTHxHEIGHT')
    args = parser.parse_args(argv)
    try:
        match = re.fullmatch(r'(\d+)x(\d+)', args.tile)
        if not match:
            raise ValueError('--tile must look like 160x320')
        report, sheet, tiles = build(find_shots(args.root, args.shot), tile_w=int(match[1]), tile_h=int(match[2]),
                                     reference=args.reference)
        write(args.out, report, sheet, tiles)
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(json.dumps({'pages': len(report['pages']), 'envs': len(report['envs']), 'cells': len(report['cells']),
                      'missing': len(report['missing']), 'reference': report['reference'], 'out': str(args.out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
