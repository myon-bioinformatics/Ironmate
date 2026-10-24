<!-- image-digest.md -->
# Image digest page (image_digest)

Builds a single lightweight HTML page and a Markdown summary for review from many images and their pass/fail status.
Rows and columns can be anything (page × environment, case × device, slide × theme, etc.). It is for seeing everything on one page
when the full output is too large to download conveniently, as with browser-test-kit's published-app runs.

```sh
python -S image_digest.py input.json --out digest/            # image paths are relative to input.json
python -S image_digest.py input.json -o digest/               # -o and --output are the same as --out
node image_digest.cjs input.json digest/                       # from Node (Python does the work)
node image_digest.cjs input.json --out digest/ --tile 64x128   # same flags as Python
node image_digest.cjs --help
```

Unfixable input exits with code 2. With `--json`, that failure becomes a single JSON object on stderr; stdout on success is unchanged. Missing arguments print usage without waiting.

Types for the Node API (`buildDigest`) are in `image_digest.d.cts`. The other Node APIs (`flow_export.cjs`,
`flow_workspace.cjs`, `studio/ingress.cjs`) also have `.d.cts` files of the same name; the implementations stay JavaScript.

The Node wrapper launches Python with `vendor/py_launch.cjs`, inherited from the parent. When the API's `python` is omitted,
each call runs a short version check for 3.9+ and then tries, in order, `IRONMATE_PYTHON` → `PYTHON` → `python3` →
`python` (`py -3` on Windows). The API's `python` or a set `IRONMATE_PYTHON` does not fall back.
Launch failures give `image digest Python process failed: …` (library) or CLI exit code `2`.
Details are the same as [Node launch for flow export](flow-export.md).

Input is `ironmate-image-digest-input/1`:

```json
{"schema": "ironmate-image-digest-input/1", "title": "Published app run",
 "rows": ["home", "hub"], "cols": ["Linux-chromium-desktop", "macOS-webkit-iphone"],
 "meta": {"build": "d161b0cd4967", "link": "https://github.com/.../actions/runs/1"},
 "cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "shots/home.png", "status": "pass"},
           {"row": "home", "col": "macOS-webkit-iphone", "image": "shots/home-i.png", "status": "fail",
            "notes": ["320px:overlap"]}]}
```

Output:

- `digest.html`: one file with thumbnails embedded as data URIs. No JavaScript; opens anywhere.
- `summary.md`: pass counts per row and a table of what to look at. Can be pasted as-is into PR comments or job summaries.
- `digest.json` (`ironmate-image-digest/1`): the thumbnail size used, byte count and counts per status.

Thumbnails start at 64x128 px (changeable with `--tile`) and are halved in each dimension (1/4 the pixels) until
they fit in `--max-bytes` (default 1 MB). The minimum is 16x32. Status is used only for color coding and counts; pass/fail is never inferred from pixels.
Combinations without a cell are marked explicitly as "not run". Image paths must be relative paths inside the input directory.

## Input/output contract

- `base` is an existing input directory. The CLI uses the input JSON's parent directory (changeable with `--base`);
  stdin and the Node API specify it explicitly. Real image paths are resolved, and references that leave the input directory through
  a symlink on the file itself or a parent directory are rejected. Symlinks pointing inside the input are allowed.
- Images are regular PNG files (8-bit gray / gray+alpha / RGB / RGBA, non-interlaced).
  **At most** 32 MiB per file and 16,777,216 (4096×4096) total pixels. Size is checked before reading,
  and reading itself is capped at 32 MiB + 1 byte. Cells without an image may omit `image` or set it to `null`.
- Rows and columns are unique labels of 1–120 characters (no control characters). At most 2000 cells, with no duplicate row/column pairs.
  `status` is `[a-z][a-z0-9_-]{0,23}` (default `unknown`). Only `pass` counts toward the pass count.
  `notes` are at most 200 characters each; the first 6 are shown in HTML and the first 2 as failure reasons in Markdown.
  Line breaks in Markdown tables are collapsed to spaces, and separator, HTML and formatting characters are escaped.
- Each image file is read and decoded exactly once. PNGs for each candidate size are made from the original
  and reused across downscaling iterations. Candidates halve each dimension down to 16×32. Full-resolution pixels of all images are not kept.
- The output must be a new or empty directory. `write()` rejects a regular file, a nonempty directory or a symlink
  (including a dangling one) with `ValueError`. On error the CLI exits with code 2,
  and the Node API throws. Input is used as a snapshot that does not change during the run.
- `build(spec, base, max_bytes=..., tile=(64, 128))` returns `(HTML, Markdown, info)`.
  `write(out, *build(...))` saves the 3 files. Node saves with
  `buildDigest(spec, {base, out, maxBytes, tile: "64x128"})` and returns the same `info`.
- `info` has `schema`, `tile: [width,height]`, `bytes` (UTF-8 byte count of the HTML), `fits`,
  `rows`, `cols` (row/column counts), `passed`, and `statuses` (counts per status of explicit cells).
  Omitted cells are not counted in `statuses`. If even the minimum size does not fit, output is still produced with `fits: false`.
  The limit is not guaranteed, so callers should check `fits` before uploading.

## Connecting from browser-test-kit

Observation and pass/fail judgment in `scripts/app_digest.py` stay on the browser-test-kit side; only the rendering input can be converted as follows.

| browser-test-kit | image_digest input |
| --- | --- |
| List of planned pages | `rows` (keep pages that did not run) |
| `planned_envs(runners)` | `cols` (keep environments that did not run) |
| `(adapter, OS-channel/browser-profile)` | `cell.row`, `cell.col` |
| PNGs from `find_shots(root, shot)` | `cell.image` (relative path from the input root) |
| Observation `verdict` | `cell.status` (not inferred from pixels) |
| Layout/click failure reasons | `cell.notes` |
| Build SHA, run URL | `meta.build`, `meta.link` (https only) |

With only an image, use `status: "unknown"` and `notes: ["no record"]`; with only an observation,
use a cell without an image. Omit the cell when there is neither image nor observation, giving "not run".
If builds differ per cell, add a short build label to each cell's notes to distinguish it from the overall build.

Current btk uses `pages` / `envs` from `btk-app-digest/1`, so this is not a drop-in JSON replacement.
Either rename from `rows` / `cols` in a migration adapter or update the caller to the new schema.
Also, `app_digest_comment.py` requires `<!-- platform-apps-digest -->` and Markdown of at most 60,000 bytes.
In Python, `summary_markdown(validate(spec), marker='<!-- platform-apps-digest -->')` keeps the existing marker.
Node's default marker is `<!-- ironmate-image-digest -->`, so adjust it in the adapter before posting.
`max_bytes` is the HTML limit and is checked separately from the Markdown posting limit.

Example call (pass a `spec` in the schema above, built on the btk side):

```python
from image_digest import build, summary_markdown, validate, write

page, _, info = build(spec, results_root)
summary = summary_markdown(validate(spec), marker='<!-- platform-apps-digest -->')
write(out, page, summary, info)
# check info['fits'] and len(summary.encode('utf-8')) <= 60_000 before posting or distributing.
```

This PR sets up the contract and safety on the Ironmate side. It does not replace btk's existing rendering.
