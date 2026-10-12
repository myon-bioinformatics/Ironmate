"""Reversibility contract of grid_tools: where round trips are exact and where they are not."""
import base64, io, json, random, subprocess, sys, time
from pathlib import Path

import pytest

import grid_png
import grid_svg
import grid_tools as g
import photo_grid
import pixel_grid

ROOT = Path(__file__).resolve().parents[1]
HAS_NUMPY = g._backend('auto', 'numpy') == 'numpy'
HAS_PIL = g._backend('auto', 'PIL') == 'PIL'
needs_numpy = pytest.mark.skipif(not HAS_NUMPY, reason='numpy not installed')
needs_pil = pytest.mark.skipif(not HAS_PIL, reason='Pillow not installed')


def _random_art(w, h, ncolors, seed, alpha=True):
    rnd = random.Random(seed)
    colors = ['#00000000'] + ['#%02X%02X%02X%02X' % (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256),
                                                     rnd.randrange(1, 256) if alpha else 255)
                              for _ in range(ncolors)]
    colors = list(dict.fromkeys(colors))
    return {'schema': 'ironmate-pixel-grid/1', 'width': w, 'height': h, 'colors': colors,
            'pixels': [[rnd.randrange(len(colors)) for _ in range(w)] for _ in range(h)]}


ALL_ART = [pixel_grid.render(m, pid, e, s) for m in pixel_grid.MASKS for pid in ('C01', 'C07')
           for e in pixel_grid.EFFECTS for s in (16, 33)]


# --- PNG / Base64 with metadata: exact JSON -------------------------------------------------
@pytest.mark.parametrize('scale', [1, 2, 5])
def test_png_base64_with_meta_is_exact(scale):
    for art in ALL_ART:
        assert g.restore(g.encode(art, 'png', scale)) == art
        assert g.restore(g.encode(art, 'base64', scale)) == art
        assert g.restore(g.encode(art, 'base64', scale, data_uri=True)) == art


@pytest.mark.parametrize('ncolors', [1, 16, 300])
def test_semi_transparent_many_colors_exact(ncolors):
    art = _random_art(23, 17, ncolors, ncolors)
    assert len(art['colors']) > ncolors * 0.9
    assert g.restore(g.encode(art, scale=3)) == art
    plain = g.restore(g.encode(art, scale=3, meta=False), size=23)
    assert g.cells(plain) == g.cells(art)          # alpha 1..255 survives PNG exactly


def test_meta_default_png_bytes_unchanged():
    art = ALL_ART[0]
    assert grid_png.to_png(art) == grid_png.to_png(art, meta=False)
    assert b'ironmate\x00' in grid_png.to_png(art, meta=True)


def test_duplicate_palette_rgba_is_the_one_meta_exception():
    art = dict(ALL_ART[0], colors=ALL_ART[0]['colors'] + [ALL_ART[0]['colors'][1]])
    art['pixels'] = [[len(art['colors']) - 1 if v == 1 else v for v in row] for row in art['pixels']]
    back = g.restore(g.encode(art))
    assert back != art and g.cells(back) == g.cells(art)   # first matching index wins


def test_tampered_meta_and_pixels_fail_clearly():
    art = ALL_ART[0]
    data = bytearray(g.encode(art, 'png'))
    i = data.index(b'ironmate\x00') + 12
    data[i] ^= 1
    with pytest.raises(ValueError, match='bad CRC'):
        g.restore(bytes(data))
    other = dict(art, colors=['#00000000', '#123456FF', '#123457FF', '#123458FF', '#123459FF'])
    foreign = grid_png.to_png(art)  # no meta; splice meta of a different palette
    meta = grid_png.to_png(other, meta=True)
    spliced = meta[:meta.index(b'IDAT') - 4] + foreign[foreign.index(b'IDAT') - 4:]
    with pytest.raises(ValueError, match='not in the ironmate metadata'):
        g.restore(spliced)


# --- PNG without metadata: scale detection ---------------------------------------------------
def test_scale_auto_detect_64_to_32():
    art = pixel_grid.render('circle', 'C03', 'outline', 32)
    back = g.restore(grid_png.to_png(art, 2))
    assert back['width'] == 32 and back['restored']['scale'] == 2
    assert g.cells(back) == g.cells(art)
    assert back['colors'] == g.canonical(art)['colors']


