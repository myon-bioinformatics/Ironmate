# PNG zoom and return GIF

Create one animation from a PNG: show the full image, smoothly zoom toward the
bottom-left, then retrace the same frames back to the original view.

```sh
uv sync --locked --only-group codecs
uv run --no-sync python png_zoom_gif.py input.png zoom.gif --zoom 3 --steps 16
```

`--anchor X Y` selects the focus: `0 1` bottom-left (default), `0.5 0.5` center,
`1 0` top-right. `--duration-ms 60` controls each frame and `--hold-ms 400` adds
pauses at the start, zoom peak and end. Times must be multiples of 10 ms.
The output repeats forever and existing output files are refused.
Consecutive identical frames may be merged by the GIF encoder. Their combined
delay must also fit the GIF limit of 655350 ms; excessive timing is rejected.

Named focuses: `bottom-left`, `bottom-right`, `top-left`, `top-right`, `center`.
Use `--focus top-right` for one focus, or choose any order:

```sh
python png_zoom_gif.py input.png zoom.gif --sequence bottom-left bottom-right top-left top-right
```

Each focus zooms in and reverses back to the full view before the next focus.

Arrow characters and emoji work in both the CLI and Python API. Text/emoji
presentation variants (for example `↙`, `↙︎`, `↙️`) mean the same focus.

| Input | Focus |
|---|---|
| ↙️ | bottom-left |
| ↘️ | bottom-right |
| ↖️ | top-left |
| ↗️ | top-right |
| ← / ⬅️ | left (middle of edge) |
| → / ➡️ | right (middle of edge) |
| ↑ / ⬆️ | top (middle of edge) |
| ↓ / ⬇️ | bottom (middle of edge) |
| 🎯 | center |

```sh
python png_zoom_gif.py input.png zoom.gif --sequence '↙️' '↘️' '↖️' '↗️'
python png_zoom_gif.py input.png zoom.gif --focus '↗️'
```

Python: `to_gif(png_bytes, anchors=['↙️', '↘️', '↖️', '↗️'])`.
Names, arrows and coordinate pairs can be mixed in the API sequence.

`--focus`, `--sequence` and `--anchor` are mutually exclusive. The default remains
bottom-left first. A sequence can repeat focuses and contains 1–16 entries.
The Python API accepts `anchor='top-left'` or
`anchors=['bottom-left', 'top-right', (0.25, 0.75)]`, allowing mixed named and
custom coordinates. Timing and zoom settings apply to all focuses; every peak
and return to full view receives one pause. Frame memory bounds cover the whole
sequence, so long sequences may require smaller input or fewer steps.

Python API: `png_zoom_gif.to_gif(png_bytes, zoom=3, steps=16,
anchor=(0, 1), background=(255, 255, 255), duration_ms=60, hold_ms=400)`.
`zoom_frames` exposes the RGB frames for later video export.

Uses the existing optional Pillow codec group; no dependency or lock changes.
PNG is decoded through pillow_min, including indexed PNG. APNG uses its default
image only. GIF has at most 256 colors: a shared source-derived palette prevents
frame-by-frame palette changes, but photographic color fidelity is reduced.
Partial transparency is composited onto the background (white by default).
Returning to the original means the original view, not lossless PNG color storage.
Input is limited to 4 million pixels and retained forward frames to 32 million
pixels. Resize large input images first. This feature does not encode video files.

Validation: `python -m unittest discover -s tests -p test_png_zoom_gif.py -v`.
