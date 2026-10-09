# PPTX attribute CLI — prototype contract (Issue #80)

Python >=3.11; runtime dependency: python-pptx. TOML is read with stdlib tomllib.

## Example

```toml
[[rules]]
operation = "replace_text"
old = "Draft"
new = "Final"
slide = 1

[[rules]]
operation = "text_color"
color = "#000000"
slide = 1
```

```sh
python pptx_replace.py input.pptx --rules rules.toml --dry-run
python pptx_replace.py input.pptx --rules rules.toml --output updated.pptx
```

Rules run in declaration order (sequential/cascading). A rule's optional `slide` is a 1-based slide number. No shape filter yet. Text replacement operates **within each run**, retaining run formatting; text spanning runs is not matched. Color updates require explicit RGB runs; theme and inherited colors fail explicitly. Slide backgrounds require explicit solid RGB fill, not inherited/theme fills. Shapes in groups, tables, notes, masters and relationships are not intentionally modified. No guarantee is made for unsupported constructs; test on disposable fixture files before production use.

Dry-run reports planned edits and does not write a PPTX. A zero-match operation is reported as zero changes. The output must be a new path; existing files are never overwritten. This prototype is intentionally narrower than the full Issue #80 plan; future revisions in the same Draft PR should add target selectors, preconditions, atomic output and stronger structure/visual diff checks before claiming general document preservation.
