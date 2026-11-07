"""Reversible translation on a bounded RGBA canvas.

Translation is lossless only for retained pixels; clipped pixels are reported.
"""
from __future__ import annotations


def translate_rgba(width, height, pixels, dx, dy, fill=(0, 0, 0, 0)):
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("invalid dimensions")
    if width * height > 4_194_304 or len(pixels) != width * height:
        raise ValueError("invalid pixel grid")
    if any(type(v) is not int for v in (dx, dy)):
        raise ValueError("integer translation required")
    if len(fill) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in fill):
        raise ValueError("invalid fill")
    if any(len(p) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in p) for p in pixels):
        raise ValueError("invalid RGBA pixel")
    out = [tuple(fill)] * (width * height)
    clipped = 0
    for y in range(height):
        for x in range(width):
            i = y * width + x
            xx, yy = x + dx, y + dy
            if 0 <= xx < width and 0 <= yy < height:
                out[yy * width + xx] = tuple(pixels[i])
            elif pixels[i] != tuple(fill):
                clipped += 1
    return {"pixels": out, "dx": dx, "dy": dy, "clipped_nonfill": clipped}


def invert_translation(width, height, translated, dx, dy, fill=(0, 0, 0, 0)):
    return translate_rgba(width, height, translated, -dx, -dy, fill)
