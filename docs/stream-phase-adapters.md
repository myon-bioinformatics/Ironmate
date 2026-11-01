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

Redirect stdout to a Markdown report or append it to "$GITHUB_STEP_SUMMARY".
Mermaid rendering depends on the viewer; fenced ASCII is always included as a
fallback. No GitHub workflow, permissions or existing production pipeline is
changed. Aoi can consume the CSV API without NumPy/Pandas, but no Aoi data or
pipeline modification is included. Layer 1–9 completion, reported classification
percentages, timing claims and arbitrary rotation invariance remain unverified.

Verification: `python -m pytest -q tests/test_stream_phase_report.py tests/test_five_way_survey.py`.
