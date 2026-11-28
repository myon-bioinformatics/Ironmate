# Image Studio — scenes, the CLI and the hand-off formats

Pictures are made in **the one editor** ([docs/slide-studio.md](slide-studio.md); ONE-EDITOR, #301): a page is a scene
(`ironmate-image-studio/1`), and 🎛️ with nothing selected sets its size (64–4096 per side, at most 4 MP) and its background
(a colour or transparent). The separate Image Studio page, its clipboard shelf and its work-history files are gone; this page
covers what stays: the scene format and its CLI, how images come in, Base64 for Flutter, heatmaps, mosaics and PPTX.

```sh
python -S image_studio.py
```

Open the shown `http://127.0.0.1:8765` in a browser: the editor runs with only the Python standard library and a browser, and
images and scenes are processed in the browser, not sent to the server. The portfolio publishes the same files under its Tools.

## Passing to Flutter via Base64

`📤` → `Base64` copies this page's PNG as a PNG data URI to the clipboard (where the browser cannot copy, it saves a
`.base64.txt`). The text matches the PNG bytes exactly: no URL-safe conversion, padding removal or percent encoding.

Checked against `lib/shared/clipboard/base64_image_bridge.dart` in
Flutter main `13905a4d90f97daa73069d6fbff43acd6a65a760`.
Output meets that implementation's accepted PNG data URI / standard Base64 at 32 MiB or less.
This is a hand-off for pasting into the existing clipboard field without changing Flutter code, builds or CI.
It does not mean the operation in Flutter was re-run this time. It was verified with the existing strict Python Base64 decoder and PNG byte equality.

## Image input and clipboard format selection

Drop a PNG, JPEG or WebP file (or a JSON) on the slide, or use `📥` → `画像` / `カメラ`. These paths use the same byte limit, MIME check and PNG normalization as clipboard images; of several dropped files, the first comes in.

