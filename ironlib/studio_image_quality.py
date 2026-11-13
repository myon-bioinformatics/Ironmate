"""Explainable image comparison: alignment, mask overlap and channel errors.

Input pixels are flat RGBA tuples; no external images or dependencies required.
"""
from __future__ import annotations


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


# studio_alignment
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


# studio_shape_metrics
def _validate(width, height, a, b):
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("positive integer grid required")
    if width * height > 4_194_304:
        raise ValueError("grid too large")
    for group in (a, b):
        if any(type(i) is not int or not 0 <= i < width * height for i in group):
            raise ValueError("mask index outside grid")


def _neighbors(index, width, height):
    x, y = index % width, index // width
    if x: yield index - 1
    if x + 1 < width: yield index + 1
    if y: yield index - width
    if y + 1 < height: yield index + width


def _directed_soft(reference, candidate, width, height):
    if not candidate:
        return 1.0 if not reference else 0.0
    # Exact hit: 1; a non-overlapping 4-neighbor hit: 1/2.
    exact = len(reference & candidate)
    nearby = sum(any(j in reference for j in _neighbors(i, width, height))
                 for i in candidate - reference)
    return (exact + nearby / 2) / len(candidate)


def metrics(width, height, ground_truth, reconstructed, energy=None):
    a, b = set(ground_truth), set(reconstructed)
    _validate(width, height, a, b)
    union, inter = a | b, a & b
    iou = len(inter) / len(union) if union else 1.0
    dice = (len(inter) << 1) / (len(a) + len(b)) if a or b else 1.0
    # Symmetric mean of two directed tolerance recalls, exact match is 1.
    soft = (_directed_soft(a, b, width, height) +
            _directed_soft(b, a, width, height)) / 2
    weighted = None
    if energy is not None:
        if len(energy) != width * height or any(
            type(v) is not int or v < 0 for v in energy
        ):
            raise ValueError("energy must contain nonnegative integer weights")
        denom = sum(energy[i] for i in a) + sum(energy[i] for i in b)
        weighted = (sum(energy[i] for i in inter) << 1) / denom if denom else None
    return {"IoU": iou, "Dice": dice, "Energy_Dice": weighted,
            "Symmetric_Near_Field": soft}
