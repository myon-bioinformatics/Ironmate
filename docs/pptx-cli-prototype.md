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


## Visual regression verification (planned in this Draft PR)

Render **both** original and transformed PPTX using the same pinned LibreOffice version and fonts, convert resulting PDFs to per-slide PNGs, and produce a side-by-side contact sheet plus pixel-difference images and machine-readable manifest. LibreOffice and a PDF rasterizer are **optional verification dependencies**, not requirements for basic CLI transformation. Never download tools implicitly.

A future `--visual-check` CLI flag should trigger rendering, and `--visual-output DIR` should allow retaining artifacts. Verify slide counts, image dimensions and renderer exit status; missing renderer or render failure must not be reported as success. Keep conversion in a temporary working directory and do not overwrite source files.

Expected changes (text/color/shape) naturally generate visual differences: do not equate zero diff with success. Report changed pixel count and bounding boxes as diagnostic evidence, and distinguish expected target regions from unintended regions once target-region mapping is implemented. Pixel comparisons are renderer/font-sensitive and should not be treated as cross-platform bit-for-bit guarantees.

CI should test the renderer on synthetic PPTX fixtures and upload PNG/contact sheet/diff artifacts; structural checks (slide/shapes/relationships and unmodified contents) remain separate. Real or sensitive presentations must not be uploaded as CI artifacts. If a renderer is unavailable, explicitly mark visual verification as skipped/unverified, never passed.


## Round-trip and repair-oriented testing roadmap (Issue #80)

The intended pipeline is Markdown/Marp -> PPTX -> python-pptx edits -> PPTX/Open XML inspection -> rendered output -> JUnit XML. Markdown/Marp is a fixture generator, **not** a lossless reverse serializer for arbitrary PPTX. Separate invariants into: (1) exact source package preservation where required, (2) semantic content/geometry/style invariants, (3) rendered visual comparison with tolerances. For a round trip, compare a canonical semantic projection rather than expecting identical ZIP/XML bytes. Use explicit supported-feature manifests and report unsupported/lost features, never silently claim full reversibility.

The one-liner CLI remains the primary interface; all extra stages are optional adapters. Marp and browser tooling must not become unconditional runtime dependencies. Probe existing vendor/ assets first, then evaluate pinned tools only for uncovered needs.

TOML is optional for **reusable master policies** (target selectors, allowed changes, preconditions, invariants, renderer profile, comparison tolerances, expected changes, and validation matrices). Simple one-off commands should need no TOML. Store each test's intent and results as reproducible evidence, export pytest/JUnit XML, and preserve renderer logs and artifacts.

Future automated repair is a **separate, gated workflow**: failed test -> structured failure classification -> proposed patch on isolated branch -> repeat deterministic tests -> review. Never mutate the original input, rewrite expectations to force green, or merge an unreviewed patch. Include a bounded attempt count and rollback; distinguish product failures, missing environment dependencies, and flaky render differences.

Suggested incremental PR #83 checkpoints: A) validate current CLI and add one-liner regression tests; B) synthetic Markdown/Marp fixture with pinned environment; C) PPTX Open XML canonical structural checks and preservation manifest; D) optional render-and-diff evidence; E) reusable master-rule TOML and JUnit failure classification; F) proof-of-concept repair suggestion only, without autonomous merging.


## Minimal README fixture for first integration test

Start with a **synthetic** small README (title, two headings, body and MIT license label), not a real confidential document. Generate a PPTX with one mapped text shape per Markdown block; record a stable source-block identifier and heading level in a sidecar manifest. Apply an explicit RGB heading-color change via python-pptx, then inspect slide XML and relationships to verify the intended run properties changed and unrelated text/shape positions did not. Reopen the PPTX and emit pytest/JUnit XML; optionally render before/after for human inspection.

Test separately: visible text equality, heading-to-shape mapping, intended color mutation, unchanged body text, and XML preservation of unrelated elements. Use XML-aware comparison rather than raw XML string equality because serialization may reorder benign attributes. This is a constrained fixture round trip, not general PPTX-to-Markdown reversibility.

Do not require web-ui, browser-test-kit, Node or Marp for this initial test. Reuse their existing capabilities only if they demonstrably help a later optional visual/interaction lane. Keep the whole workflow accessible from a single CLI invocation.


## Agreed implementation order (2026-10-09)

Keep all prototype improvements in Draft PR #83, with small reviewed commits and clean documentation. First **prove PPTX-only** on a synthetic presentation: create with python-pptx, edit text and RGB attributes using the one-line CLI, reopen, inspect Open XML and produce pytest/JUnit evidence. Make the runtime and CI dependencies explicit. Do not block this first proof on Markdown, Marp, Node or browser rendering.

Next add optional rendering and before/after evidence; then a minimal README Markdown input and heading mapping; evaluate Marp only if it reduces effort or adds useful independent verification. It is acceptable to avoid hand-building complex PPTX: fixture generation is deliberately minimal. Maintain the same PR, preserve unrelated repository functionality, and document any unsupported features or skipped visual checks.
