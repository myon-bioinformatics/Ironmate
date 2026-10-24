# Image Studio: Pages, Base64, CLI and upscaling comparison

2026-10-17. Additional verification of PR #110's Image Studio. The earlier
[first experiment record](../image-studio/report.md) and [Three-Way Survey](../three-way-survey/report.md)
are not overwritten. This record verifies rendering and hand-off of synthetic stamps and known shapes;
it evaluates something different from structure-detection IoU or natural-image restoration accuracy.

## Implementation and hand-off

- Pages serves only 4 HTML/JS/CSS files with relative paths and an empty `.nojekyll`.
  Checked with a static HTTP server under `/Ironmate/`. Input images, scenes and CLI programs are not served.
- The same bytes as the PNG are output as standard padded Base64 / a PNG data URI.
  Real clipboard copy/readback and the fallback to selection/manual copy when copying is refused were checked in a real browser.
- Referenced the input contract of `lib/shared/clipboard/base64_image_bridge.dart` and `photo_import_limits.dart`
  in Flutter main `13905a4d90f97daa73069d6fbff43acd6a65a760`.
  It meets decoded PNG ≤ 32 MiB, standard Base64, and matching MIME and signature. Pasting on a real Flutter device was not done this time.
  Flutter separately decodes up to 40 MP and downscales to 4096 px etc., so pasting a 4x PNG
  does not necessarily keep the Flutter document size as-is.
- Monochrome conversion of text, emoticons, emoji and PNGs fills the chosen color through the alpha mask.
  Pixels confirmed that, from an image with red and blue regions, both become the chosen RGBA `[1,160,96,255]`.
  An opaque photo is filled entirely. This is not subject extraction.
- The clock is 12 ticks plus 2 hands for the saved time. The arrow is a straight line plus a triangle, placed at the tip or center.
  The center/direction contract was compared with the existing PPTX `arrow_geometry` over 80 cases (seed `20261017`).
- Checked the UI's 2x PNG, 4x SVG/PNG (5120×2880), changing the clock time / arrowhead position, and undo.
  Text and shapes are redrawn in the same viewBox. Original images are kept; only raster images get a choice of interpolation.
- The CLI runs the same validation and SVG renderer as the UI in Node.js. PNG/Base64 use the standard WebSocket of
  Node.js 22+ and CDP on an installed Chrome. No runtime npm packages or image-generation APIs are needed.
  Chrome is launched with `--disable-gpu`. SVG does not need Chrome.
  The CLI PNG and the PNG decoded from Base64 are byte-identical. The original scene is not modified.

![Actual output of clock, arrow, emoticons and emoji](stamps.png)

[Re-editable scene](stamps-scene.json) / [4x SVG](stamps-4x.svg)

## Upscaling comparison: recording both improvements and regressions

A PNG of a known circle + triangle drawn at 256×256 is the reference; a PNG downscaled to 16×16 was scaled back to 256×256.
MAE and RMSE were computed over all RGB pixels and all 3 channels (white background, 0–255, alpha excluded).
A redraw from the kept original shape data is compared against the same reference. No training or threshold tuning was done.

| Method | RGB MAE | RGB RMSE |
|---|---:|---:|
| Nearest-neighbor upscaling | 14.497629801432291 | 36.02362599237717 |
| Smooth interpolation | 16.515345255533855 | 30.6190683861587 |
| Redraw of the kept original shapes | 0 | 0 |

Smoothing lowered RMSE but worsened MAE. Adopting only one of them is not treated as an accuracy improvement.
The redraw matches because coordinates, shapes and colors were kept, not because unknown detail was inferred from 16×16.
Nothing about natural images, text legibility, face restoration or super-resolution can be concluded from this test.
It is a single synthetic example and does not show general superiority between methods. It is not compared directly with Three-Way IoU.

![16×16 image, nearest-neighbor, smooth interpolation, redraw of kept original shapes](scale-comparison.png)

[Raw measurements](scale-results.json) and the reference, nearest-neighbor and smooth-interpolation scenes are kept in the same directory.

## Speed and failed attempts

A path producing CLI output with only Chrome's `--screenshot` option was tried first,
but it hit a 45-second timeout in this environment. This failure is not counted as success.
With the adopted CDP path, a 64×64 solid PNG took 1381.553629 ms in a single measured run including
Python, Node and Chrome startup and shutdown. It is not a repeated benchmark for speed comparison and does not show millisecond-level or GPU-substitute performance.
12 MP photos were not measured. Fonts depend on the OS; Japanese and emoji need suitable fonts.

## Regression checks

Local: Python 3.12.14 / Node 24.19.0 / Chromium 133.0.6943.0 / Playwright 1.58.2.
The test browser and CLI have GPU disabled. The sandbox-disabling environment variable is set only in the isolated root experiment environment;
the product CLI does not disable the Chrome sandbox by default.

```sh
python -m pytest -q tests/test_image_studio.py tests/test_studio_delivery.py
IRONMATE_STUDIO_STATIC=1 IRONMATE_CHROME=/path/to/chrome node tests/image_studio_browser.cjs
```

- 23 target Python tests passed. Default suite: 797 passed / 13 skipped / 7 deselected.
- Browser: besides the existing placement, moving, scaling, undo/redo, 20-image cache, mobile, offline and PPTX image match,
  checked the static subpath, Base64, clipboard, monochrome conversion, CLI and upscaling. Page errors and external requests were both 0.
  The list is saved in [run results](browser-result.json).
- actionlint and Python/Node syntax checks passed. CI runs the static version in the existing PPTX integration
  and saves all browser output as an artifact. The Pages workflow builds deliverables on PRs and deploys only from main.
- [source-sha256.json](source-sha256.json) holds SHA-256 of the code under this local experiment.
  Matching PNG hashes with CI, which has different fonts and Chrome, is not a requirement.

The code review and tests here were by the implementer and are distinct from an independent third-party approval review.

In the final UI check, a fix was added so that when `mono` is omitted in an old scene, the monochrome checkbox is off, matching the original rendering.
The checkbox state when selecting an old scene was regression-checked in the browser, and all browser checks passed again.
That code is recorded in [regression-source-sha256.json](regression-source-sha256.json).
The measurements, images and first source hash above were kept unchanged.