The Node entry runs the Python validator. Its regression test uses the same 19 Base64 cases as the archived Flutter project, including MIME mismatches, padding and data-URI parameters. The archived [Dart expectations](https://github.com/myon-bioinformatics/flutter_navigation_basic/blob/647fb74c36899e52906cce6db7fe0d1fbbb04bf2/test/fixtures/base64_bridge/flutter_expectations.json) can be compared offline. [Flutter #208](https://github.com/myon-bioinformatics/flutter_navigation_basic/pull/208) contains the published Ironmate → Flutter Web handoff test. Its PR-head Flutter workflow passed, and the separate Non-Dart E2E workflow reported a failure. These browser fixtures cover file delivery and decoded pixels. Camera hardware, OS dialogs and physical-device clipboard behavior require a separate device run.
Canceling file selection does not change the deck. `capture` is a hint to the OS/browser and does not guarantee the camera opens.

`📥` → `クリップボード` chooses in this order (`StudioCore.clipboardImage`, the one reader).

1. If a valid image Base64/data URI can be read as text, it takes priority.
2. An explicit `data:image/...`, or raw Base64 starting with PNG/JPEG/WebP magic bytes, that is invalid is an error.
   It never silently imports a different older image. This includes MIME mismatch, decode failure and exceeding the size limit.
3. For unrelated ordinary text (including non-image Base64), an empty string or a failed text read,
   it looks for PNG/JPEG/WebP via `clipboard.read()`. Formats/items that cannot be read do not stop it from trying later images.
4. If nothing is obtained, it distinguishes permission denied, API unsupported, read failure, no image and invalid image.
   A permission denial on the text read alone does not abort. If both fail, priority is permission denied → invalid image → other read failures.

The status line's `data-code` (`#slides-status`) is set to `clipboard-denied`, `clipboard-unsupported`,
`clipboard-read-failed`, `clipboard-no-image` or `clipboard-invalid-image`.
The Clipboard API needs a secure context (HTTPS/localhost), a user gesture or permission, and support depends on the OS/browser.
When unsupported or denied, file selection and dropping a file remain available.

Spec differences, referencing [PhotoImportLimits](https://github.com/myon-bioinformatics/flutter_navigation_basic/blob/f8fe4e81d783258a4b8c730ea400acb7167372a2/lib/features/photo_studio/data/photo_import_limits.dart) and
[Base64ImageBridge](https://github.com/myon-bioinformatics/flutter_navigation_basic/blob/f8fe4e81d783258a4b8c730ea400acb7167372a2/lib/shared/clipboard/base64_image_bridge.dart)
in Flutter main `f8fe4e81d783258a4b8c730ea400acb7167372a2`:

| Item | Ironmate | Flutter Photo Studio |
| --- | --- | --- |
| Input byte limit | 32 MiB (after Base64 decoding; same for binary) | 32 MiB |
| Image pixel limit | 4,194,304 pixels for what is stored (the 4 MP limit on mosaic and rendering) | 40,000,000 pixels |
| Downscaling on import | To 4 MP and 1920 px on the long side, aspect kept (one pipeline, `StudioCore.picture`) | Default 2/3, downscaled to a document long side of 4096 or less |
| Stored image | PNG-normalized after validation, at most 4 MP | PNG-normalized and downscaled |

Ironmate's 4 MP is an intentional limit on mosaic processing and rendering load, so it holds for what is stored: a larger
image (a phone's photo through 📥 カメラ) is decoded once and shrunk, never refused for its pixels. A file over 32 MiB,
or whose bytes are not PNG / JPEG / WebP or disagree with its declared type, is refused before decoding.
Embedded PNGs in existing scenes are also limited to 12,000,000 characters per image and 20,000,000 in total, so a 32 MiB input is not necessarily storable.

Reproduction (test-only Playwright 1.58.2, no added runtime dependencies):

```sh
npm ci --ignore-scripts   # Playwright is a locked devDependency of the root package.json
npx playwright install --with-deps chromium firefox webkit
node tests/studio_clipboard.cjs
```

On the static build's `/Ironmate/` subpath, it checks the real-browser UI, PNG/JPEG/WebP decoding, RGBA, input byte/pixel boundaries and cancellation.
Coexisting formats, permission denial and lack of support are reproduced with test doubles at the Clipboard API boundary.
On Chromium it additionally writes ordinary text and a PNG together to a real `ClipboardItem` and reads them via the button.
Passing this test is not a claim about OS clipboard integration on Firefox/WebKit, real Android/iOS devices or real cameras.
CI runs the three engines independently and saves versions, checks and screenshots to `studio-clipboard-*` artifacts.
This reading logic stays in Ironmate (`StudioCore`) and will not move to PySaiyanWeBoo until real use in two or more places is confirmed.

## Clock, arrow, emoticon and monochrome stamps

`時計` (clock) is a snapshot of a time, saved as shapes: 12 ticks and 2 hands (✏️ edits it as `14:30`).
`矢印` (arrow) is drawn as a straight line plus a separate arrowhead: 🎛️ 矢印の形 is 三角 (triangle) or 初心者マーク (🔰 made
solid black through its alpha mask and turned to point along the arrow), and 矢印の先端 places it at the tip or the center.
Center placement is compared against the same center/direction contract as the PPTX `arrow_geometry`.

🎛️ `単色` (one colour) on a text or a picture fills 🎨's colour through the original alpha as a mask (a picture starts black):
it does not rely on changing a colour font's fill, and on a photo it fills the whole opaque area (no outline or cutout).

## Output scale and CLI

The CLI redraws a scene at 1×/2×/4×/8× keeping the same viewBox (max 8192 px per side and 16 MP); the scene's size and layer
coordinates are unchanged. Text and shapes are redrawn from source data; embedded images are upscaled pixelated or smooth
(🎛️ 拡大 くっきり / なめらか). Interpolation does not mean recovering detail. In the editor a page itself can be up to 4096 per side.

A scene prepared in Python can be output from the CLI with the same renderer as the editor's.
SVG needs Node.js; PNG/Base64 need Node.js 26+ and an installed Chrome/Chromium.
No image-generation API, GPU or Playwright/Puppeteer runtime dependency is needed. Fonts come from the host OS.

```sh
python -S image_studio.py --render scene.json --format svg --scale 4 -o poster.svg
python -S image_studio.py --render scene.json --format png --scale 2 -o poster.png
python -S image_studio.py --render scene.json --format base64 --data-uri -o image.base64.txt
# add --chrome /path/to/chrome only if Chrome is not on PATH
python -S image_studio.py --build-site build/studio-site
```

Existing output files are rejected and replaced only with an explicit `--force`.
For the static site, specify a new or empty output directory.

The [CLI comparison of MAE-priority, RMSE-priority, midpoint and balanced versions](image-comparison.md) is available as an optional experiment tool separate from the UI.

Successes, errors and processing times are kept in the [verification record for upscaling comparison and hand-off](evidence/studio-delivery/report.md).

## Numbers → color → heatmap

Open the [DRAgoWing heatmap editor](https://myon-bioinformatics.github.io/tools/#heatmap), paste a matrix or load a Plotly JSON file, then download scene.json and open it in the editor with `📥` → `JSON` (one scene becomes a one-page deck of its size; ↩️ brings the previous deck back). The scene's heatmap `palette` is kept through editing, SVG and PNG export, and saving. Color conversion uses [PySaiyanWeBoo's shared heatmap code](https://github.com/myon-bioinformatics/PySaiyanWeBoo/pull/189).
It uses `z`, `x`, `y`, `zmin` and `zmax`, and places **the first row at the top**.
It is not rendering-compatible with Plotly's axis order, layout, annotations, colorscale or customdata.
DRAgoWing's research results are not rewritten; this is a separate composite image that stores the input in the JSON's source.

🎛️ `色の段階` (color steps) from 2 to 256 quantizes only the colors; 0 is continuous color. `値を表示` shows the values.
The original z values are unchanged. null is treated as missing and drawn transparent, distinct from 0.
Each cell's title holds the label and original value. Value labels are omitted in narrow cells.
Scenes without a `palette` use the original five-stop Viridis-like scale.
Max 4096 cells. NaN, Infinity, bools and integers beyond JavaScript's safe integer range are rejected.
JSON decimals are ordinary Python/JavaScript floats, not arbitrary-precision decimal arithmetic.

Editable JSON can also be prepared from Python.

```sh
python -S image_studio.py --heatmap matrix.json -o scene.json
```

It errors if the output file exists. Add `--force` for an intended replacement.
Open the resulting scene.json with `📥` → `JSON` to add text and stamps.

## Image → mosaic → exploring granularity and color count

Select a picture and change 🎛️ `モザイクの幅` (mosaic cell width) and `色の段階` (color steps).
Original RGBA pixels in each block are averaged, including leftover edge cells.
RGB is weighted by alpha so hidden colors of transparent pixels do not taint opaque ones.
Each step is computed **from the kept original image**, so setting cell width back to 1 and color steps to 256 restores the original display.
It does not restore lost detail when only a mosaicked image exists.

The same operation is also provided in Python, and RGBA equality with the independent JS implementation is tested.

```python
import grid_tools
from image_studio import mosaic
art = grid_tools.restore('input.png')
result = mosaic(art, cell=8, levels=16)
with open('mosaic.png', 'wb') as out:
    out.write(grid_tools.encode(result, 'png'))
```

This Python example targets PNG/grid handled by grid_tools.
For browser input, the browser decodes PNG/JPEG/WebP and normalizes to PNG.
Keeping hidden RGB of fully transparent pixels, metadata such as EXIF, or animation is not guaranteed.

## Connecting to PPTX

Output PNGs can be inserted into PowerPoint as images.
In the existing Marp/Markdown path, a PNG can be embedded as a Base64 data URI like `![図](data:image/png;base64,...)`.
The existing standard conversion does not allow local file references, so relative-path PNGs may not load as-is.
Browser verification inserts the output PNG into a one-slide PPTX with the existing pinned PptxGenJS 4.0.1
and checks that `ppt/media/*.png` in the ZIP matches the original PNG byte for byte.
It does not mean individual stamps are editable as native shapes in the PPTX.
On-screen export targets are PNG, SVG, JSON and PNG Base64. Sample PPTX generation is done by the verification script.

## What was carried over from prior implementations

| Reference | Idea adopted | Ironmate implementation |
|---|---|---|
| Flutter photo studio `studio_document.dart` / `photo_studio_state.dart` | Frames and stamps independent of whether there is an image; separating edit state from history | SVG layer scenes, JSON history, PNG rendering. Dart code is not ported |
| DRAgoWing `dragowing/figures.py::heatmap_figure` | Separating values from display colors; keeping missing values and labels | Importing values from a single heatmap JSON and custom color-step adjustment. Research values and rendering definitions are not replaced |
| Ironmate `grid_tools.py` / `ironlib/grid_output.py` | Pixel verification with fixed RGBA and PNG | Reused for Python mosaic input/output |
| Ironmate's PptxGenJS | PPTX generation using the existing pinned dependency | Inserts browser-output PNGs and verifies the media match |

Reference points: the photo studio including Flutter main `13905a4d`, and DRAgoWing on Aoi main.
Exact checked SHAs are in the [verification record](evidence/image-studio/report.md).
Sources were referenced, but no code or dependencies from other repositories were newly vendor-copied.

## Limits and verification

Max 100 layers a page; embedded PNGs up to 12 MB each and 20 MB a page; 4 MP per image; the deck JSON 32 MiB.
It depends on browser memory use, so interactive editing and processing speed for 12 MP photos are out of scope.
The editor keeps the deck in this browser (best effort; ⚠️ 💾 when the device is full, then save JSON) and 64 undo steps.

The work-history format (`ironmate-studio-workspace/1`, `StudioCore.workspaceText` / `workspaceHistory`) stays for the Python /
Node API; the browser no longer reads or writes it (⏪ ↩️ ↪️ ⏩ and the deck JSON cover it).

```sh
uv run pytest -q tests/test_studio.py
# the editor in a real browser (a served build at IRONMATE_PAGES_URL), and the clipboard matrix (builds and serves its own)
IRONMATE_PAGES_URL=http://127.0.0.1:8080/Ironmate/ node tests/slides_browser.cjs
node tests/studio_clipboard.cjs
```

Regression tests cover Python/JS color conversion, mosaics with alpha, leftover edges, value preservation, SVG escaping,
restricted HTTP serving and refusing to overwrite existing files.

Exact pixel matches and RGBA residuals are the primary test of reversibility.
3-Way Survey continues as an auxiliary structural evaluation and is not turned into a metric guaranteeing this screen's image quality.

### Shelf items from Python

`studio_ingress.parse_shelf()` (Python standard library only) checks a list of clipboard items: at most 20 items and 32 MiB of
decoded image bytes and UTF-8 text in all. `data:` URIs, raw Base64 starting with a known image signature, and dicts specifying
`type="image"` or `mime` are validated as images; invalid formats, MIME mismatches and over-limit sizes are not demoted to text.
Strings with no image meaning are treated as ordinary text. Example image dict:
`{"type": "image", "mime": "image/png", "text": "data:image/png;base64,...", "label": "画像"}`.
Each returned item has `type`, `data`, `mime`, `text` and `label`.
