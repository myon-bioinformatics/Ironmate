"""Local image composition studio and exact cell-average mosaic helpers (stdlib).

    python -S image_studio.py
    python -S image_studio.py --heatmap matrix.json -o scene.json
    python -S image_studio.py --render scene.json --format svg --scale 4 -o image.svg
    python -S image_studio.py --build-site build/site

The server serves only fixed public UI assets on loopback; it never accepts uploads
or writes files. Browser exports are explicit downloads. Existing grid tools own
PNG encoding; numeric source data is kept separate from its display colors.
The web editor runs without Python. Scene CLI rendering uses Node.js; PNG/Base64
also use installed Chrome through Node 26 built-in WebSocket (no runtime npm package).
"""
from __future__ import annotations

import argparse, base64, json, math, os, shutil, struct, subprocess, sys, tempfile
from functools import lru_cache; from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer; from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = 'ironmate-image-studio/1'

from ironlib.dragowing_heatmap import heatmap_scene


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


def host_rows() -> str:
    """🧰 What a host's header shows for a studio, as a JSON data block in the page (PySaiyanWeBoo chrome rows): one 💾 whose panel
    lists every format, one 📂, the temporary shelf under ⋯. The page carries no header of its own: it
    answers each key (``ui-chrome-action`` in studio.js) by pressing its own control. ``replaces`` names the page's own menus, which
    a host that shows these rows hides; without a host (the local server) they stay."""
    rows = lambda pairs: [{'label': label, 'key': key} for label, key in pairs]
    save = [('🖼 PNG', 'png'), ('🖼 PNG ×2', 'png-2'), ('🖼 PNG ×4', 'png-4'), ('🖼 PNG ×8', 'png-8'), ('📐 SVG', 'svg'),
            ('📦 JSON（再編集用）', 'json'), ('🕘 作業履歴', 'workspace'), ('🔤 Base64 / 渡す', 'base64')]
    opened = [('📦 JSON', 'open-json'), ('🕘 作業履歴', 'open-workspace')]
    spec = {'tools': {'💾': {'label': '保存', 'label_en': 'Save', 'links': rows(save)}, '📂': {'label': '開く', 'label_en': 'Open', 'links': rows(opened)}},
            'screen': rows([('📋 クリップボード・シェルフ', 'shelf')]),
            'replaces': '#studios,#studio-import,#studio-export'}
    return '<script type="application/json" id="ui-chrome-rows">' + json.dumps(spec, ensure_ascii=False).replace('<', '\\u003c') + '</script>'


def public_assets():
    """Explicit publication allowlist; no user scenes, globbing, or local images."""
    from ironlib.studio_bundle import BRAND_HTML, BROWSER_TASK_JS, PHONE_HTML, RECORDS_JS, STUDIO_HTML, STUDIO_JS, STYLE_CSS, TOOLS_HTML
    names = ('brand/mono.svg', 'brand/dark-green.svg',
             'brand/famicom.svg', 'brand/gameboy.svg', 'brand/pixel-3d.svg',
             'brand/manifest.webmanifest', 'brand/apple-touch-icon.png', 'brand/app-192.png',
             'brand/app-512.png', 'brand/app-maskable-512.png',
             'brand/icon.svg', 'brand/heatmap.svg', 'brand/hero.svg', 'brand/favicon.ico', 'brand/favicon-16.png',
             'brand/favicon-32.png', 'brand/favicon-48.png', 'brand/icon-192.png')
    assets = {name: (ROOT / 'studio' / name).read_bytes() for name in names}
    assets['index.html'] = STUDIO_HTML.replace('<header>', host_rows() + '<header>', 1).encode('utf-8')
    assets['style.css'] = STYLE_CSS.encode('utf-8')
    from scripts.pages_catalog import catalog_script
    assets['studio.js'] = STUDIO_JS.encode('utf-8') + b'\n' + catalog_script()
    assets['tools/index.html'] = TOOLS_HTML.encode('utf-8')
    assets['tools/async-task.js'] = BROWSER_TASK_JS.encode('utf-8')
    assets['tools/records.js'] = RECORDS_JS.encode('utf-8')
    assets['brand/index.html'] = BRAND_HTML.encode('utf-8')
    # 📽️ slides/ is the one slide editor (phone-first, the same page on a PC). slides/phone/ (its address before) and slides/pc/
    # (the PC studio it replaced) only send on to it, so old links and bookmarks keep working.
    assets['slides/index.html'] = PHONE_HTML.encode('utf-8')
    for old in ('slides/phone/index.html', 'slides/pc/index.html'):
        assets[old] = ('<!doctype html>\n<html lang="ja"><head><meta charset="utf-8" /><meta http-equiv="refresh" content="0; url=../" />'
                       '<link rel="canonical" href="../" /><title>Ironmate — Slides</title></head>'
                       '<body><a href="../">📽️</a></body></html>\n').encode('utf-8')
    return assets


