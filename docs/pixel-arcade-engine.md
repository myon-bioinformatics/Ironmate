# Prototype: sparse scanning and four-probe downscaling

Connects `pixel_arcade_engine.py` (standard library, Python 3.11+) to the existing
`ironmate-pixel-grid/1` and `grid_tools`. The default nearest-neighbor conversion is unchanged.

## Reversible operations and frames

```python
import grid_tools as g

original = g.make('circle', 'C02', 'outline', 16)
scanner = g.sparse(original, quota_per_frame=4)
frames = scanner.iter_shift_frames(1, 0)
first_frame = next(frames)  # updates at most 4 dots; no sleep or real-time wait
scanner.quota_per_frame = 8  # change the workload from the next frame
for frame in frames:
    current_artifact = scanner.grid.to_artifact()
scanner.grid.rollback_all()
assert scanner.grid.to_artifact() == original
```

Batch execution is `scanner.shift_formation_step_by_step(1, 0)`.
The returned `frames_for_one_step` is the batch count, and `relative_speed_vs_55` is a prototype
comparison ratio, not a measured run time. An empty grid gives 0 frames.
To stop midway, call `frames.close()` and then `rollback_all()`.
Do not mix other pixel operations or rollback while an iterator is still in progress.

- `iter_active_coords()` returns `(flat_index, x, y)`. With LSB extraction and
  `mask &= mask - 1`, the number of yields equals the number of active dots.
- The scanner moves only one adjacent cell up, down, left or right. Swaps in reverse order of the direction of travel
  move adjacent multicolor dots one cell at a time too. Diagonal and multi-cell moves are rejected.
- Edge contact is `check_sentinel_collision()`; contact with a given region is
  `check_sentinel_collision(precomputed_mask)`. Checks do not scan pixels or coordinates.
- If the destination would be out of range, it is rejected up front by ANDing with the edge mask for the direction of travel.
  Merely touching another outer edge still allows the move. There is no silent truncation after a partial move.
- Swaps record the diff as color-value XOR and occupancy-mask XOR, and are restored by applying them in reverse.
  Swaps with equal color values are not recorded. `rollback_all()` returns the history count.
- The adapter copies input and output and keeps color indices, unused colors, duplicate colors and metadata.
  `pixels` is a read-only tuple snapshot, so external array changes cannot corrupt history.

Python integers are arbitrary-precision, so AND, LSB handling and bit_count also depend on the integer's word count.
So this is not called "strict O(1) boundary checks", "zero wait" or "the whole scan strictly O(N_active)".
Building the initial mask reads every cell, and each frame start allocates a list of active indices.
History grows in proportion to the number of swaps that actually changed something.

## 2x downscaling with four probes

```bash
python -S -m grid_tools make circle --size 32 --resize 16 --resize-method probes --to png -o small.png
python -S -m grid_tools load small.png --to base64 --data-uri
```

```python
small = g.downscale_2x(original)
assert small == g.resize(original, 8, method='probes')
assert g.restore(g.encode(small), backend='stdlib') == small
```

Only even width and even height (each at least 2) are supported. An odd right or bottom edge is never silently dropped.
`resize(..., method='probes')` is limited to exactly half size on both axes.
This path always computes with the standard library and does not depend on the existing `backend` choice.
The output `resampling` is `pacman_probes_2x_lossy`.

| Probe | Coordinate rule |
| --- | --- |
| Akabei (`akabei`) | References `akabei_ref` directly |
| Pinky (`pinky`) | `(x + (dx << 2), y + (dy << 2))` |
| Aosuke (`aosuke`) | With the cell 2 ahead as the pivot, `(pivot << 1) - akabei_ref` |
| Guzuta (`guzuta`) | Chases if the Manhattan distance to the previously kept feature point is 8 or more; retreats to the corner if under 8 |

Compared with the input prototype, the following points were corrected for safe grid processing.

- Color indices are unordered labels, so direction is estimated from occupancy, not index magnitude.
  The representative color is a vote over local non-background colors, plus matching votes from Akabei/Pinky/Aosuke.
  On a tie, the color appearing first in local row order wins. Renumbering the palette gives the same visible result.
- Even when a local block has only one dot, it is not erased just because the top-left cell is empty.
- Every color index with alpha=0 is background; alpha=1–255 is active. Color index 0 is active too if opaque.
  For palettes without a transparent color, one is appended at the end only if downscaling produced a transparent cell.
- The corner is a virtual background anchor; it neither erases the original image's corner nor assumes that color is background.
  The actual distance is also checked, so retreating is not confused with a previous feature point that sat at the corner coordinate.

Guzuta thinning happens when the local 2×2 has 3+ dots, the feature point is under 8 away, Pinky/Aosuke see background,
and the output coordinate has odd parity. This is an experimental heuristic that depends on raster scan order and
does not guarantee line connectivity, symmetry or legibility for arbitrary art. Tests cover a dense 4×2 input thinning nearest-neighbor's
`[1, 1]` to `[1, 0]`, and an example that keeps an isolated dot.

## What can be restored

Swap → rollback fully restores the original pixels, occupancy mask and artifact.
A downscaled artifact → PNG/Base64 → artifact round-trips under the existing spec.
PNG metadata keeps only the fields allowed by the existing `grid_png.header_info()`;
arbitrary extra metadata is kept in JSON or the grid adapter.
Color indices with duplicate RGBA map to the first index, as before.
SVG draws color index 0 too when its alpha is nonzero, and visible RGBA is compared
(RGB of transparent colors, palette order and full metadata restoration are not guaranteed by SVG).

**Downscaling itself is irreversible.** Original detail cannot be restored from the output alone.
The existing nearest-neighbor upscaling still works, but it does not reconstruct lost detail.
This prototype adds neither four-probe upscaling interpolation nor a mechanism that hides and keeps the pre-downscale image.

```bash
python -m pytest -q tests/test_pixel_arcade_engine.py tests/test_grid_tools.py -m 'not heavy'
```
