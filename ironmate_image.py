"""Ironmate image facade: one call for the fiddly decisions (stdlib only; Pillow optional for JPEG/WebP).

    python -c "import ironmate_image as im; print(im.fit_to_limit('a.png', max_chars=20000).text)"
    python -m grid_tools fit a.png --limit-chars 20000 -o out.b64

``src`` is anything: a path, PNG/JPEG/WebP bytes, Base64, a data URI, ironmate JSON or a grid dict.
Output is always the default grid_tools PNG (8-bit RGBA, ironmate metadata when it fits).
"""
from __future__ import annotations
import base64, json, os
from dataclasses import dataclass, field
from fractions import Fraction

import grid_tools
import photo_grid
import size_estimate

__all__ = ['FitError', 'FitResult', 'fit_to_limit', 'load', 'to_base64', 'from_base64', 'to_png', 'resize']


class FitError(ValueError):
    """The image cannot be made to fit the limit (even the smallest candidate without metadata)."""


@dataclass
class FitResult:
    data: bytes                 # PNG bytes
    text: str                   # Base64 (with data: prefix when data_uri)
    ratio: str                  # e.g. '1', '1/2', '2/3'
    width: int
    height: int
    bytes: int                  # len(data)
    chars: int                  # len(text)
    meta_used: bool
    lossless: bool              # nearest-neighbour ratio that loses no dot-art cells
    command: str                # equivalent grid_tools CLI
    warnings: list = field(default_factory=list)


def _bytes(src):
    if isinstance(src, os.PathLike) or (isinstance(src, str) and len(src) < 4096 and os.path.isfile(src)):
        with open(src, 'rb') as fh:
            return fh.read(photo_grid.MAX_BYTES * 2)
    return src


def _image(src):
    """-> raw image bytes (PNG/JPEG/WebP/SVG) from any accepted form."""
    src = _bytes(src)
    if isinstance(src, bytes) and photo_grid._sniff(src):
        return src
    return photo_grid.decode_base64(src)


def load(src):
    """Anything -> ironmate grid artifact (dict). PNG/SVG dot art exactly; JPEG/WebP at full size, 1 cell = 1 px."""
    src = _bytes(src)
    if isinstance(src, dict) or (isinstance(src, (str, bytes)) and (src.lstrip()[:1] in ('{', b'{'))):
        return grid_tools.restore(json.loads(src) if isinstance(src, (str, bytes)) else src)
    data = _image(src)
    kind = photo_grid._sniff(data)
    if kind in ('png', 'svg'):
        return grid_tools.restore(data)
    _, pixels = size_estimate.inspect(data)
    if pixels is None:
        raise ValueError(f'cannot decode {kind}: install Pillow for JPEG/WebP')
    return size_estimate._candidate_artifact(None, kind, pixels[0], pixels, pixels[0])


def to_png(src, meta=True):
    return grid_tools.encode(load(src), 'png', 1, meta=meta)


def to_base64(src, data_uri=False, meta=True):
    """Anything -> Base64 PNG (reversible: from_base64(to_base64(x)) == load(x))."""
    return grid_tools.encode(load(src), 'base64', 1, data_uri, meta)


def from_base64(text):
    """Base64 / data URI -> grid artifact (exact when it carries ironmate metadata)."""
    return load(photo_grid.decode_base64(text) if isinstance(text, str) else text)


def resize(src, width, height=None):
    """Nearest-neighbour resize of the grid (height keeps the aspect ratio)."""
    return grid_tools.resize(load(src), width, height)


def fit_to_limit(src, max_bytes=None, max_chars=None, data_uri=False, prefer='lossless'):
    """Largest verified PNG/Base64 of ``src`` that fits ``max_bytes`` or ``max_chars``.

    ``prefer='lossless'`` takes the largest dot-art-lossless ratio that fits (else the largest ratio);
    ``prefer='largest'`` takes the largest ratio. Metadata is kept when it fits and dropped (with a
    warning) only if nothing fits with it. Raises FitError when nothing fits.
    """
    if prefer not in ('lossless', 'largest'):
        raise ValueError("prefer must be 'lossless' or 'largest'")
    if (max_bytes is None) == (max_chars is None):
        raise ValueError('give exactly one of max_bytes or max_chars')
    data = _image(src)
    warnings, picks = [], []
    for meta in (True, False):
        r = size_estimate.estimate(data, limit_bytes=max_bytes, limit_chars=max_chars, data_uri=data_uri,
                                   verify=True, meta=meta)
        if r['confidence'] != 'verified':
            raise ValueError('could not decode pixels to verify (install Pillow for JPEG/WebP)')
        picks += [(bool(o['nearest_lossless']) if prefer == 'lossless' else False, Fraction(o['ratio']), meta, o, r)
                  for o in r['options'] if o['actual_bytes'] <= r['target_bytes']]
    if not picks:
        raise FitError(f"cannot fit: smallest candidate is {r['smallest']['actual_bytes']} bytes "
                       f"({r['smallest']['actual_chars']} chars) without metadata > limit")
    # Pixels first (lossless, then larger ratio); metadata only breaks ties.
    _, _, meta, pick, r = max(picks, key=lambda t: t[:3])
    if not meta:
        warnings.append('ironmate metadata dropped to fit (palette order/size header not embedded; '
                        'pixels still exact)')
    if prefer == 'lossless' and not pick['nearest_lossless']:
        warnings.append(f"no lossless ratio fits; using {pick['ratio']} (dot-art cells may be dropped)")
    png = grid_tools.encode(size_estimate._candidate_artifact(
        data if r['input']['format'] == 'png' else None, r['input']['format'], r['input']['width'],
        size_estimate.inspect(data)[1], pick['width']), 'png', 1, meta=meta)
    text = ('data:image/png;base64,' if data_uri else '') + base64.b64encode(png).decode('ascii')
    assert len(png) == pick['actual_bytes'] and len(text) == pick['actual_chars']
    assert (len(png) <= max_bytes) if max_bytes is not None else (len(text) <= max_chars)
    h = grid_tools.restore(png)['height'] if meta else pick['height']
    return FitResult(png, text, pick['ratio'], pick['width'], h, len(png), len(text), meta,
                     pick['nearest_lossless'], pick['command'], warnings)
