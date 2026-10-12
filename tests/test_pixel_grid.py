import json, re, subprocess, sys
from pathlib import Path

import pytest

import pixel_grid as p

ODD = (13, 15, 17, 23, 29, 31)


def _shape(grid):
    return [[bool(v) for v in row] for row in grid]


def _independent_quality(grid, vertical_symmetry, notch=False):
    """Re-check the core rule without pixel_grid helpers: margin, symmetry, 4-connected,
    no column gaps, and no 2x2 stairs on the top/bottom/left edges."""
    size = len(grid)
    cells = {(y, x) for y in range(size) for x in range(size) if grid[y][x]}
    assert cells and not any(grid[0]) and not any(grid[-1]) and all(r[0] == r[-1] == 0 for r in grid)
    assert all(row == row[::-1] for row in grid)
    if vertical_symmetry:
        assert grid == grid[::-1]
    stack, seen = [min(cells)], {min(cells)}
    while stack:
        y, x = stack.pop()
        for n in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if n in cells and n not in seen:
                seen.add(n)
                stack.append(n)
    assert seen == cells
    cols = sorted({x for _, x in cells})
    tops, bottoms = [], []
    for x in cols:
        ys = [y for y in range(size) if grid[y][x]]
        assert ys == list(range(ys[0], ys[-1] + 1))
        tops.append(ys[0])
        bottoms.append(ys[-1])
    lefts = [row.index(1) for row in grid if any(row)]
    if notch:  # cloud: the puff notch is a deliberate concave corner; check the edge below it
        drops = [a - b for a, b in zip(lefts, lefts[1:])]
        lefts = lefts[drops.index(max(drops)) + 1:]
    for profile in (tops, bottoms, lefts):
        steps = [b - a for a, b in zip(profile, profile[1:])]
        for i in range(len(steps) - 1):
            assert not (abs(steps[i]) >= 2 and steps[i + 1] == 0), (profile, i)
            assert not (steps[i] == 0 and abs(steps[i + 1]) >= 2), (profile, i)


@pytest.mark.parametrize('mask', p.MASKS)
def test_quality_rule_over_default_range(mask):
    low, high = p.MASK_BOUNDS[mask]
    for size in list(range(low, 97)) + [128, 160, 199, 256]:
        grid = p.silhouette(mask, size)
        assert p.mask_problem(mask, grid) is None
        _independent_quality(grid, mask in ('circle', 'diamond'), mask == 'cloud')


@pytest.mark.heavy
@pytest.mark.parametrize('mask', p.MASKS)
def test_quality_rule_over_whole_range(mask):
    low, high = p.MASK_BOUNDS[mask]
    for size in range(low, high + 1):
        _independent_quality(p.silhouette(mask, size), mask in ('circle', 'diamond'), mask == 'cloud')


def test_bounds_are_tight_below_and_reject_cleanly():
    for mask, (low, high) in p.MASK_BOUNDS.items():
        for bad in (low - 1, high + 1, 0, -3, True, 16.0, '16'):
            with pytest.raises(ValueError, match=f'{mask} needs an integer size from {low} to {high}'):
                p.silhouette(mask, bad)
    assert p.MASK_BOUNDS == {'triangle': (5, 256), 'diamond': (9, 256), 'cloud': (16, 256),
                             'circle': (6, 256), 'rock': (7, 256)}


def test_masks_are_distinct_and_recognizable():
    for size in range(16, 65):
        shapes = [p.silhouette(m, size) for m in p.MASKS]
        assert len({json.dumps(s) for s in shapes}) == len(p.MASKS)
    tri = p.silhouette('triangle', 31)
    widths = [sum(r) for r in tri if any(r)]
    assert widths == list(range(widths[0], widths[-1] + 1, 2)) and widths[0] <= 2
    cloud = p.silhouette('cloud', 31)
    tops = [min(y for y in range(31) if cloud[y][x]) for x in range(31) if any(cloud[y][x] for y in range(31))]
    assert sum(1 for i in range(1, len(tops) - 1) if tops[i] > tops[i - 1] and tops[i] >= tops[i + 1]) >= 2


