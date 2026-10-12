"""Review fixes on PR #90: PNG tRNS, strict zlib termination, and non-destructive -o output."""
import io, os, random, struct, subprocess, sys, zlib
from pathlib import Path

import pytest

import grid_tools as g
import photo_grid
from grid_output import write_output

ROOT = Path(__file__).resolve().parents[1]
SIG = b'\x89PNG\r\n\x1a\n'


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _png(width, height, color, samples, extra=b'', stream=None, depth=8):
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = b''.join(b'\0' + bytes(samples[y * width * channels:(y + 1) * width * channels]) for y in range(height))
    head = _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0))
    return SIG + head + extra + _chunk(b'IDAT', zlib.compress(raw) if stream is None else stream) + _chunk(b'IEND', b'')


def _cells(width, height, rows):
    return {(x, y): tuple(rows[y][4 * x:4 * x + 4]) for y in range(height) for x in range(width)}


def _pillow_cells(data):
    Image = pytest.importorskip('PIL.Image')
    img = Image.open(io.BytesIO(data)).convert('RGBA')
    raw = img.tobytes()
    w, h = img.size
    return _cells(w, h, [raw[y * w * 4:(y + 1) * w * 4] for y in range(h)])


def _cases():
    rnd = random.Random(90)
    for _ in range(25):
        w, h = rnd.randint(1, 9), rnd.randint(1, 7)
        gray = [rnd.choice([7, 7, rnd.randrange(256)]) for _ in range(w * h)]
        yield 'gray', w, h, _png(w, h, 0, gray, _chunk(b'tRNS', struct.pack('>H', 7))), {
            (i % w, i // w): (v, v, v, 0 if v == 7 else 255) for i, v in enumerate(gray)}
        key = (10, 20, 30)
        rgb = [rnd.choice([key, key, tuple(rnd.randrange(256) for _ in range(3))]) for _ in range(w * h)]
        yield 'rgb', w, h, _png(w, h, 2, [c for p in rgb for c in p], _chunk(b'tRNS', struct.pack('>3H', *key))), {
            (i % w, i // w): p + ((0,) if p == key else (255,)) for i, p in enumerate(rgb)}


def test_trns_gray_and_rgb_stdlib_matches_expected_and_pillow():
    pil = g._backend('auto', 'PIL') == 'PIL'
    n = 0
    for kind, w, h, data, want in _cases():
        got = _cells(*photo_grid.decode_png(data))
        assert got == want, kind
        if pil:
            assert _pillow_cells(data) == got, kind
        n += 1
    assert n == 50


def test_trns_reaches_the_grid():
    data = _png(2, 1, 2, [10, 20, 30, 200, 0, 0], _chunk(b'tRNS', struct.pack('>3H', 10, 20, 30)))
    art = photo_grid.convert(data, 8, 'contain', 2)
    assert {art['colors'][v] for row in art['pixels'] for v in row} >= {'#00000000'}
    back = g.restore(data, size=2)
    assert g.cells(back) == [['#0A141E00', '#C80000FF']]  # RGB kept, alpha 0 (same as Pillow)


def test_palette_with_trns_via_pillow_matches_rgba_reference():
    Image = pytest.importorskip('PIL.Image')
    img = Image.new('P', (4, 2))
    img.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * 759)
    img.putdata([0, 1, 2, 0, 2, 1, 0, 1])
    buf = io.BytesIO()
    img.save(buf, 'PNG', transparency=bytes([0, 128, 255]))
    w, h, rows = photo_grid.decode_image(buf.getvalue()) if hasattr(photo_grid, 'decode_image') else (None,) * 3
    alpha = {0: 0, 1: 128, 2: 255}
    rgb = {0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255)}
    want = {(i % 4, i // 4): rgb[v] + (alpha[v],) for i, v in enumerate([0, 1, 2, 0, 2, 1, 0, 1])}
    assert _cells(w, h, rows) == want == _pillow_cells(buf.getvalue())
    with pytest.raises(photo_grid.ImageDecodeError, match='color type 3'):
        photo_grid.decode_png(buf.getvalue())   # stdlib: explicit, Pillow fallback handles it


@pytest.mark.parametrize('extra, match', [
    (_chunk(b'tRNS', b'\0\7') * 2, 'once'),
    (_chunk(b'tRNS', b'\0\7\0'), 'length'),
    (_chunk(b'tRNS', b'\1\0'), '8-bit'),
])
def test_invalid_trns_rejected(extra, match):
    with pytest.raises(photo_grid.ImageDecodeError, match=match):
        photo_grid.decode_png(_png(1, 1, 0, [7], extra))


def test_trns_on_alpha_types_and_after_idat_rejected():
    with pytest.raises(photo_grid.ImageDecodeError, match='not allowed'):
        photo_grid.decode_png(_png(1, 1, 6, [1, 2, 3, 4], _chunk(b'tRNS', b'\0\1')))
    good = _png(1, 1, 0, [7])
    late = good[:-12] + _chunk(b'tRNS', b'\0\7') + good[-12:]
    with pytest.raises(photo_grid.ImageDecodeError, match='before IDAT'):
        photo_grid.decode_png(late)


def test_zlib_stream_must_terminate():
    raw = b'\0' + bytes(12) + b'\0' + bytes(12)
    full = zlib.compress(raw)
    cases = {
        'no checksum': full[:-4],             # all rows present, Adler-32 missing
        'half checksum': full[:-2],
        'flush only': (lambda c: c.compress(raw) + c.flush(zlib.Z_SYNC_FLUSH))(zlib.compressobj()),
    }
    for name, stream in cases.items():
        with pytest.raises(photo_grid.ImageDecodeError, match='truncated|length|corrupt'):
            photo_grid.decode_png(_png(3, 2, 6, list(raw.replace(b'\0' + bytes(12), bytes(12))), stream=stream))
    with pytest.raises(photo_grid.ImageDecodeError, match='extra bytes'):
        photo_grid.decode_png(_png(3, 2, 6, [0] * 24, stream=full + zlib.compress(b'')))
    assert photo_grid.decode_png(_png(3, 2, 6, [0] * 24, stream=full))[:2] == (3, 2)


CLIS = [
    ['pixel_grid.py', '--mask', 'cloud', '--format', 'png'],
    ['photo_grid.py', 'SRC', '--size', '8', '--format', 'png'],
    ['grid_png.py', 'JSON'],
    ['grid_svg.py', 'JSON'],
    ['-m', 'grid_tools', 'make', 'cloud'],
]


def _cli(args, tmp_path, out, *extra):
    src = tmp_path / 'src.png'
    src.write_bytes(g.encode(g.make('cloud'), 'png'))
    js = tmp_path / 'g.json'
    js.write_text(g.encode(g.make('cloud'), 'json'))
    args = [str(src) if a == 'SRC' else str(js) if a == 'JSON' else a for a in args]
    return subprocess.run([sys.executable, *args, '-o', str(out), *extra], cwd=ROOT, capture_output=True, timeout=60)


@pytest.mark.parametrize('args', CLIS, ids=lambda a: a[0] if a[0] != '-m' else a[1])
def test_cli_output_does_not_clobber(tmp_path, args):
    out = tmp_path / 'out'
    out.write_bytes(b'keep')
    r = _cli(args, tmp_path, out)
    assert r.returncode == 2 and b'refusing to overwrite' in r.stderr and out.read_bytes() == b'keep'
    target = tmp_path / 'target'
    target.write_bytes(b'precious')
    link = tmp_path / 'link'
    link.symlink_to(target)
    r = _cli(args, tmp_path, link)
    assert r.returncode == 2 and target.read_bytes() == b'precious' and link.is_symlink()
    dangling = tmp_path / 'dangling'
    dangling.symlink_to(tmp_path / 'missing')
    assert _cli(args, tmp_path, dangling).returncode == 2 and not (tmp_path / 'missing').exists()
    r = _cli(args, tmp_path, link, '--force')            # replaces the link, not its target
    assert r.returncode == 0, r.stderr
    assert target.read_bytes() == b'precious' and not link.is_symlink() and link.read_bytes() != b'precious'
    fresh = tmp_path / 'fresh'
    assert _cli(args, tmp_path, fresh).returncode == 0 and fresh.stat().st_size > 0


def test_write_output_api(tmp_path):
    p = tmp_path / 'a'
    write_output(p, b'1')
    with pytest.raises(FileExistsError):
        write_output(p, b'2')
    write_output(p, b'3', force=True)
    assert p.read_bytes() == b'3' and sorted(os.listdir(tmp_path)) == ['a']
    with pytest.raises(IsADirectoryError):
        write_output(tmp_path, b'x', force=True)
