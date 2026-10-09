# PPTX attribute CLI — prototype contract

Issue: #80. Python >=3.11, python-pptx runtime dependency, TOML via stdlib tomllib.

## Usage

```sh
python -m pip install python-pptx
python pptx_transform.py input.pptx --rules rules.toml --dry-run
python pptx_transform.py input.pptx --rules rules.toml --output changed.pptx
```

Example rules.toml:

```toml
[[rules]]
operation = "replace_text"
old = "Draft"
new = "Final"

[[rules]]
operation = "font_color"
new = "#000000"
slide = 1
```

Operations are sequential and rule order matters. Slide indices are 1-based. Text replacement only matches within a single run, preserving the formatting of that run. It does **not** match across runs. Font color targets nonempty runs; an optional `old` condition matches only direct RGB colors, not theme colors. Background operation applies a direct solid slide fill and does not resolve inherited theme/master backgrounds; background `old` conditions are rejected. Shapes within groups, tables, notes, connectors and arrow geometry are outside this initial implementation. No assertion of full OOXML byte-for-byte preservation is made. Dry-run does not write the file and reports candidate changes. It is not a complete validation of all document structures.

The prototype does not yet implement strict expected-count assertions, atomic output, simultaneous palette swaps, or render-level verification. These are required before describing the tool as production safe. Do not apply to important original documents without keeping a backup.
