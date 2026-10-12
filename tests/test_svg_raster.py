"""SVG input subset: what rasterizes exactly, what is rejected and why."""
import pytest

import grid_svg
import pixel_grid
import svg_raster as sr
from svg_raster import SvgError, rasterize

NS = 'xmlns="http://www.w3.org/2000/svg"'


def _svg(body, box='0 0 4 4', extra=''):
    return f'<svg {NS} viewBox="{box}"{extra}>{body}</svg>'


def _px(rows, x, y):
    return tuple(rows[y][x * 4:x * 4 + 4])


def test_rect_flat_fill_exact():
    w, h, rows = rasterize(_svg('<rect x="1" y="1" width="2" height="1" fill="#f00"/>'))
    assert (w, h) == (4, 4)
    assert _px(rows, 1, 1) == (255, 0, 0, 255) and _px(rows, 0, 0) == (0, 0, 0, 0)


def test_fill_opacity_and_group_inheritance():
    svg = _svg('<g fill="#00ff00" fill-opacity="0.5" transform="translate(1,0)"><rect width="1" height="1"/></g>')
    assert _px(rasterize(svg)[2], 1, 0) == (0, 255, 0, 128)


def test_grid_svg_output_rasterizes_exactly():
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'C06', 'outline', 20)
        w, h, rows = rasterize(grid_svg.to_svg(art))
        want = [b''.join(bytes.fromhex(art['colors'][v][1:]) for v in row) for row in art['pixels']]
        assert rows == want


@pytest.mark.parametrize('body', [
    '<circle cx="2" cy="2" r="1.5" fill="#123456"/>',
    '<ellipse cx="2" cy="2" rx="2" ry="1" fill="#abc" opacity="0.7"/>',
    '<polygon points="0,0 4,0 2,4" fill="#0f0" fill-opacity="0.3"/>',
])
def test_curved_shapes_supersampled_stdlib_equals_numpy(body):
    pytest.importorskip('numpy')
    svg = _svg(body, '0 0 9 9')
    assert rasterize(svg, backend='stdlib') == rasterize(svg, backend='numpy')


def test_width_scales_output():
    w, h, rows = rasterize(_svg('<rect width="4" height="2"/>', '0 0 4 2'), width=8)
    assert (w, h) == (8, 4)


@pytest.mark.parametrize('body, match', [
    ('<path d="M0 0L4 4"/>', 'path'),
    ('<line x1="0" y1="0" x2="4" y2="4"/>', 'line'),
    ('<polyline points="0,0 1,1"/>', 'polyline'),
    ('<defs><linearGradient id="a"/></defs>', 'defs|linearGradient'),
    ('<rect width="1" height="1" fill="url(#a)"/>', 'gradient'),
    ('<rect width="1" height="1" style="fill:red"/>', 'CSS'),
    ('<rect width="1" height="1" class="x"/>', 'CSS'),
    ('<script>alert(1)</script>', 'script'),
    ('<image href="http://example.com/x.png"/>', 'image'),
    ('<text>hi</text>', 'text'),
    ('<rect width="1" height="1" rx="0.2"/>', 'rx'),
    ('<rect width="1" height="1" stroke="#000"/>', 'stroke'),
    ('<rect width="1em" height="1"/>', 'number'),
    ('<g transform="rotate(45)"><rect width="1" height="1"/></g>', 'translate'),
    ('<rect width="1" height="1" fill="red"/>', 'unsupported fill'),
    ('<blink/>', 'unsupported'),
])
def test_unsupported_features_fail_with_reason(body, match):
    with pytest.raises(SvgError, match=match):
        rasterize(_svg(body))


@pytest.mark.parametrize('data, match', [
    ('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg/>', 'DOCTYPE|ENTITY'),
    ('<!doctype svg><svg/>', 'DOCTYPE'),
    ('<html/>', 'svg'),
    (f'<svg {NS}/>', 'viewBox'),
    ('<svg', 'XML'),
    (f'<svg {NS} viewBox="0 0 5000 5000"/>', 'pixels'),
])
def test_unsafe_or_malformed_documents_rejected(data, match):
    with pytest.raises(SvgError, match=match):
        rasterize(data)


def test_size_limit():
    with pytest.raises(SvgError, match='bytes'):
        rasterize(b' ' * (sr.MAX_BYTES + 1))
