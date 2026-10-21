"""Independent Python/JS parity and static publication boundary checks."""
import json
import subprocess
from pathlib import Path

import pytest
import grid_tools
import image_studio
import pixel_grid
from scripts.pages_catalog import SIZES, catalog_script

ROOT = Path(__file__).resolve().parents[1]


def js(code, payload):
    result = subprocess.run(['node', '-e', "const c=require('./studio/tools/tools-core.js');const input=JSON.parse(require('fs').readFileSync(0,'utf8'));" + code],
                            input=json.dumps(payload), text=True, capture_output=True, check=True, cwd=ROOT)
    return json.loads(result.stdout)


def test_catalog_matches_python_for_every_preset():
    script = catalog_script().decode()
    catalog = json.loads(script.split('const IronmateCatalog = ', 1)[1].removesuffix(';\n'))
    assert len(catalog['grids']) == 100
    for key, rows in catalog['grids'].items():
        mask, effect, size = key.split('/')
        assert [[int(i) for i in row] for row in rows] == pixel_grid.render(mask, 'C01', effect, int(size))['pixels']
    assert catalog['palettes'] == {key: list(value) for key, value in pixel_grid.PALETTES.items()}


def test_nearest_grid_indices_match_python_including_odd_and_nonsquare_sizes():
    grid = pixel_grid.render('cloud', 'C02', 'shadow', 23)
    cases = [[w, h] for w, h in [(1, 1), (7, 9), (31, 16), (64, 46), (256, 1)]]
    result = js('console.log(JSON.stringify(input.sizes.map(([w,h])=>c.resize(input.grid,w,h))))', {'grid': grid, 'sizes': cases})
    for got, (w, h) in zip(result, cases):
        want = grid_tools.resize(grid, w, h, backend='stdlib')
        assert got['pixels'] == want['pixels'] and got['colors'] == want['colors']
    assert grid['width'] == 23


def test_rejects_corrupt_import_and_escapes_filename_markup():
    grid = pixel_grid.render('circle', size=16)
    grid['pixels'][0][0] = -1
    assert js('try { c.canonical(input); console.log(false) } catch { console.log(true) }', grid)
    assert js('console.log(JSON.stringify(c.esc(input)))', '<img src=x onerror="alert(1)">') == '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'
    assert js('console.log(JSON.stringify([c.base64Length(input),c.base64Length(input,true)]))', 7) == [12, 34]


def test_static_allowlist_excludes_private_scenes_and_generation_inputs(tmp_path):
    target = image_studio.build_site(tmp_path / 'Ironmate')
    assert {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()} == {
        'index.html', 'style.css', 'core.js', 'studio.js', '.nojekyll',
        'tools/index.html', 'tools/tools.css', 'tools/tools-core.js', 'tools/tools.js', 'tools/catalog.js',
        'brand/index.html', 'brand/gallery.css', 'brand/mono.svg', 'brand/dark-green.svg',
        'brand/famicom.svg', 'brand/gameboy.svg', 'brand/pixel-3d.svg',
        'brand/manifest.webmanifest', 'brand/apple-touch-icon.png', 'brand/app-192.png',
        'brand/app-512.png', 'brand/app-maskable-512.png',
        'brand/icon.svg', 'brand/heatmap.svg', 'brand/hero.svg', 'brand/favicon.ico', 'brand/favicon-16.png',
        'brand/favicon-32.png', 'brand/favicon-48.png', 'brand/icon-192.png',
        'slides/index.html', 'slides/package.js', 'slides/pptx.js', 'slides/slides.js', 'slides/slides.css'}
    assert not list(target.rglob('*.py')) and not list(target.rglob('*.json'))
    assert 'href="tools/"' in (target / 'index.html').read_text()
    assert 'connect-src \'none\'' in (target / 'tools/index.html').read_text()
    link = tmp_path / 'link'
    link.symlink_to(tmp_path / 'missing')
    with pytest.raises(FileExistsError):
        image_studio.build_site(link)


def test_home_screen_manifest_stays_within_pages_subpath():
    from urllib.parse import urljoin
    assets = image_studio.public_assets()
    base = 'https://example.test/Ironmate/brand/manifest.webmanifest'
    manifest = json.loads(assets['brand/manifest.webmanifest'])
    assert urljoin(base, manifest['id']) == 'https://example.test/Ironmate/'
    assert urljoin(base, manifest['start_url']) == 'https://example.test/Ironmate/'
    assert urljoin(base, manifest['scope']) == 'https://example.test/Ironmate/'
    for icon in manifest['icons']:
        assert 'brand/' + icon['src'] in assets
    assert {urljoin(base, item['url']) for item in manifest['shortcuts']} == {
        'https://example.test/Ironmate/', 'https://example.test/Ironmate/slides/',
        'https://example.test/Ironmate/tools/'}
    for path, prefix in (('index.html', 'brand/'), ('slides/index.html', '../brand/'),
                         ('tools/index.html', '../brand/'), ('brand/index.html', '')):
        page = assets[path].decode()
        assert f'href="{prefix}manifest.webmanifest"' in page
        assert f'href="{prefix}apple-touch-icon.png"' in page
        assert "manifest-src 'self'" in page


def test_home_screen_icons_are_opaque_and_maskable_content_is_safe():
    from photo_grid import decode_png
    assets = image_studio.public_assets()
    for name, size in (('app-192.png', 192), ('app-512.png', 512),
                       ('app-maskable-512.png', 512), ('apple-touch-icon.png', 180)):
        width, height, rows = decode_png(assets['brand/' + name])
        assert (width, height) == (size, size)
        assert all(row[i] == 255 for row in rows for i in range(3, len(row), 4))
        if name == 'app-maskable-512.png':
            background = rows[0][:4]
            for y, row in enumerate(rows):
                for x in range(width):
                    if row[4*x:4*x+4] != background:
                        # All corners of every foreground pixel fit inside the central 80% circle.
                        assert all((px-width/2)**2+(py-height/2)**2 <= (width*.4)**2
                                   for px in (x, x+1) for py in (y, y+1))
