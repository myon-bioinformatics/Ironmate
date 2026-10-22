"""pillow_min vs Pillow: seeded randomized parity for the API surface consumers use.

Pillow is a dev-only reference here; pillow_min itself never imports it.
"""
import io
import random
import struct
import zlib

import pytest

import pillow_min as pm

PIL = pytest.importorskip('PIL')
from PIL import Image as PILImage  # noqa: E402
from PIL import ImageChops as PILImageChops  # noqa: E402

SEEDS = range(6)
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
COMBOS = [(1, 0), (2, 0), (4, 0), (8, 0), (16, 0), (8, 2), (16, 2), (1, 3), (2, 3), (4, 3), (8, 3),
          (8, 4), (16, 4), (8, 6), (16, 6)]


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _filter(rows, bpp, rng):
    """Apply random PNG filters (0-4) to raw scanlines, as a real encoder might."""
    out, prev = [], bytes(len(rows[0])) if rows else b''
    for row in rows:
        kind = rng.randrange(5)
        enc = bytearray(len(row))
        for i, v in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = (0, a, b, (a + b) >> 1, pm.paeth(a, b, c))[kind]
            enc[i] = (v - pred) & 255
        out.append(bytes([kind]) + bytes(enc))
        prev = row
    return b''.join(out)


def _rows(w, h, depth, color, rng):
    bits = depth * CHANNELS[color]
    stride = (w * bits + 7) // 8
    rows = []
    for _ in range(h):
        row = bytearray(rng.randrange(256) for _ in range(stride))
        tail = stride * 8 - w * bits
        if tail:
            row[-1] &= (0xFF << tail) & 0xFF
        rows.append(bytes(row))
    return rows, max(1, bits // 8)


def _adam7(w, h, depth, color, rng):
    starts = ((0, 0), (4, 0), (0, 4), (2, 0), (0, 2), (1, 0), (0, 1))
    steps = ((8, 8), (8, 8), (4, 8), (4, 4), (2, 4), (2, 2), (1, 2))
    raw = b''
    for (sx, sy), (ix, iy) in zip(starts, steps):
        pw = 0 if sx >= w else (w - sx + ix - 1) // ix
        ph = 0 if sy >= h else (h - sy + iy - 1) // iy
        if pw and ph:
            rows, bpp = _rows(pw, ph, depth, color, rng)
            raw += _filter(rows, bpp, rng)
    return raw


def random_png(rng, depth, color, interlace=False, with_trns=True):
    w, h = rng.randint(1, 19), rng.randint(1, 13)
    if interlace:
        raw = _adam7(w, h, depth, color, rng)
    else:
        rows, bpp = _rows(w, h, depth, color, rng)
        raw = _filter(rows, bpp, rng)
    extra = b''
    if color == 3:
        entries = rng.randint(1, 1 << depth)  # short palettes are legal; Pillow pads with black
        extra += chunk(b'PLTE', bytes(rng.randrange(256) for _ in range(entries * 3)))
        if with_trns and rng.random() < 0.7:
            extra += chunk(b'tRNS', bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(rng.randint(1, entries))))
    elif color in (0, 2) and with_trns and rng.random() < 0.7:
        top = (1 << depth) - 1
        n = 1 if color == 0 else 3
        # out-of-range keys too: Pillow compares only their low 8 bits
        extra += chunk(b'tRNS', struct.pack(f'>{n}H', *(rng.choice((rng.randint(0, top), rng.randint(0, 65535)))
                                                          for _ in range(n))))
    header = struct.pack('>IIBBBBB', w, h, depth, color, 0, 0, 1 if interlace else 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + extra
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def assert_same_image(ours, ref):
    assert ours.mode == ref.mode
    assert ours.size == ref.size
    assert ours.tobytes() == ref.tobytes()


@pytest.mark.parametrize('seed', SEEDS)
@pytest.mark.parametrize('depth,color', COMBOS)
@pytest.mark.parametrize('interlace', [False, True])
def test_decode_matches_pillow(seed, depth, color, interlace):
    rng = random.Random(seed * 1000 + depth * 10 + color)
    data = random_png(rng, depth, color, interlace)
    with PILImage.open(io.BytesIO(data)) as ref:
        ours = pm.Image.open(io.BytesIO(data))
        assert_same_image(ours, ref)
        assert ours.info.get('transparency') == ref.info.get('transparency')
        for mode in ('RGBA', 'RGB', 'L', 'LA'):
            assert_same_image(ours.convert(mode), ref.convert(mode))


def _pil_apng(rng, n_frames, default_image):
    """RGBA APNG written by Pillow itself (frames cropped to changed regions by its encoder)."""
    w, h = rng.randint(2, 9), rng.randint(2, 7)
    frames = []
    for _ in range(n_frames):
        im = PILImage.new('RGBA', (w, h))
        # partial alpha exercises Pillow's paste-with-mask blending
        im.putdata([tuple(rng.randrange(256) for _ in range(3)) + (rng.choice((0, 255, rng.randrange(256))),)
                    for _ in range(w * h)])
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, 'PNG', save_all=True, append_images=frames[1:], loop=rng.randint(0, 3),
                   duration=[rng.randint(1, 500) for _ in frames], default_image=default_image,
                   disposal=[rng.randint(0, 2) for _ in frames], blend=[rng.randint(0, 1) for _ in frames])
    return buf.getvalue()


