# report.md

Image Studio clipboard fallback verification, 2026-10-18. Refs #114.

On baseline main `214f1b39bd50ad24a8ea28624c9fb24c5b5adca2`, the new
`ordinary-text-and-PNG` test fails: a modal error is visible and no image is
imported. The same test passes with this change.

| Browser | Version | Passed checks | Native clipboard |
| --- | --- | ---: | --- |
| Chromium | 145.0.7632.6 | 44 | Actual ClipboardItem write/read of text/plain + PNG |
| Firefox | 146.0.1 | 43 | API boundary doubles |
| WebKit | 26.0 | 43 | API boundary doubles |

Playwright 1.58.2; Linux headless; real static build at `/Ironmate/`. No page
errors or external page requests were observed. See the adjacent engine JSON
files for the complete check lists. The matrix supplies deterministic clipboard
representations and errors while retaining real UI, validation, image decoders,
Canvas PNG normalization, RGBA and dimension checks. It is not an OS clipboard
compatibility matrix. Native Chromium adds the reported mixed-format integration.

Coverage includes text/image precedence, malformed explicit image URI,
non-image Base64, MIME mismatch, corrupt image, denied/unsupported/other API
failures, later usable formats/items, picker cancellation, explicit Base64 input,
PNG transparency, JPEG/WebP decode, 32MiB and 32MiB+1 bytes, and 4,194,304 vs
4,196,352 pixels. At-limit raw Base64 and binary PNG fixtures have zero bytes
after IEND to reach the byte ceiling while retaining a small real decoded image.
A synthetic oversized Blob verifies rejection before arrayBuffer allocation.

Local environment preparation: Chromium used the official Chrome for Testing
headless-shell binary matching Playwright's 145.0.7632.6 revision. Firefox
required content sandbox level 0 plus MOZ_DISABLE_CONTENT_SANDBOX and
MOZ_DISABLE_RDD_SANDBOX in this restricted container. WebKit used Ubuntu shared
libraries extracted to a temporary directory; its local launch wrapper preserved
LD_LIBRARY_PATH and host-library validation was bypassed after resolving these
libraries. These local preparation changes are not shipped in the product or CI.
CI installs the pinned browsers and their normal host dependencies. No product
rendering/clipboard APIs were replaced beyond the disclosed boundary doubles.

The 30 existing targeted Python tests passed:

```sh
python -m pytest -q tests/test_studio_ingress.py tests/test_image_studio.py tests/test_studio_workspace.py tests/test_studio_delivery.py
```

`node --check` passed for the changed JS files, `git diff --check` passed,
`actionlint 1.7.7` passed for the modified workflow, and the stdlib-only static
build succeeded. The existing complete `tests/image_studio_browser.cjs` suite
also passed with `IRONMATE_STUDIO_STATIC=1` in Chromium, including its scale,
tradeoff, export, history and PPTX image checks. Browser reproduction commands and Flutter source references
are in [image-studio.md](../../image-studio.md#image-input-and-clipboard-format-selection).

The existing 32MiB input ceiling, 4MP limit and PNG normalization remain.
Flutter's 40MP ceiling and default 2/3 downscale are intentionally not adopted:
there is no automatic resize or claim of 40MP support. Larger input handling
requires a separately bounded decoder/normalization design and an explicit
original-retention policy. Pages assets and deployment settings remain static;
no backend or web-ui extraction was added.

Android/iOS physical devices, real camera/picker dialogs, native Firefox/WebKit
clipboard permissions, EXIF orientation across OSes, and Flutter itself were
not executed here. Flutter PR #208 is separate existing regression evidence.