def test_gcd_detection_limit_is_documented():
    """Without a hint the scale is the largest exact one: a 2x2-checker 8x8 grid looks like 4x4 at 2x."""
    art = {'schema': 'ironmate-pixel-grid/1', 'width': 8, 'height': 8, 'colors': ['#00000000', '#FF0000FF'],
           'pixels': [[((x // 2) + (y // 2)) % 2 for x in range(8)] for y in range(8)]}
    data = grid_png.to_png(art, 3)
    assert g.restore(data)['width'] == 4                    # ambiguous: smaller grid also explains it
    assert g.cells(g.restore(data, size=8)) == g.cells(art)  # size hint restores exactly


def test_canonical_palette_gives_exact_json_without_meta():
    art = g.canonical(_random_art(12, 9, 7, 3))
    back = g.restore(g.encode(art, scale=4, meta=False), size=12)
    back.pop('restored')
    assert back == art


def test_non_nearest_images_rejected():
    art = pixel_grid.render('rock', 'C01', 'shadow', 16)
    with pytest.raises(ValueError, match='does not divide'):
        g.restore(grid_png.to_png(art, 2), size=7)
    smoothed = g.resize(g.restore(grid_png.to_png(art, 4)), 50)  # 64 -> 50: uneven blocks
    with pytest.raises(ValueError, match='not one color'):
        g.restore(grid_png.to_png(smoothed), size=25)


def test_lossy_inputs_point_to_photo():
    with pytest.raises(ValueError, match='lossy'):
        g.restore(b'\xff\xd8\xff\xe0' + b'\0' * 20)


# --- resize / recolor -----------------------------------------------------------------------
@pytest.mark.parametrize('k', [2, 3, 7])
def test_resize_up_then_down_exact(k):
    for art in ALL_ART[::5]:
        up = g.resize(art, art['width'] * k)
        assert up['height'] == art['height'] * k
        assert g.resize(up, art['width']) == art
        w, h, rows = photo_grid.decode_png(grid_png.to_png(art, k))
        assert g.cells(up) == g._rows_to_cells(w, h, rows)              # resize == PNG --scale


def test_resize_down_then_up_needs_uniform_blocks():
    art = pixel_grid.render('cloud', 'C01', 'normal', 32)
    blocky = g.resize(g.resize(art, 16), 32)
    assert g.resize(g.resize(blocky, 16), 32) == blocky       # uniform 2x2 blocks: exact
    assert g.resize(g.resize(art, 16), 32) != art              # detail lost


def test_any_upscale_then_back_is_exact_even_non_integer():
    """Cell-center sampling: every upscale (also 10->15) keeps every source cell, so down again is exact."""
    for a in range(1, 40):
        art = _random_art(a, 3, 6, a)
        for b in range(a, 3 * a + 2):
            assert g.resize(g.resize(art, b, 3), a, 3) == art
    art = _random_art(10, 10, 5, 9)
    assert g.resize(g.resize(art, 7), 10) != art                      # downscale drops cells


def test_recolor_round_trip_and_limits():
    art = pixel_grid.render('diamond', 'C01', 'outline', 21)
    there = g.recolor(art, 'C09')
    assert there['pixels'] == art['pixels'] and there['colors'] == list(pixel_grid.PALETTES['C09'])
    assert g.recolor(there, 'C01') == art
    with pytest.raises(ValueError, match='unknown color ID'):
        g.recolor(art, 'lava')
    with pytest.raises(ValueError, match='beyond the 5 roles'):
        g.recolor(_random_art(4, 4, 9, 1), 'C01')


# --- SVG -----------------------------------------------------------------------------------
def test_svg_output_loads_back_to_same_visible_cells():
    for art in ALL_ART[::3] + [_random_art(9, 7, 20, 5)]:
        back = g.restore(g.encode(art, 'svg'))
        want = [[c if c[7:] != '00' else '#00000000' for c in row] for row in g.cells(art)]
        assert g.cells(back) == want


# --- JPEG/WebP chain -----------------------------------------------------------------------
@needs_pil
@pytest.mark.parametrize('fmt', ['JPEG', 'WEBP'])
def test_photo_to_png_base64_to_svg_chain(fmt):
    from PIL import Image
    img = Image.new('RGB', (90, 60))
    img.putdata([(x * 3 % 256, y * 4 % 256, 120) for y in range(60) for x in range(90)])
    buf = io.BytesIO()
    img.save(buf, fmt, quality=85)
    art = g.photo(buf.getvalue(), 32, colors=6)
    assert art == g.photo(buf.getvalue(), 32, colors=6)                      # deterministic
    assert g.photo(base64.b64encode(buf.getvalue()).decode(), 32, colors=6) == art
    b64 = g.encode(art, data_uri=True)
    assert g.restore(b64) == art                                             # lossless from here
    svg = g.encode(art, 'svg')
    assert svg.startswith('<svg') and g.cells(g.restore(svg)) == g.cells(art)


# --- backend cross-checks (stdlib is the oracle) ---------------------------------------------
@needs_pil
def test_png_decode_stdlib_matches_pillow():
    for art in ALL_ART[::4] + [_random_art(31, 5, 50, 2)]:
        data = g.encode(art, 'png', 3, meta=False)
        assert g._decode_png(data, 'stdlib') == g._decode_png(data, 'PIL')
        assert g.restore(data, backend='stdlib') == g.restore(data, backend='PIL')


@needs_numpy
def test_scale_detect_and_resize_stdlib_matches_numpy():
    for i, art in enumerate(ALL_ART[::4]):
        grid = g.cells(g.resize(art, art['width'] * (i % 4 + 1)))
        assert g._runs_gcd(grid, 'stdlib') == g._runs_gcd(grid, 'numpy')
        for w in (1, 7, 40, art['width'] * 3):
            assert g.resize(art, w, backend='stdlib') == g.resize(art, w, backend='numpy')


@needs_pil
def test_integer_resize_matches_pillow_nearest():
    from PIL import Image
    art = _random_art(13, 11, 9, 4)
    w, h, rows = photo_grid.decode_png(grid_png.to_png(art))
    img = Image.frombytes('RGBA', (w, h), b''.join(rows)).resize((39, 33), Image.NEAREST)
    assert img.tobytes() == b''.join(photo_grid.decode_png(grid_png.to_png(g.resize(art, 39)))[2])


def test_without_optional_backends(monkeypatch):
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name.split('.')[0] in ('numpy', 'PIL'):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, '__import__', blocked)
    art = ALL_ART[7]
    assert g._backend('auto', 'numpy') == 'stdlib' and g._backend('auto', 'PIL') == 'stdlib'
    assert g.restore(g.encode(art, scale=2)) == art
    assert g.cells(g.restore(g.encode(art, 'svg'))) == g.cells(art)
    assert g.resize(g.resize(art, 99), art['width']) == art


@needs_numpy
@needs_pil
def test_relative_timing_report(capsys):
    art = pixel_grid.render('circle', 'C02', 'outline', 128)
    data = g.encode(art, 'png', 4, meta=False)
    times = {}
    for be in ('stdlib', 'PIL', 'numpy'):
        t = time.perf_counter()
        out = g.restore(data, backend=be)
        times[be] = time.perf_counter() - t
        assert g.cells(out) == g.cells(art)
    with capsys.disabled():
        print('\nrestore 512x512 PNG ->128:', {k: f'{v * 1000:.0f}ms' for k, v in times.items()})


# --- one-liners -----------------------------------------------------------------------------
def _run(*args, stdin=None):
    return subprocess.run([sys.executable, *args], cwd=ROOT, input=stdin, capture_output=True, timeout=120)


def test_python_c_one_liner():
    r = _run('-c', "import grid_tools as g;print(g.encode(g.make('cloud','C01','shadow',16),data_uri=True))")
    assert r.returncode == 0, r.stderr
    uri = r.stdout.decode().strip()
    assert uri.startswith('data:image/png;base64,')
    assert g.restore(uri) == pixel_grid.render('cloud', 'C01', 'shadow', 16)


def test_python_m_pipeline(tmp_path):
    r = _run('-m', 'grid_tools', 'make', 'circle', '--palette', 'C04', '--size', '32', '--scale', '2', '--no-meta')
    assert r.returncode == 0, r.stderr
    b64 = r.stdout.decode().strip()
    r = _run('-m', 'grid_tools', 'load', b64, '--to', 'json')
    art = json.loads(r.stdout)
    assert art['width'] == 32 and art['restored']['scale'] == 2
    out = tmp_path / 'x.png'
    r = _run('-m', 'grid_tools', 'load', '-', '--resize', '64', '--recolor', 'C05', '--to', 'png', '-o', str(out),
             stdin=b64.encode())
    assert r.returncode == 0 and out.read_bytes().startswith(b'\x89PNG')
    assert g.restore(out.read_bytes())['palette'] == 'C05'
    r = _run('-m', 'grid_tools', 'load', str(out), '--to', 'svg')
    assert r.stdout.startswith(b'<svg')


@pytest.mark.parametrize('args, message', [
    (['load', 'not base64!'], b'invalid Base64'),
    (['load', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0"/></svg>'], b'path'),
    (['make', 'cloud', '--size', '8'], b'16 to 256'),
    (['load', '{"width": 1}', '--recolor', 'C01'], b'error'),
])
def test_cli_errors_exit_2(args, message):
    r = _run('-m', 'grid_tools', *args)
    assert r.returncode == 2 and message in r.stderr, r.stderr
