"""Explainable image comparison: alignment, mask overlap and channel errors.

Input pixels are flat RGBA tuples; no external images or dependencies required.
"""
from __future__ import annotations
from studio_shape_metrics import metrics


def _validate_pixels(width, height, pixels):
    if len(pixels) != width * height:
        raise ValueError("pixel count does not match dimensions")
    if any(len(p) != 4 or any(type(c) is not int or not 0 <= c <= 255 for c in p) for p in pixels):
        raise ValueError("RGBA must contain integer channels in [0,255]")


def compare_rgba(width, height, reference, candidate, *, radius=2, threshold=0):
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("invalid dimensions")
    if width * height > 4_194_304 or type(radius) is not int or not 0 <= radius <= 16:
        raise ValueError("invalid grid or radius")
    _validate_pixels(width, height, reference)
    _validate_pixels(width, height, candidate)
    if type(threshold) is not int or not 0 <= threshold <= 255:
        raise ValueError("invalid alpha threshold")

    a = {i for i, p in enumerate(reference) if p[3] > threshold}
    b = {i for i, p in enumerate(candidate) if p[3] > threshold}
    base = metrics(width, height, a, b)
    # Registration is scored separately, not used to conceal location error.
    best = (-1.0, 0, 0)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            moved = set()
            for i in b:
                x, y = i % width + dx, i // width + dy
                if 0 <= x < width and 0 <= y < height:
                    moved.add(y * width + x)
            aligned = metrics(width, height, a, moved)["IoU"]
            # Prefer smaller displacement for equal IoU.
            key = (aligned, -(abs(dx) + abs(dy)), -abs(dy), -abs(dx))
            if key > (best[0], -(abs(best[1]) + abs(best[2])), -abs(best[2]), -abs(best[1])):
                best = (aligned, dx, dy)
    # Pixel similarity on the same coordinates; alpha included. This is not perceptual color difference.
    channel_error = sum(abs(x - y) for p, q in zip(reference, candidate) for x, y in zip(p, q))
    similarity = 1 - channel_error / (len(reference) * 4 * 255)
    return {
        **base,
        "RGBA_L1_Similarity": similarity,
        "Aligned_IoU": best[0],
        "Alignment_dx": best[1],
        "Alignment_dy": best[2],
        "Alignment_L1_Pixels": abs(best[1]) + abs(best[2]),
    }


def foreground_mask(pixels):
    # Composite onto white before measuring RGB distance. Fixed threshold, never fitted.
    return {i for i,p in enumerate(pixels)
            if max((255-c)*p[3]/255 for c in p[:3]) > 32}


def reference_energy(pixels, width, height):
    # Nonnegative integer local RGB edge energy, frozen from reference for all variants.
    def rgb(p):
        return tuple((c*p[3]+255*(255-p[3]))//255 for c in p[:3])
    values = [rgb(p) for p in pixels]
    return [sum(abs(a-b) for j in (i+1 if i%width+1<width else i,
                                 i+width if i//width+1<height else i)
                for a,b in zip(values[i],values[j])) for i in range(width*height)]
