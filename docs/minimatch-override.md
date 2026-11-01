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
| `exceljs` → `unzipper@0.10.14` → `fstream@1.0.12` → `rimraf@2.7.1` | `rimraf` / `rimraf.sync` (throws TypeError) |

ExcelJS itself only uses `archiver` append/finalize and `unzipper.Parse`, so it never calls these.
`archiver@5.3.2`'s own `glob()` and `directory()` APIs use `readdir-glob@1.1.3`, not `archiver-utils`
`file.expand`, and `readdir-glob` works with minimatch 11 (checked: `directory()` + `glob()` produced entries).

Only these break: calling `archiver-utils` `file.expand` directly, and `rimraf` / `rimraf.sync`
(for example through unzipper `Extract` / fstream).
CI job `ExcelJS smoke` (`.github/workflows/exceljs-smoke.yml`, script `scripts/exceljs_smoke.cjs`) checks the following: the xlsx write/read
round-trip, the streaming WorkbookWriter/WorkbookReader, and CSV.

Remove the override once exceljs ships a release whose dependency tree resolves to minimatch >= 11.0.1.
