# Markdown / CSV tables and simple PPTX diagrams (#80)

Creation follows **Markdown → Marp → python-pptx → PPTX inspection**.
`pptx_pipeline.py` owns conversion and native editing in one file. No separate
enrichment runtime module or added dependency. Use the existing vendored
`markdown.py` table parser rather than implementing another Markdown parser.

## Direct input: no TOML required

```sh
python pptx_pipeline.py slides.md --table comparison.csv -o result.pptx
python pptx_pipeline.py slides.md --table comparison.md -o result.pptx
python pptx_pipeline.py slides.md --table comparison.md --table-pattern cards --table-columns 3 -o result.pptx
python pptx_pipeline.py slides.md --table comparison.csv --table-pattern flow -o result.pptx
```

`slides.md` defines the Marp base slides, including free space for the objects.
`--table` is the data source. Defaults: native table on slide 1, region
`0.5 1.2 9 4` inches. Set `--table-slide N` and `--table-region X Y WIDTH HEIGHT`
for placement. CSV is UTF-8 (BOM accepted), with a header and rectangular body
rows; standard quoting is supported. Markdown uses the **first live GFM table**
via `vendor.markdown.markdown_table_to_rows`: fenced examples are skipped,
escaped pipes are unescaped, short rows padded and excess cells truncated by
that existing helper. Other tables are ignored. Inline Markdown formatting stays
literal text; this adapter does not render cell markup into rich text.

| Pattern | Data mapping | Native output |
| --- | --- | --- |
| table | Header + body rows unchanged | Editable PowerPoint table |
| cards | First column = title, remaining columns = header: value lines | Boxes, top bars, bold titles, body text |
| regions | Same mapping | Rounded areas with header badges |
| flow | Same mapping, source row order | Boxes and simple straight lines with triangular arrowheads |

There is no scoring, ranking, or automatic semantic evaluation. Cards optionally
wrap with `--table-columns`. Flows stay one row. Text uses Meiryo; body text is
black, headings bold. Defaults are white, black and neutral grays. Table headers
are dark gray (#222222) with white text; body fills alternate white/light gray
(#F2F2F2); borders are 0.5-point gray (#B3B3B3). Region header badges are white
text on black. Agenda work is deferred.

## Optional TOML configuration

Use `--enrich examples/pptx_enrich.toml` for several patterns or explicit color
changes instead of `--table`. TOML is a convenience, not the primary input.
Both options together are rejected. The example requires four existing Marp
slides and uses synthetic `comparison.csv`. CSV references in TOML resolve
relative to its directory.

Each pattern requires `pattern`, 1-based `slide`, `x`, `y`, `width`, `height`.
Optional `gap` defaults to 0.2 inches, `font_size` to 14 points, and `accent` to
black. Native tables accept `rows` or `csv` (not both). Optional `header_fill`,
`header_text`, `row_fills` and `border_color` change colors; otherwise the
monochrome defaults apply. Non-table patterns accept `items` with `title` and
`body`. The Python API `pptx_pipeline.enrich()` supports already existing PPTX;
`table_pattern()` adapts CSV/Markdown data for that API.

## Preservation and validation

Dry-run is available through `enrich(..., dry_run=True)` for existing PPTX.
Coordinates are finite nonnegative inches, dimensions positive, fonts 6–72
points. Shapes must fit the slide; cells must be at least 0.7 inches in each
dimension. IDs and counts are reported. Existing shapes remain unchanged with
new objects appended above them. Every non-target ZIP member, relationship,
media and note is copied unchanged. Input and existing output are never
 overwritten. The Marp intermediate remains private; failed edits do not publish
a final output. The result is reopened before atomic publication.

The caller chooses free regions. Overlap and text overflow are not automatically
measured. Arrows are not attached to boxes, so later box moves do not reroute them.
Branch/merge lines, return arrows, legends and automatic page numbers remain
future work. Rasterized Marp background text is not made editable by adding
native objects. Reference photos and their work content are not committed.

Integration tests stub the Marp boundary and run real native editing/inspection.
Actual Marp rendering and final PowerPoint Web display remain unverified.

```sh
python -m pytest -q tests/test_pptx_pipeline.py tests/test_pptx_enrich.py tests/test_markdown_pptx.py tests/test_pptx_replace.py tests/test_pptx_diagram_shapes.py
```

Existing-shape spacing is a separate proposal in PR #97, with no dependency here.
