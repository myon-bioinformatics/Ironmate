"""Arcade engine invariants, reference target vectors, and existing export integration."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

import grid_tools as g
from pixel_arcade_engine import InvaderSparseScanner, PacmanGhostProbes, ReversiblePixelGrid

ROOT = Path(__file__).resolve().parents[1]


def artifact(rows, colors=None):
    return {'schema': 'ironmate-pixel-grid/1', 'width': len(rows[0]), 'height': len(rows),
            'colors': colors or ['#00000000', '#FF0000FF', '#0000FFFF'], 'pixels': rows}


def assert_mask(grid):
    assert grid.active_mask == sum(1 << i for i, v in enumerate(grid.pixels) if grid.is_active(v))


@pytest.mark.parametrize('seed', range(10))
def test_random_swaps_restore_exact_pixels_mask_and_metadata(seed):
    rnd = random.Random(seed)
    art = artifact([[rnd.randrange(3) for _ in range(13)] for _ in range(9)])
    art['source'] = {'format': 'png', 'width': 13, 'height': 9}
    original = deepcopy(art)
    scanner = g.sparse(art)
    grid = scanner.grid
    before, mask = grid.pixels, grid.active_mask
    for _ in range(200):
        y, x = rnd.randrange(9), rnd.randrange(12)
        grid.swap_pixels_reversible(y * 13 + x, y * 13 + x + 1)
        assert_mask(grid)
        assert Counter(grid.pixels) == Counter(before)
    assert grid.rollback_all() > 0
    assert grid.pixels == before and grid.active_mask == mask
    assert grid.to_artifact() == original == art
    assert grid.rollback_all() == 0


def test_sparse_and_sentinel_do_not_read_pixel_array():
    grid = ReversiblePixelGrid(100, 100, [1 if i in (101, 5050, 9999) else 0 for i in range(10000)])

    class NoRead(list):
        def __iter__(self):
            raise AssertionError('full pixel scan')

        def __getitem__(self, key):
            raise AssertionError('pixel access')

    grid._pixels = NoRead(grid._pixels)
    hits = list(InvaderSparseScanner(grid).iter_active_coords())
    assert hits == [(101, 1, 1), (5050, 50, 50), (9999, 99, 99)]
    assert len(hits) == grid.active_count == 3
    assert grid.check_sentinel_collision()
    assert grid.check_sentinel_collision(1 << 5050)
    assert not grid.check_sentinel_collision(1 << 202)


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_formation_moves_once_per_active_cell_and_rolls_back(direction):
    rows = [[0] * 7 for _ in range(7)]
    rows[2][2:5], rows[3][2:5] = [1, 2, 1], [2, 1, 2]
    scanner = g.sparse(artifact(rows), quota_per_frame=4)
    grid, (dx, dy) = scanner.grid, direction
    before = grid.to_artifact()
    result = scanner.shift_formation_step_by_step(dx, dy)
    expected = [[0] * 7 for _ in range(7)]
    for y in range(7):
        for x in range(7):
            if rows[y][x]:
                expected[y + dy][x + dx] = rows[y][x]
    assert grid.to_artifact()['pixels'] == expected
    assert result['active_dots'] == 6 and result['frames_for_one_step'] == 2
    assert_mask(grid)
    grid.rollback_all()
    assert grid.to_artifact() == before


def test_frame_quota_changes_and_partial_step_can_be_rolled_back():
    art = artifact([[0] * 8, [0, 1, 2, 1, 2, 1, 0, 0], [0] * 8])
    scanner = g.sparse(art)
    frames = scanner.iter_shift_frames(1, 0)
    assert next(frames)['processed'] == 1
    scanner.quota_per_frame = 2
    assert next(frames)['processed'] == 3
    frames.close()
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == art
    assert scanner.shift_formation_step_by_step(1, 0)['frames_for_one_step'] == 3
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == art


@pytest.mark.parametrize('dx,dy,index', [(1, 0, 5), (-1, 0, 3), (0, 1, 7), (0, -1, 1)])
def test_overflow_is_atomic_and_distinct_from_border_contact(dx, dy, index):
    values = [0] * 9
    values[index] = 1
    grid = ReversiblePixelGrid(3, 3, values)
    scanner = InvaderSparseScanner(grid)
    assert grid.check_sentinel_collision()
    with pytest.raises(ValueError, match='outside'):
        scanner.shift_formation_step_by_step(dx, dy)
    assert grid.pixels == tuple(values) and grid.rollback_all() == 0
    # Touching an unrelated edge does not block a legal horizontal/vertical move.
    scanner.shift_formation_step_by_step(-dx, -dy)
    assert_mask(grid)
    grid.rollback_all()
    assert grid.pixels == tuple(values)


def test_empty_grid_and_invalid_inputs():
    scanner = InvaderSparseScanner(ReversiblePixelGrid(2, 2))
    assert list(scanner.iter_active_coords()) == []
    assert scanner.shift_formation_step_by_step(1, 0)['frames_for_one_step'] == 0
    for quota in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match='quota'):
            InvaderSparseScanner(scanner.grid, quota)
    for move in ((0, 0), (1, 1), (-1, 1), (2, 0), (True, 0)):
        with pytest.raises(ValueError, match='cardinal'):
            scanner.shift_formation_step_by_step(*move)
    for args in ((0, 2), (2, -1), (True, 2), (4097, 1), (2, 2, []), (1, 1, [-1])):
        with pytest.raises(ValueError):
            ReversiblePixelGrid(*args)
    for index in (-1, 4, True):
        with pytest.raises(ValueError):
            scanner.grid.swap_pixels_reversible(0, index)


def test_exact_probe_targets_and_guzuta_distance_boundary():
    probes = PacmanGhostProbes(corner_pos=(-2, -3))
    targets = probes.compute_targets(10, 20, -1, 1, (2, 4), (13, 24))
    assert targets.akabei == (2, 4)
    assert targets.pinky == (6, 24)
    assert targets.aosuke == (14, 40)
    assert targets.guzuta == (-2, -3)  # Manhattan 7: retreat
    assert probes.compute_targets(10, 20, -1, 1, (2, 4), (14, 24)).guzuta == (14, 24)  # 8


def test_guzuta_thins_dense_blocks_but_keeps_isolated_feature():
    dense = artifact([[1] * 4 for _ in range(2)])
    naive = g.resize(dense, 2, 1, backend='stdlib')
    adaptive = g.downscale_2x(dense)
    assert naive['pixels'] == [[1, 1]]
    assert adaptive['pixels'] == [[1, 0]]
    assert dense['pixels'] == [[1] * 4 for _ in range(2)]
    isolated = artifact([[0, 0], [0, 2]])
    assert g.downscale_2x(isolated)['pixels'] == [[2]]
    assert g.downscale_2x(artifact([[0, 0], [0, 0]]))['pixels'] == [[0]]


def test_palette_permutation_preserves_visible_output_and_transparent_indices():
    art = artifact([[0, 1, 1, 2], [1, 2, 1, 0], [2, 1, 2, 1], [1, 2, 0, 2]])
    permutation = [2, 0, 1]
    renamed = deepcopy(art)
    renamed['colors'] = [art['colors'][1], art['colors'][2], art['colors'][0]]
    renamed['pixels'] = [[permutation[v] for v in row] for row in art['pixels']]
    assert g.cells(g.downscale_2x(art)) == g.cells(g.downscale_2x(renamed))
    more = artifact([[0, 1], [2, 3]], ['#FF0000FF', '#01020300', '#00000000', '#12345601'])
    scanner = g.sparse(more)
    assert list(scanner.iter_active_coords()) == [(0, 0, 0), (3, 1, 1)]
    scanner.grid.swap_pixels_reversible(0, 1)
    assert_mask(scanner.grid)
    scanner.grid.rollback_all()
    assert scanner.grid.to_artifact() == more


def test_opaque_zero_is_active_and_background_is_appended_only_if_needed():
    art = artifact([[0] * 4 for _ in range(2)], ['#FF0000FF'])
    scanner = g.sparse(art)
    assert scanner.grid.active_count == 8
    assert scanner.grid.to_artifact() == art
    out = g.downscale_2x(art)
    assert out['colors'] == ['#FF0000FF', '#00000000']
    assert out['pixels'] == [[0, 1]]


def test_adapter_copies_and_rejects_invalid_palette_or_shape():
    art = artifact([[0, 1], [2, 0]])
    grid = ReversiblePixelGrid.from_artifact(art)
    art['pixels'][0][0] = 2
    out = grid.to_artifact()
    out['colors'][0] = '#FFFFFFFF'
    assert grid.to_artifact()['pixels'][0][0] == 0
    assert grid.to_artifact()['colors'][0] == '#00000000'
    for changes in ({'schema': 'other'}, {'width': 3}, {'colors': []}, {'colors': ['red']},
                    {'pixels': [[0, -1], [0, 0]]}, {'pixels': [[0, 3], [0, 0]]},
                    {'pixels': [[0, True], [0, 0]]}):
        with pytest.raises(ValueError):
            ReversiblePixelGrid.from_artifact(dict(art, **changes))


@pytest.mark.parametrize('width,height', [(1, 2), (2, 1), (3, 4), (4, 3)])
def test_odd_or_tiny_dimensions_are_rejected_without_cropping(width, height):
    with pytest.raises(ValueError, match='even'):
        PacmanGhostProbes().adaptive_downscale_2x(ReversiblePixelGrid(width, height))


def test_existing_png_base64_svg_pipeline_after_filter_and_rollback():
    original = g.make('circle', 'C02', 'outline', 16)
    scanner = g.sparse(original, 10)
    scanner.shift_formation_step_by_step(1, 0)
    scanner.grid.rollback_all()
    assert g.restore(g.encode(scanner.grid.to_artifact()), backend='stdlib') == original
    small = g.resize(original, 8, method='probes')
    assert small == g.downscale_2x(original)
    assert small['resampling'] == 'pacman_probes_2x_lossy'
    for fmt in ('base64', 'png'):
        assert g.restore(g.encode(small, fmt, scale=3), backend='stdlib') == small
    assert g.cells(g.restore(g.encode(small, 'svg'), backend='stdlib')) == g.cells(small)
    # Existing default resize still has its existing round-trip behavior.
    assert g.resize(g.resize(original, 32), 16) == original
    with pytest.raises(ValueError, match='exact 2x'):
        g.resize(original, 7, method='probes')
    with pytest.raises(ValueError, match='method'):
        g.resize(original, 8, method='other')


def test_cli_stdlib_probe_png_round_trip_and_invalid_resize():
    cli = [sys.executable, '-S', '-m', 'grid_tools', 'make', 'circle', '--size', '16']
    result = subprocess.run(cli + ['--resize', '8', '--resize-method', 'probes', '--to', 'png'],
                            cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    restored = g.restore(result.stdout, backend='stdlib')
    assert restored == g.downscale_2x(g.make('circle', size=16))
    load = subprocess.run([sys.executable, '-S', '-m', 'grid_tools', 'load', '-', '--to', 'json'],
                          cwd=ROOT, input=result.stdout, capture_output=True)
    assert load.returncode == 0 and json.loads(load.stdout) == restored
    for args in (['--resize-method', 'probes'], ['--resize', '7', '--resize-method', 'probes'], ['--resize', '0']):
        bad = subprocess.run(cli + args, cwd=ROOT, capture_output=True)
        assert bad.returncode == 2 and b'Traceback' not in bad.stderr
