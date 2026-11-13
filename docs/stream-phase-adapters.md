# Standard library stream adapters and verified ladders

`python -S scripts/stream_phase_report.py --image input.pgm` runs the existing
CalibratedTernaryPatch / FiveWaySurveyEngine on binary P5 (maxval 255).
For RAW use `--image input.raw --width 64 --height 64 --channels 1` (or 3).
Dimensions must be positive multiples of eight; truncated or trailing pixels
are errors. RGB uses the explicit approximation (R + 2G + B) / 4.
The CLI reads the file once; the adapter borrows its pixel buffer via memoryview
and yields descriptors. It is not an end-to-end zero-copy or constant-memory
image pipeline. Pixel addressing still uses integer multiplication.

`python -S scripts/stream_phase_report.py --csv seasons.csv --id-col team_season --columns rd bullpen_era`
streams JSON records with separate pos/neg masks plus interleaved spin_board.
CSV requires a seekable, unchanged source: first pass calibrates min/max, second
pass emits records. Hundredths are parsed exactly; missing, malformed or more
precise values fail rather than silently changing data. Constant columns are
neutral. Thresholds are range quarters, not statistical quartiles. All seasons
in the file calibrate together: use a training-only fit for predictive studies.
No bundled illustrative NPB values are described as measured league data.

Add `--ladder-spec classes.json` to emit verified Mermaid and ASCII paths for
CSV records. Example spec (integer masks refer to interleaved features):

```json
{"target":"high_rd","classes":[{"name":"high_rd","must_and":1},{"name":"other"}]}
```

Classes are first-match predicates, supporting must_and, or_masks and forbid_not.
This explicit policy is not the proposed resonance router. BFS searches up to
three flips and 10,000 states, with at most 20 bits. It rejects simultaneous
positive/negative spins. A found path is shortest in this discrete domain;
resource_limit and not_found_within_bound are separate outcomes. Feature-space
edits do not establish realizable image edits, topology changes, baseball rank
changes or causal interventions. Overlapping predicates and OR clauses are
checked through the actual choice function; no greedy minimality claim is made.
The Python API accepts a deterministic router callback and domain validator.

The ladder JSON, router/validator callbacks and bit-name mapping are initialized
once per CSV invocation, before reading rows. Invalid JSON is a CLI error even
for a header-only CSV, with no partial report. Missing observations still reject
ladder generation; the candidate router retains its existing three-valued policy.

Local setup-hoisting comparison (2026-11-01, CPython 3.12.14, Linux x86_64;
baseline `f1238392`, same process and warm filesystem cache):

| CSV rows | Baseline ms | Hoisted ms | Baseline / hoisted |
|---|---:|---:|---:|
| 1 | 0.272 | 0.351 | 0.78 |
| 100 | 3.111 | 1.962 | 1.59 |
| 1,000 | 28.995 | 18.103 | 1.60 |
| 10,000 | 290.102 | 167.622 | 1.73 |

Each cell is the median of seven full `main()` calls, alternating version order;
stdout is captured in StringIO (JSON plus ladder Markdown), not written to disk.
Input is `id,x` with `x = row_index % 3 - 1`; spec is
`{"target":"high","classes":[{"name":"high","must_and":1},{"name":"other"}]}`.
CLI arguments are `--csv rows.csv --id-col id --columns x --ladder-spec ladder.json`.
Both modules were loaded before timing. All output strings matched byte for byte
at every size. These small synthetic timings include CSV calibration, BFS and
rendering, exclude process startup, and are not a general throughput guarantee.
Regression tests separately count one spec read/parse and check callback/mapping
identity across rows, complete-row output, NULL/empty candidate truth values and
ladder rejection, and malformed JSON for empty and populated CSVs.

Redirect stdout to a Markdown report or append it to "$GITHUB_STEP_SUMMARY".
Mermaid rendering depends on the viewer; fenced ASCII is always included as a
fallback. No GitHub workflow, permissions or existing production pipeline is
changed. Aoi can consume the CSV API without NumPy/Pandas, but no Aoi data or
pipeline modification is included. Layer 1–9 completion, reported classification
percentages, timing claims and arbitrary rotation invariance remain unverified.

Verification: `python -m pytest -q tests/test_research.py tests/test_five_way_survey.py`.

## Observability and active sensing extension

Use `--allow-missing --observable-spec classes.json` with CSV input. Empty cells
and literal `NULL` become unobserved; malformed numeric text still fails.
Each measured column marks both interleaved sign bits observed, including a
measured neutral value. Entirely missing columns have no fitted bounds and stay
unobserved. Default missing-value rejection is preserved. Masked records cannot
enter the existing complete-data ladder. The class JSON uses the same `classes`,
`name`, `must_and`, `forbid_not`, `or_masks` fields; width comes from CSV columns.

The new ObservableChoice API returns every compatible class and its strong
Kleene truth value. `unique` means one compatible class, not a proved real-world
label; its predicate may still be unknown. Unobserved active bits are ignored.
No inferred values are inserted into the observation mask or emitted as truth.
An explicit conflict rejects a candidate; insufficient evidence stays unknown.
Contradictory masks, impossible positive OR clauses, duplicate names and
out-of-width masks are rejected. The API accepts feature masks, not pixel
occlusion maps; projecting an occlusion map through FWHT remains future work.

A bounded bit decision index prunes only observed mandatory/prohibited
contradictions. Don't-care candidates go to both branches. Unknown pivots visit
both branches and leaf candidates are deduplicated and fully checked, including
OR clauses. Node budget exhaustion falls back to exact linear leaf evaluation.
This is not an ROBDD and has no universal log(K) depth/time bound. Unobserved
inputs may visit the whole tree. Next probe uses exact one-step branch survivor
counts, including don't-care and OR constraints, with a greedy minimax choice.
No guaranteed halving or globally minimal interrogation depth is claimed.
No recommendation means no single bit guarantees progress for both outcomes;
overlapping classes may remain indistinguishable even after full observation.

Local synthetic check (Python 3.12, 2026-11-01, one 256-query batch per mask,
including candidate evaluation and next-probe calculation; not a speedup claim):

| Observed bits out of 8 | Tree tests | Compatible classes | Mean query ns |
|---|---:|---:|---:|
| 8 | 8 | 1 | 3895 |
| 4 (low bits) | 19 | 16 | 49276 |
| 0 | 255 | 256 | 1142428 |

Dictionary: exact signatures 0..255, must=i, forbid=255 XOR i, leaf_size=1.
This exposes the cost of missing information rather than assuming it disappears.
Tests exhaust all 256 active/observed pairs for a four-bit overlapping dictionary,
compare indexed results with linear Kleene evaluation under three node budgets,
check all 256 complete signatures, full blindness, don't-care XOR counterexamples,
and missing-versus-neutral CSV handling. Combined relevant suite: 47 passed.

Layer 13's approximate angular bins, adaptive refinement and three-offset
alignment are not added here: the claimed arbitrary-angle guarantee and unique
coarse alignment need separate validation. Layers 14/15's supplied performance,
reconstruction and universal log-depth claims are not used as evidence.
