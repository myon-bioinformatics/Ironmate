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
    assert r['signals_used'] == ['input byte size only',
                                 'ironmate metadata chunk (default output; --no-meta to omit)']


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
    r = s.estimate(data, limit_chars=20000, data_uri=True, verify=True, meta=False)
    with_meta = s.estimate(data, limit_chars=20000, data_uri=True, verify=True)
    assert with_meta['recommended'] is None and '--no-meta' in with_meta['note']   # 1 header entry per color
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


# --- review #92 Blocking: verification must measure the real default grid_tools output -------
def _cli(*args):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', *args], cwd=ROOT, capture_output=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _real(src_path, opt, data_uri, meta):
    """Length of what the verified command actually prints (Base64 text, newline stripped)."""
    args = ['load', str(src_path), '--size', str(opt and SRC_W[src_path]), '--resize', str(opt['width']),
            '--to', 'base64'] + (['--data-uri'] if data_uri else []) + ([] if meta else ['--no-meta'])
    return len(_cli(*args).rstrip(b'\n'))


SRC_W = {}


def _sources(tmp_path):
    rnd = random.Random(92)
    art = g.make('circle', 'C03', 'shadow', 24)
    plain = tmp_path / 'plain.png'          # header-less PNG (e.g. from another tool)
    plain.write_bytes(g.encode(art, 'png', 3, meta=False))
    noisy = dict(art, colors=art['colors'] + ['#%08X' % rnd.getrandbits(32) for _ in range(40)])
    noisy['pixels'] = [[rnd.randrange(len(noisy['colors'])) for _ in row] for row in art['pixels']]
    noise = tmp_path / 'noise.png'
    noise.write_bytes(g.encode(noisy, 'png', 1, meta=False))
    withmeta = tmp_path / 'meta.png'        # default grid_tools output (ironmate header)
    withmeta.write_bytes(g.encode(art, 'png', 3))
    for p in (plain, noise, withmeta):
        SRC_W[p] = s.inspect(p.read_bytes())[0]['width']
    return plain, noise, withmeta


@pytest.mark.parametrize('meta', [True, False])
@pytest.mark.parametrize('data_uri', [False, True])
def test_verify_matches_real_cli_output_at_the_boundary(tmp_path, meta, data_uri):
    for src in _sources(tmp_path):
        data = src.read_bytes()
        probe = s.estimate(data, limit_chars=10 ** 7, data_uri=data_uri, verify=True, meta=meta)
        for opt in probe['options'][:6]:
            real = _real(src, opt, data_uri, meta) if opt['ratio'] in ('1', '1/2', '2/3') else None
            if real is not None:
                assert opt['actual_chars'] == real, (src.name, opt['ratio'])
            assert opt['actual_bytes'] == len(g.encode(s._candidate_artifact(
                data, 'png', SRC_W[src], s.inspect(data)[1], opt['width']), 'png', 1, meta=meta))
            assert opt['actual_bytes'] <= opt['upper_bytes']
        full = probe['options'][0]
        real = _real(src, full, data_uri, meta)
        # limit exactly at the real output size -> full size verified as fitting
        at = s.estimate(data, limit_chars=real, data_uri=data_uri, verify=True, meta=meta)
        assert at['recommended']['ratio'] == '1' and at['recommended']['actual_chars'] == real
        # one Base64 quantum below -> full size must be rejected (no fail-open)
        below = s.estimate(data, limit_chars=real - 1, data_uri=data_uri, verify=True, meta=meta)
        assert below['recommended'] is None or below['recommended']['ratio'] != '1'
        if below['recommended']:
            rec = below['recommended']
            assert _real(src, rec, data_uri, meta) == rec['actual_chars'] <= real - 1
        # byte limits: exact and 1 byte below
        nb = full['actual_bytes']
        assert s.estimate(data, limit_bytes=nb, verify=True, meta=meta)['recommended']['ratio'] == '1'
        assert s.estimate(data, limit_bytes=nb - 1, verify=True, meta=meta)['recommended']['ratio'] != '1' \
            if s.estimate(data, limit_bytes=nb - 1, verify=True, meta=meta)['recommended'] else True


def test_bare_fits_but_default_meta_exceeds(tmp_path):
    """The review's fixture: header-less size fits, the default (meta) output does not."""
    plain, _, _ = _sources(tmp_path)
    data = plain.read_bytes()
    bare = _real(plain, {'width': SRC_W[plain]}, False, False)
    withm = _real(plain, {'width': SRC_W[plain]}, False, True)
    assert withm > bare
    r = s.estimate(data, limit_chars=bare, verify=True)                # default meta=True
    assert r['options'][0]['actual_chars'] == withm > bare
    if r['recommended']:
        assert r['recommended']['ratio'] != '1'
        assert _real(plain, r['recommended'], False, True) <= bare
    r = s.estimate(data, limit_chars=bare, verify=True, meta=False)
    assert r['recommended']['ratio'] == '1'
    out = json.loads(_cli('estimate', str(plain), '--limit-chars', str(bare), '--verify'))
    assert out['meta'] is True and (out['recommended'] or {}).get('ratio') != '1'
    out = json.loads(_cli('estimate', str(plain), '--limit-chars', str(bare), '--verify', '--no-meta'))
    assert out['recommended']['ratio'] == '1' and '--no-meta' in out['recommended']['command']


def test_estimate_without_verify_includes_meta_overhead(tmp_path):
    plain, noise, withmeta = _sources(tmp_path)
    for src in (plain, noise, withmeta):
        data = src.read_bytes()
        on = s.estimate(data, limit_bytes=10 ** 7, verify=True)
        off = s.estimate(data, limit_bytes=10 ** 7, verify=True, meta=False)
        for a, b in zip(on['options'], off['options']):
            assert a['est_bytes'] > b['est_bytes'] and a['upper_bytes'] > b['upper_bytes']
            assert a['actual_bytes'] <= a['upper_bytes']
    hdr_on = s.estimate(width=64, height=64, nbytes=3000, limit_bytes=10 ** 6)
    hdr_off = s.estimate(width=64, height=64, nbytes=3000, limit_bytes=10 ** 6, meta=False)
    assert hdr_on['recommended']['upper_bytes'] > hdr_off['recommended']['upper_bytes']


@pytest.mark.parametrize('n', [2**53-1, 2**53, 2**53+1, 2**64-1, 10**400])
@pytest.mark.parametrize('data_uri', [False, True])
def test_large_base64_length_without_float_rounding_or_overflow(n, data_uri):
    groups, remainder = divmod(n, 3)
    expected = 4 * (groups + bool(remainder))
    prefix = s.DATA_URI_PREFIX if data_uri else 0
    assert s.base64_chars(n, data_uri) == expected + prefix
    budget = expected + prefix
    capacity = s.bytes_for_chars(budget, data_uri)
    assert capacity >= n
    assert s.base64_chars(capacity, data_uri) <= budget
    assert s.base64_chars(capacity + 1, data_uri) > budget


@pytest.mark.parametrize('data_uri', [False, True])
def test_base64_budget_boundary_matches_actual_encoded_bytes(data_uri):
    import base64
    prefix = s.DATA_URI_PREFIX if data_uri else 0
    for budget in range(prefix, prefix + 80):
        capacity = s.bytes_for_chars(budget, data_uri)
        assert len(base64.b64encode(bytes(capacity))) + prefix <= budget
        assert len(base64.b64encode(bytes(capacity + 1))) + prefix > budget
