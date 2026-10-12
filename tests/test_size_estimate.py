"""Downscale / size estimator: exact Base64 math, signals, bounds, lossless detection, CLI."""
import io, json, random, subprocess, sys
from fractions import Fraction
from pathlib import Path

import pytest

import grid_tools as g
import size_estimate as s

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('n', range(0, 40))
def test_base64_char_math_is_exact(n):
    import base64
    assert s.base64_chars(n) == len(base64.b64encode(bytes(n)))
    assert s.base64_chars(n, True) == len('data:image/png;base64,' + base64.b64encode(bytes(n)).decode())
    assert s.base64_chars(s.bytes_for_chars(s.base64_chars(n))) <= s.base64_chars(n)
    assert s.bytes_for_chars(s.base64_chars(n)) >= n


def test_header_only_estimate():
    r = s.estimate(width=1024, height=768, nbytes=900000, limit_chars=200000, data_uri=True)
    assert r['confidence'] == 'low' and r['achievable'] and not r['fits_now']
    rec = r['recommended']
    assert rec['est_chars'] <= 200000 and Fraction(rec['ratio']) < 1
    assert Fraction(r['integer_option']['ratio']).numerator == 1
    assert r['signals_used'] == ['input byte size only']


def test_pixel_art_signals_and_lossless_options():
    data = g.encode(g.make('cloud', 'C01', 'shadow', 32), 'png', 8)
    r = s.estimate(data, limit_bytes=10 ** 6, verify=True)
    sig = r['input']
    assert sig['cell_scale'] == 8 and sig['ironmate_meta'] and sig['color_type'] == 6 and sig['alpha'] == 'binary'
    assert sig['unique_colors'] <= 4
    lossless = {o['ratio'] for o in r['options'] if o['nearest_lossless']}
    assert lossless == {'1', '1/2', '1/4', '1/8'}
    small = g.restore(data)['width']
    assert small == 32
    tight = s.estimate(data, limit_bytes=200, verify=True)
    assert tight['confidence'] == 'verified'
    for o in tight['options']:
        assert o['actual_bytes'] <= o['upper_bytes']


def _photo(fmt, **kw):
    Image = pytest.importorskip('PIL.Image')
    rnd = random.Random(3)
    img = Image.new('RGB', (160, 120))
    img.putdata([(x % 256, (y * 2) % 256, (x * y + rnd.randrange(30)) % 256) for y in range(120) for x in range(160)])
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


@pytest.mark.parametrize('fmt, kw', [('JPEG', {'quality': 50}), ('JPEG', {'quality': 85}), ('WEBP', {'quality': 80}),
                                     ('PNG', {})])
def test_photo_signals_and_estimate_accuracy(fmt, kw):
    data = _photo(fmt, **kw)
    r = s.estimate(data, limit_chars=20000, data_uri=True, verify=True)
    sig = r['input']
    if fmt == 'JPEG':
        assert sig['quality_estimate'] == kw['quality'] and sig['subsampling'] == '4:2:0'
    if fmt == 'WEBP':
        assert sig['lossless'] is False
    for o in r['options']:
        assert o['actual_bytes'] <= o['upper_bytes']                    # hard bound holds
        assert 0.5 <= o['actual_bytes'] / o['est_bytes'] <= 2.0          # measured model accuracy
    rec = r['recommended']
    assert rec['actual_chars'] <= 20000


def test_unreachable_limit():
    data = g.encode(g.make('cloud'), 'png')
    r = s.estimate(data, limit_bytes=10, verify=True)
    assert not r['achievable'] and r['recommended'] is None and 'smallest' in r


@pytest.mark.parametrize('kwargs, match', [
    ({'width': 10, 'height': 10, 'limit_bytes': 5}, 'need nbytes'),
    ({'width': 10, 'nbytes': 5, 'limit_bytes': 5}, 'width and height'),
    ({'width': 10, 'height': 10, 'nbytes': 5}, 'exactly one'),
])
def test_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        s.estimate(**kwargs)


def test_cli_one_liners(tmp_path):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', '--width', '800', '--height', '600',
                          '--bytes', '500000', '--limit-chars', '100000'], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)['recommended']['est_chars'] <= 100000
    png = tmp_path / 'a.png'
    png.write_bytes(g.encode(g.make('circle', 'C02', 'normal', 40), 'png', 4))
    out = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', str(png), '--limit-bytes', '400', '--verify'],
                         cwd=ROOT, capture_output=True, timeout=60)
    r = json.loads(out.stdout)
    assert r['confidence'] == 'verified' and r['input']['cell_scale'] == 4
    one = subprocess.run([sys.executable, '-c', "import size_estimate as s;print(s.estimate(width=64,height=64,"
                          "nbytes=3000,limit_chars=2000)['recommended']['ratio'])"], cwd=ROOT, capture_output=True)
    assert one.returncode == 0 and Fraction(one.stdout.decode().strip()) < 1
    bad = subprocess.run([sys.executable, '-m', 'grid_tools', 'estimate', '--width', '5'], cwd=ROOT, capture_output=True)
    assert bad.returncode == 2 and b'error' in bad.stderr
