import base64, json, subprocess, sys
from pathlib import Path

import pytest

import grid_png as gp
import photo_grid
import pixel_grid

ROOT = Path(__file__).resolve().parents[1]


def _cells(art, scale=1):
    rgba = [bytes.fromhex(c[1:]) for c in art['colors']]
    return [b''.join(rgba[v] * scale for v in row) for row in art['pixels'] for _ in range(scale)]


@pytest.mark.parametrize('scale', [1, 3])
def test_round_trip_through_stdlib_decoder(scale):
    for mask in pixel_grid.MASKS:
        art = pixel_grid.render(mask, 'water', 'shadow', 16)
        data = gp.to_png(art, scale)
        assert data == gp.to_png(art, scale)
        w, h, rows = photo_grid.decode_png(data)
        assert (w, h) == (16 * scale, 16 * scale)
        assert rows == _cells(art, scale)
        assert rows[0][3] == 0  # index 0 stays transparent


def test_png_grid_png_round_trip_is_identical():
    art = pixel_grid.render('circle', 'lava', 'outline', 32)
    back = photo_grid.convert(base64.b64encode(gp.to_png(art)).decode(), size=32, colors=16)
    assert _cells(back) == _cells(art)
    raw = photo_grid.convert(gp.to_png(art), size=32, colors=16)  # plain PNG bytes, no Base64
    assert raw == back


@pytest.mark.parametrize('art,kw', [
    (pixel_grid.render(size=8), {'scale': 0}), (pixel_grid.render(size=8), {'scale': 65}),
    (pixel_grid.render(size=8) | {'width': 9}, {}), (pixel_grid.render(size=8) | {'colors': ['#000']}, {}),
    (pixel_grid.render(size=128), {'scale': 64})])
def test_invalid(art, kw):
    with pytest.raises(ValueError):
        gp.to_png(art, **kw)


def test_plain_png_file_and_oversize():
    data = gp.to_png(pixel_grid.render(size=8))
    with pytest.raises(ValueError, match='exceeds'):
        photo_grid.convert(data, size=8, max_bytes=len(data) - 1)


def test_cli_png_outputs(tmp_path):
    art = pixel_grid.render('rock', 'snow', 'normal', 8)
    png = tmp_path / 'in.png'
    png.write_bytes(gp.to_png(art))
    b64 = tmp_path / 'in.b64'
    b64.write_text('data:image/png;base64,' + base64.b64encode(png.read_bytes()).decode(), encoding='ascii')
    photo = [sys.executable, '-S', str(ROOT / 'photo_grid.py')]
    outs = []
    for src in (png, b64):
        out = tmp_path / f'{src.suffix[1:]}-out.png'
        r = subprocess.run(photo + [str(src), '--size', '8', '--format', 'png', '--scale', '2', '-o', str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == '', r.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    assert photo_grid.decode_png(outs[0])[:2] == (16, 16)
    j = subprocess.run(photo + [str(png), '--size', '8'], capture_output=True, text=True)
    assert _cells(json.loads(j.stdout)) == _cells(art)
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'pixel_grid.py'), '--mask', 'rock', '--palette', 'snow',
                        '--size', '8', '--format', 'png'], capture_output=True)
    assert r.returncode == 0 and r.stdout == gp.to_png(art)
    jf = tmp_path / 'a.json'
    jf.write_text(json.dumps(art), encoding='utf-8')
    r = subprocess.run([sys.executable, '-S', str(ROOT / 'grid_png.py'), str(jf)], capture_output=True)
    assert r.returncode == 0 and r.stdout == gp.to_png(art)


def test_inert_import(tmp_path):
    probe = 'import sys;sys.path.insert(0,sys.argv[1]);import grid_png'
    r = subprocess.run([sys.executable, '-S', '-c', probe, str(ROOT)], cwd=tmp_path, capture_output=True)
    assert r.returncode == 0 and r.stdout == r.stderr == b'' and list(tmp_path.iterdir()) == []
