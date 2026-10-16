# Excel workbooks

Ironmate does not generate or edit `.xlsx` files. This note is the path to use when a concrete workbook need appears. It adds no package, CLI, sample file, or test.

The PowerPoint package split in draft PR [#104](https://github.com/myon-bioinformatics/Ironmate/pull/104) is the model: a pinned Node library writes the OOXML package, and Ironmate owns any JSON ↔ XML mapping that has to be checked without a desktop app.

## What is already here

A search of requirements, workflows, `vendor.lock.json`, Python sources, and docs found no `openpyxl`, `xlsxwriter`, `xlrd`, ExcelJS, or SheetJS.

`vendor/oci-cost-analysis.py` is a locked copy of `myon-bioinformatics/oci-cost-analysis`. It imports pandas, calls `pd.read_csv`, and prints `Date (UTC)` and `Total (USD)`. It never opens a workbook. Leave it on the vendor lock.

Tables that Ironmate does write are PowerPoint tables. CSV and Markdown supply the rows, and CSV parsing is the stdlib `csv` module in `pptx_pipeline.py`. That path stays a CSV-to-slide-table path.

`docs/pixel-grid-prototype.md` already records the policy: skip openpyxl, meet table needs with CSV/TSV or an existing service, and add Excel-only create or edit only after a specific demand exists.

## When a workbook caller exists

1. Keep rows as rows. CSV read and write stay in the stdlib `csv` module. ExcelJS 4.4.0 (the stable release on 2026-10-16; recheck the registry on the day it is added) can also read and write CSV. SheetJS (`xlsx`, 0.18.5 on the same date) is the fallback for a file that is not rectangular CSV, such as legacy `.xls`, and only when a caller has that file and neither the stdlib nor ExcelJS can read it.
2. Pin ExcelJS in `package.json` and `package-lock.json` at that day's exact stable version. Ignore `node_modules/`. Keep the package out of `vendor.lock.json`. Ironmate does not auto-install it. Add `npm ci` only to the workflow job that runs the new tests. Leave workflow `permissions` unchanged.
3. ExcelJS performs create and edit: `Workbook`, worksheets, cell values, and only the number formats and fills that caller needs, then `writeBuffer` or `xlsx.writeFile`. An edit reads with `workbook.xlsx.readFile` and writes a new file.
4. When that subset has to be checked without Excel, document each JSON field against the worksheet XML (shared strings, cell types, styles, column widths) and add round-trip tests: JSON → worksheet XML → JSON equals the original, and XML → JSON → XML matches after canonicalization. List what the reader will not preserve in the same document: charts, pivot tables, VBA, drawings, comments, defined names, conditional formatting outside the subset, the calc chain, and ZIP part order. The mapping stays in Ironmate. The first caller sets the subset.
5. Keep the existing tests. New tests cover the operations that caller uses. There is no Python workbook behavior to port today.

Until that caller exists, the tree stays without an `exceljs` or `xlsx` dependency, without a workflow change, and without a sample workbook.
