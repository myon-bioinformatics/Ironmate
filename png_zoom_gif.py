"""PNG to a zoom-in / reverse zoom-out GIF (optional Pillow codec)."""
from __future__ import annotations

import argparse
import io
import math
from pathlib import Path

from pillow_min import decode_png_rgba


def zoom_frames(png, *, zoom=3.0, steps=16, anchor=(0.0, 1.0), background=(255, 255, 255)):
    """Return RGB frames: full image, zoom toward anchor, then exact reverse.

    Anchor coordinates range from 0 to 1; (0, 1) means bottom-left.
    GIF cannot retain partial alpha: composite onto background before encoding.
    PNG/APNG input uses its default image. Pillow is imported only on use.
    """
    if isinstance(zoom, bool) or not isinstance(zoom, (int, float)) or not math.isfinite(zoom) or not 1 < zoom <= 64:
        raise ValueError('zoom must be finite and greater than 1, at most 64')
    if type(steps) is not int or not 2 <= steps <= 120:
        raise ValueError('steps must be an integer from 2 to 120')
    if len(anchor) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in anchor):
        raise ValueError('anchor must contain two coordinates from 0 to 1')
    if len(background) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in background):
        raise ValueError('background must contain three bytes')
    width, height, rows = decode_png_rgba(png, max_pixels=4_000_000)
    if width * height * (steps + 1) > 32_000_000:
        raise ValueError('animation exceeds 32000000 retained frame pixels; reduce input size or steps')
    from PIL import Image
    source = Image.frombytes('RGBA', (width, height), b''.join(rows))
    canvas = Image.new('RGBA', source.size, tuple(background) + (255,))
    source = Image.alpha_composite(canvas, source).convert('RGB')
    frames = [source]
    for i in range(1, steps + 1):
        t = i / steps
        factor = 1 + (zoom - 1) * (t * t * (3 - 2 * t))
        crop_w, crop_h = max(1, round(width / factor)), max(1, round(height / factor))
        left = round((width - crop_w) * anchor[0])
        top = round((height - crop_h) * anchor[1])
        frames.append(source.crop((left, top, left + crop_w, top + crop_h)).resize(source.size, Image.Resampling.LANCZOS))
    return frames + frames[-2::-1]


def to_gif(png, *, duration_ms=60, hold_ms=400, loop=0, **options):
    """Encode one GIF. Durations use GIF's 10 ms units; loop=0 repeats forever.

    All frames share one palette; GIF output is limited to 256 colors.
    First, peak and final frames receive an additional hold_ms pause.
    """
    for name, value, low, high in (('duration_ms', duration_ms, 10, 655350), ('hold_ms', hold_ms, 0, 655350)):
        if type(value) is not int or not low <= value <= high or value % 10:
            raise ValueError(f'{name} must be a multiple of 10 from {low} to {high}')
    if duration_ms + hold_ms > 655350:
        raise ValueError('combined frame duration exceeds GIF limit')
    if type(loop) is not int or not 0 <= loop <= 65535:
        raise ValueError('loop must be an integer from 0 to 65535')
    frames = zoom_frames(png, **options)
    from PIL import Image
    palette = frames[0].quantize(colors=256)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [duration_ms] * len(encoded)
    for index in (0, len(encoded) // 2, len(encoded) - 1):
        durations[index] += hold_ms
    result = io.BytesIO()
    encoded[0].save(result, format='GIF', save_all=True, append_images=encoded[1:],
                    duration=durations, loop=loop, optimize=False, disposal=2)
    return result.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--zoom', type=float, default=3)
    parser.add_argument('--steps', type=int, default=16)
    parser.add_argument('--anchor', nargs=2, type=float, default=(0, 1), metavar=('X', 'Y'))
    parser.add_argument('--duration-ms', type=int, default=60)
    parser.add_argument('--hold-ms', type=int, default=400)
    args = parser.parse_args(argv)
    try:
        data = to_gif(args.input.read_bytes(), zoom=args.zoom, steps=args.steps,
                      anchor=args.anchor, duration_ms=args.duration_ms, hold_ms=args.hold_ms)
        with args.output.open('xb') as stream:
            stream.write(data)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
