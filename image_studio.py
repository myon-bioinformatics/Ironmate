"""Local image composition studio and exact cell-average mosaic helpers (stdlib).

    python -S image_studio.py
    python -S image_studio.py --heatmap matrix.json -o scene.json

The server serves only four fixed UI assets on loopback; it never accepts uploads
or writes files. Browser exports are explicit downloads. Existing grid tools own
PNG encoding; numeric source data is kept separate from its display colors.
"""
from __future__ import annotations

import argparse
import json
import math
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


class StudioHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        assets = {'/': ('index.html', 'text/html'), '/core.js': ('core.js', 'text/javascript'),
                  '/studio.js': ('studio.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        resource = assets.get(self.path.split('?', 1)[0])
        if resource is None:
            self.send_error(404)
            return
        filename, mime = resource
        payload = (ROOT / 'studio' / filename).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src data: blob:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--heatmap', type=Path)
    p.add_argument('-o', '--output', type=Path)
    p.add_argument('--force', action='store_true')
    args = p.parse_args(argv)
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
