# Slide Studio: build multiple slides in the browser and save as PPTX

https://myon-bioinformatics.github.io/Ironmate/slides/

Image Studio's shape, text and image editing is reused per slide.
No installation, external CDN or server processing is needed. Input images and in-progress JSON are not sent anywhere.

## Usage

1. The first slide has a black title and body. Select a layer, paste into the text field on the left, and press `入力した文字・色を適用` (apply entered text and color). Adjust with the position, size and font size on the right.
2. Text boxes with content can be added from the title and body fields at the top. `文字の見本` (text samples) inserts Japanese, alphanumeric and English text into the body field. Titles are bold. You can also select a text layer and use `太字を切替` (toggle bold).
3. `編集できる矢印を追加` (add an editable arrow) places a straight line with a triangular arrowhead. Moving, scaling, rotating and recoloring work as in Image Studio. The centered arrowhead is also available.
4. Build a deck with `白紙` (blank), `スライド複製` (duplicate slide), slide selection, reordering and deletion. All slides use the same canvas size. Switching slides keeps the current layout and restarts the edit history.
5. `PPTXを書き出す` (export PPTX) saves all slides. Also using `全スライドJSON保存` (save all slides as JSON) lets you reload the editable data, images included, later. The regular `JSON保存` (save JSON) and `作業履歴を保存` (save work history) save only the current slide.

Unsaved changes are confirmed when leaving the page. There is no autosave or re-import of PPTX files.

## What is editable in PowerPoint

| Target | Saved form in PPTX |
| --- | --- |
| Regular text | Native text box. Keeps line breaks, size, color, opacity, bold and rotation |
| Rectangles, circles, triangles | Native shapes |
| Arrows with triangular heads | A grouped straight line and triangular freeform. Keeps rotation and centering. Does not use the standard line-end arrow attribute |
| Images | PNG; the processed PNG when a mosaic is applied |
| Clocks, heatmaps, solid stamps, 🔰 arrows | Rendered to PNG per layer. That image's position, size and rotation remain editable in the PPTX |

The on-screen `タイトル` (title) and `本文` (body) are starter templates. They are exported as independent text boxes, not placeholders tied to a PowerPoint master.
Fonts are Meiryo normally and MS Gothic for monospace. Font files are not embedded. Missing fonts are substituted on the viewing side, so line-break positions, character widths and emoji display may not match.
Text wraps automatically at the box width. Japanese and English words are segmented, and long words or URLs wider than the box are split by grapheme. Splits never land inside combining characters or emoji. Explicit line breaks, blank lines and trailing line breaks are kept, and wrapping is recomputed when font size, bold, font or width change. Rotation is applied to the whole box after line splitting.
On-screen display and browser PPTX export use the same measured font metrics, line splitting and 1.3x line spacing. Explicit line breaks become PPTX paragraphs; automatic wraps become editable line breaks. Width-based wrapping on the PPTX side is also enabled. The exported line breaks remain, so widening the box in PowerPoint does not rejoin lines automatically. Narrowing it, font substitution or PowerPoint's typesetting may add extra wraps. Full Japanese line-breaking rules (kinsoku) are not applied.
There is no auto-shrink or automatic box-height change. Text taller than the box continues downward both on screen and in the PPTX, so adjust height, position or font size for long text. Automatic wrap positions are not written into the original text in the JSON. Half-width spaces and tabs at wrap points are trimmed at line ends, but the original text is kept in the JSON.
Old-format all-slide JSON, single-scene JSON and work history can also be loaded. Slide Studio's regular text wraps when `wrap` is omitted; with `wrap: false` only explicit line breaks apply. Image Studio's default when omitted is unchanged. Generating PPTX directly from Node uses a conservative character-width estimate instead of measured fonts, so line splitting may differ from browser output.
Even with multiple slides, a PPTX never converts a whole slide into a single image.

## Limits

Up to 20 slides; all-slide JSON and PPTX are each at most 32 MiB. Image Studio's limits, such as 100 layers and 4 MP per slide, also apply.
Layers converted to images are rendered at up to 4 MP. PNG compression efficiency and rendering fonts depend on the browser.
Edits involving images in the PPTX are kept in the re-editable JSON. Keeping photo EXIF, hidden RGB of fully transparent pixels or original image metadata in the PPTX is not guaranteed.
Reading arbitrary existing PPTX and reproducing themes, PDF rendering, animation, notes, and native tables/charts are out of scope for now.

## Implementation and regeneration

An empty PPTX skeleton is generated from PptxGenJS 4.0.1, pinned by the existing `npm ci`, and `pptxgen_render.mjs`. The generated XML is kept in `studio/slides/package.js` with a fixed date for reproducibility. The browser loads no external libraries.

```sh
npm ci --ignore-scripts
python -S scripts/build_slide_shell.py
```

The browser's `pptx.js` assembles slide order, native text, shapes and image Open XML onto this skeleton and stores it in a standard ZIP with CRCs. Required parts and relationships are generated explicitly; no arbitrary XML, ZIP paths or external references are accepted from input JSON.
Only the generated XML, JS/CSS and editor screen are added to `image_studio.py --build-site` and Docker's public allowlist. User output such as PPTX and images is not included in the public build.

## Verification

- Multi-slide decks generated on the Node side are checked with the existing PPTX inspection, XML parser, ZIP CRC verification and resolution of every Relationship.
- Checked string escaping, line breaks, color/size/bold, opacity, grouped arrows, and rejection of mismatched slide sizes and XML control characters.
- Confirmed the generated XML skeleton matches a regeneration from the existing pinned JS writer.
- In the browser, verified text editing, adding/duplicating/reordering/deleting slides, JSON save and reload, keeping current state on invalid input, and a two-slide PPTX with native text + arrows and a clock image.
- Verified long Japanese, English, URLs, combining characters and emoji; explicit line breaks, blank lines and trailing line breaks; and changes to width, font size, bold, monospace font and rotation. Each line shown in the browser was matched against the text, paragraphs and line breaks of the actually downloaded PPTX, and loading old JSON/work history and a 390 px width were also checked.
- Generated files were read with the test-only third-party library python-pptx and converted to PDF with LibreOffice for visual checks. Hands-on use in the Microsoft PowerPoint app has not been done.

```sh
python -m pytest -q tests/test_browser_slides.py tests/test_pages_tools.py tests/test_studio_delivery.py
IRONMATE_PLAYWRIGHT_MODULE="$PWD/build/pages-test/node_modules/playwright" node tests/slides_browser.cjs
```
