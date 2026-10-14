# Editable PPTX enrichment patterns (#80)

`pptx_enrich.py` adds reusable native objects to explicit regions of existing
slides. It accepts TOML data instead of generating disposable Python per slide.
Uses the existing python-pptx dependency; no additional install or API is needed.

```sh
python pptx_enrich.py input.pptx --patterns examples/pptx_enrich.toml --dry-run
python pptx_enrich.py input.pptx --patterns examples/pptx_enrich.toml --output enriched.pptx
```

The example requires four existing slides. For a real deck, change slide numbers,
text and region coordinates. Input is never overwritten. Output must be new.

| Pattern | Reference structure | Native output |
| --- | --- | --- |
| agenda (deferred) | Vertical agenda rows | Prototype retained; not included in the current example |
| cards | Heading cards, comparison columns | Boxes, top bars, bold headings, body text |
| regions | Labeled rounded areas | Rounded boxes, accent badges, editable text |
| flow | Horizontal boxes and arrows | Independent boxes and straight lines with triangular arrowheads |
| table | Comparison/condition table | Editable native PowerPoint table |

Several patterns can be placed in separate regions of one slide, e.g. a flow
above cards and a one-row agenda/callout below. Cards can use `columns` to wrap
into multiple rows. Patterns fill their given rectangle; dimensions and gaps
are shared across cells. This covers basic reference structures, not exact
reproduction of every photographed slide.

## Contract

Each `[[patterns]]` requires `pattern`, 1-based `slide`, `x`, `y`, `width`,
`height` (inches). Optional `gap` defaults to 0.2, `font_size` to 14 points,
`accent` to black. Cards optionally accept `columns` (default item count).
Non-table patterns use `[[patterns.items]]` with `title`, `body` and optional
`label` (agenda annotation). Table uses rectangular `rows` or `csv`, with the first row
rendered using the header colors. Region badges and table headers use white text;
other text uses black Meiryo. Titles are bold. New shapes have stable descriptive
names and the report includes their Open XML IDs.

Coordinates must be finite nonnegative numbers; positive dimensions and 6–72
point font size are required. Content must be strings. Cells must be at least
0.7 inches in each dimension. Patterns must fit slide bounds; flows require
at least 0.15 inches of gap for arrows. Invalid input prevents publication,
including when a later pattern fails after earlier ones were built in memory.

Dry-run constructs the same objects in memory and reports counts and IDs without
writing output. Only target slide XML members are replaced. All other member
bytes, relationships, notes, media, and ZIP archive comments are preserved.
Existing shapes are retained, with new objects appended above them in z-order.
Reopen the output before atomic publication; existing destinations are rejected.

## Acceptance boundary and remaining patterns

The caller must choose free regions. Existing-object overlap is not detected or
resolved. Text wrapping is enabled, but font metrics and text overflow are not
measured; long text requires manual adjustment. A successful dry-run establishes
native geometry and structure, not a successful visual fit.

Flow arrows are straight editable lines with triangular end arrowheads, without box attachments;
moving a box later does not automatically reroute them. Branch/merge paths,
stacked model boxes with fan-out lines, return arrows, legends, automatic title/
footer/page-number generation and detailed style matching remain future work.
Use several explicit patterns for simple multi-region compositions. Source
image OCR, raster-to-shape conversion and automatic semantic content enrichment
are not implemented. The uploaded work photos and their text are not committed.

PowerPoint Web visual acceptance is still required for the final PPTX. Tests
verify editable shapes/table text, bounds, sequential additions, dry-run parity,
input preservation, and byte preservation outside target slides. No final
PowerPoint rendering or pixel-level match is claimed by these tests.

```sh
python -m pytest -q tests/test_pptx_enrich.py tests/test_pptx_replace.py tests/test_pptx_diagram_shapes.py
```

The separate `pptx_layout.py` proposal in PR #97 arranges existing shapes; this
module creates new patterns and has no runtime dependency on that proposal.

## CSV comparison tables and monochrome defaults

Comparison means direct CSV-to-table conversion only: no scoring, ranking,
inference or automatic evaluation. Use `csv = "comparison.csv"` instead of
`rows`; setting both is rejected. CLI paths resolve relative to the TOML file.
The Python API resolves CSV paths relative to its working directory. CSV is
comma-separated UTF-8 (BOM accepted), supports quoted fields, and uses its first
row as the header. Ragged input is rejected rather than truncated.

`header_fill` defaults to `#222222`, `header_text` to `#FFFFFF`,
`row_fills` to `["#FFFFFF", "#F2F2F2"]`, and `border_color` to `#B3B3B3`.
Body fills repeat over rows; give one entry per body row to specify all rows
individually. Borders are 0.5-point lines. Defaults are white, black and neutral grays. Color changes are explicit optional
overrides; reference photos guide structure, not the default palette.

Agenda work is deferred. The previously added prototype remains available,
but the shipped example and current focus are cards, regions, simple flows
and CSV tables.
