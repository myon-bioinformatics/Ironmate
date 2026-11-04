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
