"""Minimal Pillow replacement for PNG read/write and image diff (stdlib only, Python 3.9+).

Single-file module: no third-party imports. Non-PNG formats are rejected with a clear error.
"""
from __future__ import annotations

import base64
import binascii
import re
import struct
import zlib
from typing import Callable, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

__all__ = [
    'Image',
    'ImageChops',
    'ImageDecodeError',
    'UnsupportedImageError',
    'MAX_PIXELS',
    'MAX_DIMENSION',
    'decode_base64',
    'encode_png',
    'open_bytes',
    'diff_metrics',
    'iter_apng_frames',
    'paeth',
    'unfilter_scanlines',
]

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PIXELS = 4096 * 4096
MAX_DIMENSION = 4096
MAX_DECOMPRESSED = 64 * 1024 * 1024
_DATA_URI = re.compile(
    r'data:([\w.+-]+/[\w.+-]+)?((?:;[\w.+-]+=[\w.+-]+)*);base64,',
    re.ASCII | re.IGNORECASE,
)
_BASE64 = re.compile(r'[A-Za-z0-9+/]*={0,2}', re.ASCII)

_ADAM7_START = ((0, 0), (4, 0), (0, 4), (2, 0), (0, 2), (1, 0), (0, 1))
_ADAM7_INCREMENT = ((8, 8), (8, 8), (4, 8), (4, 4), (2, 4), (2, 2), (1, 2))

_COLOR_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class ImageDecodeError(ValueError):
    """PNG or image payload could not be decoded."""


class UnsupportedImageError(ImageDecodeError):
    """Format is not PNG."""


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def unfilter_scanlines(raw: bytes, width: int, height: int, bpp: int) -> List[bytes]:
    """Reverse PNG scanline filters into ``height`` rows of ``width * bpp`` bytes."""
    stride = width * bpp
    if len(raw) != height * (stride + 1):
        raise ImageDecodeError('PNG image data has unexpected length')
    rows: List[bytes] = []
    prev = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + paeth(left, prev[i], up_left)) & 255
        elif kind != 0:
            raise ImageDecodeError(f'unknown PNG filter type {kind}')
        rows.append(bytes(line))
        prev = line
    return rows


def _check_limits(
    width: int,
    height: int,
    max_pixels: int = MAX_PIXELS,
    max_dimension: int = MAX_DIMENSION,
) -> None:
    if width <= 0 or height <= 0:
        raise ImageDecodeError('image has zero width or height')
    if width > max_dimension or height > max_dimension:
        raise ImageDecodeError(f'image dimension exceeds limit {max_dimension}')
    if width * height > max_pixels:
        raise ImageDecodeError(f'image has {width * height} pixels; limit is {max_pixels}')


def _pass_size(width: int, height: int, pass_no: int) -> Tuple[int, int]:
    sx, sy = _ADAM7_START[pass_no]
    ix, iy = _ADAM7_INCREMENT[pass_no]
    w = 0 if sx >= width else (width - sx + ix - 1) // ix
    h = 0 if sy >= height else (height - sy + iy - 1) // iy
    return w, h


def _unpack_palette_row(line: bytes, width: int, depth: int) -> bytes:
    if depth == 8:
        return line[:width]
    out = bytearray(width)
    bit = 0
    for x in range(width):
        byte = line[bit >> 3]
        shift = 8 - depth - (bit & 7)
        mask = (1 << depth) - 1
        out[x] = (byte >> shift) & mask
        bit += depth
    return bytes(out)


def _palette_rgba(
    indices: Sequence[int],
    palette: Sequence[Tuple[int, int, int]],
    trans: Optional[Sequence[int]],
) -> bytes:
    out = bytearray(len(indices) * 4)
    for i, idx in enumerate(indices):
        if idx >= len(palette):
            raise ImageDecodeError('PNG palette index out of range')
        r, g, b = palette[idx]
        if trans is not None:
            if idx < len(trans):
                a = trans[idx]
            else:
                a = 255
        else:
            a = 255
        o = i * 4
        out[o:o + 4] = bytes((r, g, b, a))
    return bytes(out)


