import base64, json, struct, subprocess, sys, zlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import grid_svg as s
import pixel_grid

NS = '{http://www.w3.org/2000/svg}'
ROOT = Path(__file__).resolve().parents[1]


def _art(pixels, colors=('#00000000', '#FF0000FF', '#0000FF80')):
    return {'schema': 'ironmate-pixel-grid/1', 'width': len(pixels[0]), 'height': len(pixels),
            'colors': list(colors), 'pixels': pixels}


def _cover(svg):
    root = ET.fromstring(svg)
    cells = {}
    for r in root.iter(NS + 'rect'):
        x, y, w = int(r.get('x')), int(r.get('y')), int(r.get('width'))
        assert r.get('height') == '1'
        for i in range(w):
            assert (y, x + i) not in cells
            cells[(y, x + i)] = (r.get('fill'), r.get('fill-opacity'))
    return root, cells


def _expected(art):
    out = {}
    for y, row in enumerate(art['pixels']):
        for x, v in enumerate(row):
            c = art['colors'][v]
            if int(c[7:], 16):
                a = int(c[7:], 16)
                out[(y, x)] = ('#' + c[1:7].lower(), None if a == 255 else f'{a / 255:.4g}')
    return out


def test_cells_colors_transparency_and_runs():
    art = _art([[0, 1, 1, 2], [2, 2, 0, 1]])
    svg = s.to_svg(art, scale=4)
    root, cells = _cover(svg)
    assert root.get('viewBox') == '0 0 4 2' and root.get('width') == '16' and root.get('height') == '8'
    assert root.get('shape-rendering') == 'crispEdges'
    assert cells == _expected(art)
    assert len(list(root.iter(NS + 'rect'))) == 4
    assert cells[(0, 3)] == ('#0000ff', '0.502')
    assert (0, 0) not in cells and (1, 2) not in cells


def test_merge_equivalence_on_real_grids():
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'C03', 'outline', 32)
        merged, single = s.to_svg(art), s.to_svg(art, merge=False)
        assert _cover(merged)[1] == _cover(single)[1] == _expected(art)
        assert len(merged) < len(single)
        assert merged == s.to_svg(art)


def test_metadata_is_escaped():
    art = _art([[1]]) | {'palette': '<&"x">'}
    root = ET.fromstring(s.to_svg(art))
    assert '<&"x">' in root.find(NS + 'title').text


@pytest.mark.parametrize('art,kw', [
    (_art([[3]]), {}), (_art([[1, 1]]) | {'width': 3}, {}),
    (_art([[1]], ('#000000', '#FF0000FF')), {}), (_art([[1]]), {'scale': 0}), (_art([[1]]), {'scale': 65})])
def test_invalid(art, kw):
    with pytest.raises(ValueError):
        s.to_svg(art, **kw)


def _png_b64():
    raw = b''.join(b'\x00' + b''.join(bytes((255 * (x < 2), 0, 255 * (x >= 2), 255 * (y < 3))) for x in range(4))
                   for y in range(4))

    def chunk(k, b):
        return struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return base64.b64encode(data).decode()


def test_cli_end_to_end_from_base64_png(tmp_path):
    src = tmp_path / 'in.b64'
    src.write_text(_png_b64(), encoding='ascii')
    out = tmp_path / 'out.svg'
    cmd = [sys.executable, '-S', str(ROOT / 'photo_grid.py'), str(src), '--size', '8', '--colors', '2']
    r = subprocess.run(cmd + ['--format', 'svg', '--scale', '3', '-o', str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == '', r.stderr
    j = subprocess.run(cmd, capture_output=True, text=True)
    art = json.loads(j.stdout)
    root, cells = _cover(out.read_text(encoding='utf-8'))
    assert root.get('width') == '24' and cells == _expected(art)
    assert any(v == 0 for row in art['pixels'] for v in row)
    assert out.read_text(encoding='utf-8') == s.to_svg(art, 3)
    jf = tmp_path / 'a.json'
    jf.write_text(j.stdout, encoding='utf-8')
    r2 = subprocess.run([sys.executable, '-S', str(ROOT / 'grid_svg.py'), str(jf), '--scale', '3'],
                        capture_output=True, text=True)
    assert r2.returncode == 0 and r2.stdout == s.to_svg(art, 3)


def test_pixel_grid_cli_svg_and_inert_imports(tmp_path):
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'pixel_grid.py'), '--mask', 'circle', '--size', '8', '--format', 'svg'],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == s.to_svg(pixel_grid.render('circle', size=8))
    probe = ('import sys;sys.path.insert(0,sys.argv[1]);import pixel_grid, grid_svg;'
             'import photo_grid;assert "PIL" not in sys.modules')
    r = subprocess.run([sys.executable, '-S', '-c', probe, str(ROOT)], cwd=tmp_path, capture_output=True)
    assert r.returncode == 0 and r.stdout == r.stderr == b''
    assert list(tmp_path.iterdir()) == []
