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
    assert bm.build(shots, tile_w=16, tile_h=16, expected_envs=['Linux-chromium-desktop'])[0]['reference'] == 'macOS-webkit-desktop'
    with pytest.raises(ValueError, match='reference environment'):
        bm.build(shots, tile_w=16, tile_h=16, reference='Linux-chromium-desktop', expected_envs=['Linux-chromium-desktop'])
    for size in ((8, 16), (16, 2000), (16.0, 16)):
        with pytest.raises(ValueError, match='tile size'):
            bm.build(shots, tile_w=size[0], tile_h=size[1])
    # 8 px multiples are the default, not a rule: a device-sized tile and another gap work too.
    report, sheet, _ = bm.build(shots, tile_w=195, tile_h=422, gap=5)
    assert report['tile'] == {'width': 195, 'height': 422, 'gap': 5, 'fit': 'width, then crop or pad white'}
    assert sheet[:2] == (195 + 2 * 5, 422 + 2 * 5)
    assert bm.build(shots, tile_w=16, tile_h=16, gap=0)[1][:2] == (16, 16)
    for gap in (-1, 65, 8.0):
        with pytest.raises(ValueError, match='gap'):
            bm.build(shots, tile_w=16, tile_h=16, gap=gap)
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


def test_name_conventions_select_before_duplicate_detection(tmp_path):
    tree(tmp_path, {
        ('home', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('home', 'Windows-firefox-desktop', 'width-384'): (16, 16, (4, 5, 6, 255)),
        ('detail', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
    })
    duplicate = tmp_path / 'duplicate' / 'home' / 'Windows-firefox-desktop' / 'width-384.png'
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b'bad png, must not decode')
    result = bm.find_shots(tmp_path, pages=('home', 'detail'), environments=('Linux-*', '*-webkit-*'))
    assert list(result) == [('detail', 'Linux-chromium-desktop'), ('home', 'Linux-chromium-desktop')]
    assert bm.find_shots(tmp_path, pages=('HOME',)) == {}
    with pytest.raises(ValueError, match='two screenshots'):
        bm.find_shots(tmp_path)


def test_native_list_is_read_only_and_filtered_build_uses_same_selection(tmp_path, capsys):
    source, output = tmp_path / 'input', tmp_path / 'output'
    tree(source, {
        ('home', 'Linux-chromium-desktop', 'initial'): (16, 16, (1, 2, 3, 255)),
        ('home', 'macOS-webkit-iphone', 'initial'): (16, 16, (4, 5, 6, 255)),
    })
    args = [str(source), '--shot', 'initial', '--page', 'home', '--env', 'Linux-*']
    assert bm.main(args + ['--list']) == 0
    listing = json.loads(capsys.readouterr().out)['shots']
    assert [(r['page'], r['env']) for r in listing] == [('home', 'Linux-chromium-desktop')]
    assert not output.exists()
    assert bm.main(args + ['--out', str(output), '--tile', '16x16']) == 0
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert report['pages'] == ['home'] and report['envs'] == ['Linux-chromium-desktop']
    assert len(report['cells']) == len(listing)


def test_list_does_not_decode_candidate_pngs(tmp_path, capsys):
    path = tmp_path / 'home' / 'Linux-chromium-desktop' / 'width-384.png'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not png')
    assert bm.main([str(tmp_path), '--list']) == 0
    assert json.loads(capsys.readouterr().out)['shots'][0]['path'] == str(path)
    assert bm.main([str(tmp_path / 'missing'), '--list']) == 2
    assert 'directory' in capsys.readouterr().err


@pytest.mark.parametrize('options,error', [
    ({'pages': 'home'}, TypeError), ({'environments': ['']}, ValueError), ({'pages': [1]}, ValueError),
])
def test_bad_selection_rules(tmp_path, options, error):
    with pytest.raises(error):
        bm.find_shots(tmp_path, **options)


@pytest.mark.parametrize('options', [[], ['--list', '--out', 'unused']])
def test_list_and_output_cli_contract(tmp_path, options):
    with pytest.raises(SystemExit) as error:
        bm.main([str(tmp_path), *options])
    assert error.value.code == 2


def test_patterned_dpr_images_and_completely_missing_environment(tmp_path):
    # Replicate each source pixel into a 3x3 block: equal CSS content at DPR 1/3.
    w, h = 32, 64
    source = bytes(c for y in range(h) for x in range(w)
                   for c in ((255, 0, 0, 255) if (x // 4 + y // 4) % 2 else (0, 0, 255, 255)))
    large = b''.join(source[y*w*4+x*4:y*w*4+x*4+4] * 3
                     for y in range(h) for _ in range(3) for x in range(w))
    shots = {}
    for env, image in [('Linux-chromium-desktop', (w, h, source)),
                       ('macOS-webkit-iphone', (w*3, h*3, large))]:
        path = tmp_path / (env + '.png')
        path.write_bytes(bm.encode_png(*image))
        shots['p', env] = path
    report, sheet, tiles = bm.build(shots, tile_w=16, tile_h=32,
                                   expected_pages=['p', 'never-captured'],
                                   expected_envs=['Windows-firefox-desktop'])
    assert all(c['difference']['rgb_mae'] == c['difference']['rgb_rmse'] == 0 for c in report['cells'])
    assert all(c['fit']['cropped_rows'] == c['fit']['padded_rows'] == 0 for c in report['cells'])
    assert len(report['missing']) == 4  # includes an entirely absent page and environment
    out = tmp_path / 'empty'
    out.mkdir()
    bm.write(out, report, sheet, tiles)
    assert 'no screenshot' in (out / 'index.html').read_text()


@pytest.mark.parametrize('kind', ['file', 'dangling', 'nonempty', 'child-link'])
def test_output_protection_preserves_existing_targets(tmp_path, kind):
    out, target = tmp_path / 'out', tmp_path / 'target'
    target.mkdir()
    marker = target / 'keep'
    marker.write_bytes(b'unchanged')
    if kind == 'file':
        out.write_bytes(b'unchanged')
    elif kind == 'dangling':
        out.symlink_to(tmp_path / 'absent', target_is_directory=True)
    else:
        out.mkdir()
        if kind == 'nonempty':
            (out / 'keep').write_bytes(b'unchanged')
        else:
            (out / 'tiles').symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        bm.write(out, {}, (16, 16, bytes(16*16*4)), {})
    assert marker.read_bytes() == b'unchanged'
    assert list(target.iterdir()) == [marker]
    if kind == 'dangling':
        assert not (tmp_path / 'absent').exists()


def test_bad_library_cell_names_fail_before_any_output(tmp_path):
    with pytest.raises(ValueError, match='plain path'):
        bm.write(tmp_path / 'out', {}, (16, 16, bytes(16*16*4)), {('../escape', 'env'): None})
    assert not (tmp_path / 'out').exists()
