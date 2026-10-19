"""browser_matrix: browser-test-kit screenshots -> one sheet, tiles and a report."""
import json

import pytest

import browser_matrix as bm
from photo_grid import decode_png


def png(width, height, color):
    return bm.encode_png(width, height, bytes(color) * (width * height))


def tree(root, shots):
    for (page, env, name), (w, h, color) in shots.items():
        path = root / 'platform-app-x' / page / env / f'{name}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png(w, h, color))


def test_sheet_report_and_tiles_from_a_btk_tree(tmp_path):
    red, blue = (255, 0, 0, 255), (0, 0, 255, 255)
    tree(tmp_path / 'in', {
        ('flutter-home', 'Linux-chromium-desktop', 'width-384'): (384, 800, red),
        ('flutter-home', 'macOS-webkit-iphone', 'width-384'): (1152, 1992, red),   # 3x DPR, shorter viewport
        ('flutter-home', 'Windows-firefox-desktop', 'width-384'): (384, 800, blue),
        ('flutter-hub', 'Linux-chromium-desktop', 'width-384'): (384, 800, blue),
        ('flutter-hub', 'Linux-chromium-desktop', 'initial'): (1280, 800, blue),
    })
    shots = bm.find_shots(tmp_path / 'in')
    assert sorted(shots) == [('flutter-home', 'Linux-chromium-desktop'), ('flutter-home', 'Windows-firefox-desktop'),
                             ('flutter-home', 'macOS-webkit-iphone'), ('flutter-hub', 'Linux-chromium-desktop')]
    report, sheet, tiles = bm.build(shots, tile_w=40, tile_h=80)
    assert report['schema'] == 'ironmate-browser-matrix/1' and report['reference'] == 'Linux-chromium-desktop'
    assert report['pages'] == ['flutter-home', 'flutter-hub']
    assert report['missing'] == [{'page': 'flutter-hub', 'env': 'Windows-firefox-desktop'},
                                 {'page': 'flutter-hub', 'env': 'macOS-webkit-iphone'}]
    cells = {(c['page'], c['env']): c for c in report['cells']}
    assert cells['flutter-home', 'macOS-webkit-iphone']['width'] == 1152
    assert cells['flutter-home', 'Linux-chromium-desktop']['difference']['rgb_mae'] == 0
    # Same color, but the iPhone viewport is shorter: the bottom is padded white.
    assert 0 < cells['flutter-home', 'macOS-webkit-iphone']['difference']['rgb_mae'] < 50
    assert cells['flutter-home', 'Windows-firefox-desktop']['difference']['rgb_mae'] == pytest.approx(170, abs=0.5)
    assert sheet[:2] == (3 * 40 + 4 * bm.GAP, 2 * 80 + 3 * bm.GAP)
    assert tiles['flutter-home', 'Linux-chromium-desktop'][2][:4] == bytes(red)

    out = tmp_path / 'out'
    bm.write(out, report, sheet, tiles)
    w, h, rows = decode_png((out / 'sheet.png').read_bytes())
    assert (w, h) == sheet[:2]
    first_tile = bytes(rows[bm.GAP])[bm.GAP * 4:bm.GAP * 4 + 4]
    assert first_tile == bytes(red)
    assert json.loads((out / 'report.json').read_text(encoding='utf-8')) == report
    page = (out / 'index.html').read_text(encoding='utf-8')
    assert 'tiles/flutter-home/macOS-webkit-iphone.png' in page and 'no screenshot' in page and 'reference' in page
    with pytest.raises(ValueError, match='empty directory'):
        bm.write(out, report, sheet, tiles)
    (tmp_path / 'empty').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'empty', target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic link'):
        bm.write(tmp_path / 'link', report, sheet, tiles)
    assert not any((tmp_path / 'empty').iterdir())


def test_reference_choice_and_input_errors(tmp_path):
    tree(tmp_path, {('p', 'macOS-webkit-desktop', 'width-384'): (24, 40, (0, 0, 0, 255))})
    shots = bm.find_shots(tmp_path)
    assert bm.build(shots, tile_w=16, tile_h=16)[0]['reference'] == 'macOS-webkit-desktop'
    with pytest.raises(ValueError, match='reference environment'):
        bm.build(shots, tile_w=16, tile_h=16, reference='Linux-chromium-desktop')
    for size in ((8, 16), (16, 2000), (16.0, 16), (20, 16), (16, 36)):
        with pytest.raises(ValueError, match='multiples of 8'):
            bm.build(shots, tile_w=size[0], tile_h=size[1])
    with pytest.raises(ValueError, match='no screenshots'):
        bm.build({})
    with pytest.raises(ValueError, match='plain file stem'):
        bm.find_shots(tmp_path, '../x')
    (tmp_path / 'again' / 'p' / 'macOS-webkit-desktop').mkdir(parents=True)
    (tmp_path / 'again' / 'p' / 'macOS-webkit-desktop' / 'width-384.png').write_bytes(png(4, 4, (0, 0, 0, 255)))
    with pytest.raises(ValueError, match='two screenshots'):
        bm.find_shots(tmp_path)


def test_cli(tmp_path, capsys):
    tree(tmp_path / 'in', {('p', 'Linux-chromium-desktop', 'initial'): (64, 32, (10, 20, 30, 255))})
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'out'), '--shot', 'initial', '--tile', '32x32']) == 0
    assert json.loads(capsys.readouterr().out) == {'pages': 1, 'envs': 1, 'cells': 1, 'missing': 0,
                                                   'reference': 'Linux-chromium-desktop', 'out': str(tmp_path / 'out')}
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'o2'), '--tile', 'big']) == 2
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'o3')]) == 2  # no width-384 shots
    assert 'no screenshots' in capsys.readouterr().err