def _to_rgba_row(line: bytes, channels: int, trns: Optional[bytes]) -> bytes:
    if channels == 4:
        return bytes(line)
    out = bytearray()
    if channels == 3:
        key = trns
        for i in range(0, len(line), 3):
            rgb = bytes(line[i:i + 3])
            out += rgb + (b'\x00' if key is not None and rgb == key else b'\xff')
    elif channels == 2:
        for i in range(0, len(line), 2):
            out += bytes((line[i], line[i], line[i], line[i + 1]))
    else:
        key = trns[0:1] if trns else None
        for i in range(len(line)):
            out += bytes((line[i], line[i], line[i], 0 if key == bytes((line[i],)) else 255))
    return bytes(out)


def _chunk_crc(kind: bytes, body: bytes, crc: bytes) -> None:
    if zlib.crc32(kind + body) != struct.unpack('>I', crc)[0]:
        raise ImageDecodeError(f'PNG chunk {kind!r} has a bad CRC')


def _decompress_idat(
    chunks: Iterable[bytes],
    expected: int,
    max_decompressed: int,
) -> bytes:
    inflater = zlib.decompressobj()
    out = bytearray()
    for piece in chunks:
        out.extend(inflater.decompress(piece, max_decompressed + 1 - len(out)))
        if len(out) > max_decompressed:
            raise ImageDecodeError('PNG image data exceeds decompressed size limit')
    if not inflater.eof:
        tail = inflater.decompress(inflater.unconsumed_tail, max_decompressed + 1 - len(out))
        out.extend(tail)
    if inflater.unused_data:
        raise ImageDecodeError('PNG image data has extra bytes after the zlib stream')
    if len(out) != expected:
        raise ImageDecodeError('PNG image data has unexpected length')
    return bytes(out)


