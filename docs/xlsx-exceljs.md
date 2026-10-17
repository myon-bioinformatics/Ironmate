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
| `f` | `<f>` with its leading `=` removed. CSV fields beginning with `=` and explicit `formulas` use the same formula subset below. Unsupported expressions raise instead of becoming executable formulas. A cached `<v>` is ignored on read. |
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

`rows` can be used instead of `csv`. An entry `"formulas": [{"cell": "C2", "formula": "B2*1.1"}]` sets that cell inside the grid; a leading `=` is optional for this explicit form.

## Formula subset

`xlsx_spec._check_formula` validates the complete expression before it reaches
ExcelJS or SheetJS. At write time sheet qualifiers must match a sheet in this
workbook (case-insensitively). `write_workbook` applies the same check to canonical specs,
so constructing a cell with `f` directly does not bypass validation. Expressions
are stored unchanged after stripping the optional leading `=` and outer spaces;
Ironmate does not calculate them.

Supported syntax:

- Decimal/scientific numbers, double-quoted strings (escaped quotes use `""`), and `TRUE` / `FALSE`.
- A1 cell references, including `$A$1`, and rectangular ranges such as `A1:B10`, within Excel's row/column bounds. Local sheet qualifiers such as `Sheet2!A1` and `'売上 メモ'!A1` are allowed; escaped apostrophes use `''`.
- Parentheses, unary `+` / `-`, postfix `%`, and binary `+ - * / ^ & = <> <= >= < >`. Commas separate function arguments only. Excel applies operator precedence.
- Function names are case-insensitive; spaces before `(` and nested allowed calls are supported. The complete allowlist is: `ABS`, `AND`, `AVERAGE`, `CONCAT`, `COUNT`, `COUNTA`, `COUNTIF`, `DATE`, `IF`, `IFERROR`, `INT`, `LEFT`, `LEN`, `LOWER`, `MAX`, `MID`, `MIN`, `MOD`, `NOT`, `OR`, `POWER`, `PRODUCT`, `RIGHT`, `ROUND`, `ROUNDDOWN`, `ROUNDUP`, `SQRT`, `SUBSTITUTE`, `SUM`, `SUMIF`, `TEXT`, `TRIM`, `UPPER`, `VALUE`.

Every other function is rejected, including `IMAGE`, `HYPERLINK`, `WEBSERVICE`,
`FILTERXML`, `RTD`, `CALL`, `REGISTER.ID`, `INDIRECT`, and prefixed calls such as
`_xlfn.IMAGE`. This also applies inside allowed calls, so `SUM(IMAGE(A2))` raises
without having to inspect the contents of A2. URL text and text resembling calls
inside double quotes are ordinary string literals; they do not execute.

External workbook references, paths, DDE, defined names, structured references,
3D ranges, array/union/intersection syntax, spill/implicit-intersection operators,
and locale-specific argument separators are outside the subset. Control
characters, unbalanced/unterminated expressions, more than 8192 characters, and
nesting deeper than 64 are rejected. Function arity, types,
and calculation results are left to Excel and may produce ordinary cell errors.

Verification covers both input paths and both writer engines, inspecting the
resulting worksheet formulas and checking that literal URL cells introduce no
external relationships or image parts. Excel desktop rendering, calculation,
and network traffic have not been tested.

## How the two libraries are checked

Both engines write values, formulas, sheet names, and autofilter. Ironmate then rewrites `xl/styles.xml` and each cell's `s` attribute so borders, alignment, and number formats do not depend on which library wrote the package. SheetJS community does not write those styles, and its reader does not return them.

Tests, with no Excel and no Google account:

- Unzip the xlsx and require `autoFilter`, thin borders, `numFmt`, alignment, and both sheet names. A safe CSV formula such as `=B2*1.1` stays a formula in `<f>`. `=IMAGE(A2)` raises for both CSV input and explicit formula entries, including when A2 contains the URL.
- XML → JSON equals the spec for a package from either engine.
- ExcelJS write → SheetJS read matches values, formulas, number formats, sheet names, and autofilter.
- SheetJS write → ExcelJS read matches the full spec, including borders and alignment. An empty bordered cell stays in the grid for that read. SheetJS's own reader keeps the width and autofilter and returns that cell as empty, because it does not return borders.

## Not in this subset

Merged cells, images, drawings, and conditional formatting are rejected. Also untouched: charts, pivot tables, VBA, comments, defined names, column widths, fonts, fills, and the calc chain. ZIP part order is whatever the writer produced. A second style pass does not try to make the two engines' packages byte-identical.
