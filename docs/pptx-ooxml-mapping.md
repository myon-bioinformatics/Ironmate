# JSON slide spec ↔ OOXML

Ironmate's supported slide spec is a flat z-ordered `slides[].objects` list. For that subset the mapping is one-to-one: `canonical_spec` → slide XML → `canonical_spec` is identical, and writing the spec read back from that XML is the same document under XML canonicalization (`xml.etree.ElementTree.canonicalize`).

Tests live in `tests/test_pptx_mapping.py`. They do not open PowerPoint or a browser. A package-level test also builds the ZIP with pinned **PptxGenJS 4.0.1** and then replaces each slide part with this mapping, so the package shell comes from PptxGenJS and the shape XML does not.

The same idea applies to Excel later: a documented xlsx subset should round-trip as JSON ↔ worksheet XML, with an explicit list of what the reader will not preserve. That workbook mapping is not implemented here.

## Units

| JSON | OOXML | Conversion |
| --- | --- | --- |
| inches (`x`, `y`, `w`, `h`, margins, row `h`, `colW`) | EMU on `a:off`, `a:ext`, `a:gridCol/@w`, `a:tr/@h`, body insets | `round(inches × 914400)`. Read back divides by 914400. Whole inches stay JSON integers. |
| points (`fontSize`, line `width`, border `pt`) | `a:rPr/@sz` is points × 100. `a:ln/@w` is points × 12700 (1 pt = 12700 EMU, so 0.5 pt = 6350). | Whole points stay integers. |
| degrees (`rotate`) | `a:xfrm/@rot` = degrees × 60000, clockwise | Quantized to 1/60000 degree. `0` is omitted. |
| color | `a:srgbClr/@val` | 6 hex digits, uppercase, no `#`. Theme or scheme colors are not in the subset. |

`p:sldSz/@cx` and `@cy` use the same inch→EMU rule. The default deck is 10 × 7.5 in (9144000 × 6858000), which is PptxGenJS `LAYOUT_4x3`.

## What is always present and not a JSON field

These are package structure. The writer emits them and the reader ignores them, so a second write is stable.

- `p:spTree/p:nvGrpSpPr` with `p:cNvPr/@id="1"`
- `p:grpSpPr/a:xfrm` zero `off`/`ext`/`chOff`/`chExt`
- `p:clrMapOvr/a:masterClrMapping`
- `p:cNvSpPr`, `p:nvPr`, empty `a:avLst`
- shape `p:cNvPr/@id` values `2, 3, …` in z-order. Ids are derived. They are not stored in the spec.

`p:cSld/@name` is optional. When the spec has `name`, it is that attribute and it round-trips. Surgical renames (`set_slide_name`) still edit the attribute in place.

## Objects

`p:spTree` child order is `objects` order.

### `op: "shape"`

`p:sp`

| JSON | XML |
| --- | --- |
| `name` | `p:cNvPr/@name` |
| `shape` | `a:prstGeom/@prst` (`rect`, `roundRect`, `triangle`, `rtTriangle`, `chevron`, `downArrow`, `ellipse`) |
| `options.x`, `y`, `w`, `h` | `a:off/@x`, `@y`, `a:ext/@cx`, `@cy` |
| `options.rotate` | `a:xfrm/@rot` when non-zero |
| `options.flipH` / `flipV` | `a:xfrm/@flipH` or `@flipV` = `1` only when true. `false` is omitted. |
| `options.fill.color` | `p:spPr/a:solidFill/a:srgbClr/@val` |
| fill omitted | no `a:solidFill` and no `a:noFill` |
| `options.line.color` | `a:ln/a:solidFill/a:srgbClr/@val` |
| `options.line.width` | `a:ln/@w` |
| `options.line.dashType` | omitted for `solid`; otherwise `a:ln/a:prstDash/@val` |
| line omitted | no `a:ln` |
| `paragraphs` | `p:txBody` (see text) |

`roundRect` adjustments and `rectRadius` are not written. `a:avLst` is empty.

### `op: "text"`

Same as a shape, with `p:cNvSpPr/@txBox="1"` and `a:prstGeom/@prst="rect"`. There is no separate `shape` field. That attribute is how a text box is distinguished from a rectangle.

### `op: "line"`

`p:sp` with `a:prstGeom/@prst="line"` and `a:noFill`. The line color and width live on `a:ln`, not on a connector and not on `a:tailEnd` / `a:headEnd`.

A horizontal edge-to-edge arrow has `h: 0` (`cy="0"`). `flipH` follows the line-box rule: true only when the endpoints are not on the main diagonal. `flipV` from the geometry helper is always false and is omitted.