def build_site(directory):
    """Publish the allowlisted browser assets and generated procedural presets."""
    directory = Path(directory)
    payloads = public_assets()
    if directory.is_symlink() or (directory.exists() and (not directory.is_dir() or any(directory.iterdir()))):
        raise FileExistsError('site output must be a new or empty directory')
    directory.mkdir(parents=True, exist_ok=True)
    from ironlib.grid_output import write_output
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
        from ironlib.grid_output import to_png
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
    source and dimensions; remote HTTP(S) resources are blocked by `render.cjs png`.
    """
    from xml.etree import ElementTree
    root = ElementTree.fromstring(svg)
    width, height = int(root.attrib['width']), int(root.attrib['height'])
    if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 16777216):
        raise ValueError('output must be each side <=8192px and <=16MP')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('PNG export requires Node.js 26 or newer')
    with tempfile.TemporaryDirectory(prefix='ironmate-studio-render-') as temp:
        directory = Path(temp)
        html = directory / 'render.html'
        html.write_bytes(b'<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>' + svg)
        command = [node, str(ROOT / 'studio' / 'render.cjs'), 'png', _find_chrome(chrome),
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
        filename = {'/': 'index.html', '/tools/': 'tools/index.html', '/slides/': 'slides/index.html', '/slides/pc/': 'slides/pc/index.html', '/slides/phone/': 'slides/phone/index.html', '/brand/': 'brand/index.html'}.get(route, route.lstrip('/'))
        if filename not in assets:
            self.send_error(404)
            return
        mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
                '.svg': 'image/svg+xml', '.png': 'image/png', '.gif': 'image/gif', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json'}[Path(filename).suffix]
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
    p.add_argument('--port', type=int, default=8765,help="port of the local studio on 127.0.0.1 (default: %(default)s)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--heatmap', type=Path,help="heatmap JSON -> scene JSON (needs -o)")
    mode.add_argument('--render', type=Path, help='scene JSON -> SVG/PNG/Base64')
    mode.add_argument('--build-site', type=Path, help='write standalone GitHub Pages assets')
    p.add_argument('--format', choices=('svg', 'png', 'base64'), default='svg',help="--render output format (default: %(default)s)")
    p.add_argument('--scale', type=float, default=1,help="--render scale (default: %(default)s)")
    p.add_argument('--chrome', help='installed Chrome/Chromium executable')
    p.add_argument('--data-uri', action='store_true', help='prefix Base64 with data:image/png;base64,')
    p.add_argument('-o', '--output', type=Path,help="output file (default: stdout)")
    p.add_argument('--force', action='store_true',help="replace an existing -o file")
    p.add_argument('--json', action='store_true',
                   help='on a fixable failure, write one JSON object to stderr; success output is unchanged')
    args = p.parse_args(argv)
    try:
        return _run_studio(p, args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        from ironlib.ironmate_cli import emit_error
        return emit_error('image_studio.py', exc, json_mode=args.json)


def _run_studio(p, args):
    if args.build_site:
        site = build_site(args.build_site)
        files = sorted(path for path in site.rglob('*') if path.is_file())
        for path in files:
            if path.suffix == '.html':
                print(f'{path.relative_to(site)}: {path.stat().st_size:,} bytes', file=sys.stderr)
        print(f'Public site (uncompressed): {sum(p.stat().st_size for p in files):,} bytes', file=sys.stderr)
        print(site)
        return 0
    if args.render:
        data = render_scene(json.loads(args.render.read_text(encoding='utf-8')), args.format, args.scale, args.chrome, args.data_uri)
        if args.output:
            from ironlib.grid_output import write_output
            write_output(str(args.output), data, args.force)
        else:
            sys.stdout.buffer.write(data)
        return 0
    if args.heatmap:
        if not args.output:
            p.error('--heatmap needs -o scene.json')
        from ironlib.grid_output import write_output
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
