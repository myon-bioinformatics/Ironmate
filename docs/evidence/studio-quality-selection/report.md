# Cross-checking upscaling candidate selection with the 110-case quality evaluation

2026-10-19. Base is main `b91fbcb52885c10d5d7cb69ff42f6718103d66ca`.
The [original 110-case experiment](../studio-quality/report.md) and
[existing upscaling candidate selection](../../image-comparison.md) are connected on the same reference images.
[All candidates, per-metric tie sets, Pareto sets and processing cost](results.json) are saved.
Human preference and the ground truth of perceptual quality are not measured. Selection is an oracle that saw the reference, not learning or independent evaluation of a policy fixed for unknown images.

## Reproduction

```sh
# No network, browser or extra image libraries needed. Specify a new/empty output directory.
python -S scripts/quality_selection_experiment.py --out build/quality-selection
python -m pytest -q tests/test_studio_candidate_selection.py tests/test_image_compare.py tests/test_quality_experiment.py tests/test_studio_shape_metrics.py tests/test_studio_image_quality.py tests/test_studio_alignment.py
# On the original 256px upscaling example, prioritize Energy Dice and constrain uncorrected missing foreground to 0.
python -S image_compare.py \
  --reference docs/evidence/studio-delivery/tradeoff-original/reference.png \
  --nearest docs/evidence/studio-delivery/tradeoff-original/nearest.png \
  --smooth docs/evidence/studio-delivery/tradeoff-original/smooth.png \
  --quality --select-by energy_dice --max-missing-foreground 0 --out build/quality-choice
```

The existing MAE/RMSE/Balanced selection formulas and tie handling were extracted into shared functions and reused by both experiments.
The existing four roles, 11 candidates, PNGs and normal JSON format are kept. Diagnostics and
`quality_selected.png` are added only with `--quality`. Original images are not modified. CLI details are in the [usage guide](../../image-comparison.md).

## Comparison scope and overlapping metrics

The 110 cases' PNGs are read back, and sizes and reference/candidate RGBA hashes are matched.
The original foreground metrics and RGBA similarity were recomputed and confirmed to match the record before reusing alignment and API cost.
Newly computed: RGB MAE/RMSE, Balanced, uncorrected missing/extra foreground pixels, and clipping by the alignment operation itself.
Comparison groups are split by scenario, seed, size and reference RGBA hash. References with added probes form separate groups.

The 396 same-reference pairs include the identity transform and were matched against the same population as the original experiment.
Explicit identity transforms are excluded from selection/Pareto. Probe groups have only one candidate, so no ranking among candidates is possible.
Cases where dilation or a downscale round-trip happens to match the original are not removed; their tie sets are recorded.

| Metric pair | Relation | Handling in this experiment |
|---|---|---|
| IoU / Dice | `Dice=2*IoU/(1+IoU)` on the same binary mask | 0 rank reversals. Not counted as separate independent evidence |
| RGB MAE / RGBA similarity | `RGBA=1-3*MAE/1020` when every pixel is opaque | Same ranking across the 110 cases. A counterexample with differing hidden RGB in transparent pixels is tested |
| Alpha IoU | 1 in all 110 cases | Useless for detecting changes in opaque images |
| IoU / Energy Dice / Near Field | Differ in area, reference edge weights and 1px neighborhood tolerance | Individual selections and reversals are kept |
| Raw IoU / Aligned IoU | Comparison including misalignment / comparison after search shifts position | Loss and shift are reported alongside; one does not replace the other |

The equal ranking of RGB MAE and RGBA similarity holds for these opaque images.
For transparent images, RGB error after compositing onto white is not the same as channel error on the original RGBA.

A strict reversal against IoU is a product of signed utility differences `< -1e-12`; ties, tiny differences and undefined values are counted separately.
MAE/RMSE are converted so that higher is better before comparing. The 396 pairs are not mutually independent samples.

| Compared with | Rank reversals vs IoU |
|---|---:|
| RGB MAE (ascending) / RGBA similarity (descending) | 37 each |
| RGB RMSE (ascending) | 35 |
| Balanced (descending) | 34 |
| Energy Dice | 32 |
| Near Field | 7 |
| Aligned IoU | 10 |
| Uncorrected missing foreground pixels (ascending) | 48 |

