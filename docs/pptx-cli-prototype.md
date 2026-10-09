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


## Verified first-stage CI evidence

At commit `79e5fcdbfbb048120f94dc65ebacccb623e9a02e`, GitHub Actions run [37938817783](https://github.com/myon-bioinformatics/Ironmate/actions/runs/37938817783) completed successfully across resolve-vendor, locked baseline, test and failure-identity/collect. The default pytest job reported **51 passed**, including the CLI one-liner and deliberately failing child pytest/JUnit regression. The controlled failure artifact was uploaded. This confirms failure capture wiring, not a production renderer or Markdown/Marp integration.

Stage 2 is intentionally deferred until the PPTX-only structural preservation checks and CLI error cases are sufficiently covered. Keep this same Draft PR until review and tests are complete; do not infer visual fidelity from a green pytest run.


## Stage 2 implementation: minimal Markdown fixture

`tests/fixture_pptx.py` is a small **editable** Markdown→PPTX fixture generator, intentionally separate from the existing PPTX editing CLI. It accepts `# title`, `## heading` and plain single-line body text (at most eight nonempty blocks). It rejects unsupported heading levels, lists and other explicit constructs rather than pretending to be a full Markdown parser. Shape names include stable line-based IDs and roles, and the CLI prints a JSON mapping manifest.

```sh
python tests/fixture_pptx.py tests/fixtures/mini_readme.md -o sample.pptx
python pptx_replace.py sample.pptx --text-color '#2244AA' -o colored.pptx
```

The new integration test generates a fixture, checks Markdown→shape text/role mapping, applies a color change, reopens the PPTX, checks text and RGB values, compares unrelated ZIP package members and inspects slide XML. Tests produce JUnit through the existing CI pytest command.

**Marp remains optional and not yet integrated.** Its standard PPTX export can flatten slides, making run-level python-pptx editing unsuitable. Evaluate a pinned Marp/Node toolchain and editable export only after this independent editable-PPTX path is green. No visual rendering fidelity is claimed by the XML tests.


## Stage 2 gate and later Marp sequencing (confirmed)

At head `eac914f56ded500b574c4195e1523ba358296e62`, [CI run 37939923108](https://github.com/myon-bioinformatics/Ironmate/actions/runs/37939923108) finished green: 61 pytest passed; resolve-vendor, locked baseline, test, and failure-identity/collect succeeded. This validates the **minimal direct Markdown→editable PPTX→attribute edit→XML** integration, not Marp conversion or visual fidelity.

**Do not combine the next steps prematurely.** First finish/review the regular Stage 2 direct path and its tests. Next conduct an **independent Marp conversion proof** (Markdown→Marp→PPTX), recording tool versions, runtime/browser/LibreOffice dependencies, whether PPTX text remains editable, and rendering limitations. Only **after** that proof succeeds, add an optional end-to-end one-liner orchestrating Markdown generation → Marp → PPTX → XML/structural verification. Keep Marp optional and preserve the original direct fixture path as a regression baseline. Continue in Draft PR #83 without merging until explicitly approved.


## Test-only fixture boundary

The ad-hoc Markdown→PPTX generator has been removed from the repository root and retained **only** as `tests/fixture_pptx.py` for deterministic regression fixtures. It is not a supported production conversion CLI. Future Markdown input should use existing `vendor/markdown.py` where its API fits, or a separately validated optional Marp adapter. The production entry point remains `pptx_replace.py`; do not restore a parallel `markdown_pptx.py` runtime without a concrete need.


## Independent Marp conversion proof (optional, before orchestration)

The simple Markdown fixture `tests/fixtures/mini_readme.md` is the first Marp input. `marp_pptx.py` calls an **already installed** Marp CLI and validates that the produced PPTX can be reopened; it does not install Node, npm or a browser automatically.

```sh
marp --version
python marp_pptx.py tests/fixtures/mini_readme.md -o marp-sample.pptx
```

Run the gated real conversion test only in an explicitly provisioned environment:

```sh
IRONMATE_RUN_MARP_INTEGRATION=1 python -m pytest -q tests/test_marp_pptx.py
```

This first proof checks actual output existence and PPTX readability, **not** that the output has editable text or that it is visually faithful. Standard Marp PPTX export can rasterize slide content; that must be measured before using python-pptx to edit generated text. Do not build the unified Markdown→Marp→PPTX→XML one-liner until this independent integration is green and the editability limitations are understood. The production PPTX editing CLI stays independent.


## Web-first validation boundary (user decision)

For this prototype, **do not introduce LibreOffice** and do not require compatibility or visual equivalence with desktop PowerPoint. Prioritize Open XML structural correctness and browser-accessible inspection. Record separately whether the browser displays (a) Marp-generated HTML or (b) the actual generated/edited PPTX through a real PPTX-capable web viewer. HTML screenshots alone do **not** prove that the PPTX was opened in the browser. If a PPTX web viewer is unavailable, report that lane as unverified rather than substituting a claim about desktop compatibility.

Use existing browser-test-kit/web-ui/Playwright/Stagehand facilities where they actually apply, without introducing redundant browser automation. App-versus-web differences are explicitly out of scope for this phase and can be investigated as separate follow-ups if concrete issues arise. Keep the Markdown→Marp→PPTX→Open XML and JUnit validation work in the same Draft PR.


## TOML as a tri-state editability master (prototype)

Use TOML for an auditable **capability/pattern registry**, not as a substitute for the Open XML DOM or test results. Classify operations and detected conditions as `editable`, `unsupported`, or `unknown`. Default to `unknown`; only `editable` entries backed by executable test evidence may be offered for automated mutation. Unsupported entries should explain why and may name a safe alternative (e.g., regenerate a rasterized Marp slide from Markdown rather than changing nonexistent text runs). Unknown cases must never silently be treated as editable.

The initial registry is `tests/fixtures/openxml/editability_patterns.toml` with contract tests. It is **descriptive test data only**, not yet wired into `pptx_replace.py`. Future work: produce stable Open XML feature observations; map observations to rules, validate coverage/precedence and evidence against JUnit; store representative successful, unsupported and unknown fixtures; and make the CLI emit explicit decisions before writing. Avoid claiming all image-based or theme-based cases have been exhaustively measured.


## Format-neutral observations and optional rule storage

Do not require TOML as the canonical source of truth. Preserve actual PPTX package/Open XML bytes and, where a real web viewer is available, raw DOM/HTML/CSS snapshots as distinct reproducible evidence. DOM generated by a viewer is not automatically equivalent to PPTX source XML. Record tool versions, origin, hashes, extraction method, and supported mapping claims; redact sensitive content before publishing CI artifacts.

Keep three separable layers: (1) observed source data (XML/HTML/CSS/JSON and binary package), (2) feature/selector/editability decisions (editable, unsupported, unknown; fail closed), and (3) execution/JUnit/visual evidence. TOML may remain a convenient *candidate* for human-authored rules, but choose the serialization based on what can be validated and reused; do not force DOM or XML into TOML. Compare markup languages through a small common vocabulary (element, attribute, text, selector, parent/child, reference), while retaining format-specific semantics.

If a browser-test-kit or web-ui capture facility can extract the actual viewer DOM and styles, reuse it rather than building a parallel browser automation stack. First verify a real PPTX-capable web viewer opened the output; Marp HTML preview is a different validation lane. Store success, unsupported and unknown patterns with provenance and explicit evidence links, and promote observations into rules only after tests support the inference.


## Cross-repository failure evidence and source validation

The canonical CI already compiles every tracked Python file **before** pytest collection (`git ls-files '*.py' -z | xargs -0 python -m py_compile`), including when pytest could not collect a syntactically broken test. Reuse this existing preflight and the pinned xprobe/JUnit failure-identity collector instead of keeping a second Ironmate-specific recursive tokenizer scanner. The standalone `tests/test_python_source_escaping.py` prototype was removed as redundant; its prior success does not replace the pre-collection compiler check.

When an escape/newline/regex failure occurs, first search related test fixtures and failure evidence across markdown, xprobe, ascii_artist, cli_args and other consumer repos, then add only a minimal domain-specific regression to Ironmate. Preserve normal Python string-literal escape sequences; do not blanket-replace `\\n` in source files. CI results and PR review history should be used as evidence before proposing shared fixes in the parent tooling.


## Batch style edits: color, font size, bold

The prototype now accepts ordered `text_color`, `font_size` (1–400 points), and `bold` (boolean) operations, including through the inline CLI:

```sh
python pptx_replace.py input.pptx --text-color '#112233' --font-size 24 --bold false -o output.pptx
```

These operations target explicit text runs. The Open XML regression checks `a:rPr/@sz` in hundredths of a point, `a:rPr/@b` as 0/1, and `a:srgbClr/@val` for RGB. **Do not** blindly replace XML text across a PPTX ZIP: theme inheritance, shared style references, relationships, run boundaries, and unsupported constructs can change semantics. Use python-pptx for the supported operations and Open XML as independently checked evidence. Consider targeted XML mutation only when a verified capability rule proves it safe; preserve unrelated package members and reject unknown cases.

The raw Marp Open XML evidence is stored in a separate CI artifact from JUnit, so the canonical failure-identity collector receives only expected JUnit XML paths.


## Attribute update versus insertion (decision)

Prefer python-pptx for operations it supports, including adding explicit run attributes that were previously absent. Treat missing attributes separately from unsupported features: missing values may be inherited from themes, masters or styles. Test absent→explicit, explicit→changed and explicit→removed cases on disposable fixtures, comparing semantic output and package structure.

For operations unsupported by python-pptx, prototype a **narrow, schema-aware Open XML mutation** on an isolated fixture; verify namespaces, element ordering, relationships, serialization, package integrity, re-opening and any available web rendering. Never assume successful ZIP/XML parsing proves visual correctness. Promote an XML strategy into the editability registry only after deterministic success and failure tests; otherwise mark it unknown or unsupported. Keep the original input unchanged and avoid general regex replacement across XML.


## Attribute matrix experiments

`tests/test_pptx_attribute_matrix.py` exercises absent→explicit bold and font-size attributes, inherited text-color rejection, ordered style updates and dry-run parity. It also performs a **test-only** Open XML insertion of an explicit `a:solidFill/a:srgbClr` under `a:rPr`, reconstructs the PPTX package, reopens it with python-pptx, and checks unrelated ZIP members are unchanged. This is deliberately not a general XML rewrite engine. Expand with theme colors, font family, paragraph alignment, shape fills and malformed packages only after each operation has a distinct observable contract. Record successes and failures as JUnit evidence, with unknown cases remaining fail-closed.


## Pragmatic business/scientific slide editing scope

Prioritize a small, repeatable set of operations over full PowerPoint automation: globally consistent readable font (candidate Meiryo; configurable), black text as a **requested preset** rather than an unconditional mutation, bold headings, targeted title sizing, simple text-box creation/repositioning and basic shapes. Role-specific font *families* are low priority. Preserve existing slides and allow repeated user edits followed by additional CLI operations.

For diagram connectors, prefer a background straight line plus separate arrowhead shapes and foreground text boxes over elaborate auto-routing. The line should be placed behind foreground objects; explicit shape order and idempotency need tests. This deliberately does not promise automatic reconnection when boxes move. Prefer a narrow stable shape vocabulary and explicit opt-in operations. Do not silently add arrows, alter inherited fonts or recolor existing artwork merely because a preset exists.

Stage work: verify existing text/font/color changes and XML evidence first; add safe text-box insertion and geometry tests; then minimal line/arrowhead layers; finally expose optional one-liner presets. Any web/Marp visual check remains distinct from actual PPTX editability and no LibreOffice dependency is introduced.


## Simple repeated box connections

Use full-span straight lines behind boxes and place independent filled arrowhead shapes at the center of each **visible gap**, not at the center of the entire line. For horizontal neighbors, the line spans the left edge of A to the right edge of B and the head is centered between A's right edge and B's left edge. For vertical neighbors, span the outer top/bottom edges and place the head in the vertical gap, rotated/oriented toward the destination. Repeated neighbors use the same mechanical rule. Default to a filled triangle; optionally evaluate angular chevrons. These are static shapes, not auto-routing connectors; no movement-following guarantee.

Initial multi-box and vertical geometry tests are in `tests/test_pptx_diagram_shapes.py`. Verify layering separately before exposing this in the production CLI; if existing shapes already occupy the slide, simply adding a line after them does not put it behind them.


## Diagonal links: explicit edge anchors

Prototype diagonal links by selecting the midpoint of a source edge and destination edge, each one of `left/right/top/bottom`. Use a single straight line between anchors and a separate triangle centered on the segment. Rotation is calculated with `atan2(dy, dx)` and should be validated visually before any production claim. This avoids routing heuristics, handles C.left→A.bottom, C.top→A.bottom and C.bottom→A.bottom uniformly, and retains a simple static shape model. The initial regression is test-only; verify actual rendering and arrowhead orientation before adding a CLI option.


## Directed edge-pair geometry and arrowhead calibration

Source and destination each independently select one of `left/right/top/bottom`; test all 16 combinations in both directions (32 directed cases). The arrowhead is centered on the line segment between edge midpoints, with the tip facing the destination. For the conceptual triangle, derive its tip and two base vertices from a normalized direction vector and perpendicular vector; verify equal base distances and forward-facing tip. Reject coincident anchors explicitly.

`tests/test_pptx_edge_geometry.py` implements mathematical geometry checks only. PowerPoint shape presets may have different native orientations and rotation conventions; do not assume `head.rotation = atan2(...)` produces a visually aligned arrowhead until the rendered PPTX is checked. Future CLI adoption also requires line layering, shape insertion and visible-gap checks. No pathfinding or automatic box movement tracking is promised.


## Mermaid / Marp / PPTX responsibility boundary

Reuse `vendor/markdown.py` for safe Mermaid fence generation and extraction; its helpers treat Mermaid source as opaque and do not parse or render diagrams. Do not introduce a second Mermaid syntax dialect for the slide CLI. Use ordinary Mermaid flowchart source for portable diagram *presentation* when the installed Marp engine supports it; Marp Core's Mermaid rendering requires a plugin/dependency and must be tested with the actual pinned engine rather than assumed enabled.

A standard Marp PPTX can rasterize the diagram, so editable native PPTX boxes and connectors remain a **separate, opt-in reconstruction path** using python-pptx. Mermaid arrows do not encode the four-edge anchor choice or the independent arrowhead geometry contract; those remain PPTX-specific parameters, not a modification to the Mermaid grammar. Verify a representative Markdown→Marp render separately from a native editable PPTX geometry fixture, and do not claim one is a lossless round trip of the other.


## Mermaid source preservation and optional Markdown utilities

Treat original Markdown and fenced Mermaid source as the canonical regeneration inputs. Do **not** claim that a rendered PPTX can be parsed back into equivalent Mermaid. For simple diagrams, pass source through to an explicitly verified Marp Mermaid rendering lane without adding a mandatory Markdown parser. Use `vendor/markdown.py` only for optional fence extraction, formatting and source-preservation checks; do not impose its helpers on the basic conversion path.

Keep source hashes and a mapping to generated PPTX artifacts. Native PPTX edge anchors and arrowhead geometry remain an Ironmate/python-pptx concern and should not be encoded as proprietary Mermaid syntax. Add the final one-liner only after a real Markdown+Mermaid→Marp→PPTX proof succeeds; if Mermaid rendering is not enabled by the pinned Marp toolchain, report unsupported instead of silently emitting a non-rendered code block.
