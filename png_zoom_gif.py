"""PNG to a zoom-in / reverse zoom-out GIF (optional Pillow codec)."""
from __future__ import annotations

import argparse, io, math
from pathlib import Path

from pillow_min import decode_png_rgba


ANCHORS = {
    'bottom-left': (0.0, 1.0), 'bottom-right': (1.0, 1.0),
    'top-left': (0.0, 0.0), 'top-right': (1.0, 0.0), 'center': (0.5, 0.5),
    'left': (0.0, 0.5), 'right': (1.0, 0.5),
    'top': (0.5, 0.0), 'bottom': (0.5, 1.0),
}
ARROW_ANCHORS = {
    '↙': 'bottom-left', '↘': 'bottom-right', '↖': 'top-left', '↗': 'top-right',
    '←': 'left', '⬅': 'left', '→': 'right', '➡': 'right',
    '↑': 'top', '⬆': 'top', '↓': 'bottom', '⬇': 'bottom',
    '🎯': 'center',
}


def _focus_name(value):
    # Unicode text/emoji presentation selectors do not change the direction.
    if value.endswith(('\ufe0e', '\ufe0f')):
        value = value[:-1]
    name = ARROW_ANCHORS.get(value, value)
    if name not in ANCHORS:
        raise ValueError('unknown anchor: ' + value)
    return name


def _anchor(value):
    if isinstance(value, str):
        return ANCHORS[_focus_name(value)]
    if not isinstance(value, (tuple, list)) or len(value) != 2 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or
        not math.isfinite(v) or not 0 <= v <= 1 for v in value
    ):
        raise ValueError('anchor must be a name or two coordinates from 0 to 1')
    return tuple(value)


def zoom_frames(png, *, zoom=3.0, steps=16, anchor='bottom-left', anchors=None,
                background=(255, 255, 255)):
    """Return RGB frames: full image, zoom toward anchor, then exact reverse.

    Named anchors or an ordered anchors sequence are accepted. Each focus returns
    to the full view before the next focus. Anchor coordinates range from 0 to 1; (0, 1) means bottom-left.
    GIF cannot retain partial alpha: composite onto background before encoding.
    PNG/APNG input uses its default image. Pillow is imported only on use.
    """
    if isinstance(zoom, bool) or not isinstance(zoom, (int, float)) or not math.isfinite(zoom) or not 1 < zoom <= 64:
        raise ValueError('zoom must be finite and greater than 1, at most 64')
    if type(steps) is not int or not 2 <= steps <= 120:
        raise ValueError('steps must be an integer from 2 to 120')
    if anchors is None:
        route = [_anchor(anchor)]
    else:
        if not isinstance(anchors, (list, tuple)) or not 1 <= len(anchors) <= 16:
            raise ValueError('anchors must contain 1 to 16 focus points')
        route = [_anchor(value) for value in anchors]
    if len(background) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in background):
        raise ValueError('background must contain three bytes')
    width, height, rows = decode_png_rgba(png, max_pixels=4_000_000)
    if width * height * (steps * len(route) + 1) > 32_000_000:
        raise ValueError('animation exceeds 32000000 retained frame pixels; reduce input size or steps')
    from PIL import Image
    source = Image.frombytes('RGBA', (width, height), b''.join(rows))
    canvas = Image.new('RGBA', source.size, tuple(background) + (255,))
    source = Image.alpha_composite(canvas, source).convert('RGB')
    frames = [source]
    for anchor in route:
        forward = [source]
        for i in range(1, steps + 1):
            t = i / steps
            factor = 1 + (zoom - 1) * (t * t * (3 - 2 * t))
            crop_w, crop_h = max(1, round(width / factor)), max(1, round(height / factor))
            left = round((width - crop_w) * anchor[0])
            top = round((height - crop_h) * anchor[1])
            forward.append(source.crop((left, top, left + crop_w, top + crop_h)).resize(source.size, Image.Resampling.LANCZOS))
        frames.extend(forward[1:] + forward[-2::-1])
    return frames



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
    steps = options.get('steps', 16)
    # Every zoom peak and every return to the full view gets one pause.
    for index in range(0, len(encoded), steps):
        durations[index] += hold_ms
    # Pillow coalesces consecutive identical frames, including their durations.
    # Validate the resulting delay too, rather than leaking an OverflowError.
    previous = None
    combined = 0
    for frame, duration in zip(encoded, durations):
        pixels = frame.tobytes()
        combined = combined + duration if pixels == previous else duration
        if combined > 655350:
            raise ValueError('merged identical frame duration exceeds GIF limit; reduce timing')
        previous = pixels
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
    focus = parser.add_mutually_exclusive_group()
    focus.add_argument('--anchor', nargs=2, type=float, metavar=('X', 'Y'))
    focus.add_argument('--focus', type=_focus_name, choices=tuple(ANCHORS), default='bottom-left',
                       help='focus name or arrow, e.g. ↙️, ↗️, ⬅️, 🎯')
    focus.add_argument('--sequence', nargs='+', type=_focus_name, choices=tuple(ANCHORS),
                       help='ordered names/arrows; return to full view between each')
    parser.add_argument('--duration-ms', type=int, default=60)
    parser.add_argument('--hold-ms', type=int, default=400)
    args = parser.parse_args(argv)
    try:
        data = to_gif(args.input.read_bytes(), zoom=args.zoom, steps=args.steps,
                      anchor=args.anchor if args.anchor is not None else args.focus,
                      anchors=args.sequence, duration_ms=args.duration_ms, hold_ms=args.hold_ms)
        with args.output.open('xb') as stream:
            stream.write(data)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