def _read_png_chunks(
    data: bytes,
    max_pixels: int,
    max_dimension: int,
    max_decompressed: int,
    *,
    animation: bool,
) -> Tuple[dict, List[Tuple[dict, bytes]]]:
    if not data.startswith(PNG_SIGNATURE):
        raise UnsupportedImageError('not a PNG file')
    pos = 8
    header = None
    palette: List[Tuple[int, int, int]] = []
    trns: Optional[bytes] = None
    idat: List[bytes] = []
    frames: List[Tuple[dict, List[bytes]]] = []
    current_fc = None
    actl = None
    while True:
        if pos + 8 > len(data):
            raise ImageDecodeError('truncated PNG (missing IEND)')
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise ImageDecodeError('truncated PNG chunk')
        _chunk_crc(kind, body, crc)
        pos += 12 + length
        if header is None and kind != b'IHDR':
            raise ImageDecodeError('PNG must start with IHDR')
        if kind == b'IHDR':
            if length != 13:
                raise ImageDecodeError('invalid IHDR')
            header = struct.unpack('>IIBBBBB', body)
            width, height, depth, color, compression, filtering, interlace = header
            if color not in _COLOR_CHANNELS:
                raise ImageDecodeError(f'unsupported PNG color type {color}')
            if depth not in (1, 2, 4, 8, 16):
                raise ImageDecodeError(f'unsupported PNG bit depth {depth}')
            if color == 3 and depth not in (1, 2, 4, 8):
                raise ImageDecodeError('invalid palette PNG bit depth')
            if color != 3 and depth != 8 and depth != 16:
                raise ImageDecodeError(
                    f'unsupported PNG (bit depth {depth}, color type {color}); '
                    'only 8-bit truecolor/grayscale and low-bit palette are supported')
            if depth == 16:
                raise ImageDecodeError(f'unsupported PNG bit depth {depth}')
            if compression or filtering:
                raise ImageDecodeError('invalid PNG compression/filter method')
            _check_limits(width, height, max_pixels, max_dimension)
        elif kind == b'PLTE':
            if header is None or header[3] != 3:
                raise ImageDecodeError('PLTE is not allowed for this PNG color type')
            if length % 3 or length > 768:
                raise ImageDecodeError('invalid PLTE length')
            palette = [tuple(body[i:i + 3]) for i in range(0, length, 3)]
        elif kind == b'tRNS':
            if idat or trns is not None:
                raise ImageDecodeError('tRNS must appear once, before IDAT')
            if header is None:
                raise ImageDecodeError('tRNS before IHDR')
            color = header[3]
            if color in (4, 6):
                raise ImageDecodeError(f'tRNS is not allowed for PNG color type {color}')
            if color == 0:
                if length != 2:
                    raise ImageDecodeError('invalid tRNS length')
                sample = struct.unpack('>H', body)[0]
                if sample > 255:
                    raise ImageDecodeError('tRNS value exceeds the 8-bit sample range')
                trns = bytes((sample,))
            elif color == 2:
                if length != 6:
                    raise ImageDecodeError('invalid tRNS length')
                samples = struct.unpack('>3H', body)
                if any(v > 255 for v in samples):
                    raise ImageDecodeError('tRNS value exceeds the 8-bit sample range')
                trns = bytes(samples)
            else:
                trns = bytes(body)
        elif kind == b'acTL':
            if not animation:
                continue
            if length != 8:
                raise ImageDecodeError('invalid acTL length')
            actl = struct.unpack('>II', body)
        elif kind == b'fcTL':
            if not animation:
                continue
            if length != 26:
                raise ImageDecodeError('invalid fcTL length')
            seq, fw, fh, xo, yo, delay_num, delay_den, dispose, blend = struct.unpack('>IIIIIHHBB', body)
            current_fc = {
                'seq': seq,
                'width': fw,
                'height': fh,
                'x': xo,
                'y': yo,
                'delay': (delay_num, delay_den),
                'dispose': dispose,
                'blend': blend,
            }
        elif kind == b'IDAT':
            if animation and current_fc is not None:
                frames.append((current_fc, [body]))
                current_fc = None
            else:
                idat.append(body)
        elif kind == b'fdAT':
            if not animation:
                continue
            if length < 4:
                raise ImageDecodeError('invalid fdAT length')
            seq = struct.unpack('>I', body[:4])[0]
            payload = body[4:]
            if current_fc is None:
                current_fc = {'seq': seq}
            if frames and frames[-1][0].get('seq') == seq:
                frames[-1][1].append(payload)
            else:
                frames.append((current_fc or {'seq': seq}, [payload]))
                current_fc = None
        elif kind == b'IEND':
            if pos != len(data):
                raise ImageDecodeError(f'{len(data) - pos} bytes of trailing data after PNG IEND')
            break
    if header is None:
        raise ImageDecodeError('PNG missing IHDR')
    if header[3] == 3 and not palette:
        raise ImageDecodeError('palette PNG missing PLTE')
    meta = {
        'header': header,
        'palette': palette,
        'trns': trns,
        'idat': idat,
        'actl': actl,
        'frames': frames,
    }
    return meta, frames


def _adam7_raw_length(width: int, height: int, depth: int, color: int) -> int:
    channels = _COLOR_CHANNELS[color]
    total = 0
    for p in range(7):
        pw, ph = _pass_size(width, height, p)
        if not pw or not ph:
            continue
        if color == 3:
            row_bytes = (pw * depth + 7) // 8
        else:
            row_bytes = pw * channels
        total += ph * (row_bytes + 1)
    return total


