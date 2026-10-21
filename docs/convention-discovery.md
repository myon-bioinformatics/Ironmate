# Discover files and production entry points by convention

## Built-in screenshot selection and comparison

```sh
python -S browser_matrix.py app-results --page 'flutter-*' --env 'Linux-*' --env 'macOS-*' --list
python -S browser_matrix.py app-results --page 'flutter-*' --env '*-chromium-*' --out matrix
```

`find_shots(..., pages=('flutter-*',), environments=('Linux-*', 'macOS-*'))`
now accepts the same name conventions as the CLI. Repeated page rules are ORed,
as are environment rules; the two groups intersect. Matching is case-sensitive
and happens before duplicate detection, so excluded pages/environments do not
block a selected comparison. `--shot` retains its literal stem contract.

`--list` returns JSON `shots` with page/env/path without decoding PNGs or
creating output. Without `--list`, the same selected mapping feeds the existing
sheet/tile/HTML/JSON pipeline and requires `--out`; `--list --out` is rejected.
An empty selection lists an empty array; building an empty selection or using
an invalid root returns 2. Explicit reference selection still must refer to an
included environment. These commands use the repository alone.

Validation: **59 pytest tests** passed across browser_matrix, photo_grid and
image_compare. A standalone `python -S` smoke copied the existing
`docs/pixel-grid-preview.png` into two environment paths, selected Linux only,
and produced one cell plus sheet PNG, tile PNG, HTML and JSON. Selection/list
parity, excluded duplicates, case sensitivity, invalid rules and CLI mode errors
are covered. No browser launch or sibling checkout was needed for this pipeline.

## Optional source-symbol inspection

Find transformation, export and rendering entry points across the image/PPTX tools before changing an output path.

Use a sibling xprobe checkout with the convention-discovery API from
[xprobe PR #28](https://github.com/myon-bioinformatics/xprobe/pull/28).
For a fresh checkout, select this tested revision:

```sh
git clone https://github.com/myon-bioinformatics/xprobe.git ../xprobe
git -C ../xprobe checkout --detach 045b54dd35baf43758a484e458712ed5ad47ba24
```

The commands below run from this repository root. If xprobe is elsewhere,
replace `../xprobe/xprobe.py` with that checkout's path. They use Python's
standard library and work with `python -S`.

```sh
python -S ../xprobe/xprobe.py --symbols . --exclude-dir tests --exclude-dir vendor --symbol-pattern '*transform*' --symbol-pattern '*export*' --symbol-pattern '*render*' --brief
python -S ../xprobe/xprobe.py --discover --root . --include '*.yml' --include '*.toml' --include-hidden --brief
```

Repeat `--symbol-pattern` or `--include` to inject different naming conventions;
alternatives are ORed. `--symbol-kind class` (also `function`, `async_function`)
filters the selected definitions. For example, replace the name rules with
`--symbol-pattern '*Adapter' --symbol-pattern '*Reader' --symbol-kind class`
to look for class families. There is no required `tests/` path or `test_*` prefix.

Filename patterns match basenames or relative paths; symbol patterns match
short or lexical dotted names. Both are case-sensitive. Wildcard `*` spans
slashes/dots, so a parent-name match also selects nested definitions. Repeated
source definitions remain separate. This is a source inventory, not a count of
callable runtime members or an import/plugin registration mechanism.

JSON is the default for further processing; omit `--brief`. Exit status 0 means
complete matches, 1 means none, and 2 means errors, skipped inputs or truncated
output. Default bounds are 5,000 matched files, 1 MB per source and 1,000 symbols;
set `--max-files`, `--max-bytes`, `--max-matches` when needed. Hidden paths are
opt-in; dependency/build directories are excluded by default. Targets are parsed
without importing them. No `.gitignore` interpretation is implied.

## Observed trial

On 2026-10-21 at `68898410f540ee25187f278e4a81e0b8fc0ef191`, the first command parsed
55 files and found 11 definitions with no errors, skips or
truncation. Examples:

- `flow_export.py`: `render_flow`
- `flow_workspace.py`: `patch_and_render`
- `flow_workspace.py`: `render_workspace`
- `image_studio.py`: `render_scene`

The second command selected 17 YAML/TOML files at the same revision.
These are observations for that snapshot, not future expected counts. Full
query options, source SHA-256 values and results are recorded in xprobe's
[`docs/evidence/convention-discovery.json`](https://github.com/myon-bioinformatics/xprobe/blob/045b54dd35baf43758a484e458712ed5ad47ba24/docs/evidence/convention-discovery.json).

This is an explicit developer checkout, separate from existing vendored copies.
Existing vendor locks and CI/deployment configuration are unchanged; promoting
these APIs to an installed consumer requires its normal source-pin review.
