# Ironmate

![Ironmate — pixel logo with the apostrophe in I’m replaced by 🔰](studio/brand/readme.svg)

The logo is **I’m with a 🔰 apostrophe**. The 6 variants are used by purpose; for now the favicon uses dark green, the README the Famicom style, the web UI the heatmap palette and the home-screen icon Pixel 3D, provisionally. The final version is undecided. Each variant can be saved from the [6-variant gallery](https://myon-bioinformatics.github.io/Ironmate/brand/). [Design and regeneration](docs/brand.md).

A Python-centered project for verifying **conversion and replacement of content and attributes** in documents, images and more.
Replacing text, color and arrow attributes in PPTX is a future target, and pixel/palette-based dot representations are being prototyped.
Requirements are in [Issue #80](https://github.com/myon-bioinformatics/Ironmate/issues/80),
and the dot representation prototype was merged as [PR #79](https://github.com/myon-bioinformatics/Ironmate/pull/79).
Markdown→PPTX conversion and a CLI for editing attributes of existing PPTX files are prototyped. Photo conversion is prototyped only for stage 1 (Base64 → color-index grid), and character part composition is not implemented. See the next section for the implemented scope of dot representations.

## Conversion and editing concept diagram

<a href="docs/assets/repository-concept.png"><img src="docs/assets/repository-concept.png" alt="Ironmate concept diagram: from Markdown, PPTX and images, through conversion, slide creation and Image Studio, to PPTX and image output, checked with tests and screen comparison." width="501"></a>

The provided concept diagram is cropped with its original text and figures. Each feature is an independent prototype or helper tool;
it does not depict conversion between all formats or a single integrated UI that operates everything.
See the sections and links below for implemented scope and limits. [Crop information](docs/assets/repository-concept.json).

### Problems, division of roles and benefits

<a href="docs/assets/repository-concept-v2.png"><img src="docs/assets/repository-concept-v2.png" alt="Ironmate problems, division of roles and benefits: a concept diagram splitting editing of Markdown, PPTX and images into conversion, creation and verification, leading to slide and image deliverables." width="499"></a>

This is an additional concept diagram supplementing the processing flow above. The existing diagram and feature limits are kept as they are.
"Can also be converted to HTML" refers to individual paths such as Marp HTML previews built from Markdown sources,
not a guarantee of faithfully reproducing edited PPTX in HTML.
[Difference between previews and PPTX verification](docs/pptx-cli-prototype.md) / [crop information for the additional diagram](docs/assets/repository-concept-v2.json).

## Image Studio: stamp shapes, text and emoji into an image

`python -S image_studio.py` opens a local editor. Layer shapes, images and custom stamps, change heatmap color steps and mosaic granularity, and output PNG, SVG, Base64 and re-editable JSON. Clock, arrow, emoticon and monochrome stamps and CLI rendering are also supported.

[Open Image Studio in the browser](https://myon-bioinformatics.github.io/Ironmate/) / [Open the pixel art and image list](https://myon-bioinformatics.github.io/Ironmate/tools/) / [Docker startup and Pages version scope](docs/browser-tools.md)

[Usage and verification scope](docs/image-studio.md) / [Real-browser screens and verification evidence](docs/evidence/image-studio/report.md).

## Create slides in the browser

[Open Slide Studio](https://myon-bioinformatics.github.io/Ironmate/slides/). Place titles, body text and arrows with the same operations as Image Studio, and save multiple slides to PPTX. Text and ordinary shapes are output in a form editable in PowerPoint. [Usage and scope](docs/slide-studio.md).

## PPTX conversion and editing

The entry point for generating PPTX from Markdown is unified as **`pptx_pipeline.py`**. The old `marp_pptx.py` has been removed, and no compatibility CLI is provided. Arguments are built with the pinned vendor `vendor/cli_args.py`.

```sh
python pptx_pipeline.py slides.md -o slides.pptx
python pptx_pipeline.py --text '# Title' -o slides.pptx
printf '# Title\n' | python pptx_pipeline.py - -o slides.pptx
# Add only when pre-converting Mermaid to SVG:
python pptx_pipeline.py diagrams.md --mmdc node_modules/.bin/mmdc -o diagrams.pptx
```

Marp CLI must be installed beforehand; the command never installs Node/npm on its own. Standard conversion does not allow local file references; only with `--mmdc` are local references enabled, for trusted input. The output JSON contains the results of conversion and PPTX inspection.

To change text, colors or attributes of existing PPTX files, use the separate `pptx_replace.py`. See the [prototype contract and verification status](docs/pptx-cli-prototype.md) for details.

## Pixel art prototype candidates

`pixel_grid.py` turns 5 shapes (procedural), 10 palettes (color IDs `C01`–`C10`) and 4 effects into reproducible color-index grids
at any size within each shape's range (odd sizes allowed).
Sizes that cannot be drawn cleanly are not generated and give an error.

| Shape | Min–max size |
| --- | --- |
| triangle | 5–256 |
| diamond | 9–256 |
| cloud | 16–256 |
| circle | 6–256 |
| rock | 7–256 |

```bash
python -S pixel_grid.py --mask cloud --palette C01 --effect shadow --size 23
python -S pixel_grid.py --mask circle --palette C02 --size 31 --format png --scale 8 > circle.png
```

[First-stage contract, verification and future design](docs/pixel-grid-prototype.md).

![Examples: 5 shapes × 10 color IDs (shadow effect), 4 effects, odd sizes](docs/pixel-grid-preview.png)

Examples (from the top: 5 shapes × color IDs `C01`–`C10` with the shadow effect / 4 effects on cloud and rock / odd sizes 5, 9, 7, 13, 17, 31).
It can be regenerated with `python -S grid_preview.py -o docs/pixel-grid-preview.png --force`,
and a test (`tests/test_grid_preview.py`) checks byte equality with the committed PNG, so the implementation and image cannot drift.

`photo_grid.py` reads Base64 (a raw string or `data:image/...;base64,`) or an image file
and converts it to the same `ironmate-pixel-grid/1` format (fixed RGBA + color-index grid).

Detection uses the leading bytes (magic bytes), not the extension. Files are passed as-is, and Base64 as a raw string or
`data:<type>;base64,` (the data URI type must be omitted or one of `image/png`, `image/jpeg`, `image/jpg` and `image/webp`).

| Input | Status | Required dependency | Reason / behavior |
| --- | --- | --- | --- |
| `.png` (8-bit gray / gray+alpha / RGB / RGBA, non-interlaced) | Supported | None (standard library) | PNG compression is zlib (deflate), so the standard `zlib` + `struct` can decompress and undo filters. `tRNS` (transparent color) for gray and RGB is applied as alpha 0 (RGB values kept; pixel-identical with Pillow). The zlib stream must be complete through its end and checksum; truncation or trailing data is an error. APNG is not an error; only the default image (IDAT) is read (same when the default image is not part of the animation; matches via Pillow too) |
| `.png` (palette, 16-bit, interlaced) | Conditional | Pillow | The standard decoder gives an explicit error for unsupported formats. With Pillow it automatically reads via Pillow (otherwise errors "unsupported PNG …" or "interlaced PNG …"). Transparency from palette + `tRNS` is also applied to RGBA via Pillow (pixel equality with expected values is tested) |
| PNG as Base64 (raw string) | Supported | None | Converted back to the original bytes with the standard `base64`, then processed as above. Standard alphabet + required `=` padding (URL-safe and omitted padding are errors). Whitespace, newlines (CRLF) and BOM are ignored |
| data URI (`data:image/png;base64,`) | Supported | None | Same as above. If the type and content differ (e.g. `image/jpeg` but PNG), or for other types (gif, svg+xml etc.), errors such as "unsupported data URI type" |
| `.jpg` / `.jpeg` (file, Base64, `image/jpeg`) | Conditional | Pillow | JPEG needs DCT + Huffman decoding, and the standard library has no decoder. Without Pillow, error "needs the optional Pillow package". EXIF orientation is corrected |
| `.webp` (same, `image/webp`) | Conditional | Pillow | WebP needs VP8/VP8L decoding, and the standard library has no decoder. Same error without Pillow. For animations, the first frame only |
| `.svg` | Unsupported in `photo_grid.py` / conditional in `grid_tools.py load` | None (faster with numpy) | Photo input (`photo_grid.py`) still gives "SVG input is not supported". Reading pixel art back (`grid_tools.py`, `svg_raster.py`) renders only a safe subset: `rect` (fill only, exact by area), `circle`/`ellipse`/`polygon` (4×4 supersampling), `g` (translate only), `#rgb`/`#rrggbb`, `fill-opacity`/`opacity`. DOCTYPE, ENTITY, `path`, `line`, gradients, `style`/`class`, `script`, `image`, `text` and transforms such as rotation give `SvgError` with a reason. Reversibility through SVG is not guaranteed (transparent cells become `#00000000`) |
| `.gif` | Unsupported | — | LZW decoding would have to be written ourselves, and frame selection for animations is undefined. Pillow can read it, but it is rejected as out of scope ("GIF input is not supported") |
| `.bmp` | Unsupported | — | Not adopted (to be considered if demand arises). "BMP input is not supported" regardless of Pillow |
| `.tif` / `.tiff` | Unsupported | — | Not adopted due to varied compression, multiple pages and color spaces. "TIFF input is not supported" |
| `.ico` | Unsupported | — | Contains images of multiple sizes, so selection rules are undefined. "ICO input is not supported" |
| `.heic` / `.avif` | Unsupported | — | Needs HEVC/AV1 decoding. Some Pillow builds can read them, but they are rejected as out of scope ("HEIC/HEIF/AVIF input is not supported") |
| Unrecognizable bytes | Unsupported | — | Error "unrecognized image format" |

| Output (`--format`) | Status | Required dependency | Reason / behavior |
| --- | --- | --- | --- |
| JSON (default) | Supported | None | `ironmate-pixel-grid/1` (fixed RGBA + color indices). Canonical data |
| SVG | Supported | None | Written directly as a string (`grid_svg.py`, `<rect>` merging horizontal runs of one color) |
| PNG | Supported | None | Writes 8-bit RGBA with `zlib` + `struct` (`grid_png.py`, integer nearest-neighbor upscaling, same input gives same bytes) |
| Base64 | Supported | None | The same bytes as PNG output, stringified with `base64`. `--data-uri` gives `data:image/png;base64,...`. Can be fed back into photo_grid.py |
| WebP output | Unsupported | — | The standard library has no VP8/VP8L encoder. Out of requirements |
| Native PPTX shapes | Unsupported | — | Out of scope by the user's decision (image output only) |

All errors are `ValueError` (including `ImageDecodeError`); the CLI prints the reason and exits with code 2.
`-o` does not overwrite existing files or symlinks and exits 2 ("refusing to overwrite"). To replace, use `--force` (temporary file + `os.replace`, replacing the symlink itself rather than its target). Common to all CLIs (`grid_output.py`).
Pillow is not a required dependency.

```bash
base64 -w0 photo.png > photo.b64
python -S photo_grid.py photo.b64 --size 32 --colors 8
python photo_grid.py photo.b64 --size 16 --palette C01 --fit contain
python -S photo_grid.py photo.b64 --size 32 --format svg --scale 8 -o photo.svg
python -S pixel_grid.py --mask cloud --format svg > cloud.svg
python -S grid_svg.py grid.json -o grid.svg   # SVG from an existing grid JSON
python -S photo_grid.py photo.png --size 32 --format png --scale 4 -o dots.png
python -S pixel_grid.py --mask cloud --format png --scale 8 > cloud.png
python -S grid_png.py grid.json --scale 8 -o grid.png
python -S pixel_grid.py --mask cloud --format base64 --data-uri -o cloud.b64
python -S photo_grid.py cloud.b64 --size 16 --palette C01   # returns to the original grid
```

[Photo input contract and limits](docs/pixel-grid-prototype.md#first-milestone-for-photo-input-base64-to-a-dot-grid).

### Round-trip in one line (`grid_tools.py`)

For AI agents embedding small Base64 images in message bodies, generation, reading back, scaling and color ID replacement
are bundled into one function / one command. Runs on the standard library only; Pillow and numpy are optional (they give the same results faster if present).

```bash
python -c "import grid_tools as g;print(g.encode(g.make('cloud','C01','shadow',16),data_uri=True))"
python -m grid_tools make circle --palette C02 --size 32 --scale 4 > c.b64          # Base64 (default)
python -m grid_tools load c.b64 --to json                                          # auto-restores 128px → 32 cells
python -m grid_tools load dots64.png --to json                                      # 64×64 (2× of 32) → 32×32
python -m grid_tools load c.b64 --resize 64 --recolor C05 --to png --scale 4 -o c.png
python -m grid_tools load c.png --to svg -o c.svg                                   # SVG for PPTX
python -m grid_tools photo photo.jpg --size 32 --colors 8 --to base64 --data-uri    # JPEG/WebP need Pillow
```

`g.sparse(artifact)` scans and swaps neighbors over active dots only,
and `scanner.grid.rollback_all()` fully restores pixels and the occupancy mask.
`--resize-method probes` (e.g. `--resize 16` with 32-cell input) is an experimental
2× downscale using 4 kinds of probes. Downscaling is lossy, and the default stays the existing nearest neighbor.
[Frame operations, reversibility scope and probe spec](docs/pixel-arcade-engine.md).

`encode` adds an `ironmate` tEXt chunk (color table and dimensions) to the PNG by default, and `load`/`restore` return
the original JSON as-is when it is present (`--no-meta` omits it; the default PNG bytes themselves are the same as `grid_png.py`).

| Path | Reversible? | Conditions (pinned by tests) |
| --- | --- | --- |
| grid → PNG/Base64 (with meta, any `--scale`) → load | Exact match through JSON | Only when the color table has duplicate RGBA, indices map to the first one (cell RGBA matches) |
| grid → PNG/Base64 (no meta) → load | Cell RGBA matches exactly | The scale is given by `--size` or auto-detected as the GCD of all same-color run lengths. Detection picks "the largest scale that explains it", so an image of only 2×2 patterns is restored smaller (resolve with `--size`). The color table becomes canonical order (transparent + ascending RGBA); if the original table was canonical, the JSON matches too |
| Semi-transparency (alpha 1–254), color counts (1–300 colors verified) | Exact match | PNG is 8-bit RGBA, so no degradation |
| Upscale (integer or non-integer) → downscale to original size | Exact match | Nearest neighbor at cell centers. Upscaling keeps every cell |
| Downscale → upscale | Generally lossy | Matches only when each block is a single color |
| Color ID replacement A→B→A | Exact match | Color indices are unchanged. Grids with indices beyond the 5 roles (0–4) are errors |
| grid → SVG → load | RGBA of visible cells matches | Cells with alpha 0 become `#00000000`. Reversibility of SVG itself is out of requirements |
| JPEG/WebP → grid | Lossy (downscaling, color reduction, binarized alpha) | From grid onward (PNG/Base64/SVG), as in the table above |
| Corrupted or tampered PNG | Error | CRC mismatch, extra bytes after IEND, extra bytes after zlib, and inconsistent dimensions or color tables in the meta header are all errors (via Pillow, extra bytes after IEND are ignored) |
| PNG broken by downscaling or interpolation | Error | "block … is not one color", "does not divide". Never fixed by guessing |

The standard library implementation is the reference (oracle), and tests confirm byte-level equality with results from Pillow (PNG decoding, NEAREST upscaling) and numpy (scale detection, scaling, SVG rendering). Rough timing for 512×512 PNG → 128-cell restore: standard about 250 ms, Pillow about 190 ms, numpy about 180 ms (local measurement).

#### Estimating reduction ratio and output size (`estimate`)

Gives the reduction ratio needed to fit within a Base64 character limit (e.g. an agent's message limit).

Readable Base64 is up to 32 MiB (33,554,432 bytes) after decoding (`photo_grid.MAX_BYTES`; the same value and check as flutter_navigation_basic's `maxInputBytes`).
Output is estimated as the same 8-bit RGBA PNG as grid_tools (filter 0, zlib 9).
The target is **the default grid_tools output**: with `ironmate` metadata (tEXt), measuring the length that `load INPUT --size W --resize w2 --to base64 [--data-uri]` actually produces. To measure output without metadata, specify `--no-meta` (`meta=False` in Python).

```bash
python -m grid_tools estimate --width 1024 --height 768 --bytes 900000 --limit-chars 200000 --data-uri
python -m grid_tools estimate photo.jpg --limit-chars 100000 --data-uri --verify   # actually encode to check
python -c "import size_estimate as s;print(s.estimate(width=64,height=64,nbytes=3000,limit_chars=2000)['recommended'])"
```

| Item | Details |
| --- | --- |
| Base64 character count | `4*ceil(bytes/3)` (including `=` padding; `--data-uri` adds the 22 characters of `data:image/png;base64,`). Exact |
| Recommendations | `recommended` (simple fractions such as 2/3 or 1/2), `integer_option` (1/k), `lossless_option` (lossless with nearest neighbor) |
| Lossless check | Only 1/k where k divides the GCD of same-color run lengths (cell scale) is lossless |
| Metadata | By default `est_bytes`, `upper_bytes` and `actual_bytes` include the tEXt part. resize keeps the whole palette, so photos with many colors get large from the header alone (in that case `--no-meta` is suggested) |
| Upper bound | `upper_bytes` is an exact upper bound including uncompressed deflate and metadata. `typical_low_bytes` is a rough guide |
| Signals used | `signals_used`: PNG IHDR, PLTE, tRNS, IDAT compression ratio and meta; JPEG SOF, quality estimated from quantization tables, subsampling and EXIF; WebP VP8/VP8L/VP8X; color count, alpha, entropy, run lengths and cell scale |
| Confidence | `confidence`: low (dimensions and bytes only) / medium (pixels re-encoded and measured) / verified (`--verify` actually encodes each candidate with `grid_tools.encode`; each candidate lists a `command` producing the same output) |

In measurements (photo JPEG/WebP/PNG, pixel art), estimates were within 0.75–1.6× of actual. PNG compression varies with content, so use `--verify` when close to the limit.

#### Simple API (`ironmate_image`)

An entry point you can call without worrying about reduction ratio, metadata or format detection (standard modules only; JPEG/WebP input works if Pillow is available).
Input can be a path, PNG/JPEG/WebP bytes, Base64, a data URI or ironmate JSON.

```bash
# Fit into Base64 of at most 20,000 characters (prefers lossless ratios; if it doesn't fit, retries without metadata)
python -c "import ironmate_image as im;r=im.fit_to_limit('a.png',max_chars=20000,data_uri=True);print(r.ratio,r.chars,r.meta_used,r.warnings)"
python -m grid_tools fit a.png --limit-chars 20000 --data-uri -o a.b64    # result summary as JSON on stderr
# Back and forth (the same operations are also available from the CLI)
python -S ironmate_image.py load a.png
python -S ironmate_image.py to-base64 a.png
python -S ironmate_image.py resize a.png 64
python -c "import ironmate_image as im;s=im.to_base64('a.png');print(im.from_base64(s)['width'])"
python -c "import ironmate_image as im,grid_tools as g;print(g.encode(im.resize('a.png',64)))"
```

| Function | Details |
| --- | --- |
| `fit_to_limit(src, max_bytes=None, max_chars=None, data_uri=False, prefer='lossless')` | The largest result that actually encodes within the limit (`FitResult`: `data`, `text`, `ratio`, `width`, `height`, `bytes`, `chars`, `meta_used`, `lossless`, `command`, `warnings`). Prioritizes pixels (lossless → larger ratio), and with the same ratio picks the one with metadata. `FitError` if nothing fits |
| `to_base64(src, data_uri=False, meta=True)` / `to_png(src)` | Default grid_tools output |
| `from_base64(s)` / `load(src)` | To a grid (dict). Fully restored if metadata is present |
| `resize(src, width, height=None)` | Nearest-neighbor scaling (height keeps the aspect ratio) |

`FitResult.command` is the grid_tools CLI producing the same bytes (equality confirmed by tests).

#### Privacy (source image metadata is always discarded)

Output (PNG, Base64, data URI, SVG, JSON) contains **none** of the source image's EXIF (including GPS location, capture time, device model and author), XMP, ICC profile, PNG `tEXt`/`zTXt`/`iTXt` (author, comments etc.), `eXIf` or `tIME`. Only pixels are read, and output is written from scratch. Tests (`tests/test_privacy.py`) confirm that no original strings remain in the output on every path: `ironmate_image`, `grid_tools` (`photo`/`load`/`fit`) and `photo_grid`.

PNG output contains only `IHDR`, `IDAT`, `IEND` and, by default, a single ironmate `tEXt`. Its content is limited to the following (omitted with `--no-meta`).

| Item | Details |
| --- | --- |
| `schema`, `width`, `height` | Format name and grid size |
| `colors`, `palette` | Palette (a list of `#RRGGBBAA`) and color IDs |
| `mask`, `effect`, `fit`, `quantize`, `resampling` | Generation and conversion settings |
| `source`, `restored` | Source image width, height, format name and scale (numbers and short identifiers only) |

Any other keys or free-form strings are discarded both when writing and when reading PNGs with an ironmate header (personal information in headers made by other tools is not carried over).

#### Clipboard / Base64 input case collection

`tests/fixtures/base64_bridge_cases.json` collects inputs that commonly occur when pasting Base64 images (data URI type/content mismatch, unlabeled GIF, uppercase `DATA:`, BOM, parameters such as `;charset=`, 76-column CRLF line breaks, URL-safe, `%3D` padding etc.) and their expected results. Handling in Ironmate:
`;key=value` parameters are accepted and ignored; quoted values or missing `;base64` are errors; the limit is authoritative in bytes (character count is derived from `4*ceil(bytes/3)`, whitespace not counted). Other implementations (Flutter etc.) can read the same JSON in their tests.

## Responsibilities

- For shared GitHub operations and vendor management, see the [parent repository](https://github.com/myon-bioinformatics/myon-bioinformatics) and [gh_identity](https://github.com/myon-bioinformatics/gh_identity).
- The old GitHub catalog, MCP server, repository metadata/diagnostics and artifact provenance generation prototypes have been retired. This does not mean every old API has a compatible implementation at its destination.
- The source/niconico implementation and tests moved to [mcp-toolcall-lab PR #108](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/108), which is merged. This repository's `vendor/niconico_search_api_template.py` still remains for now. The design for absorbing API/MCP differences was handled in that repo's #107 (closed).
- `vendor/` and `vendor.lock.json` are the consumer's pinned copies. 58 shared tool files (from 24 repositories, including LICENSE) are registered with the parent's management scheme and verified against pinned hashes. `vendor.lock.json` is the only provenance.

Introduction and metadata are consolidated in the [portfolio](https://myon-bioinformatics.github.io/#ironmate). Ironmate's dedicated metadata stub Pages has been retired. [Image Studio](https://myon-bioinformatics.github.io/Ironmate/) is published statically as a working demo, and images and scenes are handled only in the browser.

For details, see [cleanup and vendor survey](docs/cleanup-stage-two.md) and [vendor CI](docs/vendor-automation.md).

## Local tests

```sh
git clone https://github.com/myon-bioinformatics/xprobe.git build/shared
git -C build/shared checkout 7e7015b2df69ad446b968f6fa49711b5b1dbdd3f
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout a9df23dec720f125772a24b77b413552d60060ba
python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json
uv run --locked python -m pytest -q -m 'not heavy'
python -S ironmate_tests.py list
```

`ironmate_tests.py list` outputs JSON by default. Run fast Node tests by id, like `python -S ironmate_tests.py run studio-ingress`; the child process's exit code is returned as-is. Each tool's `--help` and fixable errors (exit code 2, JSON on stderr with `--json`) follow the `ironmate_cli.py` contract. `-o` / `--output` / `--out` are the same output destination for the image digest and comparison sheet.

xprobe and the parent's vendor tools are separate checkouts for testing. They are not fetched automatically as runtime dependencies.
New PPTX packages need Node.js 24+ and `npm ci` (pinned `pptxgenjs@4.0.1`). Ironmate does not install dependencies automatically. The source of truth for slide shapes is the [JSON ↔ OOXML mapping](docs/pptx-ooxml-mapping.md). A separately installed Marp CLI is needed only for Marp conversion.
To turn CSV into xlsx, use the [Excel workbook](docs/xlsx-exceljs.md). Encoding detection covers UTF-8 / BOM / Shift_JIS / CP932. openpyxl and pandas are not used. The same `npm ci` also installs `exceljs@4.4.0` and SheetJS `xlsx@0.20.3`.

## Comparing screenshots across browsers

`browser_matrix.py` collects screenshots of the same page taken by browser-test-kit on Linux, macOS and Windows × Chromium, Firefox and WebKit
into a "page × environment" comparison sheet (PNG, table, JSON). See the [comparison sheet](docs/browser-matrix.md) for details.

## Image digest page

`image_digest.py` (`image_digest.cjs` from Node) builds a single lightweight HTML page with thumbnails and
a Markdown summary from a rows × columns set of images and pass/fail results. Thumbnails are shrunk by 1/4 at a time until it fits the size limit. See the [image digest page](docs/image-digest.md) for details.

## Python from Node (`py_launch`)

`flow_export.cjs`, `flow_workspace.cjs` and `image_digest.cjs` leave the processing to Python and delegate only the launch
to `vendor/py_launch.cjs` from the parent repository (Node.js 24+). When the API's `python` is omitted, each call briefly checks
for 3.9+ and tries `IRONMATE_PYTHON` → `PYTHON` → `python3` → `python` (`py -3` on Windows)
in that order. If `IRONMATE_PYTHON` or the API's `python` is given explicitly, only that is used, with no
fallback if it is not found. `flow_workspace.cjs` uses `isolated` (CPython `-I`) to ignore the child process's `PYTHON*` environment,
and `flow_export` etc. in the same directory are put on `sys.path` by the script itself. JSON requests are limited to 4 MiB; exceeding it gives
`EINPUTTOOLARGE` (`maxInputBytes`) prefixed with `flow workspace Python process failed:`. `IRONMATE_PYTHON` only selects the
interpreter on the Node side and is not subject to `-I`. For details see
[flow export](docs/flow-export.md) and [image digest](docs/image-digest.md).

## Common JSON flow diagrams

[web-ui flow export](docs/flow-export.md) connects a single bounded JSON input to Mermaid Markdown, SVG, PNG, standard Base64 and PNG data URI, through Python/Node APIs and CLIs. It reuses the upstream contract and Image Studio raster output.

Retain, edit and regenerate flow JSON with the [flow workspace CLI and Python/Node APIs](docs/flow-export.md#retained-json-workspace-import--patch--regenerate), while preserving the original UTF-8 source.

## Discover production entry points

```sh
python -S browser_matrix.py app-results --page 'flutter-*' --env '*-chromium-*' --out matrix
```

Select page/environment families in the existing screenshot comparison pipeline; use `--list` for paths only. [Discovery usage and optional source inspection](docs/convention-discovery.md).
