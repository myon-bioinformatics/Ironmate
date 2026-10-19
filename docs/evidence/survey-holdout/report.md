# report.md

# Frozen shape/signal-family holdout

Synthetic row/column profiles; patch-support IoU, not pixel restoration or natural-image generalization.

Config: {'deadzone_shift': 3, 'ub_threshold': 64, 'min_links': 2, 'max_diff': 4}; strides: [1, 2, 4] (no tuning).
Seeds: [20261020, 20261021]; trials/seed/pair: 3; grid: 32x32; cases: 120.
Engine SHA-256: b39984a0fa3bcce7216adaabc1381997a22efe622726b61269b1892aadfde6c7
Harness SHA-256: ce694f1e80deaf5b8b97600f5c8bc62d892e1644bd6a2857db4bb8fa92c91334
Records SHA-256: 7acf010a5d5a37fc0deddc1d4c3a6bce3cbba8b96d8282c0dc70378aef6cd520

Reference uses the original dense shape/signal; shape-only and signal-only controls isolate each change.
Families were absent from the original six-scenario generator/tuning. These results now form a regression set, not a reusable unseen validation set.

| Panel | Shape | Signal | Cases | Mean IoU | Minimum IoU | FP | FN | Exact cases |
|---|---|---|---:|---:|---:|---:|---:|---:|
| reference | dense_reference | reference | 6 | 1.000000 | 1.000000 | 0 | 0 | 6 |
| signal_only | dense_reference | phase_mixture | 6 | 0.984429 | 0.979239 | 0 | 27 | 0 |
| signal_only | dense_reference | quantized_low_contrast | 6 | 0.091119 | 0.062284 | 0 | 1576 | 0 |
| signal_only | dense_reference | impulsive_tail | 6 | 0.666317 | 0.612795 | 52 | 544 | 0 |
| signal_only | dense_reference | correlated_walk | 6 | 0.276240 | 0.256055 | 0 | 1255 | 0 |
| shape_only | concave_comb | reference | 6 | 1.000000 | 1.000000 | 0 | 0 | 6 |
| shape_and_signal | concave_comb | phase_mixture | 6 | 0.909483 | 0.883621 | 0 | 126 | 0 |
| shape_and_signal | concave_comb | quantized_low_contrast | 6 | 0.034483 | 0.000000 | 0 | 1344 | 0 |
| shape_and_signal | concave_comb | impulsive_tail | 6 | 0.605088 | 0.546559 | 81 | 501 | 0 |
| shape_and_signal | concave_comb | correlated_walk | 6 | 0.139266 | 0.099138 | 1 | 1198 | 0 |
| shape_only | perforated_slab | reference | 6 | 1.000000 | 1.000000 | 0 | 0 | 6 |
| shape_and_signal | perforated_slab | phase_mixture | 6 | 0.982353 | 0.976471 | 0 | 63 | 0 |
| shape_and_signal | perforated_slab | quantized_low_contrast | 6 | 0.083754 | 0.065546 | 0 | 3271 | 0 |
| shape_and_signal | perforated_slab | impulsive_tail | 6 | 0.683447 | 0.658940 | 47 | 1098 | 0 |
| shape_and_signal | perforated_slab | correlated_walk | 6 | 0.240443 | 0.201342 | 3 | 2711 | 0 |
| shape_only | border_serpentine | reference | 6 | 1.000000 | 1.000000 | 0 | 0 | 6 |
| shape_and_signal | border_serpentine | phase_mixture | 6 | 0.866890 | 0.832215 | 0 | 119 | 0 |
| shape_and_signal | border_serpentine | quantized_low_contrast | 6 | 0.019016 | 0.000000 | 0 | 877 | 0 |
| shape_and_signal | border_serpentine | impulsive_tail | 6 | 0.557742 | 0.465409 | 58 | 364 | 0 |
| shape_and_signal | border_serpentine | correlated_walk | 6 | 0.081655 | 0.040268 | 0 | 821 | 0 |

## Interpretation and failure policy

Phase mixtures change neighboring ternary signs; low amplitudes can fall below the frozen energy/deadzone gates; bounded 0/255 impulsive contamination alters foreground and background; random walks change AC structure. Misses and false positives are retained observations.
An accuracy mismatch is not a harness failure. Invalid fixtures, non-finite serialization, broken accounting/history, or engine exceptions fail execution. No all-100%-IoU, positive-shift-drop or runtime gate is imposed.
The CLI writes build/survey-holdout/results.json.gz with every profile, label and prediction, seeds and hashes. The raw archive is generated, not checked in beside this report. summary.json retains per-case fingerprints and outcomes. Gzip uses mtime=0; floating-point timing is absent.
Reproduce the default archive and report: python -S scripts/survey_holdout.py --trials 3 --output build/survey-holdout. Preserve the archive separately for replay independent of future generator versions.
The prior H8//2 rounding, projection collision and connected false-pattern counterexamples remain unchanged. No engine changes, new scheduled CI or Aoi implementation changes are included.
