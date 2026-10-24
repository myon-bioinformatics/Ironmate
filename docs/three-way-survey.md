# 3-Way Survey: prototype auxiliary evaluation of image structure

An experiment in structure evaluation using matrix projections and ternary bitmasks, added to the verification of
pixel-art upscaling, downscaling and restoration. It is used together with the existing exact-pixel and residual checks in `grid_tools.py`.
This experiment's output is a set of patch coordinates; it does not generate smooth RGB images or lost detail.

## Running

Runs on Python 3.10+ with only the standard library. No I/O at import time.

```sh
python -S scripts/littlebit_jev_3way_survey.py --trials 40 --train-trials 4 --large-raster
python -m pytest -q tests/test_three_way_survey.py
```

Writes `report.md`, `results.json` for all trials and 6 SVGs to `build/three-way-survey/`.
In the SVGs, green = match with ground truth, red = false positive, yellow = miss, gray = background.
The JSON saves the code's SHA-256, Python/OS/architecture, seeds, threshold search history,
each trial's TP/FP/FN/TN, IoU, precision/recall, centroid error, five translations,
a hash of the predicted coordinate set, and per-stage timings.

## Method and verification boundaries

This is a research candidate inheriting names such as LittleBit/FairyFuse/Jev suggested by the user.
Equivalence with each paper's implementation has not been confirmed. Script and function names map to the proposal.
It uses no trained model outputs, gradients or predictors, and no XAI fidelity comparison was performed.

| Stage | Implementation | Meaning and limits |
|---|---|---|
| Input | Integer signals of 8 row elements and 8 column elements | The 6 main-evaluation scenarios are synthetic profiles, not real 8×8 pixels |
| Real-pixel adapter | `project_raster`, row and column means of 8×8 blocks | Non-overlapping blocks, dimensions limited to multiples of 8. Not a rank decomposition |
| Encoding | Integer-rounded H8/2 of FWHT, DC removed, AC ternarized | Not an orthonormal rotation; loses absolute brightness, color and some detail |
| Way 1 | Candidate screening by active_spins and the L1 sum of AC | The name `ub_threshold` is kept for compatibility with the proposal. No upper-bound guarantee on the decision score |
| Way 2 | Distance differences under rotation, flip and erasure; 4-neighborhoods at stride 1/2/4 | Ternary L1 distance computed with bit AND/OR/XOR/popcount |
| Way 3 | Matches history coordinates/direction bits against the partner's reverse-direction bits | An independent function that takes no original pixels or bit strings as arguments. No hole filling or surface interpolation |
| Inject | Re-run after injecting blank → a single pattern → a connected 9-point pattern | Dropping isolated noise does not mean consistent fake patterns are caught |

Ternary distance matches `sum(abs(a_i-b_i))` exactly. A positive/negative collision is 2,
and a transition to/from a vacancy is 1. This distance alone does not implement a physics model's Hamiltonian
or thermodynamic behavior.

The multiplication-free and floating-point-free targets are `fwht8_add_only`, `rotate_8bit`,
`fairyfuse_ternary_diff`, `LittleBitTernaryPatch`, `interaction`, `row_offsets`,
`ThreeWaySurveyEngine` and `reconstruct_blind`, checked via the AST.
Coordinate row offsets are also built by addition. The old reconstruction reproducing the proposal, synthetic data,
the real-pixel adapter, and evaluation/timing aggregation do use multiplication and division.
This guarantees nothing about operations inside the Python interpreter or hardware instruction counts.
The candidate skip rate after encoding differs from the fraction of total work skipped or a speedup.

## Evaluation conditions corrected from the proposal

1. Erasure perturbation is measured as `abs(collapse_distance-original_distance)`.
   The proposal's `collapse_distance >> 1` was not a difference from the original state.
2. A neighbor merely existing in history is not enough; the reverse-direction bit at the same stride is also required.
   x/y bounds are checked before converting to a one-dimensional coordinate.
3. Sensitivity comparison translates **the same fixed coordinate set** on a torus.
   The point-acceptance conditions do not change between original and shifted. Point counts are kept exactly, and ground truth does not move.
   Values filtered under the proposal's separate conditions are recorded separately as `legacy_shift_iou`.
4. Centroids are not truncated to integers; L1 error is reported in patch units. With no centroid, it is `None`.
   IoU and FP/FN are reported alongside, so different outlines with the same centroid are not hidden.
