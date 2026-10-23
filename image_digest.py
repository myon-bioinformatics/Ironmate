# image_digest.py
# __all__: 6
"""Many images with a status each -> one small, self-contained review page (and a Markdown summary).

Generic: rows and columns are any labels (pages x environments, cases x devices, slides x
themes). Input is ``ironmate-image-digest-input/1`` JSON; image paths are relative to it.

    {"schema": "ironmate-image-digest-input/1", "title": "...", "rows": ["home", ...],
     "cols": ["Linux-chromium-desktop", ...], "meta": {"build": "...", "link": "https://..."},
     "cells": [{"row": "home", "col": "...", "image": "shots/home.png", "status": "pass",
                "notes": ["320px:overlap"]}]}

Every image becomes a thumbnail embedded as a data URI, so the page is one file anyone can
open. Thumbnails start at ``--tile`` (default 64x128) and are halved in each direction (a
quarter of the pixels) until the page fits ``--max-bytes``; the size used is printed on the
page and in ``digest.json``. Status drives only colour and counts; it is never inferred from
pixels. Standard library only; image_digest.cjs is the Node entry point.

    python -S image_digest.py input.json --out digest/ [--max-bytes 1000000] [--tile 64x128]
    python -S image_digest.py input.json -o digest/          # -o and --output are the same as --out
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
from pathlib import Path
import re
import stat
import sys

from browser_matrix import encode_png, tile as thumbnail
from photo_grid import decode_png

__all__ = ['validate', 'page_html', 'summary_markdown', 'build', 'write', 'main']

SCHEMA = 'ironmate-image-digest-input/1'
OUT_SCHEMA = 'ironmate-image-digest/1'
MIN_TILE = (16, 32)
MAX_CELLS = 2000
MAX_IMAGE_BYTES = 32 * 1024 * 1024
_LABEL = re.compile(r'[^\x00-\x1f\x7f]{1,120}')
_STATUS = re.compile(r'[a-z][a-z0-9_-]{0,23}')


def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema') != SCHEMA:
        raise ValueError(f'expected schema {SCHEMA}')
    rows, cols, cells = spec.get('rows'), spec.get('cols'), spec.get('cells')
    for name, values in (('rows', rows), ('cols', cols)):
        if not isinstance(values, list) or not values or len(set(values)) != len(values) or not all(
                isinstance(v, str) and _LABEL.fullmatch(v) for v in values):
            raise ValueError(f'{name} must be distinct nonempty labels')
    if not isinstance(cells, list) or len(cells) > MAX_CELLS:
        raise ValueError(f'cells must be a list of at most {MAX_CELLS}')
    seen, out = set(), []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get('row') not in rows or cell.get('col') not in cols:
            raise ValueError('each cell needs a listed row and col')
        key = (cell['row'], cell['col'])
        if key in seen:
            raise ValueError(f'two cells for {key}')
        seen.add(key)
        status = cell.get('status', 'unknown')
        if not isinstance(status, str) or not _STATUS.fullmatch(status):
            raise ValueError(f'status must be a short lowercase token: {status!r}')
        image = cell.get('image')
        if image is not None and (not isinstance(image, str) or not image or Path(image).is_absolute()
                                  or '..' in Path(image).parts):
            raise ValueError(f'image must be a relative path inside the input directory: {image!r}')
        notes = cell.get('notes', [])
        if not isinstance(notes, list) or not all(isinstance(n, str) and len(n) <= 200 for n in notes):
            raise ValueError('notes must be short strings')
        out.append({'row': cell['row'], 'col': cell['col'], 'status': status, 'image': image, 'notes': notes[:6]})
    meta = spec.get('meta', {})
    if not isinstance(meta, dict) or not all(isinstance(v, str) and len(v) <= 300 for v in meta.values()):
        raise ValueError('meta must map names to short strings')
    link = meta.get('link')
    if link is not None and not re.fullmatch(r'https://[^\s"<>]+', link):
        raise ValueError('meta.link must be an https URL')
    title = spec.get('title', 'Image digest')
    if not isinstance(title, str) or not _LABEL.fullmatch(title):
        raise ValueError('title must be a short label')
    return {'title': title, 'rows': rows, 'cols': cols, 'cells': out, 'meta': meta}


def _thumbs(data, base, sizes):
    # Keep encoded thumbnails, not every full-resolution image, across shrink passes.
    root = Path(base).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('base must be an input directory')
    out, cache = {size: {} for size in sizes}, {}
    for cell in data['cells']:
        if not cell['image']:
            continue
        path = (root / cell['image']).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError(f'{cell["image"]}: image must stay inside the input directory')
        if path not in cache:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f'{cell["image"]}: image must be a regular file')
            if info.st_size > MAX_IMAGE_BYTES:
                raise ValueError(f'{cell["image"]}: larger than 32MiB')
            with path.open('rb') as stream:
                if os.fstat(stream.fileno()).st_size > MAX_IMAGE_BYTES:
                    raise ValueError(f'{cell["image"]}: larger than 32MiB')
                raw = stream.read(MAX_IMAGE_BYTES + 1)
            # A file may grow after the size check: the read is still bounded.
            if len(raw) > MAX_IMAGE_BYTES:
                raise ValueError(f'{cell["image"]}: larger than 32MiB')
            width, height, rows = decode_png(raw, max_pixels=4096 * 4096)
            cache[path] = {size: encode_png(*thumbnail(width, height, rows, *size)) for size in sizes}
            del raw, rows
        for size in sizes:
            out[size][cell['row'], cell['col']] = cache[path][size]
    return out


def _markdown_cell(value):
    text = html.escape(' '.join(value.split()), quote=False)
    return re.sub(r'([\\`*_\[\]])', r'\\\1', text).replace('|', '&#124;')


def page_html(data, thumbs, tile):
    cells = {(c['row'], c['col']): c for c in data['cells']}
    head = ''.join(f'<th>{html.escape(c)}</th>' for c in data['cols'])
    body = []
    for row in data['rows']:
        tds = [f'<th>{html.escape(row)}</th>']
        for col in data['cols']:
            cell = cells.get((row, col))
            if cell is None:
                tds.append('<td class="missing">not run</td>')
                continue
            img = ''
            if (row, col) in thumbs:
                img = (f'<img src="data:image/png;base64,{base64.b64encode(thumbs[row, col]).decode("ascii")}" '
                       f'width="{tile[0]}" height="{tile[1]}" alt=""><br>')
            notes = '<br>'.join(html.escape(n) for n in cell['notes'])
            tds.append(f'<td class="s-{cell["status"]}">{img}{html.escape(cell["status"])}'
                       + (f'<br><small>{notes}</small>' if notes else '') + '</td>')
        body.append('<tr>' + ''.join(tds) + '</tr>')
    meta = ' · '.join(f'{html.escape(k)} {html.escape(v)}' for k, v in data['meta'].items() if k != 'link')
    link = data['meta'].get('link')
    link_html = f' · <a href="{html.escape(link, quote=True)}">link</a>' if link else ''
    return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(data["title"])}</title><style>body{{font:13px system-ui,sans-serif;margin:8px}}'
            'table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:4px;vertical-align:top;text-align:center}'
            'td.s-fail,td.s-error{background:#ffebe9}td.missing{color:#666}small{color:#555}</style>'
            f'<h1>{html.escape(data["title"])}</h1><p>Thumbnails {tile[0]}x{tile[1]} px'
            + (f' · {meta}' if meta else '') + link_html + '. Thumbnails are for orientation, not pixel review.</p>'
            f'<table><tr><th></th>{head}</tr>{"".join(body)}</table>\n')


def summary_markdown(data, *, marker='<!-- ironmate-image-digest -->'):
    cells = {(c['row'], c['col']): c for c in data['cells']}
    total = len(data['rows']) * len(data['cols'])
    passed = sum(1 for c in data['cells'] if c['status'] == 'pass')
    meta = ', '.join(f'{k} {v}' for k, v in data['meta'].items() if k != 'link')
    link = data['meta'].get('link')
    lines = [marker, f'### {data["title"]}', '',
             f'{passed}/{total} passed' + (f'; {meta}' if meta else '') + '.' + (f' [Link]({link})' if link else ''),
             '', '| Row | Passed | Needs a look |', '| --- | --- | --- |']
    for row in data['rows']:
        ok = [c for c in data['cols'] if cells.get((row, c), {}).get('status') == 'pass']
        bad = []
        for col in data['cols']:
            cell = cells.get((row, col))
            if cell is None:
                bad.append(f'{col} (not run)')
            elif cell['status'] != 'pass':
                bad.append(f"{col} ({', '.join(cell['notes'][:2]) or cell['status']})")
        lines.append(f"| {_markdown_cell(row)} | {len(ok)}/{len(data['cols'])} | {_markdown_cell('; '.join(bad) or '-')} |")
    return '\n'.join(lines) + '\n'


def build(spec, base, *, max_bytes=1_000_000, tile=(64, 128)):
    """(page html, summary markdown, info) with thumbnails quartered until the page fits."""
    data = validate(spec)
    if type(max_bytes) is not int or not 20_000 <= max_bytes <= 20_000_000:
        raise ValueError('max_bytes must be 20000..20000000')
    if (not isinstance(tile, (tuple, list)) or len(tile) != 2 or not all(type(v) is int for v in tile)
            or not (MIN_TILE[0] <= tile[0] <= 640 and MIN_TILE[1] <= tile[1] <= 1280)):
        raise ValueError('tile must be within 16..640 x 32..1280 pixels')
    tile = tuple(tile)
    sizes = [tile]
    while sizes[-1] != MIN_TILE:
        w, h = sizes[-1]
        sizes.append((max(MIN_TILE[0], w // 2), max(MIN_TILE[1], h // 2)))
    thumbs = _thumbs(data, base, sizes)
    for tile in sizes:
        page = page_html(data, thumbs[tile], tile)
        size = len(page.encode('utf-8'))
        if size <= max_bytes or tile == MIN_TILE:
            break
    info = {'schema': OUT_SCHEMA, 'tile': list(tile), 'bytes': size, 'fits': size <= max_bytes,
            'rows': len(data['rows']), 'cols': len(data['cols']),
            'passed': sum(1 for c in data['cells'] if c['status'] == 'pass'),
            'statuses': {s: sum(1 for c in data['cells'] if c['status'] == s)
                         for s in sorted({c['status'] for c in data['cells']})}}
    return page, summary_markdown(data), info


def write(out, page, summary, info):
    out = Path(out)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise ValueError(f'{out} must be a new or empty directory')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'digest.html').write_text(page, encoding='utf-8')
    (out / 'summary.md').write_text(summary, encoding='utf-8')
    (out / 'digest.json').write_text(json.dumps(info) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('input', help=f'{SCHEMA} JSON; image paths are relative to it ("-" = stdin with --base)')
    parser.add_argument('--out', '-o', '--output', required=True, dest='out')
    parser.add_argument('--base', help='directory image paths are relative to (default: the input file directory)')
    parser.add_argument('--max-bytes', type=int, default=1_000_000)
    parser.add_argument('--tile', default='64x128', help='starting thumbnail WIDTHxHEIGHT')
    parser.add_argument('--json', action='store_true',
                        help='on a fixable failure, write one JSON object to stderr; success JSON is unchanged')
    args = parser.parse_args(argv)
    try:
        match = re.fullmatch(r'(\d+)x(\d+)', args.tile)
        if not match:
            raise ValueError('--tile must look like 64x128')
        if args.input == '-':
            if not args.base:
                raise ValueError('--base is required with stdin input')
            spec, base = json.loads(sys.stdin.buffer.read(8 * 1024 * 1024).decode('utf-8')), Path(args.base)
        else:
            spec, base = json.loads(Path(args.input).read_text(encoding='utf-8')), Path(args.base or Path(args.input).parent)
        page, summary, info = build(spec, base, max_bytes=args.max_bytes, tile=(int(match[1]), int(match[2])))
        write(args.out, page, summary, info)
    except (OSError, ValueError, UnicodeError) as error:
        from ironmate_cli import emit_error
        if args.json:
            return emit_error('image_digest.py', error, json_mode=True)
        print(f'error: {error}', file=sys.stderr)
        from ironmate_cli import hint_for
        hint = hint_for(error)
        if hint:
            print(f'hint: {hint}', file=sys.stderr)
        return 2
    print(json.dumps(info))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
