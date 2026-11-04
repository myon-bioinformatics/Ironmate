# Optional reduced-bit PNG output

`grid_png.to_png(artifact, indexed=True)` and `grid_png.py input.json --indexed` write
lossless indexed PNG with the smallest palette depth (1, 2, 4, or 8 bits per pixel).
`to_base64(..., indexed=True)` supports the same option. No new dependency is used.
The default remains the original RGBA bytes. Palette order and alpha are retained;
`meta=True` retains the same whitelisted metadata. This changes representation, not quantization.

```sh
python -S -m unittest discover -s tests -p test_grid_png_indexed.py -v
python -S scripts/benchmark_indexed_png.py
```

The existing `pillow_min.open_bytes` stdlib decoder can read the output, including
sub-byte indexes and transparency. The narrower `photo_grid.decode_png` direct
API only accepts 8-bit non-palette PNG; do not send indexed output to that API.
Existing RGBA consumers continue using the default. This option does not modify
other export entry points or install Pillow.

## Measurement on 2026-11-04

Linux x86_64, CPython 3.12.14. Nine procedural images: circle/cloud/rock at 16/64/256,
palette C02, shadow, scale 1; seven timing samples after warmup per mode.
Decoded RGBA bytes match exactly. Raw timings and SHA-256 values are in
`indexed-png-measurement.json`; the script recreates the inputs.

| Size | Circle RGBA / indexed bytes | Cloud | Rock |
|---|---:|---:|---:|
| 16 | 121 / 148 | 108 / 139 | 98 / 130 |
| 64 | 293 / 258 | 230 / 217 | 192 / 184 |
| 256 | 1048 / 772 | 816 / 576 | 738 / 432 |

The palette overhead increases tiny files. At 256, output decreases about 26–41%,
but generation-time results vary by image. The current raw samples supersede the
initial measurements taken before trailing opaque alpha entries were removed.
This is an opt-in storage/transfer tradeoff, not a general speed optimization.
No build-time or dependency-environment reduction is claimed.

Tests cover all four depths, odd row widths and padding, scale 1/3, transparency,
all procedural masks, malformed arguments, Base64, and CLI under `python -S`.
The default output was also compared directly with the previous git version
across all masks, scale 1/3 and metadata on/off: byte-identical.

Indexed PNG now also restores through `grid_tools.restore(..., backend="stdlib")` using
the bounded pillow_min decoder. Tests cover metadata roundtrips and rejection of a
corrupted palette CRC; the narrow photo_grid.decode_png API remains unchanged.

Without metadata, explicit `size` restoration preserves RGBA pixels; the original
palette order and generation parameters cannot be recovered. With metadata, the
full artifact roundtrip is tested. Indexed restoration also enforces the shared
MAX_PIXELS limit before decoding.
