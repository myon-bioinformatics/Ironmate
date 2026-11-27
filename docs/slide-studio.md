# Slide Studio: build multiple slides in the browser and save as PPTX

https://myon-bioinformatics.github.io/tools/slide-studio/

Text, shapes, arrows, emoji, clocks and pictures on several slides, saved as a PowerPoint file that stays editable.
No installation, external CDN or server processing is needed. Input images and in-progress JSON are not sent anywhere.

## Usage

<img src="assets/phone-slides.gif" width="240" alt="Phone slides in a 390×844 browser: blank slide, text box, editing later, bigger text, 🔷 😊 (^^) 🕒 placed from candidates, page 2, ⬅️ back to page 1, then 🧭 through the six pager shapes">

One editor for phones and PCs, phone-first. The slide stays pinned at the top while you work, and every control is an emoji (its words are only in the tooltip / screen-reader label). A phone held sideways and a PC window (960 px and wider) put the controls beside the slide, every row on one line. `/tools/slide-studio/phone/`, its address before it became the entrance, sends on to it. The pinned slide and the page controls are PySaiyanWeBoo's `stage` and `pager` components (`scripts/build_studio_css.py` writes them from the pinned commit).

| | |
| --- | --- |
| ⬜ | Starts blank (one 1280×720 slide) |
| 🔤 | Add a text box (type right away) |
| 🔷 😊 (^^) | One row of candidates opens under the tools; tap one and it is placed: ▭ ◯ △ → for shapes, emoji, kaomoji (the same candidates as Image Studio's tools). Tap the tool again to close the row |
| 🕒 | A clock showing the time now |
| 📚 | With two or more things on the page, a row lists them from back to front (a text shows its first three characters, a shape its sign); tap one to select it, even when it is covered. The selected one is underlined |
| ✏️ | Edit the selected text, or a clock's time (`14:30`; what is not a time leaves it as it was). Tapping a selected text or clock again does the same |
| 🎨 | The selection's look, from the candidate row: 🎨 fill and 🖌 line to the next colour (black, teal, red, blue, yellow, white), 🌗 opacity 1 → ¾ → ½ → ¼, 🅱️ bold, 🔠 monospace ⇄ regular. A candidate that does not apply (bold on a shape) does nothing |
| ↻ | Turn the selection: ↻ 15° right, ↺ 15° left, ⏹ upright. The selection frame turns with it |
| ⏫ ⏬ | Bring to the front, send to the back |
| 👆 ↘ | Tap to select, drag to move, drag ↘ to resize. Tap a selected text box again (or ✏️) to edit it later; the editor sits under the slide at 16 px so phones do not zoom, and the slide updates as you type. A box left empty is removed |
| 🔽 🔄 🔼 | Every text box on every slide together: 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5 × (titles keep their ratio to body text). New boxes start at 32 px × the current step |
| ⬅️ ➡️ | Previous / next page, right under the slide; the middle shows page / pages. Keyboard ← / → (Home / End: first / last) do the same |
| 🧭 | The shape of the page controls, one tap each, no reload (kept on this device): ⬅️ 1/N ➡️ → ● dots → 🎚️ slider → 🎛️ dial → ✚ cross-key (⬆️ first, ⬇️ last) → ⏮️ ⬅️ 1/N ➡️ ⏭️ |
| ➕📄 📑 ✖️📄 | Add a blank page, duplicate, delete |
| 🗂️ | Every page as a small picture with its number (the current one underlined); tap one to go there. A view: not in ↩️ |
| 🆕 | Start over (one blank page) |
| 🗑️ ↩️ ↪️ | Delete the selection, undo, redo (64 steps) |
| 📥 📤 | Import and export; the format is picked after, in the candidate row. 📥: 📦 all-slide JSON (also those the PC studio saved), 🖼 a picture onto this page (photos become PNG, at most 4 MP and 1920 px on the long side). 📤: 📽️ PPTX (every slide, editable in PowerPoint), 📦 all-slide JSON, 🖼 PNG or 📐 SVG of this page as it looks |
| 🏠 | Image Studio |

The GIF is the frames `tests/slides_browser.cjs` saves (`build/pages-evidence/phone-*.png`, 390×844; `phone-frames.json` lists them) at 1.4 s each, 0.9 s for the 🧭 shapes.

The deck is also kept in the browser's local storage, so a reload or a killed tab comes back where it was. Nothing is sent anywhere. If the local storage is full (large pictures), the status shows ⚠️ 💾; save with 💾.

When several layers render to identical PNG bytes, the PPTX stores one media
part. Each placement retains its own size, position and opacity. This applies
across slides as well as within one slide.

Python consumers can inspect the generated PPTX directly with
`pptx_inspect.inspect(deck_bytes)`. A program that writes raw PPTX to stdout can
pipe it to `python -S pptx_inspect.py -` and read the slide report as JSON.

## 🖥️ The PC studio, retired

The PC studio that the editor above replaced is gone, so that phones and PCs are built once. Its old address, `/tools/slide-studio/pc/`, sends on to the editor, and its all-slide JSON opens there (📥 📦). Its line width, the centred arrowhead, italic, typed position and size, mosaic pictures and editing four slides in place were dropped; a file that has them keeps them, and they still show and export. Pictures, mosaics, heatmaps and the other image tools stay in Image Studio.

## What is editable in PowerPoint

| Target | Saved form in PPTX |
| --- | --- |
| Regular text | Native text box. Keeps line breaks, size, color, opacity, bold and rotation |
| Rectangles, circles, triangles | Native shapes |
| Arrows with triangular heads | A grouped straight line and triangular freeform. Keeps rotation and centering. Does not use the standard line-end arrow attribute |
| Images | PNG; the processed PNG when a mosaic is applied |
| Clocks, heatmaps, solid stamps, 🔰 arrows | Rendered to PNG per layer. That image's position, size and rotation remain editable in the PPTX |

Each new deck starts with a blank slide. The optional `タイトル` (title) and `本文` (body) are starter templates. They are exported as independent text boxes, not placeholders tied to a PowerPoint master.
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

An empty PPTX skeleton is generated from PptxGenJS 4.0.1, pinned by the existing `npm ci`, and `pptxgen_render.mjs`. The generated XML is kept in the `<slide-shell>` region of `STUDIO_JS` inside `ironlib/studio_bundle.py` (the one browser script) with a fixed date for reproducibility. The browser loads no external libraries.

```sh
npm ci --ignore-scripts
python -S scripts/build_slide_shell.py
```

The Open XML writer in `STUDIO_JS` (`IronmateSlides` in `ironlib/studio_bundle.py`) assembles slide order, native text, shapes and image Open XML onto this skeleton and stores it in a standard ZIP with CRCs. Required parts and relationships are generated explicitly; no arbitrary XML, ZIP paths or external references are accepted from input JSON. The deck itself (its check, the all-slide JSON, the title/body template and the add, duplicate, delete and reorder operations) is PySaiyanWeBoo's `slide-deck.js`, written into `STUDIO_JS` from the pinned commit by `scripts/build_studio_css.py`; the Open XML writer stays here.
Only the generated XML, the one JS and CSS file, and the editor screen are added to `image_studio.py --build-site` and Docker's public allowlist. User output such as PPTX and images is not included in the public build.

## Verification

- Multi-slide decks generated on the Node side are checked with the existing PPTX inspection, XML parser, ZIP CRC verification and resolution of every Relationship.
- Checked string escaping, line breaks, color/size/bold, opacity, grouped arrows, and rejection of mismatched slide sizes and XML control characters.
- Confirmed the generated XML skeleton matches a regeneration from the existing pinned JS writer.
- In the browser, verified text editing, adding/duplicating/reordering/deleting slides, JSON save and reload, keeping current state on invalid input, and a two-slide PPTX with native text + arrows and a clock image.
- Verified long Japanese, English, URLs, combining characters and emoji; explicit line breaks, blank lines and trailing line breaks; and changes to width, font size, bold, monospace font and rotation. Each line shown in the browser was matched against the text, paragraphs and line breaks of the actually downloaded PPTX, and loading old JSON/work history and a 390 px width were also checked.
- Generated files were read with the test-only third-party library python-pptx and converted to PDF with LibreOffice for visual checks. Hands-on use in the Microsoft PowerPoint app has not been done.

```sh
uv run pytest -q tests/test_browser_slides.py tests/test_pages_tools.py tests/test_studio.py
node tests/slides_browser.cjs
```