5. "Noise disappears" and "smooth boundaries are always rescued" are not pass conditions.
   Compared with a stride-1-only ablation, both improvements and regressions are kept.

Bit rotation is a permutation of FWHT coefficients, not a spatial shift of the original pixels.
Shift amounts in the sensitivity comparison are in patch units. On a torus, points leaving one edge wrap to the other.
With periodic patterns or false detections the IoU difference can be zero or negative, so no pass threshold is set on sensitivity drop.

## Tuning and Monte Carlo design

With training seed `20261017` and 4 trials per scenario, the following 12 configurations are compared.

- deadzone_shift: 2 / 3
- ub_threshold: 26 / 64
- min_links: 1 / 2 / 3
- max_diff: fixed at 4

The configuration with the highest mean IoU on the training side is chosen and fixed.
Then unused seeds `20261018` and `20261019` are evaluated with 40 trials each.
There is no re-tuning of thresholds after looking at the evaluation side.
Random numbers for each seed, scenario and trial are derived independently from SHA-256, so changing execution order does not change inputs.
The random stream differs from the proposal, but the signal generation distribution and the 6 shapes are kept.

Four configurations are compared: the proposed method, the corrected-evaluation defaults, the corrected version tuned on the training side, and stride 1 only.
Each configuration has 480 trials and 491,520 patches; the evaluation totals 1,920 trials and 1,966,080 patches.
On top of this are 288 training trials, 294,912 patches and an optional 12 MP raster measurement.
Shapes and signal distributions are shared, so agreement on unused seeds is not proof of generalization to unknown real images.

Timing separates synthetic generation, encoding, search/reconstruction and their total.
The main evaluation total excludes IoU computation and JSON/SVG writing.
The 12 MP measurement builds a real 4000×3000 grayscale array and also times the row/column projections.
JPEG/PNG decoding, RGB conversion and measurement on real smartphones are not included.
Timing depends on load in the execution environment and the Python version, so it is not a CI pass/fail criterion.

## Connection to image restoration evaluation

For the existing `pixel_grid.render` → `grid_tools.resize` 32→64→32 path,
pixel matches and matches of the structure set through this real-pixel adapter are checked.
The existing check of zero residual on original pixels is primary; this feature match is auxiliary.

As an explicit counterexample, an 8×8 checkerboard alternating values 1/255 and a uniform 128 have
the same row/column means and so the same encoding. Information is lost before ternarization.
This metric alone cannot judge unevenness, smoothness, color or detail in restoration.
That an injected connected fake pattern passes the structure evaluation is also kept in the control experiment and regression tests.

## CI

`.github/workflows/verify_3way_survey.yml` measures on related PRs, related pushes to main, manual runs,
and every morning at 08:00 JST. The schedule takes effect once it is on main.
Permissions are contents:read, with a 15-minute timeout. Markdown goes to the Job Summary and JSON/SVG to an artifact.
No pipes that swallow failures are used; exceptions exit nonzero.
Regression tests and JUnit are automatically included in the existing `mcp-tests.yml` and use the shared JUnit collection path.

For measured results see the [first CPU measurement](evidence/three-way-survey/report.md).

## First reading

The values chosen on the training side are `deadzone_shift=3, ub_threshold=64, min_links=2, max_diff=4`.
The table below aggregates 40 trials each on the 2 unused seeds. FP/FN are totals over 80 trials.

| Scenario | Proposed IoU | Corrected default IoU | Tuned IoU | Tuned FP/FN | Stride 1 only IoU |
|---|---:|---:|---:|---:|---:|
| Dense Object | 99.20% | 99.35% | 100.00% | 0/0 | 100.00% |
| Thin Skeleton | 96.49% | 97.67% | 100.00% | 0/0 | 100.00% |
| Hollow Ring | 97.56% | 98.33% | 100.00% | 0/0 | 97.37% |
| Smooth Gradient | 98.60% | 98.40% | 100.00% | 0/0 | 100.00% |
| High Noise Dark | 91.82% | 90.97% | 99.74% | 30/0 | 100.00% |
| Multi Scale Clusters | 98.53% | 98.94% | 100.00% | 0/0 | 100.00% |

The correction alone did not improve every metric. Threshold tuning on the training side had a large effect.
Stride 1 alone misses 320 points on the ring, while false positives on dark noise drop to 0.
Smooth Gradient gives the same result with stride 1, so multi-stride is not shown to be
necessary for this input. Per-shape benefits and costs are kept, and adoption is not based on the overall mean alone.

