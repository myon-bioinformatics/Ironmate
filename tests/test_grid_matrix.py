"""Pixel grids as per-channel matrices (numpy), after the SVD / sign+scale ideas in Aoi.

Idea credit: myon-bioinformatics/Aoi ``pythdragoras/littlebit_prune.py`` (SVD residual stages,
sign(U) / sign(V) with scales) and ``queryu/ask/suggest.py`` (SVD + binary sign index). Re-implemented
here in a few lines; nothing is imported from Aoi.

Findings encoded below: the exact residual R = restored - original (all four channels) is the
primary check and must be zero on lossless paths. Singular values alone are blind to row/column
permutations and transposition, so they are only a secondary fingerprint; adding the sign pattern of
the leading singular vectors (Aoi's sign index) recovers most of those cases but not all.
"""
import io, random

import pytest

np = pytest.importorskip('numpy')

import grid_tools as g
import photo_grid
from test_grid_properties import KINDS as KINDS_, _mutations, cases, gen


def channels(art):
    """(4, H, W) float matrix stack: R, G, B, A."""
    pal = np.array([list(bytes.fromhex(c[1:])) for c in art['colors']], dtype=np.float64)
    return pal[np.array(art['pixels'])].transpose(2, 0, 1)


def residual(a, b):
    ca, cb = channels(a), channels(b)
    if ca.shape != cb.shape:
        return None
    return cb - ca


def singular_values(art):
    return [np.linalg.svd(m, compute_uv=False) for m in channels(art)]


def sign_scale(art, rank=2):
    """Aoi-style fingerprint: per channel, singular values + sign(U[:, :r]) and sign(V[:, :r])."""
    out = []
    for m in channels(art):
        u, s, vt = np.linalg.svd(m - m.mean(), full_matrices=False)
        r = min(rank, len(s))
        su, sv = np.sign(u[:, :r]), np.sign(vt[:r].T)
        flip = np.where(np.sign(su[0]) == 0, 1, np.sign(su[0]))  # fix SVD's sign ambiguity
        out.append((np.round(s, 6), (su * flip).astype(int), (sv * flip).astype(int)))
    return out


def same_fingerprint(fa, fb):
    return all(a[0].shape == b[0].shape and np.allclose(a[0], b[0]) and np.array_equal(a[1], b[1])
               and np.array_equal(a[2], b[2]) for a, b in zip(fa, fb))


def test_residual_is_exactly_zero_on_lossless_paths():
    count = 0
    for kind, i, art in cases(40, 15):
        scale = 1 + i % 3
        paths = {
            'meta': g.restore(g.encode(art, 'base64', scale)),
            'size-hint': g.restore(g.encode(art, 'png', scale, meta=False), size=art['width']),
            'resize-back': g.resize(g.resize(art, art['width'] * 3 + 1, art['height'] * 2 + 1),
                                    art['width'], art['height']),
        }
        for name, back in paths.items():
            r = residual(art, back)
            assert r is not None and not np.any(r), (kind, i, name)
            count += 1
    assert count == len(KINDS_) * 15 * 3


def test_fingerprints_vs_exact_residual_on_mutations(capsys):
    rnd = random.Random(41)
    stats = {}
    for kind, i, art in cases(42, 10):
        for name, mut in _mutations(art, rnd).items():
            r = residual(art, mut)
            if r is not None and not np.any(r):
                continue                     # visual no-op (e.g. symmetric flip)
            s = stats.setdefault(name, [0, 0, 0, 0])
            s[0] += 1
            s[1] += 1                        # exact residual / per-pixel check: always detects
            sva, svb = singular_values(art), singular_values(mut)
            s[2] += not all(a.shape == b.shape and np.allclose(a, b) for a, b in zip(sva, svb))
            s[3] += not same_fingerprint(sign_scale(art), sign_scale(mut))
    for name, (n, exact, sv, signs) in stats.items():
        assert exact == n
    # Singular values are invariant under row permutation / transpose: provably blind.
    assert stats['flip'][2] == 0 and stats['transpose'][2] == 0
    assert stats['flip'][3] > 0.8 * stats['flip'][0]
    with capsys.disabled():
        print('\nmutation: n / exact / singular-values / sign+scale')
        for name, row in sorted(stats.items()):
            print(f'  {name:14s}', *row)


def test_lossy_paths_report_error_norms(capsys):
    lines = []
    rnd = random.Random(43)
    for kind in ('noise', 'checker', 'blocks', 'flat'):
        art = gen(rnd, kind)
        w, h = art['width'], art['height']
        if w < 2 or h < 2:
            continue
        back = g.resize(g.resize(art, max(1, w // 2), max(1, h // 2)), w, h)
        r = residual(art, back)
        rms = float(np.sqrt((r ** 2).mean()))
        changed = float((np.abs(r).sum(0) > 0).mean())
        assert rms <= 255 and float(np.abs(r).max()) <= 255
        if kind == 'flat':
            assert rms == 0                   # uniform blocks: the lossless exception
        lines.append(f'  down2-up {kind:8s} rms={rms:6.2f} changed={changed:.0%}')
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image:
        img = Image.new('RGB', (64, 64))
        img.putdata([(x * 4, y * 4, (x + y) * 2) for y in range(64) for x in range(64)])
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=90)
        art = g.photo(buf.getvalue(), 32, colors=16)
        ref = np.asarray(img.resize((32, 32), Image.BOX), dtype=np.float64).transpose(2, 0, 1)
        rms = float(np.sqrt(((channels(art)[:3] - ref) ** 2).mean()))
        assert rms < 30                       # lossy but bounded: JPEG + 16-color median cut
        lines.append(f'  jpeg->32x32x16 rms vs box-downscale={rms:.2f}')
        assert g.restore(g.encode(art)) == art    # lossless from the grid onward
    with capsys.disabled():
        print('\n' + '\n'.join(lines))


def test_low_rank_is_not_a_storage_format():
    """A rank-k sign+scale approximation (LittleBit-style) is lossy for dot art; documented, not used."""
    art = gen(random.Random(44), 'noise')
    m = channels(art)[0]
    u, s, vt = np.linalg.svd(m, full_matrices=False)
    k = max(1, len(s) // 4)
    approx = (np.sign(u[:, :k]) * np.abs(u[:, :k]).mean(0) * s[:k]) @ (np.sign(vt[:k]) * np.abs(vt[:k]).mean(1)[:, None])
    assert np.abs(np.rint(approx) - m).max() > 0
