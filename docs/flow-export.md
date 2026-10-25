# Common JSON flow export

`flow_export.py` connects the **web-ui** flow contract to Ironmate's existing
`mermaid_svg.render_mermaid` and Image Studio Chrome rasterizer. It does not
implement another graph model/layout engine. `vendor/web_ui_flow.py`, its LICENSE
and `examples/flow.json` are byte-identical locked upstream artifacts; update them
through the parent vendor registry and lock, never edit the copies.

The bounded merge-style JSON schema (1–8 sources and 1–8 steps, labels/notes only)
is documented at https://github.com/myon-bioinformatics/web-ui/blob/main/docs/flow-diagrams.md.
This is not a general graph editor or an editable Studio scene importer.

| Format | Returned bytes | Local tools |
| --- | --- | --- |
| `mermaid` | UTF-8 fenced Mermaid Markdown | Python 3.10+ standard library |
| `svg` | SVG with explicit pixel size and intrinsic viewBox | Python, installed `mmdc` and its browser |
| `png` | PNG | Above plus Node.js 22+ and Chrome/Chromium |
| `base64` | Standard padded ASCII Base64 of PNG | Same as PNG |
| `data-uri` | `data:image/png;base64,` followed by that Base64 | Same as PNG |

Nothing is installed or fetched automatically. Missing renderers fail with a
nonzero CLI exit / Python RuntimeError / Node Error, without writing a replacement
file or substituting a different format. The optional browser CI lane already
pins Mermaid CLI 12.0.0. Runtime npm dependencies are unchanged.

```sh
python -S flow_export.py examples/flow.json --format mermaid -o flow.md
python -S flow_export.py examples/flow.json --format svg --mmdc /path/to/mmdc -o flow.svg
python -S flow_export.py examples/flow.json --format png --mmdc /path/to/mmdc --chrome /path/to/chrome -o flow.png
python -S flow_export.py examples/flow.json --format base64 --mmdc /path/to/mmdc -o flow.base64.txt
python -S flow_export.py examples/flow.json --format data-uri --mmdc /path/to/mmdc -o flow.data-uri.txt
node flow_export.cjs examples/flow.json --format mermaid -o flow.md
```

Omit the input path to read stdin. Output goes to stdout unless `-o` is supplied.
Existing files are protected; `--force` atomically replaces the destination.
`--background '#FFFFFF'` selects an opaque canvas; default is transparent.
`--scale 2` doubles the intrinsic dimensions (rounded upward to whole pixels).
Both SVG and raster output are bounded to each side ≤8192px and ≤16,777,216 pixels;
PNG is at most 32MiB. UTF-8 JSON input is at most 256KiB, including API input.
Labels are validated and escaped upstream; Mermaid renders with strict security
and SVG text labels, so exported SVG has no XHTML foreignObject dependency.

The SVG renderer uses local mmdc/Puppeteer browser discovery. Set
`PUPPETEER_EXECUTABLE_PATH` for mmdc when needed; `--chrome` controls the **PNG**
rasterizer. `--puppeteer-config path.json` passes an explicit local mmdc browser
configuration (for example an executable path). No sandbox flag is added by this
adapter. Containers that require it can explicitly configure mmdc's browser and
set the existing `IRONMATE_CHROME_NO_SANDBOX=1` option for PNG rasterization.

```python
import json
from pathlib import Path
from flow_export import render_flow
spec = json.loads(Path('examples/flow.json').read_text(encoding='utf-8'))
Path('flow.png').write_bytes(render_flow(spec, 'png', mmdc='/path/to/mmdc',
                                        chrome='/path/to/chrome'))
```

```js
const {renderFlow} = require('./flow_export.cjs');
const spec = require('./examples/flow.json');
const png = renderFlow(spec, {format: 'png', mmdc: '/path/to/mmdc',
                              chrome: '/path/to/chrome', python: 'python3'});
require('node:fs').writeFileSync('flow.png', png);
```

The Node API is a synchronous, bounded Buffer-returning **Python wrapper**, not a
second implementation. It delegates process launch to the vendored parent
`vendor/py_launch.cjs` (shared with `flow_workspace.cjs` and `image_digest.cjs`).

**Interpreter resolution (Node wrappers):** each call runs a short Python 3.9+
version probe before spawning the tool. The launcher is pinned to parent commit
`1116d5c4f55d25af4d21cfe9b3c88f49d3a476fa`. The probe honors the same
`noSite` / `isolated` flags as the tool: ambient `sitecustomize` cannot run during
discovery when either flag is enabled. Node remains 24 or later, with no upper bound.
The shared launcher's asynchronous `main` also forwards every SIGINT / SIGTERM
while its child is alive,
including SIGTERM after an ignored SIGINT. Wrapper behavior is unchanged.
Order when the API `python` option is
unset: `IRONMATE_PYTHON`, then `PYTHON`, then `python3`, `python`, and on
Windows `py -3`. An explicit API `python` path or a set `IRONMATE_PYTHON` does
not fall back to later candidates. Windows `.cmd`/`.bat` shims are rejected.
Launch failures surface as `flow Python process failed: …` (library API) or exit
code `2` (CLI). Override the interpreter with `IRONMATE_PYTHON` or the API
`python` option.

All text formats are also Buffers; use `.toString('utf8')` to read them.
PNG/Base64/data URI can be imported through the existing Studio file/Base64 input.
Rendering uses CPU browser drawing, with fonts supplied by the host; identical
pixels across different operating systems/fonts/browser versions are not promised.

## Reproducible verification

