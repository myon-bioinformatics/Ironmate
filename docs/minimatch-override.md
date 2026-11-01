# minimatch override (GHSA-g3hv-75wg-m249)

`package.json` overrides `minimatch` to `^11.0.1` (resolves to 11.0.3).
Upgrading the parent package cannot fix this: `exceljs@4.4.0` is the latest release, and even
`archiver@8` pulls in `readdir-glob@3`, which requires `minimatch@^10`.

## Known latent breakages (not on ExcelJS's current path)

`glob@7.2.3` does not work with minimatch 11 (`glob.sync` throws
`TypeError: Cannot read properties of undefined (reading 'charAt')`). Three callers reach it:

| Path | Broken API |
| --- | --- |
| `exceljs` → `archiver@5.3.2` → `archiver-utils@2.1.0` | `file.expand` (only when called directly) |
| `exceljs` → `archiver` → `zip-stream@4.1.1` → `archiver-utils@3.0.4` | same `file.expand` (only when called directly) |
| `exceljs` → `unzipper@0.10.14` → `fstream@1.0.12` → `rimraf@2.7.1` | `rimraf` / `rimraf.sync` only when the path contains `*` or `?` (`[` / `{` are fine); sync throws TypeError, async crashes the process |

ExcelJS itself only uses `archiver` append/finalize and `unzipper.Parse`, so it never calls these.
`archiver@5.3.2`'s own `glob()` and `directory()` APIs use `readdir-glob@1.1.3`, not `archiver-utils`
`file.expand`, and `readdir-glob` works with minimatch 11 (checked: `directory()` + `glob()` produced entries).

Only these break: calling `archiver-utils` `file.expand` directly, and `rimraf` / `rimraf.sync` with a path that contains `*` or `?`
(for example through unzipper `Extract` / fstream).
CI job `ExcelJS smoke` (`.github/workflows/exceljs-smoke.yml`, script `scripts/exceljs_smoke.cjs`) checks the following: the xlsx write/read
round-trip, the streaming WorkbookWriter/WorkbookReader, and CSV.

Remove the override once exceljs ships a release whose dependency tree resolves to minimatch >= 11.0.1.

rimraf with a path that has no `*` / `?` (including `[` or `{`), or with `{ glob: false }`, works.
Checked locally:
- `rimraf.sync('/tmp/rq/a[b]')` and `rimraf.sync('/tmp/rq/{x,y}')` succeed. `rimraf.sync(p, { glob: false })` and async `rimraf(p)` on a plain path also succeed.
- `rimraf.sync('/tmp/rq/a?')` and `rimraf.sync('/tmp/rq/*')` throw `TypeError: Cannot read properties of undefined (reading 'charAt')`.
- Async `rimraf('/tmp/rq/*', cb)` never calls `cb` with the error. The TypeError is thrown from inside glob's readdir callback,
  so it is an uncaught exception that crashes the whole process (exit code 1). `try`/`catch` around the call does not catch it.
