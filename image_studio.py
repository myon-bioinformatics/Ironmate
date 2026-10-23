"""Local image composition studio and exact cell-average mosaic helpers (stdlib).

    python -S image_studio.py
    python -S image_studio.py --heatmap matrix.json -o scene.json
    python -S image_studio.py --render scene.json --format svg --scale 4 -o image.svg
    python -S image_studio.py --build-site build/site

The server serves only fixed public UI assets on loopback; it never accepts uploads
or writes files. Browser exports are explicit downloads. Existing grid tools own
PNG encoding; numeric source data is kept separate from its display colors.
The web editor runs without Python. Scene CLI rendering uses Node.js; PNG/Base64
also use installed Chrome through Node 22 built-in WebSocket (no runtime npm package).
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import json
import math
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = 'ironmate-image-studio/1'
PALETTE = ('#440154', '#3B528B', '#21918C', '#5EC962', '#FDE725')


def heat_color(value, low, high, levels=0):
    """Viridis-like five-stop display scale; source value is never modified."""
    if value is None:
        return None
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (value, low, high)) or low > high:
        raise ValueError('finite value and ordered range required')
    if type(levels) is not int or (levels != 0 and not 2 <= levels <= 256):
        raise ValueError('levels must be 0 (continuous) or 2..256')
    t = 0.5 if high == low else max(0, min(1, (value - low) / (high - low)))
    if levels:
        t = math.floor(t * (levels - 1) + 0.5) / (levels - 1)
    p = t * (len(PALETTE) - 1)
    i = min(len(PALETTE) - 2, int(p))
    a, b = (bytes.fromhex(c[1:]) for c in PALETTE[i:i + 2])
    return '#' + ''.join(f'{math.floor(x + (y-x)*(p-i) + 0.5):02X}' for x, y in zip(a, b))


def heatmap_scene(source):
    """Import a numeric matrix or ONE Plotly heatmap trace; row zero is at top.

    This imports data, not Plotly layout/axis rendering. Keep source metadata so
    the scene is an editable composition, never a replacement research result.
    """
    if isinstance(source, list):
        trace = {'z': source}
    elif isinstance(source, dict) and isinstance(source.get('data'), list):
        traces = [t for t in source['data'] if isinstance(t, dict) and t.get('type') == 'heatmap']
        if len(traces) != 1:
            raise ValueError('exactly one heatmap trace required')
        trace = traces[0]
    else:
        trace = source
    if not isinstance(trace, dict):
        raise ValueError('matrix or heatmap object required')
    z = trace.get('z')
    if (not isinstance(z, list) or not z or not isinstance(z[0], list) or not z[0]
            or len(z) * len(z[0]) > 4096 or any(not isinstance(r, list) or len(r) != len(z[0]) for r in z)):
        raise ValueError('rectangular matrix of 1..4096 cells required')
    finite = [v for row in z for v in row if v is not None]
    def safe(v):
        if type(v) is int:
            return abs(v) <= 2**53-1
        return type(v) is float and math.isfinite(v) and (not v.is_integer() or abs(v) <= 2**53-1)
    if any(not safe(v) for v in finite):
        raise ValueError('finite JavaScript-safe numbers or null required')
    low, high = trace.get('zmin'), trace.get('zmax')
    low = min(finite, default=0) if low is None else low
    high = max(finite, default=1) if high is None else high
    if not safe(low) or not safe(high):
        raise ValueError('finite JavaScript-safe color range required')
    heat_color(low, low, high)
    x, y = trace.get('x', list(range(len(z[0])))), trace.get('y', list(range(len(z))))
    if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(z[0]) or len(y) != len(z):
        raise ValueError('axis label counts do not match matrix')
    return {'schema': SCHEMA, 'width': 1280, 'height': 720, 'background': '#FFFFFF',
            'layers': [{'id': 'heatmap', 'kind': 'heatmap', 'name': 'Heatmap', 'x': 80, 'y': 90,
                        'w': 1120, 'h': 520, 'rotation': 0, 'opacity': 1,
                        'z': z, 'xlabels': x, 'ylabels': y, 'low': low, 'high': high,
                        'levels': 0, 'labels': True}], 'source': source}


def mosaic(artifact, cell=8, levels=256):
    """Area means of original RGBA blocks, alpha-weighted RGB, partial edges kept.

    Return a full-size indexed grid. Repeat calls on the ORIGINAL to change the
    resolution; mosaicing a mosaic does not restore lost information.
    """
    from grid_tools import canonical
    art = canonical(artifact)
    if type(cell) is not int or not 1 <= cell <= 512 or type(levels) is not int or not 2 <= levels <= 256:
        raise ValueError('cell 1..512, levels 2..256 required')
    colors = [tuple(bytes.fromhex(c[1:])) for c in art['colors']]
    width, height = art['width'], art['height']
    if width * height > 4194304:
        raise ValueError('mosaic input must be at most 4MP')
    pixels = [[0] * width for _ in range(height)]
    palette, index = [], {}
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            block = [colors[art['pixels'][j][i]] for j in range(y, min(y+cell, height)) for i in range(x, min(x+cell, width))]
            alpha = sum(p[3] for p in block)
            rgba = [math.floor(sum(p[c]*p[3] for p in block)/alpha + 0.5) if alpha else 0 for c in range(3)]
            rgba = [math.floor(math.floor(v/255*(levels-1)+0.5)/(levels-1)*255+0.5) for v in rgba]
            rgba.append(math.floor(alpha/len(block)+0.5))
            color = '#' + ''.join(f'{v:02X}' for v in rgba)
            if color not in index:
                index[color] = len(palette)
                palette.append(color)
            for j in range(y, min(y+cell, height)):
                pixels[j][x:min(x+cell, width)] = [index[color]] * min(cell, width-x)
    return {'schema': 'ironmate-pixel-grid/1', 'width': width, 'height': height, 'colors': palette, 'pixels': pixels}


def public_assets():
    """Explicit publication allowlist; no user scenes, globbing, or local images."""
    names = ('index.html', 'core.js', 'studio.js', 'style.css',
             'tools/index.html', 'tools/tools.css', 'tools/tools-core.js', 'tools/tools.js',
             'brand/index.html', 'brand/gallery.css', 'brand/mono.svg', 'brand/dark-green.svg',
             'brand/famicom.svg', 'brand/gameboy.svg', 'brand/pixel-3d.svg',
             'brand/manifest.webmanifest', 'brand/apple-touch-icon.png', 'brand/app-192.png',
             'brand/app-512.png', 'brand/app-maskable-512.png',
             'brand/icon.svg', 'brand/heatmap.svg', 'brand/hero.svg', 'brand/favicon.ico', 'brand/favicon-16.png',
             'brand/favicon-32.png', 'brand/favicon-48.png', 'brand/icon-192.png',
             'slides/package.js', 'slides/pptx.js', 'slides/slides.js', 'slides/slides.css')
    assets = {name: (ROOT / 'studio' / name).read_bytes() for name in names}
    from scripts.pages_catalog import catalog_script
    assets['tools/catalog.js'] = catalog_script()
    page = assets['index.html'].decode('utf-8')
    for name in ('style.css', 'core.js', 'studio.js', 'brand/icon.svg', 'brand/heatmap.svg', 'brand/favicon.ico',
                 'brand/manifest.webmanifest', 'brand/apple-touch-icon.png'):
        page = page.replace('"' + name + '"', '"../' + name + '"')
    page = page.replace('href="tools/"', 'href="../tools/"')
    page = page.replace('<a href="slides/">スライド・PPTX作成 ↗</a>', '<a href="../">Image Studio ↗</a>')
    page = page.replace('<body>', '<body data-mode="slides">').replace('画像にする。', 'スライドにする。')
    page = page.replace('IMAGE STUDIO / 01', 'SLIDE STUDIO / 03').replace('Ironmate — Image Studio', 'Ironmate — Slide Studio')
    extra = '<link rel="stylesheet" href="slides.css">' + ''.join(
        f'<script defer src="{name}"></script>' for name in ('package.js', 'pptx.js', 'slides.js'))
    page = page.replace('</head>', extra + '</head>')
    page = page.replace('</header>', '</header>' + (ROOT / 'studio/slides/panel.html').read_text())
    assets['slides/index.html'] = page.encode('utf-8')
    return assets


def build_site(directory):
    """Publish the allowlisted browser assets and generated procedural presets."""
    directory = Path(directory)
    payloads = public_assets()
    if directory.is_symlink() or (directory.exists() and (not directory.is_dir() or any(directory.iterdir()))):
        raise FileExistsError('site output must be a new or empty directory')
    directory.mkdir(parents=True, exist_ok=True)
    from grid_output import write_output
    for name, payload in payloads.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        write_output(str(directory / name), payload)
    write_output(str(directory / '.nojekyll'), b'')
    return directory


def _node_scene(scene, mode='svg', scale=1):
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for scene SVG rendering; it is not auto-installed')
    run = subprocess.run([node, str(ROOT / 'studio' / 'render.cjs')],
                         input=json.dumps({'scene': scene, 'mode': mode, 'scale': scale}, allow_nan=False),
                         text=True, capture_output=True, timeout=30)
    if run.returncode:
        raise ValueError(run.stderr.strip() or 'scene rendering failed')
    return run.stdout


def _processed_scene(scene):
    scene = json.loads(_node_scene(scene, 'validate'))
    for layer in scene['layers']:
        if layer['kind'] != 'image' or (layer['cell'] == 1 and layer['levels'] == 256):
            continue
        # Use original pixel dimensions; don't auto-infer a dot-art cell scale.
        from photo_grid import decode_png
        from grid_png import to_png
        width, height, rows = decode_png(base64.b64decode(layer['src'].split(',', 1)[1], validate=True), max_pixels=4194304)
        palette, indexes, pixels = [], {}, []
        for row in rows:
            line = []
            for x in range(width):
                color = '#' + bytes(row[x*4:x*4+4]).hex().upper()
                if color not in indexes:
                    indexes[color] = len(palette)
                    palette.append(color)
                line.append(indexes[color])
            pixels.append(line)
        art = {'schema': 'ironmate-pixel-grid/1', 'width': width, 'height': height, 'colors': palette, 'pixels': pixels}
        data = to_png(mosaic(art, layer['cell'], layer['levels']))
        layer['src'] = 'data:image/png;base64,' + base64.b64encode(data).decode()
    return scene


def _find_chrome(chrome=None):
    candidates = [chrome or os.environ.get('CHROME'), 'google-chrome', 'chromium', 'chromium-browser', 'chrome',
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if os.environ.get(key):
            candidates.append(str(Path(os.environ[key]) / 'Google/Chrome/Application/chrome.exe'))
    for candidate in filter(None, candidates):
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise RuntimeError('PNG/Base64 needs local Chrome/Chromium; use --chrome PATH (SVG needs Node.js only)')


def render_scene(scene, format='svg', scale=1, chrome=None, data_uri=False):
    """CPU-only SVG re-render; PNG uses installed headless Chrome, no GPU/AI API.

    The original scene is untouched. SVG remains vector; raster images can only
    interpolate their existing samples. Fonts are supplied by the host system.
    """
    if format not in ('svg', 'png', 'base64'):
        raise ValueError('format must be svg, png or base64')
    processed = _processed_scene(scene)
    svg = _node_scene(processed, scale=scale).encode()
    if format == 'svg':
        return svg
    return _png_output(raster_svg(svg, chrome=chrome), format, data_uri)


def _png_output(png, format='png', data_uri=False):
    if format == 'png':
        return png
    if len(png) > 32*1024*1024:
        raise ValueError('Flutter clipboard PNG must be at most 32MiB; reduce output scale')
    return (('data:image/png;base64,' if data_uri else '') + base64.b64encode(png).decode()).encode()


def raster_svg(svg, *, chrome=None):
    """Rasterize trusted, locally generated SVG using the Studio Chrome backend.

    This is not an arbitrary/untrusted SVG import API. Callers validate their
    source and dimensions; remote HTTP(S) resources are blocked by raster.cjs.
    """
    from xml.etree import ElementTree
    root = ElementTree.fromstring(svg)
    width, height = int(root.attrib['width']), int(root.attrib['height'])
    if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 16777216):
        raise ValueError('output must be each side <=8192px and <=16MP')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('PNG export requires Node.js 22 or newer')
    with tempfile.TemporaryDirectory(prefix='ironmate-studio-render-') as temp:
        directory = Path(temp)
        html = directory / 'render.html'
        html.write_bytes(b'<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>' + svg)
        command = [node, str(ROOT / 'studio' / 'raster.cjs'), _find_chrome(chrome),
                   str(html), str(directory / 'profile'), str(width), str(height)]
        run = subprocess.run(command, capture_output=True, timeout=40)
        if run.returncode:
            raise RuntimeError('Chrome PNG render failed: ' + run.stderr.decode(errors='replace')[-1000:])
        png = run.stdout
        if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (width, height):
            raise RuntimeError('Chrome returned unexpected PNG dimensions')
    if len(png) > 32*1024*1024:
        raise ValueError('PNG must be at most 32MiB; reduce output scale')
    return png



@lru_cache(maxsize=1)
def cached_public_assets():
    return public_assets()


class StudioHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        assets = cached_public_assets()
        route = self.path.split('?', 1)[0]
        filename = {'/': 'index.html', '/tools/': 'tools/index.html', '/slides/': 'slides/index.html', '/brand/': 'brand/index.html'}.get(route, route.lstrip('/'))
        if filename not in assets:
            self.send_error(404)
            return
        mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
                '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json'}[Path(filename).suffix]
        payload = assets[filename]
        self.send_response(200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if Path(filename).suffix in ('.html', '.js', '.css', '.svg') else ''))
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; manifest-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--port', type=int, default=8765)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--heatmap', type=Path)
    mode.add_argument('--render', type=Path, help='scene JSON -> SVG/PNG/Base64')
    mode.add_argument('--build-site', type=Path, help='write standalone GitHub Pages assets')
    p.add_argument('--format', choices=('svg', 'png', 'base64'), default='svg')
    p.add_argument('--scale', type=float, default=1)
    p.add_argument('--chrome', help='installed Chrome/Chromium executable')
    p.add_argument('--data-uri', action='store_true', help='prefix Base64 with data:image/png;base64,')
    p.add_argument('-o', '--output', type=Path)
    p.add_argument('--force', action='store_true')
    p.add_argument('--json', action='store_true',
                   help='on a fixable failure, write one JSON object to stderr; success output is unchanged')
    args = p.parse_args(argv)
    try:
        return _run_studio(p, args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        from ironmate_cli import emit_error
        return emit_error('image_studio.py', exc, json_mode=args.json)


def _run_studio(p, args):
    if args.build_site:
        print(build_site(args.build_site))
        return 0
    if args.render:
        data = render_scene(json.loads(args.render.read_text(encoding='utf-8')), args.format, args.scale, args.chrome, args.data_uri)
        if args.output:
            from grid_output import write_output
            write_output(str(args.output), data, args.force)
        else:
            sys.stdout.buffer.write(data)
        return 0
    if args.heatmap:
        if not args.output:
            p.error('--heatmap needs -o scene.json')
        from grid_output import write_output
        write_output(str(args.output), json.dumps(heatmap_scene(json.loads(args.heatmap.read_text(encoding='utf-8'))), ensure_ascii=False, allow_nan=False).encode(), args.force)
        return 0
    if not 0 <= args.port <= 65535:
        p.error('port must be 0..65535')
    with ThreadingHTTPServer(('127.0.0.1', args.port), StudioHandler) as server:
        print(f'Ironmate Studio: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