```sh
python -m pytest -q tests/test_flow_export.py
IRONMATE_RUN_FLOW_INTEGRATION=1 IRONMATE_MMDC_BIN=node_modules/.bin/mmdc \
  IRONMATE_CHROME=/path/to/chrome python -m pytest -q tests/test_flow_integration.py
IRONMATE_CHROME=/path/to/chrome node tests/flow_export_browser.cjs
```

The integration fixture writes all five formats, white/transparent and 2× PNG,
source/PNG hashes and a report to `build/test-results/flow-export/`. It checks
Python/Node PNG byte identity and Base64/data URI decoding identity. The browser
check opens the fixed sample, compares exact PNG/transport pixels through Canvas and records the
SVG-to-PNG white-composited mean error (tolerance <2 on a 0–255 scale), verifies escaping without remote requests or script execution,
and saves `sample.html` and `browser.png`. The existing browser CI lane preserves
these artifacts and installs/identifies Noto CJK for the Japanese fixture; fast
unit tests do not require an external renderer. Inspect the preserved screenshot
as well as numeric parity: identical missing-glyph boxes are not valid Japanese
rendering.

## Retained JSON workspace: import → patch → regenerate

`flow_workspace.py` / `flow_workspace.cjs` add a reproducible **structural JSON**
editing path. This is separate from the Image Studio pixel canvas: editing an
imported PNG there does not update flow labels, and a PNG cannot recover the source
JSON. A visual Studio scene importer is still outside this path.

The `ironmate-flow/1` workspace stores `original_json` (the exact input UTF-8 text,
including whitespace and omitted defaults) and `spec` (the validated, current
web-ui JSON). Saving and loading preserves both. Original text is never patched;
`original` extracts its bytes, while `spec` extracts the current JSON. Importing a
new source creates a new workspace. Workspace files are bounded to 2MiB, original
JSON to 256KiB, and patch documents including the working spec to 320KiB.

Editing uses web-ui's byte-identical `tool/flow_patch.py` in an isolated Python
process, with its required `tool/flow_diagram.py` kept in upstream relative layout
under `vendor/web_ui/`. The Node workspace API wraps this same Python path. The
locked native Node patcher and validator are also exercised for cross-language
contract comparison. The existing flat renderer copy remains for compatibility;
both validators, both patchers, the sample and MIT LICENSE are pinned together to
merged web-ui #71 (including #70), `95dcfc6f3fa764249566bf2f9df90dcead7c64db`.
Do not edit these vendor bytes. Parent PR #112 registers the four additional
runtime sources; the child lock records commit, Git blob and SHA-256 for each.

```sh
python -S flow_workspace.py import examples/flow.json -o work.flow.json
# edits.json: [{"path":"/steps/0/title","value":"Reviewed"}]
python -S flow_workspace.py patch work.flow.json edits.json -o edited.flow.json
python -S flow_workspace.py render edited.flow.json --format svg -o edited.svg
python -S flow_workspace.py render edited.flow.json --format png -o edited.png
python -S flow_workspace.py render edited.flow.json --format base64 -o edited.base64.txt
python -S flow_workspace.py original edited.flow.json -o original.json
python -S flow_workspace.py spec edited.flow.json -o edited.json
# Same CLI, including renderer options:
node flow_workspace.cjs render edited.flow.json --format mermaid -o edited.md
```

Supported operations are exactly web-ui's array of `{path,value}` entries:
`/title`, `/sources_label`, `/sources/<index>/title`, `/sources/<index>/note`,
`/steps/<index>/title`, `/steps/<index>/note`. Indices are canonical decimal and
must already exist. Up to 64 operations apply atomically, with final web-ui
validation. No insertion/deletion, arbitrary JSON pointers or pixel changes.
The upstream Mermaid renderer uses card labels and `sources_label`; `title` is
retained metadata and is not drawn by that renderer.

```python
from pathlib import Path
from flow_workspace import import_flow, patch_and_render, workspace_bytes
workspace = import_flow(Path('examples/flow.json').read_bytes())
updated, svg = patch_and_render(workspace,
    [{'path': '/steps/0/note', 'value': 'reviewed'}], 'svg', mmdc='/path/to/mmdc')
# Only receive replacement state and image after both patch and drawing succeed.
Path('edited.flow.json').write_bytes(workspace_bytes(updated))
Path('edited.svg').write_bytes(svg)
```

```js
const {importFlow, patchAndRender} = require('./flow_workspace.cjs');
const fs = require('node:fs');
const original = importFlow(fs.readFileSync('examples/flow.json', 'utf8'));
const {workspace, image} = patchAndRender(original,
  [{path:'/steps/0/note', value:'reviewed'}], {format:'png', mmdc:'/path/to/mmdc'});
// workspace is detached; image is the existing Buffer-returning PNG export.
```

Invalid patches and renderer failures leave caller state untouched. CLI output is
fully computed before any destination is opened; `--force` uses the shared atomic
file replacement. Each CLI command writes one file. Saving a workspace and image
in two separate commands is not a multi-file transaction; a later drawing failure
does not roll back a previously saved valid workspace. Use `patch_and_render` /
`patchAndRender` to compute both before deciding to persist either.

`tests/test_flow_workspace.py` covers exact original-byte recovery, detached state,
64/65 operations, invalid late operations, files surviving failure, and Python /
Node wrapper / native upstream parity. The existing real-renderer integration
also saves original/edited JSON, before/after PNG, edited SVG/Mermaid/Base64/data URI,
and hashes under `build/test-results/flow-export/workspace/`. It checks changed
pixels and exact Python/Node PNG and transport identity. These artifacts are
included by the existing browser CI lane. Run with the same environment shown
above plus `python -m pytest -q tests/test_flow_workspace.py`.
