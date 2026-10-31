# Browser tools on GitHub Pages

- Slide Studio: https://myon-bioinformatics.github.io/Ironmate/slides/
- Image Studio: https://myon-bioinformatics.github.io/Ironmate/
- Pixel art, image grid, Base64 size: https://myon-bioinformatics.github.io/Ironmate/tools/
- Portfolio: https://myon-bioinformatics.github.io/#ironmate

No extra JavaScript packages or external CDNs are used. Only HTML/CSS/JavaScript and public presets generated from the Python version are served. Images and JSON are processed in the browser and not uploaded.

## Build and run with Docker

```sh
docker build -f Dockerfile.pages --target runtime -t ironmate-pages .
docker run --rm -p 127.0.0.1:8080:8080 ironmate-pages
# http://localhost:8080/Ironmate/ or http://localhost:8080/Ironmate/tools/ or http://localhost:8080/Ironmate/slides/
```

To extract only the public files for GitHub Pages:

```sh
docker build -f Dockerfile.pages --target artifact --output type=local,dest=build/studio-site .
```

The same static files can also be built with only the Python standard library:

```sh
python -S image_studio.py --build-site build/studio-site
# the output must be a new or empty directory
```

`studio-pages.yml` generates the static files with Docker, verifies `/Ironmate/` in the container with a real browser, then publishes. Docker and Python do not run in the published environment. Permissions, publish target and existing Studio URLs are unchanged.

## Coverage

| Feature | Behavior on Pages | Boundary with the local version |
| --- | --- | --- |
| Image Studio | Existing shapes, images, text, heatmaps, mosaics, history, clipboard, PNG/SVG/JSON/Base64 | Existing input, pixel and size limits are kept |
| Pixel art | 5 shapes × 4 treatments × 5 sizes, 10 palette IDs, click-editing color indices, JSON import, nearest-neighbor scaling, palette change, one-step undo | Preset source sizes are 16/23/31/32/64. Output grid is 1–256 cells per side. Python's arbitrary-size procedural generation, photo color reduction, sparse scanning and probe downscaling are not ported |
| Pixel art export | PNG/SVG/JSON/Base64 at 1/2/8/16x | PNG deflates RGBA directly, keeping hidden RGB of transparent pixels and the color table. Compressed bytes are not guaranteed to match the Python version. PNG needs a browser with CompressionStream |
| Image grid | Up to 20 PNG/JPEG/WebP, column count, grid PNG, HTML with embedded images | 8 MiB per image, 32 MiB total, 4 MP per image. Pixel count is checked after decoding; thumbnails up to 512 px on the long side are kept. Keeping original bytes/metadata and pass/fail or MAE/RMSE computation are out of scope |
| Base64 size | Computes `4*ceil(bytes/3)` from File.size; adds 22 characters for a PNG data URI | Not an estimate of compression or downscaling. Uses only the size without reading the file |
| Slides / PPTX creation | Place text, shapes, arrows and images in [Slide Studio](slide-studio.md) and export multi-slide PPTX | Reading arbitrary PPTX, editing existing PPTX and PDF rendering are CLI-only |
| Existing PPTX/PDF, external APIs | The parts that need a runtime are stated on screen | Run pptx_pipeline.py / pptx_replace.py / pptx_preview.py etc. locally. The pypdf fetch from #145 is not a browser implementation |

Image grid decoding depends on the browser implementation. Animation, full EXIF/color-management preservation and cross-OS font matching are out of scope. Canceling a file selection or choosing invalid JSON keeps the current work. Work is lost when the page closes, so save explicitly.

## Verification

```sh
uv run pytest -q tests/test_pages_tools.py tests/test_studio_delivery.py tests/test_image_studio.py
# after starting Docker on port 8080 as above, run with the test-only Playwright:
IRONMATE_PLAYWRIGHT_MODULE="$PWD/build/pages-test/node_modules/playwright" node tests/pages_browser.cjs
```

Color indices of all 100 presets are checked against the existing Python implementation. Nearest-neighbor scaling is compared with Python, including odd and non-square sizes. Browser checks cover the link from the existing Studio, PNG/SVG/JSON/Base64 export, lossless PNG→Python round-trip, resizing and undo, rejecting invalid JSON, the image grid, HTML-escaping file names, Base64 size and a 390 px-wide screen.

The public allowlist excludes input images, working JSON, repository evidence and Python source. The output is about 400 KB of HTML/JS/CSS plus presets.