### Arrow = line + triangle

Authoring `op: "connector"` or `kind: "connector"` is **not** a reversible object. `expand_connector` / `arrow_geometry` replaces it with:

1. `op: "line"` — the straight segment
2. `op: "shape"`, `shape: "triangle"` — centered on the midpoint, `rotate = round((degrees(atan2(dy, dx)) + 90) % 360, 4)` because the triangle preset points up

`mode: "edge"` uses the box edges crossed by the center-to-center ray (side by side: right edge to left edge; stacked: bottom to top). `mode: "center"` joins centers; the line is placed before the boxes so only the gap shows. Neither mode sets `endArrowType`, `beginArrowType`, `lineHead`, or `lineTail`. Those keys raise.

Flow patterns use this pair. Names end with `-arrow-line` and `-arrow-head`. Stroke width is 1.5 pt. The head is 0.18 in.

### Text body

| JSON | XML |
| --- | --- |
| `options.wrap` | `a:bodyPr/@wrap` (`square` or `none`) |
| `options.valign` | `a:bodyPr/@anchor` (`top`→`t`, `middle`→`ctr`, `bottom`→`b`) |
| `marginLeft`, `marginRight`, `marginTop`, `marginBottom` | `lIns`, `rIns`, `tIns`, `bIns` in EMU |
| `paragraphs[].align` | `a:pPr/@algn` (`left`→`l`, `center`→`ctr`, `right`→`r`, `justify`→`just`) |
| `paragraphs[].runs[].text` | `a:t`. Leading or trailing spaces set `xml:space="preserve"`. |
| `fontSize` | `a:rPr/@sz` |
| `bold: true/false` | `a:rPr/@b` = `1` or `0`. Omitted bold is not the same as `b="0"`. |
| `italic` | `a:rPr/@i` |
| `color` | `a:rPr/a:solidFill/a:srgbClr/@val` |
| `fontFace` | `a:rPr/a:latin/@typeface` |

Omitted optional run fields stay omitted. There is no `lang`, `dirty`, `a:ea`, `a:cs`, `pitchFamily`, `charset`, or `a:endParaRPr`.

### `op: "table"`

`p:graphicFrame` → `a:graphicData/@uri` = `.../drawingml/2006/main/table` → `a:tbl`.

| JSON | XML |
| --- | --- |
| `name` | `p:cNvPr/@name` |
| `options.x`, `y`, `w`, `h` | `p:xfrm/a:off`, `a:ext` |
| `options.colW[]` | `a:tblGrid/a:gridCol/@w` |
| `rows[].h` | `a:tr/@h` |
| `rows[].cells[].fill` | `a:tcPr/a:solidFill/a:srgbClr/@val` |
| `rows[].cells[].paragraphs` | `a:txBody`, same run mapping as shapes |
| `options.border.color`, `pt` | each of `a:lnL`, `a:lnR`, `a:lnT`, `a:lnB` with `@w` and `a:srgbClr` |

Cell borders do not carry `a:headEnd` or `a:tailEnd`. A reader that sees four equal borders returns one `border` object.

## Normalization

`a:noFill` and a missing fill both mean “no fill color”. The writer omits the element. An empty `a:ln` (no `a:srgbClr`) and a missing `a:ln` both mean “no line”. The first XML → JSON → XML of a foreign part can drop those extras; the second pass matches the canonical document. `xml_round_trip` asserts that second pass, and that a spec written by this module already round-trips on the first pass.

## Not reversible

Preserved in the ZIP when an edit copies untouched members, but not represented in the spec:

- theme, slide master, slide layout
- notes, docProps, thumbnails, core properties (author, title, timestamps)
- pictures, charts, groups, OLE, media
- built-in connectors (`p:cxnSp`) and `endArrowType` / `beginArrowType` / `lineHead` / `lineTail`
- the authoring connector object itself (it expands to a line and a triangle; those two shapes then round-trip)
- inherited or theme colors (only explicit `a:srgbClr`)
- ZIP compression, part order, and relationship ids
- shape ids (derived)
- animations, transitions, SmartArt
- custom `roundRect` adjustments
- PptxGenJS extras stripped on overlay: `a:rPr/@lang`, `@dirty`, `a:ea`, `a:cs`, `pitchFamily`, `charset`, `a:endParaRPr`, `a:buNone`, `p14:modId`, default cell margins, cell-border `headEnd`/`tailEnd`
- Excel / xlsx — same JSON ↔ OOXML approach later, not in this change

The compatibility shim can still write a legacy `p:cxnSp` with `a:stCxn` so older layout tests can reject connected shapes. That element is outside the spec.
