# Pixel art prototype: first-stage contract and next steps

A candidate following Ironmate #77's "prototype, verify and keep as a candidate".
The user's goal is to first try machine generation and processing with emoji, and later move on to photo conversion and
expressing recognizable original characters.
The first stage does not judge quality as finished; it produces a reproducible grid of color indices.

## What is implemented

`pixel_grid.py` is a single stdlib-only file with no I/O at import time.
`render(mask, palette, effect, size)` returns `ironmate-pixel-grid/1` (`resampling: procedural_mask`).
`filename(artifact)` gives `{shape}_{colorID}_{effect}_{size}.png` (e.g. `triangle_C01_shadow_32.png`).

| Axis | Current |
| --- | --- |
| Shape | triangle / diamond / cloud / circle / rock (procedural) |
| Palette | Color IDs `C01`–`C10` (derived from main/shadow) |
| Effect | normal / shadow / highlight / outline (one of them) |
| Size | Any integer within each shape's range (table below) |
| Canonical data | 2D array of color indices + fixed RGBA palette (0 = transparent) |
| Output | Emoji / JSON / SVG / PNG |

`SIZES = (8, 16, 32, 64, 128)` is kept as the representative sizes shared with photo_grid.py.
In pixel_grid some shapes do not have 8 as their minimum (cloud and diamond are not drawn at 8).

### Color IDs

- IDs are `C` + a 2-digit sequence number (`C01`–`C10`). An assigned ID is never reused for a different color.
  Color names (grass etc.) are reference labels in `PALETTE_LABELS` and are not used in the CLI, JSON or filenames.
- Defined as `PALETTE_BASE[ID] = (main, shadow)`. Color indices: 0 = transparent, 1 = main, 2 = shadow, 3 = highlight, 4 = outline.
- highlight and outline are derived by rounding each RGB component to an integer (0.5 rounds up):
  - highlight = round((3 × main + 2 × 255) / 5) (moves main 40% toward white)
  - outline = round(shadow / 2) (moves shadow 50% toward black)
