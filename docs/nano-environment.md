# Opt-in PPTX nano environment

This recipe prepares the real PptxGenJS/OOXML rendering slice without ExcelJS,
Marp, browsers, LibreOffice/UNO or Docker. It is **not** the Markdown-to-Marp
pipeline, all Ironmate features, visual/Office validation, or the full test suite.
The recipe itself changes neither this repository's dependencies nor existing
tests or CI. The Python side is covered separately in
[Optional Python feature groups](#optional-python-feature-groups).

## Fixed source and current-main boundary

The common helper is pinned to the [merged parent source](https://github.com/myon-bioinformatics/myon-bioinformatics/blob/3128b4019b9949a6ccc80c686cd84c93f04af119/tools/nano_node.py).
The runnable source is deliberately the measured Ironmate snapshot
[`af846ee7b1fd440b8379e2a682dfc7d40365b30e`](https://github.com/myon-bioinformatics/Ironmate/tree/af846ee7b1fd440b8379e2a682dfc7d40365b30e),
not an implicit current checkout. Its 198 non-root lock records project to 18;
all retained records, versions, integrity values and paths remain unchanged.
The image-size 2.0.4 and uuid 14.0.3 overrides are preserved.

A read-only comparison with current
[`91622da39bffd2af636af60ee193e10a00dab09a`](https://github.com/myon-bioinformatics/Ironmate/tree/91622da39bffd2af636af60ee193e10a00dab09a)
found all nine non-package source/test/license blobs and all 18 retained PPTX
records unchanged. Current main adds a minimatch `^11.0.1` override and unrelated
lock changes (196 full records, root engine metadata and lock name). The current
package files therefore **fail the historical helper's checks by design**.
This recipe does not weaken that guard, remove the override, refresh a helper
pin, or claim current-main installation measurements. A future current-snapshot
contract needs separate review; use the exact historical source below meanwhile.

## 1. Verify and prepare outside the checkout (no installation)

Use an existing Python 3.12+, Node 26+ and npm 11.9.0. Nothing here installs or
upgrades those tools. Run the shell blocks in order in the same POSIX shell.
Choose a TMPDIR outside the checkout. Source download needs GitHub access; lock-only preparation is offline. The
helper is downloaded at the merged parent commit, SHA-256 checked **before
execution**, and then all 11 required child files are downloaded at their immutable
commit and checked against its Git-blob allowlist. No clone, vendor enrollment,
branch switch or write inside this checkout is required.

```sh
set -eu
WORK=$(mktemp -d "${TMPDIR:-/tmp}/nano-ironmate-XXXXXXXX")
WORK=$(python3 -I -B -S -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$WORK")
python3 -I -B -S - "$WORK" <<'PY'
import hashlib, importlib.util, sys, urllib.request
from pathlib import Path
work = Path(sys.argv[1])
parent = '3128b4019b9949a6ccc80c686cd84c93f04af119'
child = 'af846ee7b1fd440b8379e2a682dfc7d40365b30e'
def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('download exceeds the bounded input size')
    return data
data = fetch(f'https://raw.githubusercontent.com/myon-bioinformatics/myon-bioinformatics/{parent}/tools/nano_node.py')
if hashlib.sha256(data).hexdigest() != '9e042eb70a80c75f99aafb1956386b3f5e27ee795ec501d3bcece3a369d09777':
    raise ValueError('parent helper SHA-256 mismatch')
tool = work / 'nano_node.py'
tool.write_bytes(data)
spec = importlib.util.spec_from_file_location('nano_node', tool)
nano = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nano)
source = work / 'source'
for name, expected in nano.SOURCE_BLOBS.items():
    data = fetch(f'https://raw.githubusercontent.com/myon-bioinformatics/Ironmate/{child}/{name}')
    if nano.git_blob(data) != expected:
        raise ValueError(f'child Git-blob mismatch: {name}')
    path = source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
nano.read_snapshot(source, blobs=nano.SOURCE_BLOBS)
PY
python3 -I -B -S "$WORK/nano_node.py" --feature ironmate-pptx \
  --source "$WORK/source" --output-dir "$WORK/prepared" > "$WORK/prepared-path.txt"
PREPARED=$(cat "$WORK/prepared-path.txt")
PROJECT="$PREPARED/Ironmate"
```

Every required source, fixture and license file is staged; the helper records
source identities and projected manifest/lock hashes in `$PREPARED/receipt.json`.
Its source check concerns exact file bytes, not checkout HEAD or ancestry.
Official npm uses `--package-lock-only --offline --ignore-scripts` with empty
configuration and a private cache. Unknown graphs or changed retained records
fail closed. If download or preparation fails, stop and inspect the error;
do not bypass a hash check, weaken the guard, or use an unpinned fallback.

## 2. Optional explicit installation

This separate step downloads the locked packages from the official npm registry.
It is not run by preparation or by importing a module. Review it before running.
Fresh HOME/config/tmp/cache and disabled lifecycle scripts avoid using a broad
developer environment; downloads still require network access. First recheck the
helper and prepared manifest/lock digests to catch accidental intervening edits.

```sh
python3 -I -B -S - "$WORK" "$PREPARED" <<'PY'
import hashlib, importlib.util, json, sys
from pathlib import Path
work, prepared = map(Path, sys.argv[1:])
if hashlib.sha256((work / 'nano_node.py').read_bytes()).hexdigest() != '9e042eb70a80c75f99aafb1956386b3f5e27ee795ec501d3bcece3a369d09777':
    raise ValueError('helper changed after preparation')
spec = importlib.util.spec_from_file_location('nano_node', work / 'nano_node.py')
nano = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nano)
snapshot = nano.read_snapshot(work / 'source', blobs=nano.SOURCE_BLOBS)
original = json.loads(snapshot['package-lock.json'])
manifest = json.loads(snapshot['package.json'])
nano.validate_original(manifest, original, feature='ironmate-pptx')
project = prepared / 'Ironmate'
nano.validate_projection(original, json.loads((project / 'package-lock.json').read_bytes()),
                         feature='ironmate-pptx')
manifest['dependencies'] = {'pptxgenjs': '4.0.1'}
if json.loads((project / 'package.json').read_bytes()) != manifest:
    raise ValueError('projected manifest differs from the fixed contract')
for name, data in snapshot.items():
    if name not in ('package.json', 'package-lock.json') and (project / name).read_bytes() != data:
        raise ValueError(f'prepared source changed: {name}')
receipt = json.loads((prepared / 'receipt.json').read_bytes())
if receipt['feature'] != 'ironmate-pptx' or receipt['source_commit'] != 'af846ee7b1fd440b8379e2a682dfc7d40365b30e':
    raise ValueError('wrong feature receipt')
for name, field in [('package.json', 'projected_manifest_sha256'),
                    ('package-lock.json', 'projected_lock_sha256')]:
    if hashlib.sha256((prepared / 'Ironmate' / name).read_bytes()).hexdigest() != receipt[field]:
        raise ValueError(f'prepared input changed: {name}')
PY
mkdir -p "$WORK/install-home" "$WORK/install-config" "$WORK/install-tmp" "$WORK/install-cache"
: > "$WORK/user.npmrc"
: > "$WORK/global.npmrc"
(cd "$PROJECT" && env -i PATH="$PATH" HOME="$WORK/install-home" \
  XDG_CONFIG_HOME="$WORK/install-config" TMPDIR="$WORK/install-tmp" \
  PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
  npm ci --ignore-scripts --no-audit --no-fund --no-update-notifier \
  --registry https://registry.npmjs.org/ --fetch-retries=0 --fetch-timeout=30000 \
  --userconfig "$WORK/user.npmrc" --globalconfig "$WORK/global.npmrc" \
  --cache "$WORK/install-cache")
```

Stop on installation failure; keep the partial work directory for diagnosis.
This does not install Docker, browsers, Office, Python test tools or model data.
Do not run `npm install` or add packages to this projected environment to make
unrelated tests pass; use the unchanged full environment for those tests.

## 3. Run the real render/read-back path

This synthetic sample uses the existing source API and standard-library Python;
it produces an editable PPTX and checks its canonical JSON round trip. It does
not open the deck in a browser or Office. Each invocation gets a private output
and temporary directory; share the installed dependencies read-only, not outputs.

```sh
JOB=$(mktemp -d "$WORK/job-XXXXXXXX")
mkdir -p "$JOB/home" "$JOB/tmp" "$JOB/cache"
(cd "$PROJECT" && env -i PATH="$PATH" HOME="$JOB/home" TMPDIR="$JOB/tmp" \
  XDG_CACHE_HOME="$JOB/cache" python3 -B -S - "$JOB/example.pptx" <<'PY'
import sys
from pathlib import Path
from pptx_mapping import canonical_spec
from pptx_render import read_package_spec, write_new_package
from pptx_spec import sample_deck_spec
expected = canonical_spec(sample_deck_spec())
output = write_new_package(Path(sys.argv[1]), expected)
if canonical_spec(read_package_spec(output)) != expected:
    raise ValueError('PPTX canonical round trip differs')
print(output)
PY
)
```

For parallel jobs, allocate a new `JOB` for every invocation and never share the
output filename or TMPDIR. The prior comparison used one/two workers; it does
not establish an optimal worker count or general rendering speed improvement.

## Evidence and preserved tests

The [bounded historical results](https://github.com/myon-bioinformatics/myon-bioinformatics/blob/3128b4019b9949a6ccc80c686cd84c93f04af119/docs/nano-feature-environments.md)
include all installation samples, output checks and their limitations. The
[historical reproducer](https://github.com/myon-bioinformatics/myon-bioinformatics/blob/3128b4019b9949a6ccc80c686cd84c93f04af119/docs/evidence/nano-features/2026-11-01-ironmate/REPRODUCE.md)
pins its **older measured parent helper** for exact benchmark reproduction;
do not substitute this adoption helper and label it as that measured binary.
The original package-round-trip and image-size tests remain unchanged and are
included in the staged snapshot. Running them requires a separate pytest tool
environment as documented there; this runtime install does not provide pytest.
All other tests and the full browser/UNO/Marp lanes remain in their original
environments. Neither package counts nor installation bytes are Docker-image
sizes or build-time measurements. This documentation update runs no benchmark
and changes no workflow, Pages configuration, source/vendor registration or CI
permission. README/docs-only changes match no current Ironmate push/PR workflow;
Draft status is not what suppresses jobs.

## Optional Python feature groups

The Python test tools and the optional image and preview features are separate
uv dependency groups in `pyproject.toml`. `dev` includes all three groups, so
the default `uv run --locked` (CI) installs exactly the package set it installed
before: `uv export --locked` is byte-identical before and after, and no locked
version changed. Every test stays in its original lane; none is removed or
skipped by this split.

| Group | Packages | What uses them |
|---|---|---|
| `test` | pytest, PyYAML | The test runner. PyYAML is used only by the vendor and CI tests. |
| `codecs` | NumPy, Pillow | The optional NumPy backend of `grid_tools.py` and `svg_raster.py` (the standard-library backend stays the fallback), the optional Pillow decoders for JPEG, WebP and PNG variants in `photo_grid.py`, and the oracle for the `pillow_min` parity tests. |
| `preview` | Playwright, pypdf | The `pptx_preview.py` review lane and `scripts/cdn_pypdf_pages.py`. Playwright's browsers are downloaded separately and are not part of this group. |

To work on one feature, install it with the test tools in its own environment.
The shared `dev` environment is unchanged:

```sh
uv sync --locked --no-install-project --only-group test --only-group codecs
uv sync --locked --no-install-project --only-group test --only-group preview
```

Run a feature's tests only in an environment that has its group: tests of an
uninstalled group are not expected to pass, and the full suite needs `dev`.
The split selects existing locked packages. It does not replace a library, add
an implementation, or change Docker or CI. Package counts and sizes depend on
the platform and Python version, and are not Docker-image sizes or build times.

## Optional npm: runtime without the ExcelJS oracle

`xlsx_ooxml.write_package` writes xlsx with the Python standard library, so
`python xlsx_csv.py` needs neither Node.js nor npm packages. ExcelJS is a dev
dependency: the independent oracle that the xlsx tests compare against. The
plain `npm ci` (CI) still installs it and every test still runs. To install only
what the slide renderer needs:

```sh
npm ci --omit=dev --ignore-scripts
```

That installs the locked PptxGenJS closure (18 records) and not ExcelJS. The PPTX
renderer works in that tree; the tests that need the ExcelJS oracle do not, and
report that ExcelJS is missing. This uses the unchanged lock and npm's own `dev`
flags, not the parent's lock projection (which rejects `dev` markers), so the
pinned historical recipe above is unaffected.

## Optional: install with Bun, run with Node

Bun can install the same locked tree and Node.js 26 still runs everything. The
lock stays `package-lock.json`; there is no `bun.lock` to keep:

```sh
bun install --frozen-lockfile --ignore-scripts          # dev included, like npm ci
bun install --frozen-lockfile --ignore-scripts --production   # like npm ci --omit=dev
```

`--frozen-lockfile` reads `package-lock.json`, does not write it, and fails when
`package.json` has drifted from it, as `npm ci` does. The `exceljs-smoke-bun` job
in `.github/workflows/exceljs-smoke.yml` runs this install and the smoke under
Node 26 and under Bun on every change to the lock, and logs the cost of Bun.

Measured on one Linux x64 machine (Node 26.13.0, Bun 1.4.4, npm 10.9.9), the
locked tree of 196 records with `dev` included; "warm" means the package cache is
filled and `node_modules` was deleted (median of 3 runs; cold is 2 runs):

| Install | cold cache | warm cache | `node_modules` | cache + `node_modules` |
| --- | --- | --- | --- | --- |
| `npm ci` | 4.1 s | 3.3 s | 59 MiB | 71 MiB |
| `bun install --frozen-lockfile` | 5.2 s | 0.06 s | 58 MiB (hardlinks) | 65 MiB |
| `npm ci --omit=dev` | n/a | 0.59 s | 8.0 MiB | n/a |
| `bun install --production` | n/a | 0.01 s | 8.0 MiB | n/a |

Bun's `--linker isolated` with `BUN_INSTALL_GLOBAL_STORE=1` keeps one copy of each
package in the cache and links it: a warm install took 0.01 s and `node_modules`
was 0.9 MiB of symlinks (cache 64 MiB). It is not the default and is not used in
CI. These are timings from one machine and network, not CI or Docker numbers.

What was checked, and what differs:

- Same packages: 180 distinct `name@version` in both trees, every dependency
  resolves to the same `name@version` as under npm, and all 180 `integrity`
  values in `bun.lock` (generated once from the npm lock) equal the npm lock's.
- Same behavior: the 163 tests in `test_xlsx_csv.py`, `test_pptxgenjs_image.py` and
  `test_pptx_mapping.py`, the ExcelJS smoke and the 41 `node --test` tests (40
  pass, 1 skipped, as on npm's tree) pass under Node 26 on the Bun-installed tree.
  The smoke also passes under Bun (`bun scripts/exceljs_smoke.cjs`). A PPTX built
  from npm's tree with Node, from Bun's tree with Node and from Bun's tree with Bun
  has the same 40 package members; only the creation time in `docProps/core.xml` differs.
- Different layout: Bun hoists differently, so 4 of the 18 paths the parent's pinned
  recipe expects sit elsewhere (for example `safe-buffer` at the top level). Module
  resolution is unaffected; a check that compares installed paths with npm's must
  keep using npm, as the parent's lock projection does.
- Bun is not a drop-in `node` on `PATH`: with Bun 1.4.4 behind a symlink named
  `node`, `node -e CODE a b` loses its first extra argument (`process.argv.slice(1)`
  is `[b]`, Node gives `[a, b]`). `bun -e` itself and scripts run from a file give
  the same `process.argv` as Node. `test_pptxgenjs_image.py` runs `node -e` with
  arguments, so it is the one of the 163 tests that fails (162 pass) with such a
  symlink. Keep Node as `node`, and call `bun` by its own name.

Bun is worth it where its cache persists. Fetching Bun into an empty environment
cost 11 s through npm on that machine (2.0 s on a GitHub-hosted runner) and a
102 MiB binary (Node's is 143 MiB). On the runner, `exceljs-smoke-bun` spent 2.0 s
getting Bun plus 0.35 s on a cold `bun install`, against about 1 s for `npm ci`, so
a disposable environment that starts from nothing keeps npm. For a Docker-free setup, `ldd` shows Bun linking only `libc6`
(`libc`, `libm`, `libdl`, `libpthread`; highest `GLIBC` symbol version 2.17, not
run on an older glibc), while Node 26 links `libatomic1`, `libc6`, `libgcc-s1` and
`libstdc++6`. `ldd` does not show libraries opened at run time.

## Cache first: seed once, then fan out

`uv sync` already works the way Bun does: wheels are unpacked once into uv's cache
and each environment hardlinks them (`numpy/__init__.py` has 2 links in a uv
environment and 1 in a pip one). With the cache filled, installing is a linking step,
and an environment that is already in sync is skipped in about 0.03 s. Measured on
the same 2-core machine as above (Python 3.13.18, uv 0.11.32, pip 26.2.1; `pip` used
the requirements exported from `uv.lock`, so the versions are the same):

| `dev` group | cold cache | warm cache | already installed | environment + cache |
| --- | --- | --- | --- | --- |
| `uv sync --frozen --no-install-project --only-group dev` | 4.4 s | 0.04 s | 0.03 s | 229 MiB |
| `pip install -r` (exported from `uv.lock`) | 12.7 s | 5.6 s | 0.43 s | 315 MiB |
| `uv sync ... --only-group test --only-group codecs` | - | 0.06 s | - | 87 MiB |

Ten environments installed at the same time from one shared cache (every
environment imported its packages afterwards, and the existing tests pass in both
the uv and the pip environment: 165 passed in
`test_xlsx_csv.py`, `test_pptxgenjs_image.py`, `test_pptx_mapping.py` and `test_apng_input.py`):

| 10 at once | cache warm | cache empty (all start together) |
| --- | --- | --- |
| uv, `dev` | 0.71 s, 308 MiB in total | 292 s, cache grew to 2.2 GiB (one copy is 228 MiB) |
| pip, `dev` | 26.1 s, 2.5 GiB in total | - |
| Bun | 0.44 s, 85 MiB in total | 155 s, cache 59 MiB |
| npm ci | 21.5 s, 604 MiB in total | 22.5 s |

The rule that follows: fill the cache with one install first, then start the
parallel jobs. When ten installs start on an empty cache they do not corrupt each
other (all succeeded), but uv unpacked every wheel ten times into its cache and both
uv and Bun were much slower than a single install. Whether that is contention or
this machine's network was not separated.

### On CI

The same idea applies on CI only where a cache or a built environment is carried
between jobs. The `test` job of `mcp-tests.yml` (Python 3.15, the `dev` group, 13
packages) was measured on a GitHub-hosted runner with the uv cache off and on. It
now has its own `uv sync --locked` step, so the install time shows in the log.
Seconds, from the `setup-uv` step (which restores the cache), the sync step and the
post step (which saves it):

| uv cache | run | `setup-uv` | `uv sync` | save | whole job |
| --- | --- | --- | --- | --- | --- |
| off | first | 2 | 10 | 0 | 213 |
| off | re-run | 2 | 9 | 0 | 204 |
| on, not pruned (74 MB) | empty | 2 | 10 | 2 | 204 |
| on, not pruned | restored | 4 | 0 | 0 | 208 |
| on, pruned (1.3 MB) | empty | 3 | 10 | 1 | 215 |
| on, pruned | restored | 3 | 1 | 0 | 200 |

A restored cache turns about 11 s of setup and install into 4 s, a saving of about
7 s. The whole job differs by several seconds between identical runs (204 s and 213 s
with the cache off), so that saving does not show in the job total. The install is
slow for one reason: PyYAML 6.0.3 has no wheel for Python 3.15, so uv builds it from
source (`Building pyyaml==6.0.3`); uv's prepare phase takes 9.7 s with an empty cache
and 0.8 s once the built wheel is restored, while numpy, Pillow and Playwright (46 MiB)
download in under a second. That is why the pruned cache, which keeps only built
wheels, saves as much as the unpruned one at 1/50 of the size. When a PyYAML release
ships a Python 3.15 wheel there is little left for the cache to save in this job.

The jobs that install through uv (`test` and `marp-integration` in `mcp-tests.yml`,
`chromium-review` in `pptx-review.yml`, `audit` in `vendor-catalog-audit.yml`)
therefore use `enable-cache: true` and `prune-cache: true`, and set `save-cache` to
true only on `main`: pull requests restore the cache and never write it. The runs in
the table wrote the cache from the pull request itself, the only way to see a
restored run before the first merge. After the merge, a pull request restored the
cache that `main` had saved: the key matched exactly (`Cache hit`, 1.3 MB), the log
said `save-cache is false. Skipping save cache step.`, and `uv sync --locked` took 1 s
in `test`, `marp-integration` and `audit` and 2 s in `chromium-review`. `audit` as a
whole went from 25-27 s to 13 s; the longer jobs vary by more than the saving.

Jobs that use `setup-uv` only to provide Python (`cdn-pypdf.yml`, `node-tests.yml`,
`studio-pages.yml`, `verify_3way_survey.yml` and `studio-clipboard`) keep
`enable-cache: false`: they install nothing through uv, so there is nothing to
cache, and `setup-uv`'s `ignore-nothing-to-cache` defaults to false.
