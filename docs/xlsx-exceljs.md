# Excel workbooks

CSV files become `.xlsx` workbooks. Ironmate detects the CSV encoding, then ExcelJS or SheetJS writes the package and Ironmate sets the cell styles in the workbook XML. openpyxl and pandas are not used.

```sh
python xlsx_csv.py -o book.xlsx --border --autofilter 売上=costs.csv メモ=notes.csv
python xlsx_csv.py --spec book.json -o book.xlsx
```

Node.js 22 and `npm ci` are required (pinned `exceljs@4.4.0` and `xlsx@0.18.5`). The same lockfile also pins `pptxgenjs@4.0.1` for the slide package. Ironmate does not install them. They are not in `vendor.lock.json`.

`vendor/oci-cost-analysis.py` still imports pandas to print two columns from a CSV. That file is a locked vendor copy and is not part of this converter. PowerPoint tables still read CSV with the stdlib `csv` module.

## Encoding

`decode_csv_bytes` labels each file:

| Bytes | Result |
| --- | --- |
| UTF-8 BOM | `utf-8-sig`. A BOM whose remaining bytes are not UTF-8 raises; it is not re-read as Shift_JIS. |
| valid UTF-8 | `utf-8`, including the fullwidth tilde `～` stored as UTF-8 rather than as byte `8160` |
| Shift_JIS that CP932 decodes the same way, including halfwidth katakana (`0xA1`–`0xDF`) | `shift_jis` |
| CP932, including bytes Shift_JIS rejects (`①`, `髙`) | `cp932` |
| bytes the two codecs decode differently: `8160`, `8161`, `817C`, `8191`, `8192`, `81CA` | `cp932` → `～` `∥` `－` `￠` `￡` `￢`, the Windows mappings Excel writes |

Anything else raises. `--encoding utf-8|utf-8-sig|shift_jis|cp932` forces one codec. The xlsx stores Unicode, so Excel does not guess Shift_JIS when the file is opened. A file that is not valid UTF-8 is decoded entirely as Shift_JIS or CP932, so one invalid byte in a UTF-8 file can be misread.

## Workbook subset

A sheet has a name, a rectangular `rows` grid, and an optional `autofilter` ref (`A1:C10`). A cell with no value, formula, or border is omitted. Present fields:

| JSON | Workbook XML |
| --- | --- |
| `v` string | shared string, inline string, or `t="str"` |
| `v` number | `<v>` without `t`, or `t="n"`. Integers stay integers. More than 15 digits, or leading zeros (`001`), stay text. |
| `f` | `<f>` without a leading `=`. A CSV field that starts with `=` is a formula. A cached `<v>` is ignored on read. Calls are allowed only for `ABS`, `AND`, `AVERAGE`, `CONCAT`, `COUNT`, `COUNTA`, `COUNTIF`, `DATE`, `IF`, `IFERROR`, `INT`, `LEFT`, `LEN`, `LOWER`, `MAX`, `MID`, `MIN`, `MOD`, `NOT`, `OR`, `POWER`, `PRODUCT`, `RIGHT`, `ROUND`, `ROUNDDOWN`, `ROUNDUP`, `SQRT`, `SUBSTITUTE`, `SUM`, `SUMIF`, `TEXT`, `TRIM`, `UPPER`, and `VALUE`, plus arithmetic and cell or range refs (`B2*1.1`, `SUM(A1:A2)`). Any other call is rejected, including `IMAGE`, `HYPERLINK`, `WEBSERVICE`, `FILTERXML`, `RTD`, `CALL`, `REGISTER.ID`, and `INDIRECT`, in any case, with space before `(`, and when nested inside an allowed call. `|`, `[` `]`, and `://` outside a double-quoted string are rejected. |
| `z` | `xf/@numFmtId`. Builtins `0`, `0.00`, `#,##0`, `#,##0.00`, `0%`, `0.00%`, `0.00E+00`, `@` use their ECMA ids. Any other code is a `numFmt` from id 164. |
| `align` | `alignment/@horizontal` `left`, `center`, or `right` |
| `border: "thin"` | border id with `left`/`right`/`top`/`bottom` `style="thin"` and `color/@rgb="FF000000"` (罫線) |
| `autofilter` | worksheet `autoFilter/@ref` over the whole grid |

`--border` draws that thin border on every cell, including empty ones, so the grid lines stay continuous. A column with `"clear": true` opts out of the border, number format, and alignment. Column `numFmt` and `align` apply to values and formulas in that column.

Spec shape:

```json
{
  "borders": true,
  "autofilter": true,
  "sheets": [
    {
      "name": "売上",
      "csv": "costs.csv",
      "columns": [{}, {"numFmt": "#,##0", "align": "right"}, {"numFmt": "0.000", "align": "left"}]
    }
  ]
}
```

`formulas` can set a cell inside the grid: `{"cell": "C2", "formula": "B2*1.1"}`. `rows` can be used instead of `csv`.

## How the two libraries are checked

Both engines write values, formulas, sheet names, and autofilter. Ironmate then rewrites `xl/styles.xml` and each cell's `s` attribute so borders, alignment, and number formats do not depend on which library wrote the package. SheetJS community does not write those styles, and its reader does not return them.

Tests, with no Excel and no Google account:

- Unzip the xlsx and require `autoFilter`, `<f>`, thin borders, `numFmt`, alignment, and both sheet names.
- XML → JSON equals the spec for a package from either engine.
- ExcelJS write → SheetJS read matches values, formulas, number formats, sheet names, and autofilter.
- SheetJS write → ExcelJS read matches the full spec, including borders and alignment. An empty bordered cell stays in the grid for that read. SheetJS's own reader keeps the width and autofilter and returns that cell as empty, because it does not return borders.

## Not in this subset

Merged cells, images, drawings, and conditional formatting are rejected. Also untouched: charts, pivot tables, VBA, comments, defined names, column widths, fonts, fills, and the calc chain. ZIP part order is whatever the writer produced. A second style pass does not try to make the two engines' packages byte-identical.
