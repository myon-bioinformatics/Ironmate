"""High-level facade: fit_to_limit always fits, matches the real CLI, raises FitError when impossible."""
import base64, json, random, subprocess, sys
from pathlib import Path

import pytest

import grid_tools as g
import ironmate_image as im

ROOT = Path(__file__).resolve().parents[1]


def _cli(*args, ok=True):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', *args], cwd=ROOT, capture_output=True, timeout=120)
    assert (out.returncode == 0) == ok, out.stderr
    return out


@pytest.fixture
def art_png(tmp_path):
    p = tmp_path / 'art.png'
    p.write_bytes(g.encode(g.make('circle', 'C03', 'shadow', 24), 'png', 4))   # 96x96, cell 4, meta
    return p


@pytest.fixture
def noisy_png(tmp_path):
    rnd = random.Random(7)
    art = g.make('cloud', 'C01', 'normal', 32)
    art = dict(art, colors=art['colors'] + ['#%08X' % rnd.getrandbits(32) for _ in range(60)])
    art['pixels'] = [[rnd.randrange(len(art['colors'])) for _ in row] for row in art['pixels']]
    p = tmp_path / 'noisy.png'
    p.write_bytes(g.encode(art, 'png', 1, meta=False))
    return p


@pytest.mark.parametrize('data_uri', [False, True])
@pytest.mark.parametrize('prefer', ['lossless', 'largest'])
def test_fit_always_within_limit_and_matches_cli(art_png, noisy_png, data_uri, prefer):
    for src in (art_png, noisy_png):
        full = im.fit_to_limit(src, max_chars=10 ** 7, data_uri=data_uri).chars
        for limit in sorted({full, full - 1, full // 2, full // 3, 900, 400}):
            try:
                r = im.fit_to_limit(src, max_chars=limit, data_uri=data_uri, prefer=prefer)
            except im.FitError:
                continue
            assert r.chars == len(r.text) <= limit and r.bytes == len(r.data)
            assert base64.b64decode(r.text.split(',')[-1]) == r.data
            args = r.command.replace('INPUT', str(src)).split()[3:]
            assert _cli(*args).stdout.rstrip(b'\n').decode() == r.text          # same bytes as the real CLI
            if limit == full:
                assert r.ratio == '1' and r.meta_used
            if prefer == 'lossless' and src == art_png and limit >= 900:
                assert r.lossless
            out = _cli('fit', str(src), '--limit-chars', str(limit), '--prefer', prefer,
                       *(['--data-uri'] if data_uri else []))
            assert out.stdout.rstrip(b'\n').decode() == r.text
            assert json.loads(out.stderr)['ratio'] == r.ratio


def test_bytes_limit_and_meta_drop(noisy_png):
    full = im.fit_to_limit(noisy_png, max_bytes=10 ** 7).bytes
    r = im.fit_to_limit(noisy_png.read_bytes(), max_bytes=full)
    assert r.bytes <= full and r.ratio == '1' and r.meta_used
    bare = len(im.to_png(noisy_png, meta=False))
    r = im.fit_to_limit(noisy_png, max_bytes=bare)          # full size only fits without meta -> dropped
    assert r.bytes <= bare and not r.meta_used and r.warnings and r.ratio == '1'
    assert r.data == g.encode(g.restore(noisy_png.read_bytes(), 32), 'png', meta=False)


def test_impossible_raises_one_error(art_png):
    with pytest.raises(im.FitError, match='cannot fit'):
        im.fit_to_limit(art_png, max_bytes=20)
    out = _cli('fit', str(art_png), '--limit-bytes', '20', ok=False)
    assert out.returncode == 2 and b'cannot fit' in out.stderr
    with pytest.raises(ValueError, match='exactly one'):
        im.fit_to_limit(art_png)


def test_inputs_and_helpers_roundtrip(art_png):
    data = art_png.read_bytes()
    b64 = base64.b64encode(data).decode()
    for src in (art_png, str(art_png), data, b64, 'data:image/png;base64,' + b64):
        assert im.load(src) == g.restore(data)
    art = im.load(data)
    assert im.from_base64(im.to_base64(art)) == art
    assert im.from_base64(im.to_base64(art, data_uri=True)) == art
    assert im.load(json.dumps(art)) == art
    small = im.resize(data, 12)
    assert small['width'] == 12 and im.resize(small, 24)['width'] == 24


def test_jpeg_input_with_pillow():
    Image = pytest.importorskip('PIL.Image')
    import io
    img = Image.new('RGB', (64, 48))
    img.putdata([(x * 4, y * 5, (x * y) % 256) for y in range(48) for x in range(64)])
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=80)
    r = im.fit_to_limit(buf.getvalue(), max_chars=6000)
    assert r.chars <= 6000 and im.from_base64(r.text)['width'] == r.width


def test_python_c_one_liners(art_png):
    code = ("import ironmate_image as im;r=im.fit_to_limit(%r,max_chars=1500,data_uri=True);"
            "print(r.ratio, r.chars, r.meta_used)" % str(art_png))
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    ratio, chars, _ = out.stdout.decode().split()
    assert int(chars) <= 1500
    code = "import ironmate_image as im;s=im.to_base64(%r);print(im.from_base64(s)['width'])" % str(art_png)
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == b'24'