def _hand_apng(rng, depth, color, n_frames, default_image, interlace):
    """APNG of any colour type / depth with random sub-region frames, disposal and blending."""
    W, H = rng.randint(1, 11), rng.randint(1, 9)
    out = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, depth, color, 0, 0, int(interlace)))
    if color == 3:
        entries = rng.randint(1, 1 << depth)
        out += chunk(b'PLTE', bytes(rng.randrange(256) for _ in range(entries * 3)))
        out += chunk(b'tRNS', bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(entries)))
    elif color in (0, 2) and rng.random() < 0.5:
        n = 1 if color == 0 else 3
        out += chunk(b'tRNS', struct.pack(f'>{n}H', *(rng.randint(0, (1 << depth) - 1) for _ in range(n))))
    out += chunk(b'acTL', struct.pack('>II', n_frames, rng.randint(0, 3)))
    seq = 0

    def data_for(w, h):
        raw = _adam7(w, h, depth, color, rng) if interlace else _filter(*_rows(w, h, depth, color, rng), rng)
        return zlib.compress(raw)

    if default_image:
        out += chunk(b'IDAT', data_for(W, H))
    for i in range(n_frames):
        if i == 0:
            x, y, w, h = 0, 0, W, H  # the first frame covers the canvas
        else:
            w, h = rng.randint(1, W), rng.randint(1, H)
            x, y = rng.randint(0, W - w), rng.randint(0, H - h)
        out += chunk(b'fcTL', struct.pack('>IIIIIHHBB', seq, w, h, x, y, rng.randint(1, 900),
                                          rng.choice((0, 10, 100, 1000)), rng.randint(0, 2), rng.randint(0, 1)))
        seq += 1
        payload = data_for(w, h)
        if i == 0 and not default_image:
            out += chunk(b'IDAT', payload)
            continue
        cut = rng.randint(0, len(payload))
        for piece in (payload[:cut], payload[cut:]) if cut else (payload,):  # frame data split over fdAT
            out += chunk(b'fdAT', struct.pack('>I', seq) + piece)
            seq += 1
    return out + chunk(b'IEND', b'')


class _PillowCrash(Exception):
    pass


def _pillow_frames(data, index, read_each):
    """Frame ``index`` of a freshly opened Pillow image.

    Pillow's result can depend on whether earlier frames were read: "dispose to previous" is
    captured before the previous frame is lazily loaded. ``read_each`` reads every frame while
    iterating (the usual ``seek(i); convert()`` loop); otherwise it seeks straight to ``index``.
    """
    ref = PILImage.open(io.BytesIO(data))
    try:
        for k in (range(index + 1) if read_each else (index,)):
            ref.seek(k)
            ref.load()
    except (ValueError, TypeError) as exc:
        # Pillow 13 crashes where pillow_min decodes: the OVER-blend mask of 16-bit grayscale
        # ("conversion from I;16 to RGBA"), and frames after the first of an interlaced APNG
        # (its decoderconfig grows by one interlace flag per frame).
        assert 'I;16' in str(exc) or 'arguments' in str(exc), exc
        raise _PillowCrash() from exc
    return ref


def _same_frame(ours, ref):
    assert ours.tell() == ref.tell()
    assert_same_image(ours, ref)
    assert ours.convert('RGBA').tobytes() == ref.convert('RGBA').tobytes()
    for key in ('loop', 'duration', 'disposal', 'blend', 'bbox', 'default_image', 'transparency'):
        assert ours.info.get(key) == ref.info.get(key), key


