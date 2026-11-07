# Excel workbooks

CSV files become `.xlsx` workbooks. Ironmate detects the CSV encoding, then a small writer in `ironlib/xlsx_ooxml.py` (Python standard library only) writes the package and Ironmate sets the cell styles in the workbook XML. openpyxl and pandas are not used.

```sh
python xlsx_csv.py -o book.xlsx --border --autofilter 売上=costs.csv メモ=notes.csv
python xlsx_csv.py --spec book.json -o book.xlsx
```

Writing a workbook needs Python only: no Node.js and no npm package. Node.js 26 and `npm ci` are needed for the slide package (`pptxgenjs@4.0.1`) and for the xlsx tests, which compare the writer with `exceljs@4.4.0`. ExcelJS is a dev dependency that serves as the independent oracle and never writes a workbook for you; `npm ci --omit=dev` leaves it out. Ironmate does not install them. They are not in `vendor.lock.json`.

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

Text is written as inline strings. CR and CRLF become LF, and characters that XML 1.0 cannot hold (control characters other than tab and newline, DEL, U+FFFE, U+FFFF) are dropped, as ExcelJS already did for control characters. A literal `_x0041_` is written unchanged; OOXML defines `_xHHHH_` as an escape, so a reader may decode it. That gap predates the `min` writer and is not changed here.

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
the writer. At write time sheet qualifiers must match a sheet in this
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

Verification covers both input paths and both writers, inspecting the
resulting worksheet formulas and checking that literal URL cells introduce no
external relationships or image parts. Excel desktop rendering, calculation,
and network traffic have not been tested.

## How the writer is checked

There are two engines. `min` is the writer: `xlsx_ooxml.write_package` uses only the Python standard library to write the package parts, values, formulas, and sheet names. `exceljs` (`scripts/xlsx_io.mjs`, run with Node) writes and reads the same subset with ExcelJS and is the independent oracle for the tests. Ironmate then sets the autofilter and rewrites `xl/styles.xml` and each cell's `s` attribute for both, so borders, alignment, and number formats are set by Ironmate rather than by a library.

Tests, with no Excel and no Google account, run for both engines:

- Unzip the xlsx and require `autoFilter`, thin borders, `numFmt`, alignment, and both sheet names. A safe CSV formula such as `=B2*1.1` stays a formula in `<f>`. `=IMAGE(A2)` raises for both CSV input and explicit formula entries, including when A2 contains the URL.
- XML → JSON equals the spec for the written package.
- The `min` and ExcelJS writers give the same workbook content for the same spec: escaping, whitespace, line breaks, Unicode, dropped characters, numbers, formulas, and sheet names with markup characters. The stdlib reader and the ExcelJS reader both compare them.
- ExcelJS reads the package each writer wrote and matches the full spec, including borders and alignment. An empty bordered cell stays in the grid for that read.
- The bytes `min` writes are a deterministic ZIP of well-formed parts with a fixed timestamp, every text carries `xml:space="preserve"`, and values it cannot write (booleans, NaN, infinity, a book without sheets) raise.
- `min` needs neither Node.js nor npm packages: with no `node` on PATH and no `node_modules`, it still writes a workbook, and only the `exceljs` engine reports that ExcelJS is missing.

Outside the tests, only the stdlib reader (`xlsx_ooxml.read_spec`) reads these packages. LibreOffice and openpyxl opened a `min` package during development, but that check is not part of the suite.

## Not in this subset

Merged cells, images, drawings, and conditional formatting are rejected. Also untouched: charts, pivot tables, VBA, comments, defined names, column widths, fonts, fills, and the calc chain. ZIP part order is whatever the writer produced.