@pytest.mark.parametrize('grid,reason', [
    ([[0, 0, 0, 0, 0], [0, 1, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], 'not 4-connected'),
    ([[0] * 6, [0, 1, 1, 0, 0, 0], [0, 1, 1, 1, 1, 0], [0] * 6, [0] * 6, [0] * 6], 'symmetric'),
    ([[1, 1, 1]] + [[0, 0, 0]] * 2, 'margin'),
    ([[0] * 9, [0, 0, 0, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0, 0], [0, 1, 1, 1, 1, 1, 1, 1, 0],
      [0, 1, 1, 1, 1, 1, 1, 1, 0], [0] * 9, [0] * 9, [0] * 9, [0] * 9], 'jagged edge'),
])
def test_quality_rule_rejects_artifacts(grid, reason):
    assert reason in p.mask_problem('rock', grid)


def test_old_nearest_neighbour_seed_fit_is_rejected_at_odd_sizes():
    # The previous fixed 13x5 cloud seed, enlarged by nearest neighbour, shows the 2x2 stairs
    # this rule forbids at most odd sizes.
    seed = ('0011100011100', '0111110111110', '1111111111111', '1111111111111', '0111111111110')
    rejected = 0
    for size in ODD:
        span = size - 2
        scale = min(span / 13, span / 5)
        w, h = max(1, round(13 * scale)), max(1, round(5 * scale))
        left, top = (size - w) // 2, (size - h) // 2
        grid = [[0] * size for _ in range(size)]
        for y in range(h):
            for x in range(w):
                grid[top + y][left + x] = int(seed[y * 5 // h][x * 13 // w])
        rejected += p.mask_problem('cloud', grid) is not None
    assert rejected >= len(ODD) - 1


def test_palettes_are_color_ids_with_derived_roles():
    assert list(p.PALETTES) == [f'C{i:02d}' for i in range(1, 11)]
    assert all(re.fullmatch(r'C\d\d', k) for k in p.PALETTE_BASE)
    assert p.PALETTE_BASE['C01'] == ('#5BBD3E', '#418A2D') and p.PALETTE_LABELS['C01'] == 'grass'
    assert p.PALETTES['C01'] == ('#00000000', '#5BBD3EFF', '#418A2DFF', '#9DD78BFF', '#214517FF')
    assert p.derive_palette('#FFFFFF', '#000000') == ('#00000000', '#FFFFFFFF', '#000000FF', '#FFFFFFFF', '#000000FF')
    assert p.derive_palette('#000000', '#010101')[3:] == ('#666666FF', '#010101FF')  # 102 = 2*255/5; 0.5 -> 1
    for pid, (main, shadow) in p.PALETTE_BASE.items():
        assert p.PALETTES[pid][0] == '#00000000' and p.PALETTES[pid][1:3] == (main + 'FF', shadow + 'FF')
    with pytest.raises(ValueError):
        p.render('circle', 'grass', 'normal', 16)


@pytest.mark.parametrize('size', ODD + p.SIZES[1:])
def test_render_effects_and_determinism(size):
    for mask in p.MASKS:
        if size < p.MASK_BOUNDS[mask][0]:
            continue
        plain = p.render(mask, 'C02', 'normal', size)
        for effect in p.EFFECTS:
            a = p.render(mask, 'C02', effect, size)
            assert a == p.render(mask, 'C02', effect, size)
            assert a['width'] == a['height'] == size and len(a['pixels']) == size
            assert _shape(a['pixels']) == _shape(plain['pixels'])
            assert all(0 <= v < 5 for r in a['pixels'] for v in r)
            assert len(p.emoji(a).splitlines()) == size
        points = [(y, x) for y, row in enumerate(plain['pixels']) for x, v in enumerate(row) if v]
        mid = (min(y for y, _ in points) + max(y for y, _ in points)) / 2
        shadow = p.render(mask, 'C02', 'shadow', size)['pixels']
        highlight = p.render(mask, 'C02', 'highlight', size)['pixels']
        outline = p.render(mask, 'C02', 'outline', size)['pixels']
        assert all(y > mid for y, x in points if shadow[y][x] == 2)
        assert all(y < mid for y, x in points if highlight[y][x] == 3)
        for y, x in points:
            edge = any(not plain['pixels'][yy][xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
            assert (outline[y][x] == 4) == edge


def test_filename_uses_color_id():
    assert p.filename(p.render('triangle', 'C01', 'shadow', 32)) == 'triangle_C01_shadow_32.png'
    assert p.filename(p.render('cloud', 'C10', 'normal', 17), 'svg') == 'cloud_C10_normal_17.svg'


@pytest.mark.parametrize('kwargs', [{'size': True}, {'size': 13}, {'mask': 'unknown'}, {'palette': 'unknown'},
                                    {'effect': 'unknown'}])
def test_invalid_selections(kwargs):
    with pytest.raises(ValueError):
        p.render(**kwargs)


def test_cli_and_inert_import(tmp_path):
    file = Path(p.__file__).resolve()
    result = subprocess.run([sys.executable, '-S', str(file), '--mask', 'circle', '--size', '23', '--format', 'json'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['width'] == 23
    bad = subprocess.run([sys.executable, '-S', str(file), '--mask', 'cloud', '--size', '8'],
                         cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode == 2 and 'cloud needs an integer size from 16 to 256' in bad.stderr
    result = subprocess.run([sys.executable, '-S', '-c', 'import sys;sys.path.insert(0,sys.argv[1]);import pixel_grid',
                             str(file.parent)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0 and result.stdout == result.stderr == b''
    assert list(tmp_path.iterdir()) == []