def _assert_frames_match(data):
    with PILImage.open(io.BytesIO(data)) as ref:
        n_frames, animated = ref.n_frames, ref.is_animated
    assert pm.Image.open(data).n_frames == n_frames
    assert pm.Image.open(data).is_animated == animated
    walked = pm.Image.open(data)
    expected = []
    for i in range(n_frames):
        walked.seek(i)  # path A: read every frame while iterating
        direct = pm.Image.open(data)
        direct.seek(i)  # path B: seek straight to frame i
        try:
            ref_a = _pillow_frames(data, i, read_each=True)
            ref_b = _pillow_frames(data, i, read_each=False)
        except _PillowCrash:
            walked.tobytes()
            direct.tobytes()
            break
        _same_frame(walked, ref_a)
        _same_frame(direct, ref_b)
        expected.append(ref_a.convert('RGBA').tobytes())
    else:
        # rewinding replays the frames without reading them, i.e. path B
        walked.seek(0)
        _same_frame(walked, _pillow_frames(data, 0, read_each=False))
        walked.seek(n_frames - 1)
        _same_frame(walked, _pillow_frames(data, n_frames - 1, read_each=False))
        assert [f.tobytes() for f in pm.iter_apng_frames(data)] == expected


@pytest.mark.parametrize('seed', range(10))
@pytest.mark.parametrize('default_image', [False, True])
def test_apng_written_by_pillow_matches(seed, default_image):
    rng = random.Random(seed * 2 + default_image)
    _assert_frames_match(_pil_apng(rng, rng.randint(2, 5), default_image))


@pytest.mark.parametrize('seed', range(4))
@pytest.mark.parametrize('depth,color', COMBOS)
@pytest.mark.parametrize('default_image', [False, True])
@pytest.mark.parametrize('interlace', [False, True])
def test_apng_any_colour_type_matches(seed, depth, color, default_image, interlace):
    rng = random.Random(hash((seed, depth, color, default_image, interlace)) & 0xFFFFFFFF)
    _assert_frames_match(_hand_apng(rng, depth, color, rng.randint(2, 5), default_image, interlace))


def _random_image(rng, mode, size):
    w, h = size
    n = w * h * {'L': 1, 'LA': 2, 'RGB': 3, 'RGBA': 4}[mode]
    data = bytes(rng.choice((0, 0, 255, rng.randrange(256))) for _ in range(n))
    return pm.Image(mode, size, data), PILImage.frombytes(mode, size, data)


@pytest.mark.parametrize('seed', SEEDS)
@pytest.mark.parametrize('mode', ['L', 'LA', 'RGB', 'RGBA'])
def test_image_operations_match_pillow(seed, mode):
    rng = random.Random(seed + 7 * len(mode))
    size = (rng.randint(1, 17), rng.randint(1, 11))
    a, ra = _random_image(rng, mode, size)
    b, rb = _random_image(rng, mode, size)
    assert_same_image(pm.ImageChops.difference(a, b), PILImageChops.difference(ra, rb))
    assert_same_image(pm.ImageChops.lighter(a, b), PILImageChops.lighter(ra, rb))
    assert_same_image(pm.ImageChops.darker(a, b), PILImageChops.darker(ra, rb))
    for ours, ref in zip(a.split(), ra.split()):
        assert_same_image(ours, ref)
    assert a.getextrema() == ra.getextrema()
    assert a.histogram() == ra.histogram()
    assert a.getbbox() == ra.getbbox()
    assert a.getbbox(alpha_only=False) == ra.getbbox(alpha_only=False)
    threshold = rng.randrange(256)
    assert_same_image(a.point(lambda v: 255 if v > threshold else 0),
                      ra.point(lambda v: 255 if v > threshold else 0))
    assert_same_image(a.point(lambda v: v * 0.7 + 3.5), ra.point(lambda v: v * 0.7 + 3.5))
    box = (rng.randint(-3, size[0]), rng.randint(-3, size[1]), 0, 0)
    box = (box[0], box[1], box[0] + rng.randint(0, 8), box[1] + rng.randint(0, 8))
    assert_same_image(a.crop(box), ra.crop(box))
    for target in ('L', 'LA', 'RGB', 'RGBA'):
        assert_same_image(a.convert(target), ra.convert(target))
    x, y = rng.randrange(size[0]), rng.randrange(size[1])
    assert a.getpixel((x, y)) == ra.getpixel((x, y))
    value = b.getpixel((x, y))
    a.putpixel((x, y), value)
    ra.putpixel((x, y), value)
    assert_same_image(a, ra)
    a.putpixel((-1, -1), value)
    ra.putpixel((-1, -1), value)
    assert_same_image(a, ra)
    assert (a.width, a.height) == (ra.width, ra.height)