## Candidate selection from the 110 cases

An excerpt for shapes, seed 20261018, 128px, excluding the identity transform.
No single quality ranking is built; the existing selections are applied to the same candidate pool.

| Candidate | RGB MAE | RGB RMSE | Balanced | IoU | Energy Dice | Near Field | RGBA similarity | Uncorrected missing foreground |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| +1px shift | 2.934774 | 18.225269 | 95.850972 | 0.938076 | 0.870158 | 0.984024 | 0.991368 | 141 |
| 3×3 blur | 2.032654 | 8.619097 | 97.911421 | 0.942143 | 0.882496 | 0.985536 | 0.994022 | 0 |
| Outline dilation | 1.774801 | 14.244853 | 96.858891 | 0.919567 | 0.869461 | 0.979892 | 0.994780 | 0 |

MAE/RGBA choose dilation; RMSE/Balanced/IoU/Energy/Near Field choose blur.
Both blur and dilation remain in the existing MAE/RMSE Pareto and in the five-axis quality Pareto.
At 64px, MAE/RMSE/Balanced/Near Field choose blur and IoU/Energy choose the +1px shift.
Even within one image kind, the choice changes with size and goal; no uniformly best transform can be determined.

## Applying to the actual 11 upscaling candidates

The existing 256px reference, nearest-neighbor and smooth-interpolation PNGs are read as-is, and 11 candidates with mix ratios 0–1 are regenerated.
The original MAE/RMSE selections, every candidate's values and the Pareto set match the saved results.

| Selection policy | Smooth ratio | RGB MAE | RGB RMSE | IoU | Energy Dice | Near Field | Uncorrected missing foreground |
|---|---:|---:|---:|---:|---:|---:|---:|
| MAE / RGBA | 0.0 | 14.497630 | 36.023626 | 0.892017 | 0.867378 | 0.949509 | 90 |
| IoU / Energy / Near Field | 0.3 | 15.056666 | 33.237604 | 0.892722 | 0.887132 | 0.950000 | 0 |
| Midpoint | 0.5 | 15.440592 | 31.883027 | 0.879580 | 0.885771 | 0.943435 | 0 |
| Balanced | 0.8 | 16.094147 | 30.737891 | 0.859701 | 0.885771 | 0.933413 | 0 |
| RMSE | 0.9 | 16.307892 | 30.612404 | 0.856215 | 0.885771 | 0.931655 | 0 |

In this upscaling example both the MAE/RMSE Pareto and the five-axis Pareto keep 0.0–0.9.
"Midpoint" and "Balanced" are not necessarily best on shape metrics either, and the shape-first 0.3 also has more color error than MAE-first 0.0.
Constrained selection only picks an existing candidate; it does not redraw the image or infer the original's detail.

## Additional comparison of downscaling and smoothing

In the 110 cases, `shrink_expand` is nearest-neighbor restoration after 1/4 downscaling, and `enlarge_crop` is 5/4 upscaling plus a center crop.
These are not called an evaluation of general pure downscaling. Separately, an experiment was fixed from three existing sources as follows.

- Prepare seed 20261018 pixel-art / shapes / gradient at 64px with the existing floor nearest-neighbor.
- Make that known reference 128px by 2×2 block duplication, and add the same 3×3 clamp blur.
- Downscale the same 128px input to 64px with floor nearest-neighbor or 2×2 area averaging (integer floor).
- Mix these two candidates in 11 steps with the existing premultiplied mixing and compare against the fixed 64px reference.

This includes the premise of an artificial block structure. No generalization to natural images, arbitrary scale factors or browser interpolation is made.
0 = nearest-neighbor downscaling, 1 = area-average downscaling; do not confuse this table's mix ratio with the upscaling smooth ratio.

| Kind | MAE priority | RMSE priority | Balanced | IoU / Near Field | Energy Dice | MAE/RMSE Pareto | Five-axis Pareto |
|---|---:|---:|---:|---|---|---|---|
| pixel-art | 0.8 | 1.0 | 1.0 | All 11 candidates tie | All 11 candidates tie | 0.8, 1.0 | 0.8, 1.0 |
| shapes | 1.0 | 1.0 | 1.0 | 1.0 | 0.2 | 1.0 | 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0 |
| gradient | 0.8 | 0.8 | 0.8 | All 11 candidates tie | All 11 candidates tie | 0.8 | 0.8 |

