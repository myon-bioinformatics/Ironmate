"""Rasterize a small, safe subset of SVG to RGBA rows (stdlib; numpy optional). Python 3.11+.

Supported: <svg> with viewBox or width/height, <g> (translate only, inherited fill/fill-opacity),
<rect> (exact area coverage), <circle>/<ellipse>/<polygon> (4x4 supersampling per pixel),
solid fills (#rgb, #rrggbb, none) with fill-opacity/opacity, <title>/<desc>.
Everything else is rejected with an error naming the element/attribute. No import-time I/O.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET

__all__ = ['MAX_BYTES', 'MAX_PIXELS', 'SvgError', 'rasterize']
MAX_BYTES = 1024 * 1024
MAX_PIXELS = 1024 * 1024
_NS = '{http://www.w3.org/2000/svg}'
_SAMPLES = 4  # per axis for curved shapes and polygons
_NUMBER = re.compile(r'\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(px)?\s*', re.ASCII)
_TRANSLATE = re.compile(r'\s*translate\(\s*([^,\s)]+)(?:[\s,]+([^,\s)]+))?\s*\)\s*', re.ASCII)
_REASONS = {
    'path': 'path data (lines/curves/arcs) is not supported',
    'line': 'strokes are not supported', 'polyline': 'strokes are not supported',
    'linearGradient': 'gradients are not supported', 'radialGradient': 'gradients are not supported',
    'pattern': 'patterns are not supported', 'style': 'CSS is not supported',
    'script': 'scripts are not allowed', 'image': 'embedded/external images are not supported',
    'use': 'references (<use>) are not supported', 'text': 'text needs fonts and is not supported',
    'foreignObject': 'foreign content is not supported', 'filter': 'filters are not supported',
    'mask': 'masks are not supported', 'clipPath': 'clip paths are not supported',
    'defs': 'definitions are not supported', 'symbol': 'symbols are not supported',
}
_PAINT = {'fill', 'fill-opacity', 'opacity', 'id', 'stroke'}
_ATTRS = {
    'rect': {'x', 'y', 'width', 'height', 'rx', 'ry'}, 'circle': {'cx', 'cy', 'r'},
    'ellipse': {'cx', 'cy', 'rx', 'ry'}, 'polygon': {'points'},
    'g': {'transform', 'fill', 'fill-opacity', 'id'},
    'svg': {'width', 'height', 'viewBox', 'version', 'shape-rendering', 'preserveAspectRatio'},
}


class SvgError(ValueError):
    """The SVG is outside the supported subset or unsafe."""


def _num(value, what):
    match = _NUMBER.fullmatch(value or '')
    if not match:
        raise SvgError(f'{what}: unsupported number {value!r} (plain numbers or px only)')
    return float(match.group(1))


def _color(value):
    if value is None:
        return (0, 0, 0)  # SVG default fill is black
    value = value.strip()
    if value == 'none':
        return None
    if value.startswith('url('):
        raise SvgError('gradient/pattern fills (url(...)) are not supported')
    if re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    if re.fullmatch(r'#[0-9A-Fa-f]{3}', value):
        return tuple(int(c * 2, 16) for c in value[1:])
    raise SvgError(f'unsupported fill {value!r} (use #rgb, #rrggbb or none)')


def _opacity(value, what):
    if value is None:
        return 1.0
    number = _num(value, what)
    if not 0 <= number <= 1:
        raise SvgError(f'{what} must be between 0 and 1')
    return number


def _local(tag):
    if not isinstance(tag, str):
        raise SvgError('comments/processing instructions inside elements are not supported')
    if tag.startswith(_NS):
        return tag[len(_NS):]
    if tag.startswith('{'):
        raise SvgError(f'foreign namespace element {tag!r} is not supported')
    return tag


def _check_attrs(name, element):
    allowed = _ATTRS.get(name, set()) | (_PAINT if name in ('rect', 'circle', 'ellipse', 'polygon') else set())
    for key, value in element.attrib.items():
        if key.startswith('{'):
            raise SvgError(f'namespaced attribute {key!r} on <{name}> is not supported')
        if key not in allowed:
            reason = 'CSS is not supported' if key in ('style', 'class') else 'not supported'
            raise SvgError(f'attribute {key!r} on <{name}>: {reason}')
        if key == 'stroke' and value.strip() != 'none':
            raise SvgError('strokes are not supported (stroke must be none)')
        if key in ('rx', 'ry') and name == 'rect' and _num(value, key):
            raise SvgError('rounded rect corners (rx/ry) are not supported')


def _shapes(element, dx, dy, fill, fill_opacity, out):
    for child in element:
        name = _local(child.tag)
        if name in ('title', 'desc'):
            continue
        if name in _REASONS:
            raise SvgError(f'<{name}>: {_REASONS[name]}')
        if name not in _ATTRS or name == 'svg':
            raise SvgError(f'unsupported SVG element <{name}>')
        _check_attrs(name, child)
        if name == 'g':
            tx = ty = 0.0
            if 'transform' in child.attrib:
                match = _TRANSLATE.fullmatch(child.attrib['transform'])
                if not match:
                    raise SvgError('only transform="translate(x[,y])" is supported on <g>')
                tx, ty = _num(match.group(1), 'translate'), _num(match.group(2) or '0', 'translate')
            _shapes(child, dx + tx, dy + ty, child.attrib.get('fill', fill),
                    child.attrib.get('fill-opacity', fill_opacity), out)
            continue
        rgb = _color(child.attrib.get('fill', fill))
        alpha = (_opacity(child.attrib.get('fill-opacity', fill_opacity), 'fill-opacity')
                 * _opacity(child.attrib.get('opacity'), 'opacity'))
        a = child.attrib
        if name == 'rect':
            geom = ('rect', _num(a.get('x', '0'), 'x') + dx, _num(a.get('y', '0'), 'y') + dy,
                    _num(a.get('width'), 'width'), _num(a.get('height'), 'height'))
            if geom[3] < 0 or geom[4] < 0:
                raise SvgError('negative rect size')
        elif name == 'circle':
            r = _num(a.get('r'), 'r')
            geom = ('ellipse', _num(a.get('cx', '0'), 'cx') + dx, _num(a.get('cy', '0'), 'cy') + dy, r, r)
        elif name == 'ellipse':
            geom = ('ellipse', _num(a.get('cx', '0'), 'cx') + dx, _num(a.get('cy', '0'), 'cy') + dy,
                    _num(a.get('rx'), 'rx'), _num(a.get('ry'), 'ry'))
        else:
            values = [_num(v, 'points') for v in re.split(r'[\s,]+', a.get('points', '').strip()) if v]
            if len(values) < 6 or len(values) % 2:
                raise SvgError('polygon needs at least 3 x,y points')
            geom = ('polygon', [(values[i] + dx, values[i + 1] + dy) for i in range(0, len(values), 2)])
        if rgb is not None and alpha > 0:
            out.append((geom, rgb, alpha))


def _inside(geom, x, y):
    if geom[0] == 'ellipse':
        _, cx, cy, rx, ry = geom
        return rx > 0 and ry > 0 and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1
    points, hit = geom[1], False  # even-odd ray casting
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _coverage_stdlib(geom, width, height, sx, sy, ox, oy):
    """{(px, py): fraction} for one shape in pixel space."""
    cov = {}
    if geom[0] == 'rect':
        _, x, y, w, h = geom
        x0, x1, y0, y1 = (x - ox) * sx, (x + w - ox) * sx, (y - oy) * sy, (y + h - oy) * sy
        for py in range(max(0, int(y0)), min(height, int(y1) + 1)):
            fy = min(y1, py + 1) - max(y0, py)
            for px in range(max(0, int(x0)), min(width, int(x1) + 1)):
                fx = min(x1, px + 1) - max(x0, px)
                if fx > 0 and fy > 0:
                    cov[(px, py)] = fx * fy
        return cov
    step = 1 / _SAMPLES
    for py in range(height):
        for px in range(width):
            hits = sum(_inside(geom, (px + (i + 0.5) * step) / sx + ox, (py + (j + 0.5) * step) / sy + oy)
                       for j in range(_SAMPLES) for i in range(_SAMPLES))
            if hits:
                cov[(px, py)] = hits / _SAMPLES ** 2
    return cov


def _coverage_numpy(geom, width, height, sx, sy, ox, oy):
    import numpy as np
    if geom[0] == 'rect':
        return _coverage_stdlib(geom, width, height, sx, sy, ox, oy)
    offs = (np.arange(_SAMPLES) + 0.5) / _SAMPLES
    xs = ((np.arange(width)[:, None] + offs[None, :]).reshape(-1) / sx + ox)
    ys = ((np.arange(height)[:, None] + offs[None, :]).reshape(-1) / sy + oy)
    X, Y = np.meshgrid(xs, ys)
    if geom[0] == 'ellipse':
        _, cx, cy, rx, ry = geom
        hit = (((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 <= 1) if rx > 0 and ry > 0 else np.zeros_like(X, bool)
    else:
        hit = np.zeros_like(X, bool)
        points = geom[1]
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
            if y1 == y2:
                continue
            crosses = (y1 > Y) != (y2 > Y)
            hit ^= crosses & (X < (x2 - x1) * (Y - y1) / (y2 - y1) + x1)
    counts = hit.reshape(height, _SAMPLES, width, _SAMPLES).sum(axis=(1, 3))
    return {(int(px), int(py)): counts[py, px] / _SAMPLES ** 2 for py, px in zip(*np.nonzero(counts))}


def rasterize(data, width=None, backend='auto', max_bytes=MAX_BYTES, max_pixels=MAX_PIXELS):
    """SVG bytes/text -> (width, height, RGBA rows as bytes).

    Output size: ``width`` (height keeps the viewBox aspect) or the viewBox size rounded.
    ``backend``: 'stdlib', 'numpy' or 'auto' (numpy if importable); results are identical.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > max_bytes:
        raise SvgError(f'SVG exceeds {max_bytes} bytes')
    lowered = data.lower()
    if b'<!doctype' in lowered or b'<!entity' in lowered:
        raise SvgError('DOCTYPE/ENTITY declarations are not allowed')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SvgError(f'invalid XML: {exc}') from None
    if _local(root.tag) != 'svg':
        raise SvgError('root element must be <svg>')
    _check_attrs('svg', root)
    if 'viewBox' in root.attrib:
        parts = [_num(v, 'viewBox') for v in re.split(r'[\s,]+', root.attrib['viewBox'].strip())]
        if len(parts) != 4:
            raise SvgError('viewBox needs 4 numbers')
        ox, oy, vw, vh = parts
    else:
        ox = oy = 0.0
        if 'width' not in root.attrib or 'height' not in root.attrib:
            raise SvgError('<svg> needs a viewBox or both width and height')
        vw, vh = _num(root.attrib.get('width'), 'width'), _num(root.attrib.get('height'), 'height')
    if vw <= 0 or vh <= 0:
        raise SvgError('viewBox/width/height must be positive')
    out_w = round(vw) if width is None else width
    if type(out_w) is not int or out_w < 1:
        raise SvgError('width must be a positive integer')
    out_h = max(1, round(vh * out_w / vw))
    if out_w * out_h > max_pixels:
        raise SvgError(f'raster {out_w}x{out_h} exceeds {max_pixels} pixels')
    shapes = []
    _shapes(root, 0.0, 0.0, None, None, shapes)
    if backend == 'auto':
        try:
            import numpy  # noqa: F401
            backend = 'numpy'
        except ImportError:
            backend = 'stdlib'
    coverage = {'stdlib': _coverage_stdlib, 'numpy': _coverage_numpy}.get(backend)
    if coverage is None:
        raise ValueError('backend must be auto, stdlib or numpy')
    sx, sy = out_w / vw, out_h / vh
    acc = [[0.0, 0.0, 0.0, 0.0] for _ in range(out_w * out_h)]  # premultiplied RGBA, 0..1
    for geom, rgb, alpha in shapes:
        for (px, py), frac in coverage(geom, out_w, out_h, sx, sy, ox, oy).items():
            a = alpha * min(1.0, frac)
            cell = acc[py * out_w + px]
            for k in range(3):
                cell[k] = rgb[k] / 255 * a + cell[k] * (1 - a)
            cell[3] = a + cell[3] * (1 - a)
    rows = []
    for py in range(out_h):
        line = bytearray()
        for px in range(out_w):
            r, g, b, a = acc[py * out_w + px]
            alpha = round(a * 255)
            line += bytes((round(r / a * 255), round(g / a * 255), round(b / a * 255), alpha)) if alpha else bytes(4)
        rows.append(bytes(line))
    return out_w, out_h, rows
