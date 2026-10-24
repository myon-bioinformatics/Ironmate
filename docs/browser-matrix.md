# Per-browser screenshot comparison sheet

`browser_matrix.py` reads screenshots saved by browser-test-kit's `platform-apps` and builds a
"page × environment (OS, browser, profile)" comparison sheet. It uses only the Python standard library
and Ironmate's PNG codec.

```sh
python -S browser_matrix.py app-results --out matrix                     # default: the width-384 shot
python -S browser_matrix.py app-results --out matrix-initial --shot initial --reference macOS-webkit-desktop
```

Input is `.../<page>/<OS>-<browser>-<profile>/<shot>.png` at any depth. A browser-test-kit artifact tree
can be passed as extracted. It stops if the same page and environment pair has two images.

## Output

- `sheet.png`: rows are pages, columns are environments. Pairs with no screenshot are gray.
- `tiles/<page>/<env>.png` and `index.html`: the same layout as a labeled table.
- `report.json` (`ironmate-browser-matrix/1`): each cell's source file, SHA-256 and original dimensions, and its difference from the reference environment.

## What the difference means

devicePixelRatio differs per device (3x on iPhone, 2.625x on Pixel), so each image is area-sampled down to a common width,
then cropped or padded with white to a common height before comparing. Tile size (default 160x320) and gap (default 8 px) are multiples of 8 px to match browser-test-kit's default width grid. These are defaults, not rules, so you can switch to any value, e.g. `--tile 195x422 --gap 4` to match a real device width. The difference is the RGB MAE / RMSE (0–255) between tiles.
It is a screen-level hint that "this engine draws the page differently", not a pixel-level regression check.
The reference environment defaults to `Linux-chromium-desktop` (otherwise the first by environment name).

Mobile views are emulated, not real device screens. Public sites can change between runs, so
check which build was seen in browser-test-kit's record (`target.provenance`).

## CI integration and coverage

The Python `build` API accepts `expected_pages` and `expected_envs`. They add empty
rows/columns for planned captures that never produced a PNG; inferred axes alone
cannot reveal an entirely absent environment. At least one real PNG is required.
Each cell reports the scaled height and cropped/padded tile rows in `fit`. These
rows and differing CSS viewport sizes can change MAE/RMSE without a UI defect.
DPR normalization compares raster content, not CSS layout or click behavior.

Output must be a new or empty directory. A regular file, a nonempty directory,
or an output symlink (including a dangling link) is rejected before writing.
As in `image_compare.py`, trusted parent directories may themselves resolve through
symlinks; this is a CLI overwrite guard, not protection against concurrent filesystem changes.
