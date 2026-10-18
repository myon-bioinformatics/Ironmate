"""Experimental binary-mask shape metrics. No learned parameters or image codec.

These are comparisons, not replacements for IoU. All masks share a finite grid.
"""
from __future__ import annotations


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