In the injection control, it detected 0 points for blank, 0 for a single injection and 9 for a connected 9-point injection.
Connected fake patterns pass, so structural consistency cannot stand in for semantic correctness.

`results.json.gz` is compressed raw data for all trials; `summary.json` holds the summary and
the raw data's SHA-256. Re-runs can compare accuracy and prediction hashes, but matching processing times is not required.

## Additional holdout separating shapes and signal distributions

Input families not in the existing 6 scenarios or the threshold search are verified with a separate
`scripts/survey_holdout.py`. It imports the existing engine and fixes the first measurement's
`deadzone_shift=3, ub_threshold=64, min_links=2, max_diff=4` and stride 1/2/4.
No re-tuning, and no replacing the original scenarios, counterexamples or measurement evidence.
Separately from Aoi's exact FWHT, the integer rounding of H8//2 here is kept.

```sh
python -S scripts/survey_holdout.py --trials 3 --output build/survey-holdout
python -m pytest -q tests/test_three_way_survey.py tests/test_survey_holdout.py
```

- 3 new shape families: a comb with repeating notches, a plate with 9 holes, and a 1-point-wide meandering path that wraps at the image edge
- 4 new signal families: per-patch phase mixing, low-contrast quantization with amplitude 1/2/3/4/6/8, impulse noise replacing each coefficient with 0/255 with probability 0.12, and a random walk with correlated adjacent components
- Controls: the existing Dense Object shape and signal, 3 conditions changing only the shape, 4 changing only the signal, and 12 changing both
- Unused seeds 20261020/20261021, 3 trials per condition and seed, 32×32 patches; 120 cases and 122,880 patches in total. Horizontal/vertical flips of shapes are fixed in advance by trial number, and ground-truth coordinates do not change with the signal family

"Unknown" here is relative to the existing 6 scenarios and their tuning; it does not indicate generalization to natural images
or being unused in other research. Once the results have been read, this data becomes a regression set
and must not be reused as an independent holdout for evaluating later tuning.

### Measurements vs failures

The [additional measurement report](evidence/survey-holdout/report.md) and
[summary and hashes for all cases](evidence/survey-holdout/summary.json) are saved.
The 18 cases changing only the shape had 100% IoU. On the other hand, fixing the Dense Object shape and
changing the signal distribution gave mean IoU of 98.44% for phase mixing, 9.11% for low contrast,
66.63% for 0/255 outlier injection and 27.62% for the random walk.
Some shape × signal combinations have IoU 0; precision and centroid with no detections are kept as `null`.
These results are limited to these synthetic profiles and are not a universal accuracy guarantee.

False detections and misses are saved as `observed_mismatch` and are not themselves treated as failures of the experiment code.
Regression tests pin observed values and input hashes to detect unannounced changes in results.
Invalid input, aggregation inconsistencies, reconstruction mismatches from history, engine exceptions and JSON serialization of non-finite values
are handled separately as failures. Known rounding loss, misses of isolated legitimate points, projection collisions
and connected fake patterns passing are not erased by a 100%-match pass condition.

`results.json.gz` in the output directory saves all input vectors, ground-truth coordinates and predicted coordinates.
`summary.json` keeps, for the same cases, the seed, derived seed, SHA-256 of input/ground truth/prediction,
TP/FP/FN/TN, IoU, precision/recall and centroid error. The compressed full input for the default run is
about 1.6 MB; only the summary and report are kept in the repository, and the rest is regenerated at run time.
Reproducibility can be checked with the engine/harness SHA-256 and the SHA-256 of all records.
Records excluding the environment fields are deterministic; matching timings is not required.

Tests cover the standard-library-only CLI, re-running from saved input, independent per-patch aggregation,
a ban on calling tuning, non-matching with the original shapes, properties of the input families and exception propagation.
They are automatically included in the existing regular pytest; no new schedule or workflow changes are added.

## Additional experiment: exact hole counting and phase rings

The [5-Way topology and phase-ring experiment](five-way-survey.md) is an additional single-file experiment verifying
calibration, fixed-point iteration, hole counts and 8/16-direction rings.
It records independent BFS cross-checks over all 4×4 configurations, the distinction between 90-degree and arbitrary-angle rotation, and measured failure cases.
The existing main evaluator, fixed holdout and evidence are unchanged.
