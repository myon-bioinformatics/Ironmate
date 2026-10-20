"""Sparse, reversible pixel experiments and opt-in lossy 2x probe downsampling.

Stdlib only, Python 3.11+. Palette indices are categorical, not brightness values.
Integer bit operations scale with the mask's machine-word length, not O(1).
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import re


def _integer(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{name} must be an integer in range {minimum}..{maximum}')
    return value


def _bitmask(indices, size):
    # Build once in bytes: summing progressively wider Python integers would
    # repeatedly copy the entire prefix for every occupied cell of a dense grid.
    bits = bytearray((size + 7) >> 3)
    for idx in indices:
        bits[idx >> 3] |= 1 << (idx & 7)
    return int.from_bytes(bits, 'little')


class ReversiblePixelGrid:
    """Owned flat pixels; read-only snapshots keep occupancy and XOR history coherent.

    All background indices are inactive. ``background`` supplies out-of-grid samples
    and empty output cells. Direct construction uses the prototype's 0 background.
    """

    def __init__(self, width, height, pixels=None, *, background=0, background_indices=None):
        self.width = _integer(width, 'width', 1, 4096)
        self.height = _integer(height, 'height', 1, 4096)
        self.size = width * height
        self.background = _integer(background, 'background')
        self.background_indices = frozenset((background,) if background_indices is None else background_indices)
        if background not in self.background_indices:
            raise ValueError('background must be one of background_indices')
        for value in self.background_indices:
            _integer(value, 'background index')
        if pixels is not None and len(pixels) != self.size:
            raise ValueError('pixels do not match width/height')
        self._pixels = [background] * self.size if pixels is None else list(pixels)
        for value in self._pixels:
            _integer(value, 'pixel index')
        self.active_mask = 0
        self.rebuild_active_mask()
        row = (1 << width) - 1
        left = _bitmask(range(0, self.size, width), self.size)
        self._edges = {(-1, 0): left, (1, 0): left << (width - 1),
                       (0, -1): row, (0, 1): row << ((height - 1) * width)}
        self.sentinel_mask = self._edges[-1, 0] | self._edges[1, 0] | self._edges[0, -1] | self._edges[0, 1]
        self._reversible_log = []
        self._artifact = None

    @property
    def pixels(self):
        return tuple(self._pixels)

    def is_active(self, value):
        return value not in self.background_indices

    def rebuild_active_mask(self):
        self.active_mask = _bitmask((i for i, value in enumerate(self._pixels) if self.is_active(value)), self.size)

    @property
    def active_count(self):
        return self.active_mask.bit_count()

    def check_sentinel_collision(self, sentinel_mask=None):
        """Test contact with the border or a precomputed region mask; no pixel loop."""
        mask = self.sentinel_mask if sentinel_mask is None else sentinel_mask
        _integer(mask, 'sentinel_mask')
        return bool(self.active_mask & mask)

    def get(self, x, y, default=None):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return self.background if default is None else default

    def swap_pixels_reversible(self, idx_a, idx_b):
        """Swap two cells, logging only their XOR and occupancy XOR delta."""
        _integer(idx_a, 'idx_a', 0, self.size - 1)
        _integer(idx_b, 'idx_b', 0, self.size - 1)
        a, b = self._pixels[idx_a], self._pixels[idx_b]
        diff = a ^ b
        if not diff:
            return
        mask_diff = ((1 << idx_a) | (1 << idx_b)) if self.is_active(a) != self.is_active(b) else 0
        self._reversible_log.append((idx_a, idx_b, diff, mask_diff))
        self._pixels[idx_a] ^= diff
        self._pixels[idx_b] ^= diff
        self.active_mask ^= mask_diff

    def rollback_all(self):
        """Restore every logged swap in reverse order, including exact occupancy."""
        steps = len(self._reversible_log)
        while self._reversible_log:
            a, b, diff, mask_diff = self._reversible_log.pop()
            self._pixels[a] ^= diff
            self._pixels[b] ^= diff
            self.active_mask ^= mask_diff
        return steps

    @classmethod
    def from_artifact(cls, artifact):
        """Copy an ironmate-pixel-grid/1 without reordering or merging its palette."""
        if not isinstance(artifact, dict) or artifact.get('schema') != 'ironmate-pixel-grid/1':
            raise ValueError('expected an ironmate-pixel-grid/1 artifact')
        w = _integer(artifact.get('width'), 'width', 1, 4096)
        h = _integer(artifact.get('height'), 'height', 1, 4096)
        colors, rows = artifact.get('colors'), artifact.get('pixels')
        if (not isinstance(colors, list) or not colors or
                any(not isinstance(c, str) or not re.fullmatch(r'#[0-9A-Fa-f]{8}', c) for c in colors)):
            raise ValueError('colors must be a non-empty list of #RRGGBBAA')
        if not isinstance(rows, list) or len(rows) != h or any(not isinstance(r, list) or len(r) != w for r in rows):
            raise ValueError('pixels do not match width/height')
        for row in rows:
            for value in row:
                _integer(value, 'palette index', 0, len(colors) - 1)
        backgrounds = [i for i, color in enumerate(colors) if color[-2:] == '00'] or [len(colors)]
        grid = cls(w, h, [v for row in rows for v in row], background=backgrounds[0],
                   background_indices=backgrounds)
        grid._artifact = deepcopy(artifact)
        return grid

    def to_artifact(self):
        """Export an owned artifact; append transparency only if newly used by a filter."""
        if self._artifact is None:
            raise ValueError('to_artifact needs a grid created from_artifact')
        out = deepcopy(self._artifact)
        if self.background == len(out['colors']) and self.background in self._pixels:
            out['colors'].append('#00000000')
        out.update(width=self.width, height=self.height,
                   pixels=[self._pixels[i:i + self.width] for i in range(0, self.size, self.width)])
        return out


class InvaderSparseScanner:
    """Enumerate set bits only; advance an adjacent formation in bounded frames.

    Frames are work batches, not wall-clock delays. Change quota_per_frame between
    yields to change speed. Do not mutate the grid during a pending formation step.
    """

    def __init__(self, grid, quota_per_frame=1):
        self.grid = grid
        self.quota_per_frame = quota_per_frame
        _integer(quota_per_frame, 'quota_per_frame', 1)

    def iter_active_coords(self):
        mask, width = self.grid.active_mask, self.grid.width
        while mask:
            lsb = mask & -mask
            idx = lsb.bit_length() - 1
            y, x = divmod(idx, width)
            yield idx, x, y
            mask &= mask - 1

    def iter_shift_frames(self, dx, dy):
        """Preflight an entire cardinal one-cell move; refuse overflow before any write."""
        if type(dx) is not int or type(dy) is not int or abs(dx) + abs(dy) != 1:
            raise ValueError('shift must be one cardinal adjacent cell')
        if self.grid.check_sentinel_collision(self.grid._edges[dx, dy]):
            raise ValueError('formation would move outside the grid')
        indices = [idx for idx, _, _ in self.iter_active_coords()]
        delta = dy * self.grid.width + dx
        if delta > 0:
            indices.reverse()
        processed, frame = 0, 0
        while processed < len(indices):
            quota = _integer(self.quota_per_frame, 'quota_per_frame', 1)
            batch = indices[processed:processed + quota]
            for idx in batch:
                self.grid.swap_pixels_reversible(idx, idx + delta)
            processed += len(batch)
            frame += 1
            yield {'processed': processed, 'frame': frame, 'active_dots': len(indices),
                   'sentinel_touched': self.grid.check_sentinel_collision()}

    def shift_formation_step_by_step(self, dx, dy):
        dots, frames = self.grid.active_count, 0
        for result in self.iter_shift_frames(dx, dy):
            frames = result['frame']
        return {'active_dots': dots, 'frames_for_one_step': frames,
                'relative_speed_vs_55': round(55.0 / max(1, frames), 2),
                'sentinel_touched': self.grid.check_sentinel_collision()}


@dataclass(frozen=True)
class ProbeTargets:
    red: tuple[int, int]
    pink: tuple[int, int]
    blue: tuple[int, int]
    orange: tuple[int, int]


class PacmanGhostProbes:
    """Prototype target formulas; occupancy-based direction and categorical color vote."""

    def __init__(self, corner_pos=(0, 0)):
        self.corner_pos = corner_pos

    def compute_targets(self, x, y, dx, dy, red_ref, nearest_feature):
        rx, ry = red_ref
        pivot_x, pivot_y = x + (dx << 1), y + (dy << 1)
        fx, fy = nearest_feature
        distance = abs(x - fx) + abs(y - fy)
        return ProbeTargets(red=red_ref, pink=(x + (dx << 2), y + (dy << 2)),
                            blue=((pivot_x << 1) - rx, (pivot_y << 1) - ry),
                            orange=nearest_feature if (distance >> 3) > 0 else self.corner_pos)

    @staticmethod
    def estimate_local_direction(grid, x, y):
        dx = int(grid.is_active(grid.get(x + 1, y))) - int(grid.is_active(grid.get(x - 1, y)))
        dy = int(grid.is_active(grid.get(x, y + 1))) - int(grid.is_active(grid.get(x, y - 1)))
        return (1, 0) if dx == dy == 0 else (dx, dy)

    def adaptive_downscale_2x(self, src):
        """Lossy experimental thinning, never a reversible image compression method.

        Require even dimensions, so the right/bottom edge is never silently cropped.
        The corner is a virtual background anchor, even if that source cell is painted.
        """
        if src.width < 2 or src.height < 2 or src.width & 1 or src.height & 1:
            raise ValueError('probe downscale requires even width/height >= 2')
        w, h = src.width >> 1, src.height >> 1
        pixels = [src.background] * (w * h)
        last_kept = (-16, -16)
        for y in range(h):
            for x in range(w):
                sx, sy = x << 1, y << 1
                local = [src.get(sx, sy), src.get(sx + 1, sy), src.get(sx, sy + 1), src.get(sx + 1, sy + 1)]
                active = [v for v in local if src.is_active(v)]
                if not active:
                    continue
                dx, dy = self.estimate_local_direction(src, sx, sy)
                targets = self.compute_targets(sx, sy, dx, dy, (sx - dx, sy - dy), last_kept)
                red, pink, blue = (src.get(*pos) for pos in (targets.red, targets.pink, targets.blue))
                # Keep the explicit distance test: a tracked feature can itself be at corner_pos.
                retreat = (abs(sx - last_kept[0]) + abs(sy - last_kept[1])) >> 3 == 0
                if (len(active) >= 3 and retreat and targets.orange == self.corner_pos and
                        not src.is_active(pink) and not src.is_active(blue) and (x + y) & 1):
                    continue
                votes = Counter(active)
                # Shared evaluation rule for the three sampled colors; ties follow local scan order.
                for value in (red, pink, blue):
                    if value in votes:
                        votes[value] += 1
                pixels[y * w + x] = max(votes, key=votes.get)
                last_kept = (sx, sy)
        dst = ReversiblePixelGrid(w, h, pixels, background=src.background,
                                  background_indices=src.background_indices)
        dst._artifact = deepcopy(src._artifact)
        if dst._artifact is not None:
            dst._artifact['resampling'] = 'pacman_probes_2x_lossy'
        return dst
