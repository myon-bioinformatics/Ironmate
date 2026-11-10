# Locked Marp integration tools

`mcp-tests.yml` installs this package with `npm ci --prefix scripts/marp-tools
--ignore-scripts`. These are test tools, not Ironmate runtime dependencies. The
legacy `ci.yml` has a separate installation and is not changed here.

## Temporary security overrides

Marp CLI 4.5.1 and Marp Core 4.4.0 are the latest published releases checked on
2026-11-10, but retain older dependency ranges. The scoped overrides are:

- Marp CLI's `puppeteer-core` is pinned to 25.15.0, matching the existing
  Puppeteer peer used by Mermaid CLI. This removes the old `get-uri` /
  `basic-ftp` chain (GHSA-c475-qrg2-pj4r) and Chromium BiDi 14 / Zod 3 chain
  (GHSA-mrhx-c7xc-m3w5). Zod itself is not overridden across incompatible majors.
- Marp Core's `katex` is pinned to 0.18.10 for GHSA-238p-pmpm-9mq7. Mermaid CLI
  12.2.0 supports the patched KaTeX through its normal dependency range.

Puppeteer 25 changes its module format, minimum Node version and some APIs.
This package already requires Node 26. Marp loads its public `launch` API under
Node 26 and does not call the removed `Browser.isConnected`, `Puppeteer.product`,
or synchronous `executablePath` / `defaultArgs` APIs. This source review and a
successful version/HTML command do **not** replace the real rendering checks.

Remove each override when a supported Marp release adopts the fixed parent
version. Do not globally override Zod or downgrade Marp to silence npm audit.

## Verification

Run with Node 26:

```sh
npm ci --prefix scripts/marp-tools --ignore-scripts
npm audit --prefix scripts/marp-tools
python -m pytest -q tests/test_junit_failure_identity.py -k marp_tools
IRONMATE_RUN_MARP_INTEGRATION=1 \
IRONMATE_MARP_BIN="$PWD/scripts/marp-tools/node_modules/.bin/marp" \
IRONMATE_MMDC_BIN="$PWD/scripts/marp-tools/node_modules/.bin/mmdc" \
PUPPETEER_EXECUTABLE_PATH=/usr/bin/google-chrome \
uv run --locked python -m pytest -q tests/test_marp_pptx.py
```

The last command must run where Chrome can launch. The preparation container
blocked Chromium's process-singleton socket, so real PPTX/PNG/Mermaid rendering
was not validated there. Require the real integration job before merging.

Sources:
- https://github.com/advisories/GHSA-c475-qrg2-pj4r
- https://github.com/advisories/GHSA-238p-pmpm-9mq7
- https://github.com/advisories/GHSA-mrhx-c7xc-m3w5
- https://github.com/puppeteer/puppeteer/blob/main/packages/puppeteer-core/CHANGELOG.md