def _deinterlace_to_rows(
    raw: bytes,
    width: int,
    height: int,
    depth: int,
    color: int,
) -> List[bytes]:
    channels = _COLOR_CHANNELS[color]
    if color == 3:
        indices = bytearray(width * height)
    else:
        buffer = bytearray(width * height * channels)
    pos = 0
    for pass_no in range(7):
        pw, ph = _pass_size(width, height, pass_no)
        if not pw or not ph:
            continue
        if color == 3:
            row_bytes = (pw * depth + 7) // 8
            filter_width, filter_bpp = row_bytes, 1
        else:
            row_bytes = pw * channels
            filter_width, filter_bpp = pw, channels
        need = ph * (row_bytes + 1)
        chunk = raw[pos:pos + need]
        pos += need
        prows = unfilter_scanlines(chunk, filter_width, ph, filter_bpp)
        sx, sy = _ADAM7_START[pass_no]
        ix, iy = _ADAM7_INCREMENT[pass_no]
        for py, line in enumerate(prows):
            y = sy + py * iy
            if color == 3:
                idx = _unpack_palette_row(line, pw, depth)
                for px, value in enumerate(idx):
                    x = sx + px * ix
                    indices[y * width + x] = value
            else:
                for px in range(pw):
                    x = sx + px * ix
                    dst = (y * width + x) * channels
                    src = px * channels
                    buffer[dst:dst + channels] = line[src:src + channels]
    if pos != len(raw):
        raise ImageDecodeError('PNG image data has unexpected length')
    if color == 3:
        return [bytes(indices[y * width:(y + 1) * width]) for y in range(height)]
    return [bytes(buffer[y * width * channels:(y + 1) * width * channels]) for y in range(height)]


def _rows_from_idat(meta: dict, max_decompressed: int) -> Tuple[int, int, List[bytes]]:
    header = meta['header']
    width, height, depth, color, _, _, interlace = header
    channels = _COLOR_CHANNELS[color]
    if color == 3:
        packed_stride = (width * depth + 7) // 8
    else:
        packed_stride = width * channels
    raw_len = _adam7_raw_length(width, height, depth, color) if interlace else height * (packed_stride + 1)
    if raw_len > max_decompressed:
        raise ImageDecodeError('PNG image data exceeds decompressed size limit')
    if not meta['idat']:
        raise ImageDecodeError('PNG has no image data')
    raw = _decompress_idat(meta['idat'], raw_len, max_decompressed)
    if interlace:
        if color == 3:
            index_rows = _deinterlace_to_rows(raw, width, height, depth, color)
            trans = meta['trns']
            return width, height, [_palette_rgba(row, meta['palette'], trans) for row in index_rows]
        sample_rows = _deinterlace_to_rows(raw, width, height, depth, color)
        return width, height, [_to_rgba_row(line, channels, meta['trns']) for line in sample_rows]
    if color == 3:
        rows_packed = unfilter_scanlines(raw, packed_stride, height, 1)
        trans = meta['trns']
        return width, height, [
            _palette_rgba(_unpack_palette_row(line, width, depth), meta['palette'], trans)
            for line in rows_packed
        ]
    rows = unfilter_scanlines(raw, width, height, channels)
    return width, height, [_to_rgba_row(line, channels, meta['trns']) for line in rows]


def decode_png_rgba(
    data: bytes,
    *,
    max_pixels: int = MAX_PIXELS,
    max_dimension: int = MAX_DIMENSION,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> Tuple[int, int, List[bytes]]:
    meta, _ = _read_png_chunks(data, max_pixels, max_dimension, max_decompressed, animation=False)
    return _rows_from_idat(meta, max_decompressed)


def iter_apng_frames(
    data: bytes,
    *,
    max_pixels: int = MAX_PIXELS,
    max_dimension: int = MAX_DIMENSION,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> Iterator[Image]:
    """Yield each APNG frame as an RGBA :class:`Image` (compositing is not simulated)."""
    meta, extra = _read_png_chunks(data, max_pixels, max_dimension, max_decompressed, animation=True)
    w, h, rows = _rows_from_idat(meta, max_decompressed)
    yield Image.from_rgba_rows(w, h, rows)
    for fc, chunks in extra:
        if not chunks:
            continue
        fw = fc.get('width', w)
        fh = fc.get('height', h)
        channels = 4
        row_bytes = fw * channels
        raw_len = fh * (row_bytes + 1)
        raw = _decompress_idat(chunks, raw_len, max_decompressed)
        frows = unfilter_scanlines(raw, fw, fh, channels)
        yield Image.from_rgba_rows(fw, fh, frows)


def encode_png(image: Image, *, compress_level: int = 9) -> bytes:
    if image.mode not in ('RGB', 'RGBA'):
        raise ValueError('encode_png supports RGB and RGBA only')
    width, height = image.size
    _check_limits(width, height)
    channels = 3 if image.mode == 'RGB' else 4
    raw = bytearray()
    stride = width * channels
    data = image.tobytes()
    for y in range(height):
        raw.append(0)
        off = y * stride
        raw.extend(data[off:off + stride])
    color_type = 2 if image.mode == 'RGB' else 6
    header = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))

    return (PNG_SIGNATURE + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(bytes(raw), compress_level))
            + chunk(b'IEND', b''))


