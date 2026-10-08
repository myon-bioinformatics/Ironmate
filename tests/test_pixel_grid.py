import json
import subprocess
import sys
from pathlib import Path

import pytest
import pixel_grid as p


def test_full_matrix_invariants_and_determinism():
    count = 0
    for mask in p.MASKS:
        for palette in p.PALETTES:
            for size in p.SIZES:
                plain = p.render(mask, palette, 'normal', size)
                silhouette = [[bool(x) for x in row] for row in plain['pixels']]
                for effect in p.EFFECTS:
                    a = p.render(mask, palette, effect, size)
                    assert a == p.render(mask, palette, effect, size)
                    assert len(a['pixels']) == size and all(len(r) == size for r in a['pixels'])
                    assert all(type(x) is int and 0 <= x < len(a['colors']) for r in a['pixels'] for x in r)
                    assert [[bool(x) for x in row] for row in a['pixels']] == silhouette
                    assert any(any(r) for r in a['pixels'])
                    assert not any(a['pixels'][0]) and not any(a['pixels'][-1])
                    assert all(r[0] == r[-1] == 0 for r in a['pixels'])
                    assert a['colors'][0] == '#00000000'
                    assert len(p.emoji(a).splitlines()) == size
                    count += 1
    assert count == 600


def test_effects_have_defined_positions():
    plain = p.render('circle', effect='normal')['pixels']
    shadow = p.render('circle', effect='shadow')['pixels']
    highlight = p.render('circle', effect='highlight')['pixels']
    outline = p.render('circle', effect='outline')['pixels']
    points = [(y, x) for y, row in enumerate(plain) for x, v in enumerate(row) if v]
    mid = (min(y for y, x in points) + max(y for y, x in points)) / 2
    assert all(y > mid for y, x in points if shadow[y][x] == 2)
    assert all(y < mid for y, x in points if highlight[y][x] == 3)
    assert any(outline[y][x] == 4 for y, x in points)
    assert any(outline[y][x] == 1 for y, x in points)
    for y, x in points:
        boundary = any(not plain[yy][xx] for yy, xx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)))
        assert (outline[y][x] == 4) == boundary


@pytest.mark.parametrize('kwargs', [{'size': True}, {'size': 17}, {'mask': 'unknown'}, {'palette': 'unknown'}, {'effect': 'unknown'}])
def test_invalid_selections(kwargs):
    with pytest.raises(ValueError):
        p.render(**kwargs)


def test_cli_and_inert_import(tmp_path):
    file = Path(p.__file__).resolve()
    result = subprocess.run([sys.executable, '-S', str(file), '--size', '8', '--format', 'json'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['width'] == 8
    result = subprocess.run([sys.executable, '-S', '-c', 'import sys;sys.path.insert(0,sys.argv[1]);import pixel_grid', str(file.parent)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0 and result.stdout == result.stderr == b''
    assert list(tmp_path.iterdir()) == []