- For C05 (main #FFFFFF), highlight is the same color as main.

| ID | main | shadow | Label |
| --- | --- | --- | --- |
| C01 | #5BBD3E | #418A2D | grass |
| C02 | #63B3FF | #3F75CC | water |
| C03 | #FF6A00 | #CC3D00 | lava |
| C04 | #A84DFF | #7520B8 | poison |
| C05 | #FFFFFF | #CFD8E6 | snow |
| C06 | #E0C072 | #B08D45 | sand (provisional) |
| C07 | #9EA4AB | #6D737B | stone (provisional) |
| C08 | #A8693A | #744423 | wood (provisional) |
| C09 | #FFD23F | #C99A17 | gold (provisional) |
| C10 | #FF86C0 | #C9568F | blossom (provisional) |

C01–C05 are user-specified values. C06–C10 are provisional values to reach 10 colors and have not been visually evaluated.

### Shapes (procedural)

Rather than upscaling a fixed seed, the shape is recomputed for each size. The outer 1 cell is a transparent margin.

| Shape | Generation | Size range |
| --- | --- | --- |
| triangle | Widens by 1 cell on each side per row (apex 1 or 2 cells, height ≈ width/2) | 5–256 |
| diamond | L1 distance of cell centers ≤ radius | 9–256 |
| circle | Distance of cell centers ≤ radius | 6–256 |
| rock | Superellipse with exponent 2.6 (height 0.7 × width), bottom cut flat | 7–256 |
| cloud | 3 circles on a flat bottom (sides r = 0.16W, center r = 0.2W), with holes in each column filled | 16–256 |

If the quality rules (`mask_problem`) are not met, candidates are tried in a fixed order, such as slightly shrinking the radius or width,
and the first that passes is used. If none passes, `ValueError`. Out-of-range sizes also raise `ValueError`.

### Quality rules

1. Transparent margin, 4-connected, no holes or column gaps (no row gaps either, except for cloud).
2. Left-right symmetric. circle and diamond also need top-bottom symmetry.
3. No jagged outlines: split each of the top and bottom edges (per column) and the left edge (per row) into monotone runs, and
   - a step of 2 or more cells is not adjacent to a flat run (no 2×2 staircases)
   - the ratio of adjacent runs of the same kind (step size, flat run length) is within 2×
   (runs at the ends are cut off, so they are not compared). For cloud's left edge, only the part below the puff notches is checked.
4. Readable as the shape: triangle has an apex of 2 cells or less and the widest base; diamond has an apex of 2 cells or less and fill ratio 0.65 or less;
   circle has a square bounding box, empty corners and fill ratio 0.68–0.9; rock is wide, with empty corners and a base at least half the width;
   cloud has 2 or more notches on top, a base at least half the width, and a top that is not a 1-cell spike.

Size ranges were determined by scanning all sizes from 3 to 256. The minimum is "the smallest value from which all larger sizes pass".
Some sizes below the minimum pass (5 and 7 for diamond, 14 for cloud), but they are not adopted so the range stays contiguous.
The maximum 256 is a policy limit on output size, not a limit of the quality rules.
Within the range, the 5 shapes are also confirmed to differ from each other at the same size (16–64).

### Effects

Expressed as color-index replacement. Shadow = bottom 1/3 of the shape becomes 2, highlight = top 1/3 becomes 3,
outline = cells inside the shape with a transparent 4-neighbor become 4. The silhouette does not change.

The same input gives the same output. No randomness, network or external models.
Emoji are an approximate display choosing the closest emoji for each color; exact color and transparency are judged from the JSON.

## Verification and evaluation

An auxiliary structural evaluation using row/column projections and ternary bitmasks was added
in the [3-Way Survey experiment](three-way-survey.md). It combines pixel matching and structure matching for
upscaling → original size, and also verifies the checkerboard counterexample where information is lost.
Generation quality of smooth images and evaluation of color and detail are not judged by this structural metric alone.

Automated tests verify the quality rules at all in-range sizes (heavy), dimensions, color range and determinism at odd and representative sizes,
silhouette preservation before and after effects, shadow/highlight positions, outline boundaries, input rejection,
CLI JSON and side-effect-free import.
JUnit can be produced from the existing pytest, so no dedicated evidence generation is added.

Visual evaluation checks "Is the shape recognizable even in one color?", "Does the shadow explain the shape?",
"Do features survive at small sizes?" and "Can light and dark be read after changing the palette?".
Human quality evaluation has not been done. Passing tests is not a substitute for passing on aesthetic quality.
Candidates are kept in this repo and spun out once demand and contracts from other consumers are clear.

## Future stages (not implemented)

1. **Output and per-size design**: output from the JSON grid to PNG/SVG (prototyped in `grid_svg.py` and `grid_png.py`).
   Prepare seeds or outline rules for each of 16/32/64 and compare with simple upscaling.
   Upscaling for viewing uses nearest neighbor to keep cell boundaries.
2. **Character parts**: compose torso, head, eyes, mouth, limbs and equipment as layers.
   Make anchors, stacking order, left-right symmetry and its exceptions, and poses explicit.
   Evaluate distinctiveness with original shapes such as "robot" or "round face".
   Recoloring the 5 terrain masks alone is not treated as achieving character quality.
3. **Photo conversion**: image decode → orientation correction → crop/background handling → downscaling → color reduction →
   optional dither → grid → output. Input photos are ones the user chooses.
   Background removal and semantic fixes of eyes or outlines are separate processes and evaluations from simple color reduction.
4. **Photo to character**: compare a cropped/color-reduced baseline with transferring features onto parts.
   People evaluate face readability, outlines, color count and unwanted isolated pixels. No promise of automatic high quality.

Photo downscaling is not fixed to nearest neighbor from the start; BOX/LANCZOS etc. are compared.
Integer upscaling for display uses NEAREST. Color reduction uses a fixed palette or quantize, and dither uses
none as the baseline to compare its relationship with detail and noise.
Pillow has these operations. However, a photo adapter including JPEG/PNG decoding needs a decision to separate it
as an optional dependency, and no change making Pillow required in the core has been made.
Primary source: [Pillow Image reference](https://pillow.readthedocs.io/en/stable/reference/Image.html).

## What the first stage does not decide

There are no finished characters, photo adapter, web UI, PNG/SVG, bulk file saving or
animation yet. If Gradio becomes necessary, connecting to the existing mcp-toolcall-lab environment
will be considered, and Ironmate's old character/LLM foundation will not be revived.

## Purpose of palette replacement and connection to an Office CLI

The purpose is to reuse the same shape and layout and mechanically replace specified attributes
such as color or text. Emoji are the first way to check, and CSS is not needed.
The reference collection of asset ideas includes not only pure palette changes but also changes to inner patterns and parts.
Those are treated as separate effects and not confused with color-only results.

First, the cloud shape lets you compare bush, water, lava and snow palettes.
In the following example the color-index grid is identical and only the RGBA table changes.
The use names are figurative; distinctiveness as assets is evaluated visually separately.

```python
from pixel_grid import render

variants = {
    name: render("cloud", name, "shadow", 16)
    for name in ("C01", "C02", "C03", "C05")
}
baseline = variants["C01"]["pixels"]
assert all(item["pixels"] == baseline for item in variants.values())
assert len({tuple(item["colors"]) for item in variants.values()}) == 4
```

An Office CLI is a separate future prototype, first targeting replacement of text and fill colors in existing PPTX files.
This PR does not include PPTX editing or output. A PPTX is a package with multiple PresentationML parts and
relationships, so rather than unconditionally string-replacing all XML in the ZIP,
the policy is to identify and edit the target part, shape and attribute.
Future Word/Excel support will also use separate adapters that handle each format's XML structure.

Items to check in the first Office prototype:

- Specify the target slide and shape, and show planned changes and match counts in a dry run.
- Define handling when text is split across multiple runs, and keep out-of-scope text and formatting.
- Distinguish direct RGB from theme color references, and separate per-shape color changes from theme changes.
- Write to a file separate from the input, keeping the content and relationships of out-of-scope parts.
- Besides re-reading the ZIP/XML and verifying the diff, render it to check the display.

Pixel art takes a color-index grid as input and Office takes shapes and text in a document,
but they share the verification idea of "keep the structure and replace specified attributes".
Recoloring when placed as an image and changing the fill color of editable shapes are separate processes.

Primary sources: [Microsoft Learn — PresentationML](https://learn.microsoft.com/en-us/office/open-xml/presentation/overview),
[Working with slide masters](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-slide-masters).

### Priorities and dependency policy

- Focus first on converting PPTX colors, text and backgrounds. Treat "make all text black",
  "make the background white" and "replace only a specified gray" as separate operations.
  Even if text and background use the same RGB, select by the target's role.
- CSS is not a required foundation for output. On the other hand, when reading external HTML/CSS,
  understand and absorb the input spec. Separate parsing of already-fetched data from network fetching,
  and do not unconditionally increase fetching of external resources for the sake of CSS support.
  Specific missing features around CSS "#" will be defined as a separate item after checking the target code and input examples.
  This prototype is not treated as having extended an HTML/CSS reader.
- Writing our own XML parser is not a goal. Use existing standard features and
  accumulate know-how for Office target selection, conversion and verification.
- stdlib-only and single-file are not forced on all Office features.
  python-pptx is a candidate that can be adopted after checking the needed operations and compatibility,
  and is not added as a dependency at this stage.
- openpyxl is not introduced. First judge whether tabular data needs can be met with CSV/TSV or available existing services.
  Excel-specific creation and editing is limited to concrete demand those cannot meet.

Candidates for sharing are "target, attribute, pre-change condition, new value, change count and verification result".
Pixel palettes and Office formatting are not forced into the same internal structure;
first prove each format on a small scale, then extract places where the same rules apply.
Reusing existing tools such as regular expressions and Markdown is also considered where the contract fits.

Additional reference images showed examples of creating text, colors and linked shapes with python-pptx,
changing slide order and page numbers, and hashing shape information before changes.
These are references for code read from photos, not verification that the original PPTX is sound.
A hash of only shape type, position, size and text cannot confirm that colors etc. are kept,
so verification targets are defined according to the actual changes.

### First milestone for photo input: Base64 to a dot grid

The first goal on the photo side is to read an image passed as Base64 and output it as a dot grid
at a specified resolution. Better compression and CSS display are not requirements.

Base64 is a representation for passing binary as text, not an array of pixels or colors itself.
Arbitrary replacements on a JPEG/PNG Base64 string do not produce the intended pixelation.
Processing is split into the following stages.

1. Validate and decode the Base64 back into the original image file's bytes.
2. Extract width, height and pixels with a decoder for the image format.
3. Find representative colors at the specified resolution or reduction ratio, and assign them to a fixed palette if needed.
4. Output the color-index grid and palette to JSON, and use emoji for checking.

Stage 1 can be handled by Python's standard base64, but it is separate from stage 2's JPEG/PNG decoding.
Adopting Pillow is undecided; existing available decoders and shared tools will also be checked.
The policy is not to implement our own JPEG etc. decoders to avoid dependencies.
Pixel arrays can be accepted directly to verify stage 3 onward first,
but that result is not called support for photo Base64 input.

Input and pixel-count limits, handling of invalid Base64 and unsupported formats, and rules for orientation, aspect ratio and
transparency will be defined at implementation time. Automatic fetching of external URLs is not needed.
Existing cross-cutting assets for reading CSS will be referenced when needed,
and not made a required dependency of this photo conversion core.

Primary source: [Python base64](https://docs.python.org/3/library/base64.html).

#### Prototype implementation (`photo_grid.py`, Python 3.11+)

| Stage | Rule |
| --- | --- |
| Base64 | Raw Base64 or `data:<type>;base64,`. Whitespace and newlines are removed. Input with characters other than alphanumerics, `+/` and up to 2 trailing `=`, or with a length not a multiple of 4, is rejected. Up to 32 MiB (33,554,432 bytes) after decoding (same as flutter_navigation_basic's `maxInputBytes`; the Base64 length is checked first against `4*((max+2)//3)` characters) |
| decode | The adapter contract is `bytes -> (width, height, bytes of RGBA rows)`. With a PNG signature, `decode_png` (zlib+struct, CRC checks, 8-bit gray/gray+alpha/RGB/RGBA, non-interlaced only). Otherwise `decode_pillow` (only if Pillow is available; with EXIF orientation correction). Limit 4096×4096 pixels |
| crop/fit | The default `crop` cuts out a centered square fitted to the short side. `contain` fits the whole image keeping the aspect ratio, with transparent padding. Canvas is 8/16/32/64/128 |
| Downscaling | Area averaging (edge pixels weighted by overlapping area). Weighted by alpha; colors of transparent pixels are not mixed in |
| Color reduction | Default is median cut (1–16 colors, default 8, with a fixed tie-break). With `--palette`, colors are assigned to indices 1–4 of pixel_grid.py's fixed palette by nearest color (squared RGB distance; ties go to the lower index) |
| Transparency | Cells with mean alpha below 128 get color index 0 (`#00000000`). Others are output as opaque colors |

Input formats: Base64 (raw or data URI) or an image file. Detected by the leading bytes, not the extension (`_sniff`).
- PNG (8-bit gray/gray+alpha/RGB/RGBA, non-interlaced): standard library (zlib + struct).
- Palette, 16-bit and interlaced PNG: the standard decoder rejects them and automatically switches to Pillow if available.
- JPEG/JPG and WebP: only with Pillow (DCT and VP8/VP8L decoding are not in the standard library). To limit the formats
  Pillow opens, other formats claiming to be JPEG etc. are not read. For animated WebP, the first frame.
- SVG (vector, needs a renderer), GIF, BMP, TIFF, ICO, HEIC/AVIF: rejected with "… input is not supported"
  regardless of whether Pillow is available.
See the table in the README for per-format reasons and behavior. `tests/test_image_formats.py` verifies the table's behavior.

#### PNG output (`grid_png.py`)

`to_png(artifact, scale=1)` writes an 8-bit RGBA, non-interlaced, filter 0, zlib level 9
PNG from the same grid JSON with the standard library (zlib+struct). No time or text chunks, so the same input gives the same bytes.
`scale` (1–64) is integer nearest-neighbor upscaling, with output up to 4096×4096 pixels. Color index 0 is written as its RGBA (usually transparent).
Use it via `--format png` in `photo_grid.py` and `pixel_grid.py` (lazy import) or the `grid_png.py` CLI.
Tests confirm that reading back with the standard PNG decoder matches the original colors.

#### Base64 output (reversibility)

`--format base64` (`photo_grid.py`, `pixel_grid.py`, `grid_png.to_base64`) outputs the same bytes as `--format png`
as Base64. `--data-uri` adds `data:image/png;base64,`. It follows `--scale` and `-o`.
The output can be used directly as input to `photo_grid.py`.

- At scale 1, reading back with the same `--size` matches the original grid (palette + color indices).
  For pixel_grid.py grids use the same `--palette`; for photo_grid.py grids set `--colors` to the original opaque color count.
- PNGs with scale > 1 return to the same grid if the original `--size` is given (each cell is a scale × scale block of one color).
  A different `--size` gives a different grid.
- Median cut output removes colors not used by any cell from the palette (color indices are renumbered).
  So photo_grid.py output matches when read back with `--colors` = opaque color count.
- Externally made grids match if color index 0 is transparent, opaque colors are in ascending RGB order, all colors are used and there are no duplicates.
  Otherwise (0 not transparent, unused colors, semi-transparent colors with alpha 1–254), cell colors may be kept but indices or alpha will not match.
  Non-square grids or sizes other than 8/16/32/64/128 can be written to PNG/Base64, but as photo_grid.py input
  they are cropped to a square canvas and do not return to the same grid.

Base64 input rules: standard alphabet with required `=` padding (URL-safe `-_` and omitted padding are rejected).
Whitespace, CRLF newlines and a leading BOM are ignored. The `data:` scheme and type are case-insensitive.
The data URI type must be omitted or one of `image/png`, `image/jpeg`, `image/jpg` and `image/webp`,
and it is an error if it does not match the decoded bytes' format (e.g. `data:text/plain;base64,`, `data:image/svg+xml;base64,`).

#### SVG output (`grid_svg.py`)

`to_svg(artifact, scale=8)` writes SVG with only the standard library from `ironmate-pixel-grid/1` JSON (shared by pixel_grid.py and photo_grid.py).
Base64 → decode → grid → SVG can be done in one command
(`photo_grid.py --format svg [-o out.svg]`; the default stays JSON).

- `viewBox` is in grid units; `--scale` (1–64, default 8) changes only width/height. `shape-rendering="crispEdges"`.
- Horizontal runs of the same color are merged into one `<rect>` (`--no-merge` gives one per cell). The painted area is the same.
- Color index 0 and colors with alpha 0 are not output. `fill="#rrggbb"`, with `fill-opacity` for alpha < 255.
- Metadata goes into `<title>`/`<desc>`, XML-escaped. The same input gives the same SVG.
- No WebP output or native PPTX shape output.

The same input and options give the same JSON. No randomness or network.
The PNG decoder is a small adapter limited to basic 8-bit formats, and does not handle palette PNG, 16-bit,
interlaced, APNG or color-space chunks (gAMA/iCCP etc.) (the first three are explicit errors).
The policy of not implementing our own JPEG etc. decoders and leaving them to Pillow is kept.
The Pillow and standard versions share the same adapter contract, so they can be swapped or added later.

Limits: no dither, downscaling is area averaging only (no comparison with BOX/LANCZOS etc. yet),
output is JSON/SVG/PNG (no WebP output), no background removal or semantic corrections such as faces.
The standard version is pure Python, so large images are slow (roughly 1 second for 1000×1000).
Visual quality has not been evaluated.

#### Round-trip tools (`grid_tools.py`) and the SVG input subset (`svg_raster.py`)

- `restore`: PNGs with meta are fully restored to the original JSON. Without meta, the scale is determined by `--size` or the GCD of run lengths, and it errors unless each block is a single color.
- `resize`: nearest neighbor at cell centers (`(2i+1)*old // (2*new)`). Upscaling → original size always matches; downscaling loses information.
- `recolor`: only swaps the color ID table (indices unchanged), so round-trips match.
- SVG input is only `rect`, `circle`, `ellipse`, `polygon`, `g` (translate) and solid fills. Curved paths, gradients, CSS, external references and DOCTYPE/ENTITY are rejected with reasons (`tests/test_svg_raster.py`).
- The README's "Round-trip in one line" is the authoritative condition table. Pillow and numpy are added as test dependencies and are optional at runtime.

#### Stronger verification (property tests, mutation tests, matrix view)

- `tests/test_grid_properties.py`: generates 11 kinds of adversarial grids with fixed-seed randomness (many colors, near colors differing by 1, every alpha 1–255, checkerboard, one differing pixel, 1×N/N×1, prime sizes, transparent only, single color, accidentally aligned blocks) and compares every path in the condition table per (x, y, RGBA) against an independent oracle (standard, Pillow, numpy). The heavy version is `heavy`.
- Mutation tests: confirm that swapping 2 pixels, ±1 on one channel, shifting a row, transposing, flipping, reordering the color table and corrupting or tampering with meta are all detected.
- Crafted PNGs: filters 0–4 (including mixed per row), split IDAT, extra chunks, CRC mismatch, extra bytes after IEND and after zlib.
- `tests/test_grid_matrix.py`: treats a grid as four RGBA matrices and confirms the residual R = restored − original is exactly 0 for reversible paths. Singular values and sign+scale fingerprints are auxiliary only (tests show singular values miss flips and transposes). Lossy paths (downscale → upscale, JPEG) report error as RMS.
  The ideas come from myon-bioinformatics/Aoi's `pythdragoras/littlebit_prune.py` (SVD residual, sign + scale) and `queryu/ask/suggest.py` (SVD + sign index). No code was brought in.
