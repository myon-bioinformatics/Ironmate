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
second implementation. It requires Python and defaults to `python3`; set
`IRONMATE_PYTHON` (often `python` on Windows) or the API's `python` option.
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
these artifacts; fast unit tests do not require an external renderer.