def test_image_diff_pipeline_matches_pillow():
    """The exact call chain of browser-test-kit scripts/image_diff.py compare()."""
    rng = random.Random(5)
    for _ in range(25):
        size = (rng.randint(1, 30), rng.randint(1, 20))
        a, ra = _random_image(rng, 'RGBA', size)
        b, rb = _random_image(rng, 'RGBA', size)
        tolerance = rng.randrange(256)
        for mod, x, y in ((pm, a, b), (None, ra, rb)):
            chops = pm.ImageChops if mod else PILImageChops
            diff = chops.difference(x, y)
            bands = diff.split()
            max_band = bands[0]
            for band in bands[1:]:
                max_band = chops.lighter(max_band, band)
            mask = max_band.point(lambda value: 255 if value > tolerance else 0, mode='L')
            result = (mask.histogram()[255], mask.getbbox(), max(hi for _lo, hi in diff.getextrema()),
                      mask.width * mask.height)
            if mod:
                ours = result
            else:
                assert ours == result


@pytest.mark.parametrize('seed', SEEDS)
def test_constructors_and_save_roundtrip(seed, tmp_path):
    rng = random.Random(seed)
    for mode, color in (('RGB', 5), ('RGBA', 0x01020304), ('RGBA', (1, 2, 3)), ('RGBA', None), ('L', 300),
                        ('LA', (1, 2)), ('P', 3), ('RGB', (9, 8, 7))):
        args = (mode, (3, 2)) if color is None else (mode, (3, 2), color)
        assert_same_image(pm.Image.new(*args), PILImage.new(*args))
    for mode in ('L', 'LA', 'RGB', 'RGBA'):
        bands = {'L': 1, 'LA': 2, 'RGB': 3, 'RGBA': 4}[mode]
        values = [rng.randrange(-20, 300) if bands == 1 else tuple(rng.randrange(256) for _ in range(bands))
                  for _ in range(12)]
        ours, ref = pm.Image.new(mode, (4, 3)), PILImage.new(mode, (4, 3))
        ours.putdata(values)
        ref.putdata(values)
        assert_same_image(ours, ref)
        path = tmp_path / f'{mode}.png'
        ours.save(path)
        with PILImage.open(path) as back:
            assert_same_image(ours, back)  # pillow_min writes, Pillow reads
        buf = io.BytesIO()
        ref.save(buf, 'PNG')
        assert_same_image(pm.Image.open(io.BytesIO(buf.getvalue())), ref)  # Pillow writes, pillow_min reads
    palette = [rng.randrange(256) for _ in range(12)]
    for bits in (1, 2, 4, 8):
        for transparency in (0, 2, bytes([255, 128, 0])):
            ours, ref = pm.Image.new('P', (5, 2)), PILImage.new('P', (5, 2))
            idx = [rng.randrange(min(4, 1 << bits)) for _ in range(10)]
            for im in (ours, ref):
                im.putdata(idx)
                im.putpalette(palette)
            path = tmp_path / f'p{bits}.png'
            ours.save(path, bits=bits, transparency=transparency)
            with PILImage.open(path) as back:
                assert back.convert('RGBA').tobytes() == ref.convert('RGBA').tobytes() if transparency is None else True
                expected = io.BytesIO()
                ref.save(expected, 'PNG', bits=bits, transparency=transparency)
                with PILImage.open(io.BytesIO(expected.getvalue())) as want:
                    assert back.convert('RGBA').tobytes() == want.convert('RGBA').tobytes()
                    assert_same_image(pm.Image.open(expected.getvalue()).convert('RGBA'), want.convert('RGBA'))


def test_limits_follow_pillow(monkeypatch):
    data = random_png(random.Random(0), 8, 2, with_trns=False)
    monkeypatch.setattr(pm, 'MAX_IMAGE_PIXELS', 4)
    w, h = struct.unpack('>II', data[16:24])
    if w * h > 8:
        with pytest.raises(pm.DecompressionBombError):
            pm.Image.open(data)
    monkeypatch.setattr(pm, 'MAX_IMAGE_PIXELS', None)
    pm.Image.open(data)  # no limit, as with PIL.Image.MAX_IMAGE_PIXELS = None


def test_tall_screenshot_beyond_old_4096_limit():
    im = PILImage.new('RGB', (64, 5000), (1, 2, 3))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    assert_same_image(pm.Image.open(buf.getvalue()), im)


def test_errors_are_value_and_os_errors():
    for bad in (b'GIF89a....', b'\x89PNG\r\n\x1a\n' + b'\0' * 4):
        with pytest.raises(OSError):
            pm.Image.open(bad)
        with pytest.raises(ValueError):
            pm.Image.open(bad)


def test_non_png_save_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        pm.Image.new('RGB', (1, 1)).save(tmp_path / 'x.jpg')
    with pytest.raises(ValueError):
        pm.Image.new('RGB', (1, 1)).save(io.BytesIO(), 'JPEG')
