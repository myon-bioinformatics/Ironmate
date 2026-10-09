# PPTX attribute CLI — prototype contract (Issue #80)

Python >=3.11; runtime dependency: python-pptx. TOML is read with stdlib tomllib.

## Example

```toml
[[rules]]
operation = "replace_text"
old = "Draft"
new = "Final"
slide = 1

[[rules]]
operation = "text_color"
color = "#000000"
slide = 1
```

```sh
python pptx_replace.py input.pptx --rules rules.toml --dry-run
python pptx_replace.py input.pptx --rules rules.toml --output updated.pptx
```

Rules run in declaration order (sequential/cascading). A rule's optional `slide` is a 1-based slide number. No shape filter yet. Text replacement operates **within each run**, retaining run formatting; text spanning runs is not matched. Color updates require explicit RGB runs; theme and inherited colors fail explicitly. Slide backgrounds require explicit solid RGB fill, not inherited/theme fills. Shapes in groups, tables, notes, masters and relationships are not intentionally modified. No guarantee is made for unsupported constructs; test on disposable fixture files before production use.

Dry-run reports planned edits and does not write a PPTX. A zero-match operation is reported as zero changes. The output must be a new path; existing files are never overwritten. This prototype is intentionally narrower than the full Issue #80 plan; future revisions in the same Draft PR should add target selectors, preconditions, atomic output and stronger structure/visual diff checks before claiming general document preservation.


## Visual regression verification (planned in this Draft PR)

Render **both** original and transformed PPTX using the same pinned LibreOffice version and fonts, convert resulting PDFs to per-slide PNGs, and produce a side-by-side contact sheet plus pixel-difference images and machine-readable manifest. LibreOffice and a PDF rasterizer are **optional verification dependencies**, not requirements for basic CLI transformation. Never download tools implicitly.

A future `--visual-check` CLI flag should trigger rendering, and `--visual-output DIR` should allow retaining artifacts. Verify slide counts, image dimensions and renderer exit status; missing renderer or render failure must not be reported as success. Keep conversion in a temporary working directory and do not overwrite source files.

Expected changes (text/color/shape) naturally generate visual differences: do not equate zero diff with success. Report changed pixel count and bounding boxes as diagnostic evidence, and distinguish expected target regions from unintended regions once target-region mapping is implemented. Pixel comparisons are renderer/font-sensitive and should not be treated as cross-platform bit-for-bit guarantees.

CI should test the renderer on synthetic PPTX fixtures and upload PNG/contact sheet/diff artifacts; structural checks (slide/shapes/relationships and unmodified contents) remain separate. Real or sensitive presentations must not be uploaded as CI artifacts. If a renderer is unavailable, explicitly mark visual verification as skipped/unverified, never passed.