def max_base64_chars(max_bytes: int = 32 * 1024 * 1024) -> int:
    return 4 * ((max_bytes + 2) // 3)


def decode_base64(text: Union[str, bytes], max_bytes: int = 32 * 1024 * 1024) -> bytes:
    if isinstance(text, bytes):
        try:
            text = text.decode('ascii')
        except UnicodeDecodeError:
            raise ValueError('Base64 input must be ASCII') from None
    text = text.lstrip('\ufeff').strip()
    match = _DATA_URI.match(text)
    mime = (match.group(1) or '').lower() if match else ''
    if mime and mime not in ('image/png',):
        raise ValueError(f'unsupported data URI type {mime!r}; only image/png is supported')
    if match:
        text = text[match.end():]
    elif text[:5].lower() == 'data:':
        raise ValueError('data URI must be base64-encoded (data:<type>;base64,...)')
    text = ''.join(text.split())
    if not text:
        raise ValueError('Base64 input is empty')
    if len(text) > max_base64_chars(max_bytes):
        raise ValueError(f'decoded input exceeds {max_bytes} bytes')
    if len(text) % 4 or not _BASE64.fullmatch(text):
        raise ValueError('invalid Base64 input')
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('invalid Base64 input') from None
    if len(data) > max_bytes:
        raise ValueError(f'decoded input exceeds {max_bytes} bytes')
    if mime == 'image/png' and not data.startswith(PNG_SIGNATURE):
        raise ValueError('data URI says image/png but the decoded bytes are not that format')
    return data


def open_bytes(
    data: bytes,
    *,
    max_pixels: int = MAX_PIXELS,
    max_dimension: int = MAX_DIMENSION,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> Image:
    if not data.startswith(PNG_SIGNATURE):
        raise UnsupportedImageError('only PNG input is supported')
    w, h, rows = decode_png_rgba(data, max_pixels=max_pixels, max_dimension=max_dimension,
                                 max_decompressed=max_decompressed)
    return Image.from_rgba_rows(w, h, rows)


class Image:
    modes = frozenset({'L', 'RGB', 'RGBA'})

    def __init__(self, mode: str, size: Tuple[int, int], data: bytes):
        if mode not in self.modes:
            raise ValueError(f'unsupported mode {mode!r}')
        w, h = size
        bpp = {'L': 1, 'RGB': 3, 'RGBA': 4}[mode]
        if len(data) != w * h * bpp:
            raise ValueError('image data length does not match size and mode')
        self.mode = mode
        self.size = size
        self._data = data

    @classmethod
    def from_rgba_rows(cls, width: int, height: int, rows: Sequence[bytes]) -> 'Image':
        if len(rows) != height:
            raise ValueError('row count mismatch')
        stride = width * 4
        for row in rows:
            if len(row) != stride:
                raise ValueError('row stride mismatch')
        return cls('RGBA', (width, height), b''.join(rows))

    @staticmethod
    def new(mode: str, size: Tuple[int, int], color: Union[int, Tuple[int, ...]] = 0) -> 'Image':
        w, h = size
        if mode == 'L':
            c = int(color) if isinstance(color, int) else int(color[0])
            fill = bytes([c & 255]) * (w * h)
        elif mode == 'RGB':
            if isinstance(color, int):
                rgb = (color, color, color)
            else:
                rgb = tuple(color)[:3]
            fill = bytes(rgb) * (w * h)
        elif mode == 'RGBA':
            if isinstance(color, int):
                rgba = (color, color, color, 255)
            else:
                rgba = tuple(color)[:4]
                if len(rgba) == 3:
                    rgba = (*rgba, 255)
            fill = bytes(rgba) * (w * h)
        else:
            raise ValueError(f'unsupported mode {mode!r}')
        return Image(mode, size, fill)

    @classmethod
    def open(cls, source: Union[str, bytes, bytearray]) -> 'Image':
        if isinstance(source, (bytes, bytearray)):
            return open_bytes(bytes(source))
        with open(source, 'rb') as handle:
            return open_bytes(handle.read())

    def convert(self, mode: str) -> 'Image':
        if mode == self.mode:
            return Image(self.mode, self.size, self._data)
        if mode not in self.modes:
            raise ValueError(f'unsupported mode {mode!r}')
        if mode == 'RGBA':
            if self.mode == 'L':
                out = bytearray()
                for g in self._data:
                    out.extend((g, g, g, 255))
                return Image('RGBA', self.size, bytes(out))
            if self.mode == 'RGB':
                out = bytearray()
                for i in range(0, len(self._data), 3):
                    out.extend(self._data[i:i + 3])
                    out.append(255)
                return Image('RGBA', self.size, bytes(out))
        if mode == 'RGB':
            if self.mode == 'RGB':
                return Image('RGB', self.size, self._data)
            if self.mode == 'L':
                return self.convert('RGBA').convert('RGB')
            out = bytearray()
            for i in range(0, len(self._data), 4):
                out.extend(self._data[i:i + 3])
            return Image('RGB', self.size, bytes(out))
        if mode == 'L':
            if self.mode == 'L':
                return Image('L', self.size, self._data)
            rgba = self.convert('RGBA') if self.mode == 'RGB' else self
            out = bytearray()
            for i in range(0, len(rgba._data), 4):
                r, g, b = rgba._data[i], rgba._data[i + 1], rgba._data[i + 2]
                out.append(int(0.299 * r + 0.587 * g + 0.114 * b))
            return Image('L', self.size, bytes(out))
        raise ValueError(f'cannot convert {self.mode!r} to {mode!r}')

    def crop(self, box: Tuple[int, int, int, int]) -> 'Image':
        left, upper, right, lower = box
        w, h = self.size
        if not (0 <= left < right <= w and 0 <= upper < lower <= h):
            raise ValueError('bad crop box')
        bpp = {'L': 1, 'RGB': 3, 'RGBA': 4}[self.mode]
        cw = right - left
        out = bytearray(cw * (lower - upper) * bpp)
        for y in range(upper, lower):
            src_off = (y * w + left) * bpp
            dst_off = (y - upper) * cw * bpp
            out[dst_off:dst_off + cw * bpp] = self._data[src_off:src_off + cw * bpp]
        return Image(self.mode, (cw, lower - upper), bytes(out))

    def getpixel(self, xy: Tuple[int, int]):
        x, y = xy
        w, h = self.size
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError('pixel coordinates out of range')
        bpp = {'L': 1, 'RGB': 3, 'RGBA': 4}[self.mode]
        off = (y * w + x) * bpp
        if self.mode == 'L':
            return self._data[off]
        return tuple(self._data[off:off + bpp])

    def tobytes(self) -> bytes:
        return self._data

    def split(self) -> Tuple['Image', ...]:
        w, h = self.size
        if self.mode == 'L':
            return (Image('L', self.size, self._data),)
        bands = []
        for ch in range({'RGB': 3, 'RGBA': 4}[self.mode]):
            band = bytearray(w * h)
            bpp = len(band) // (w * h) or 1
            step = {'RGB': 3, 'RGBA': 4}[self.mode]
            for i in range(w * h):
                band[i] = self._data[i * step + ch]
            bands.append(Image('L', self.size, bytes(band)))
        return tuple(bands)

    def getbbox(self) -> Optional[Tuple[int, int, int, int]]:
        w, h = self.size
        if self.mode == 'L':
            nonzero = [i for i, v in enumerate(self._data) if v]
        else:
            step = 3 if self.mode == 'RGB' else 4
            nonzero = [i for i in range(w * h) if any(self._data[i * step + c] for c in range(step))]
        if not nonzero:
            return None
        ys = [i // w for i in nonzero]
        xs = [i % w for i in nonzero]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def getextrema(self):
        if self.mode == 'L':
            return (min(self._data), max(self._data))
        step = 3 if self.mode == 'RGB' else 4
        pixels = self.size[0] * self.size[1]
        out = []
        for ch in range(step):
            vals = [self._data[i * step + ch] for i in range(pixels)]
            out.append((min(vals), max(vals)))
        return tuple(out)

    def histogram(self) -> List[int]:
        if self.mode != 'L':
            raise ValueError('histogram requires mode L')
        hist = [0] * 256
        for v in self._data:
            hist[v] += 1
        return hist

    def point(self, func: Callable[[int], int]) -> 'Image':
        if self.mode != 'L':
            raise ValueError('point requires mode L')
        return Image('L', self.size, bytes(max(0, min(255, int(func(v)))) & 255 for v in self._data))

    def save(self, fp, format=None):
        if format not in (None, 'PNG'):
            raise ValueError('only PNG output is supported')
        if self.mode == 'L':
            data = encode_png(self.convert('RGBA'))
        elif self.mode == 'RGB':
            data = encode_png(self)
        else:
            data = encode_png(self)
        if hasattr(fp, 'write'):
            fp.write(data)
        else:
            with open(fp, 'wb') as handle:
                handle.write(data)

    def to_base64(self, data_uri: bool = False) -> str:
        if self.mode == 'L':
            img = self.convert('RGBA')
        else:
            img = self
        text = base64.b64encode(encode_png(img)).decode('ascii')
        return ('data:image/png;base64,' + text) if data_uri else text


class ImageChops:
    @staticmethod
    def difference(im1: Image, im2: Image) -> Image:
        if im1.size != im2.size:
            raise ValueError('images must be the same size')
        a = im1.convert('RGBA')
        b = im2.convert('RGBA')
        out = bytearray(len(a._data))
        for i in range(0, len(out), 4):
            for c in range(4):
                out[i + c] = abs(a._data[i + c] - b._data[i + c])
        return Image('RGBA', im1.size, bytes(out))

    @staticmethod
    def lighter(im1: Image, im2: Image) -> Image:
        if im1.size != im2.size:
            raise ValueError('images must be the same size')
        if im1.mode != 'L' or im2.mode != 'L':
            raise ValueError('lighter requires mode L images')
        return Image('L', im1.size, bytes(max(a, b) for a, b in zip(im1._data, im2._data)))


def diff_metrics(
    im1: Image,
    im2: Image,
    threshold: int = 1,
) -> dict:
    """One-pass diff summary matching browser-test-kit image_diff needs."""
    if im1.size != im2.size:
        raise ValueError('images must be the same size')
    a = im1.convert('RGBA')
    b = im2.convert('RGBA')
    w, h = im1.size
    changed = 0
    max_diff = 0
    min_x = min_y = w
    max_x = max_y = -1
    for y in range(h):
        for x in range(w):
            off = (y * w + x) * 4
            diffs = [abs(a._data[off + c] - b._data[off + c]) for c in range(3)]
            m = max(diffs)
            max_diff = max(max_diff, m)
            if m >= threshold:
                changed += 1
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    bbox = None if changed == 0 else (min_x, min_y, max_x + 1, max_y + 1)
    return {'changed_pixels': changed, 'bbox': bbox, 'max_diff': max_diff}


def _self_test() -> None:
    img = Image.new('RGB', (2, 2), (10, 20, 30))
    roundtrip = open_bytes(encode_png(img))
    assert roundtrip.size == (2, 2)
    assert roundtrip.getpixel((0, 0)) == (10, 20, 30, 255)


if __name__ == '__main__':
    _self_test()
