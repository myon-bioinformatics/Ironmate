# Common JSON flow export

`flow_export.py` connects the **ascii_artist** card-flow contract to Ironmate's existing
`mermaid_svg.render_mermaid` and Image Studio Chrome rasterizer. It does not
implement another graph model/layout engine. `vendor/ascii_artist.py`, its LICENSE
and `examples/flow.json` are byte-identical locked upstream artifacts; update them
through the parent vendor registry and lock, never edit the copies. (The flow code
started in web-ui, which handed it to ascii_artist; web-ui no longer has it.)

The bounded merge-style JSON schema (1–8 sources and 1–8 steps, labels/notes only)
is documented at https://github.com/myon-bioinformatics/ascii_artist/blob/main/docs/card-flows.md.
This is not a general graph editor or an editable Studio scene importer.

| Format | Returned bytes | Local tools |
| --- | --- | --- |
| `mermaid` | UTF-8 fenced Mermaid Markdown | Python 3.10+ standard library |
| `svg` | SVG with explicit pixel size and intrinsic viewBox | Python, installed `mmdc` and its browser |
| `png` | PNG | Above plus Node.js 26+ and Chrome/Chromium |
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
node vendor/py_launch.cjs --env-var IRONMATE_PYTHON -- flow_export.py examples/flow.json --format mermaid -o flow.md  # from Node
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
const {run} = require('./vendor/py_launch.cjs');
const spec = require('./examples/flow.json');
const png = run('flow_export.py', ['--format', 'png', '--mmdc', '/path/to/mmdc', '--chrome', '/path/to/chrome'],
                {envVar: 'IRONMATE_PYTHON', noSite: true, input: JSON.stringify(spec), timeout: 180000}).stdout;
require('node:fs').writeFileSync('flow.png', png);
```

There is no Node wrapper: Node starts the Python CLI through the vendored parent
`vendor/py_launch.cjs` (Node 26+), so the flags, limits and exit codes are the
Python ones above. The interpreter order is `IRONMATE_PYTHON`, `PYTHON`,
`python3`, `python` (Windows `py -3`), each checked for 3.9+; an explicit
`IRONMATE_PYTHON` or `python` option does not fall back. Windows `.cmd`/`.bat`
shims are rejected. A failure throws with the Python CLI's stderr attached.

`run(...).stdout` is a Buffer for every format; use `.toString('utf8')` for the text ones.
PNG/Base64/data URI can be imported through the existing Studio file/Base64 input.
Rendering uses CPU browser drawing, with fonts supplied by the host; identical
pixels across different operating systems/fonts/browser versions are not promised.

## Reproducible verification

```sh
uv run pytest -q tests/test_studio.py
IRONMATE_RUN_FLOW_INTEGRATION=1 IRONMATE_MMDC_BIN=node_modules/.bin/mmdc \
  IRONMATE_CHROME=/path/to/chrome uv run pytest -q tests/test_flow_integration.py
IRONMATE_CHROME=/path/to/chrome node tests/flow_export_browser.cjs
```

The integration fixture writes all five formats, white/transparent and 2× PNG,
source/PNG hashes and a report to `build/test-results/flow-export/`. It checks
Python/Node (launcher) PNG byte identity and Base64/data URI decoding identity. The browser
check opens the fixed sample, compares exact PNG/transport pixels through Canvas and records the
SVG-to-PNG white-composited mean error (tolerance <2 on a 0–255 scale), verifies escaping without remote requests or script execution,
and saves `sample.html` and `browser.png`. The existing browser CI lane preserves
these artifacts and installs/identifies Noto CJK for the Japanese fixture; fast
unit tests do not require an external renderer. Inspect the preserved screenshot
as well as numeric parity: identical missing-glyph boxes are not valid Japanese
rendering.

## Retained JSON workspace: import → patch → regenerate

`flow_workspace.py` adds a reproducible **structural JSON**
editing path. This is separate from the Image Studio pixel canvas: editing an
imported PNG there does not update flow labels, and a PNG cannot recover the source
JSON. A visual Studio scene importer is still outside this path.

The `ironmate-flow/1` workspace stores `original_json` (the exact input UTF-8 text,
including whitespace and omitted defaults) and `spec` (the validated, current
flow JSON). Saving and loading preserves both. Original text is never patched;
`original` extracts its bytes, while `spec` extracts the current JSON. Importing a
new source creates a new workspace. Workspace files are bounded to 2MiB, original
JSON to 256KiB, and patch documents including the working spec to 320KiB.

Editing runs the byte-identical `vendor/ascii_artist.py flow-patch` in an isolated
Python process (`-I -S -X utf8`). The Node workspace API wraps this same Python path;
there is no second (Node) patcher or validator. The module and the sample are pinned
together to merged ascii_artist `001de63c23396e3ea6333867a169df2c60a50244`, and the
child lock records commit, Git blob and SHA-256 for each. Do not edit these vendor bytes.

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
node vendor/py_launch.cjs --env-var IRONMATE_PYTHON -- flow_workspace.py render edited.flow.json --format mermaid -o edited.md
```

Supported operations are exactly ascii_artist's array of `{path,value}` entries:
`/title`, `/sources_label`, `/sources/<index>/title`, `/sources/<index>/note`,
`/steps/<index>/title`, `/steps/<index>/note`. Indices are canonical decimal and
must already exist. Up to 64 operations apply atomically, with final ascii_artist
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
const {call, run} = require('./vendor/py_launch.cjs');
const py = {envVar: 'IRONMATE_PYTHON', noSite: true, isolated: true};
const original = call('flow_workspace.py', 'import_flow', [require('node:fs').readFileSync('examples/flow.json', 'utf8')], py);
const workspace = call('flow_workspace.py', 'patch_workspace', [original, [{path: '/steps/0/note', value: 'reviewed'}]], py);
const {spec} = call('flow_workspace.py', 'validate_workspace', [workspace], py);
const png = run('flow_export.py', ['--format', 'png', '--mmdc', '/path/to/mmdc'], {...py, input: JSON.stringify(spec)}).stdout;
```

Invalid patches and renderer failures leave caller state untouched. CLI output is
fully computed before any destination is opened; `--force` uses the shared atomic
file replacement. Each CLI command writes one file. Saving a workspace and image
in two separate commands is not a multi-file transaction; a later drawing failure
does not roll back a previously saved valid workspace. Use `patch_and_render` /
the same two calls from Node to compute both before deciding to persist either.

`tests/test_studio.py` covers exact original-byte recovery, detached state,
64/65 operations, invalid late operations, files surviving failure, and Python /
Node (through `vendor/py_launch.cjs`) / native upstream parity. The existing real-renderer integration
also saves original/edited JSON, before/after PNG, edited SVG/Mermaid/Base64/data URI,
and hashes under `build/test-results/flow-export/workspace/`. It checks changed
pixels and exact Python/Node PNG and transport identity. These artifacts are
included by the existing browser CI lane. Run with the same environment shown
above plus `uv run pytest -q tests/test_studio.py`.
