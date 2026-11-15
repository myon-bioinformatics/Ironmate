# Opt-in nano test environment

Ironmate provides a minimal standard-library test profile (`stdlib-test`) that installs only `pytest` and `pyyaml`, omitting optional heavy dependencies (Pillow, NumPy, Playwright, pypdf, and git-pinned packages).

## Running tests in the nano profile

From the repository root:

```sh
uv run --locked --only-group stdlib-test python -m pytest -q tests/test_ooxml.py
```

This profile verifies core Open XML (PPTX and XLSX) generation, XML round-trips, and styling without external image codecs or browser automation.