For shapes, 1.0 has RMSE=8.887700 and Energy=0.891583, while 0.2 has RMSE=11.304897 and Energy=0.947728.
Area error and reference edge weights serve different goals, so the five-axis Pareto is wider than the MAE/RMSE Pareto.
Index 0 chosen on an all-tie metric is a mechanical decision by index, not a quality improvement.

## Loss and alignment

Studio demo, 128×72, +1px shift has Aligned IoU=1, but 72 non-white pixels are clipped during the transform and are not recovered by the inverse.
A matching alignment is not taken as proof that information was preserved.

| Field | Meaning |
|---|---|
| `missing_foreground` / `extra_foreground` | Missing / extra foreground mask in uncorrected coordinates. Includes color and threshold changes |
| `source_clipped_nonfill` / `source_inverse_exact` | Clipping by a known forward-shift recipe / exact inverse match with the original reference |
| `registration_clipped_nonfill` / `registration_inverse_exact` | Whether the comparison alignment clips the candidate itself / can be undone back to the candidate |
| `crop_discarded_canvas_pixels` | Number of pixel positions discarded by crop from the enlarged canvas. Does not mean how many distinct pieces of original information were lost |

The original experiment's crop `clipped_nonfill=0` is a shift-only counter.
Here `source_clipped_nonfill` is `null` for anything other than shifts and is not evidence of "no loss".
The past conversion history of regular PNG input is also unknown, so it is `null`.
The `max_source_clipped_nonfill=0` constraint excludes unknown candidates. Aligned IoU does not lift the constraint.
The original experiment's example where Energy Dice=1 still misses clipping at a gradient's edge is kept too.

## Processing time, memory and selection

In the original experiment, transform CPU was measured once, and the three API groups each recorded the median of 3 runs after an independent warmup plus tracemalloc.
Existing values are reused as-is, and time/memory of overlapping API groups are not summed.
Here `diagnostic_cpu_ms` is a single CPU measurement of the whole call, including input conversion, masks, weights, errors, alignment and loss,
and differs from the measurement scope of the original API groups. Sweep CPU includes candidate generation and RGB error and is not called the transform alone.
For the additional downscaling, endpoint transform CPU is reported separately and not extrapolated into a transform time for all mixed candidates.
So the sweep's `transform_cpu_ms` is `null`, and the cost Pareto lists undefined indices explicitly.

Original observations for shapes at 128px: shift 17.248 ms, blur 91.685 ms, dilation 13.596 ms.
The foreground metric groups took 2.454 / 2.432 / 2.778 ms respectively, with peak allocation of 1,082,584 bytes for each.
Blur, chosen by Balanced, has higher transform CPU than dilation in this observation.
Recorded transform CPU vs IoU shows rank reversals in 122 of 396 pairs, but single-measurement rankings are not a performance guarantee.

The quality Pareto has five axes: MAE/RMSE/IoU/Energy/Near Field.
Separately, a six-axis cost Pareto adding observed transform CPU is recorded, keeping slow candidates instead of removing them.
For shapes at 128px, the quality Pareto has 2 candidates and the cost Pareto has 6.
Compute cost weights are not implicitly mixed into quality; the user specifies goals and limits.

## Regression test contract and limits

Tests check existing values, roles and PNG behavior; hash/metric matching for the 110 cases; reversal counts for the 396 pairs; counterexamples to overlapping metrics with transparent images;
rejection of mismatched references; loss constraints; undefined Energy; ties and strict Pareto; and the saved 72-pixel loss.
The four 11-candidate sweeps are regenerated every time, and pixel hashes, each metric, selections and Pareto are matched against the saved record.
CPU thresholds and rankings of newly measured times are not pinned.

The image corpus, background threshold, scale factors and transforms are limited. Human perceptual evaluation, task accuracy and best selection on unknown images are unverified.
This change keeps existing transforms while making "what was chosen under which metric and constraint" reproducible in reference-based experiments.
