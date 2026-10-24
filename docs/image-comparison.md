# Comparing PNG upscaling candidates on multiple axes

`image_compare.py` takes a reference PNG, a nearest-neighbor upscaled PNG and a smooth-interpolated PNG of the same size,
sweeps the mix ratio between the two existing images and saves the candidates. It uses only the Python standard library and Ironmate's PNG codec.
It brings no extra dependencies into Image Studio's UI or served files.

```sh
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png --out variants
# example weighting MAE 75% and RMSE 25%
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png --mae-weight 0.75 --out variants-mae75
```

A reference image is required. This does not mean unknown originals can be scored; it is for comparing candidates in reference-based experiments.
Inputs are PNGs up to 32 MiB and 4 MP; inputs of different sizes are rejected.
Limited to the existing stdlib codec's range (8-bit gray/gray+alpha/RGB/RGBA, non-interlaced).
Mix ratios default to 11 steps from 0.0 to 1.0. `--steps` is an even number from 2 to 100, with all candidates totaling at most 16 MP.
Only a new or empty output directory is allowed. Inputs are not modified.

## Outputs and evaluation definitions

- `variant-00.png` etc.: all candidates. The original nearest-neighbor / smooth images are kept as endpoints.
- `mae_priority.png`: the candidate with the lowest mean absolute error (MAE).
- `rmse_priority.png`: the candidate with the lowest root mean square error (RMSE).
- `midpoint.png`: mix ratio 0.5. Being in the middle does not make it best.
- `balanced.png`: the candidate with the highest score under the explicit weights.
- `report.json`: errors for all candidates, input hashes, selection reasons, weights and the Pareto set. Several roles may point to the same image.

RGB is composited onto white, then all pixels × 3 channels are measured on the same 0–255 scale.
Alpha MAE and the count of exactly matching original RGBA pixels are reported separately. If the hidden RGB of fully transparent pixels differs,
display error can be 0 without an exact original RGBA match. This does not replace the existing exact-match/residual evaluation.
Mixing is integer-rounded in premultiplied-alpha 8-bit sRGB. It is not interpolation in linear light and adds no unknown detail.

The auxiliary score is `100 × (1 − (w × MAE + (1 − w) × RMSE) / 255)`. The default `w=0.5` is
a policy of weighting both errors equally, not a perceptual right answer or a universal best.
Changing the weight can change which candidate is chosen. Scores are not renormalized to each candidate set's min/max.
The Pareto set excludes candidates worse on both MAE and RMSE. All candidates are kept separately from the overall score.
Ties are broken by an explicit order of each error, then candidate index.

## Relation to prior logic

`rule_search.py` in PythDRagoras `83a53f60d1b5dec70df841a1104d4c78fbe4a494`
ranks by MCC while keeping precision/recall, fixes candidates before searching, and confirms on separate data.
In Aoi `62ad1e49154121cf237d52de352404c4400e6a55`,
`sakanalytics/league_laboratory.py` and `pythdragoras/score_sensitivity.py` also keep multiple axes, deltas and conditions distinct.
What was adopted here: keeping all candidates, multiple axes, fixing selection conditions and evaluating on separate seeds.
Binary-classification MCC/precision/recall are not repurposed directly for pixel error.

`scripts/check_visual_regression.py` in web-ui `9ab07c0e09cd06209dd795f7a8f9a595da302c36`
handles exact matches by PNG size and SHA-256. It provides no pixel error or candidate interpolation,
so Ironmate's existing `photo_grid.decode_png`, `grid_png.to_png` and `grid_output.write_output` were reused.
No code or Python/JS dependencies from other repos were newly copied.
If this is shared in the future, PNG size, presence of a reference, alpha/background and error definitions would be the contract,
and it would not be treated as loosening web-ui's exact-match check.

The [experiment record](evidence/studio-delivery/tradeoff-report.md) keeps both the original comparison and the separate-seed successes and regressions.

## Choosing with shape, color and loss side by side (optional)

```sh
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png \
  --quality --select-by energy_dice --max-missing-foreground 0 --out variants-quality
```

`--quality` leaves existing candidates unchanged and adds to `quality` in `report.json`, against the same reference image:
IoU, Dice, Energy Dice, Near Field, RGBA similarity, uncorrected missing/extra foreground pixel counts,
and alignment shift and clipping. The shape definition matches the 110-case experiment:
composite onto white, distance from white > 32, reference-fixed forward edge weights, search radius 2.
The default MAE/RMSE report and the four role PNGs are unchanged.
Diagnostics are limited to 1 MP of candidates in total (existing upscaling candidate generation allows 16 MP). No extra dependencies.

`--select-by` chooses from `rgb_mae` / `rgb_rmse` / `balance_score` / `iou` /
`energy_dice` / `near_field` / `rgba_similarity`. The default is the existing Balanced.
The selected source candidate is saved as `quality_selected.png`, and the selected index is also printed to stdout.
`--max-missing-foreground N` caps the uncorrected missing foreground pixel count.
This is loss in the foreground mask; it does not guarantee an exact count of lost information or reversibility.
If no candidate meets the conditions, `selected_index: null` and the exclusion reasons are recorded, and no selected PNG is made.
Undefined Energy Dice values are excluded the same way, with no automatic switch to another metric.
These flags require `--quality`.

`studio_candidate_selection.select_quality()` is the shared API.
It accepts only candidates with the same size and the same SHA-256 of the reference RGBA.
`max_source_clipped_nonfill` can also constrain known clipping during conversion.
Candidates of unknown origin are excluded by this constraint. Conversion history is not inferred from regular input PNGs, so
`source_clipped_nonfill` is `null`. It is handled separately from clipping by alignment.

Tie sets are kept for every metric. Ties in MAE/RMSE/Balanced use the existing secondary error → index;
other metrics use index order. Choosing the first when everything ties does not mean better quality.
`quality.summary.legacy` is the existing MAE/RMSE Pareto set; `quality_pareto` uses the explicit five axes
MAE, RMSE, IoU, Energy Dice and Near Field.
Dice ranks the same as IoU, and RGBA similarity for these opaque images ranks the same as MAE,
so they are not in the default five axes. For transparent images RGBA and displayed RGB error differ, so if needed
specify axes explicitly with `pareto_indices(rows, axes=...)`.
Aligned IoU, which can hide loss, and processing time are not in the default quality Pareto.
Candidates with an undefined axis are excluded from the Pareto computation, and their indices are listed explicitly.

[Cross-check with the 110 cases and reproduction experiments for upscaling and downscaling](evidence/studio-quality-selection/report.md)
records metric overlap, rank reversals, loss under alignment and observed processing time separately.
It is an exploratory reference-based selection, not a human perceptual evaluation or a universal best-quality verdict for unknown images.
