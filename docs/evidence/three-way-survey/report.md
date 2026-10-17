# 3-Way Survey CPU experiment

Synthetic row/column profiles, not natural images. IoU measures patch support, not restored pixels.

Runtime: `3.12.14 Linux-6.18.55-x86_64-with-glibc2.39 x86_64`

Train seed: 20261017; held-out seeds: (20261018, 20261019); trials/scenario/seed: 40; grid: 32×32 patches.
Frozen config: `{'deadzone_shift': 3, 'ub_threshold': 64, 'min_links': 2, 'max_diff': 4}`. Selection objective: train mean IoU; test labels never tune thresholds.

Values below are averages; FP/FN are totals across trials. Time includes generation + encoding + survey.

## supplied_reference

| Scenario | Skip% | IoU% | Precision% | Recall% | FP/FN | Shift drop pp | CoM L1 patches | ms/image |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dense_Object | 63.56 | 99.20 | 99.20 | 100.00 | 187/0 | 35.43 | 0.061 | 15.27 |
| Thin_Skeleton | 72.47 | 96.49 | 96.49 | 100.00 | 538/0 | 61.24 | 0.184 | 12.58 |
| Hollow_Ring | 75.35 | 97.56 | 97.56 | 100.00 | 306/0 | 64.15 | 0.119 | 12.38 |
| Smooth_Gradient | 75.78 | 98.60 | 98.60 | 100.00 | 165/0 | 45.36 | 0.083 | 12.68 |
| High_Noise_Dark | 67.12 | 91.82 | 91.82 | 100.00 | 1040/0 | 40.31 | 0.396 | 14.52 |
| Multi_Scale_Clusters | 71.49 | 98.53 | 98.53 | 100.00 | 233/0 | 54.20 | 0.104 | 13.68 |

Raw JSON includes every trial, seed, mask hash, IoU dispersion, missing centroids, stage timing and five shift offsets.

## corrected_default

| Scenario | Skip% | IoU% | Precision% | Recall% | FP/FN | Shift drop pp | CoM L1 patches | ms/image |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dense_Object | 63.56 | 99.35 | 99.35 | 100.00 | 153/0 | 35.68 | 0.057 | 16.23 |
| Thin_Skeleton | 72.47 | 97.67 | 97.67 | 100.00 | 354/0 | 62.40 | 0.152 | 12.72 |
| Hollow_Ring | 75.35 | 98.33 | 98.33 | 100.00 | 208/0 | 64.98 | 0.105 | 12.66 |
| Smooth_Gradient | 75.78 | 98.40 | 98.40 | 100.00 | 189/0 | 45.28 | 0.101 | 12.99 |
| High_Noise_Dark | 67.12 | 90.97 | 90.97 | 100.00 | 1156/0 | 40.42 | 0.441 | 14.26 |
| Multi_Scale_Clusters | 71.49 | 98.94 | 98.94 | 100.00 | 168/0 | 54.68 | 0.107 | 15.20 |

Raw JSON includes every trial, seed, mask hash, IoU dispersion, missing centroids, stage timing and five shift offsets.

## corrected_tuned

| Scenario | Skip% | IoU% | Precision% | Recall% | FP/FN | Shift drop pp | CoM L1 patches | ms/image |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dense_Object | 71.78 | 100.00 | 100.00 | 100.00 | 0/0 | 36.26 | 0.000 | 14.67 |
| Thin_Skeleton | 82.03 | 100.00 | 100.00 | 100.00 | 0/0 | 64.71 | 0.000 | 11.97 |
| Hollow_Ring | 85.16 | 100.00 | 100.00 | 100.00 | 0/0 | 66.67 | 0.000 | 12.32 |
| Smooth_Gradient | 85.94 | 100.00 | 100.00 | 100.00 | 0/0 | 46.81 | 0.000 | 12.18 |
| High_Noise_Dark | 75.51 | 99.74 | 99.74 | 100.00 | 30/0 | 46.52 | 0.025 | 13.14 |
| Multi_Scale_Clusters | 81.05 | 100.00 | 100.00 | 100.00 | 0/0 | 55.76 | 0.000 | 12.91 |

Raw JSON includes every trial, seed, mask hash, IoU dispersion, missing centroids, stage timing and five shift offsets.

## corrected_tuned_stride1

| Scenario | Skip% | IoU% | Precision% | Recall% | FP/FN | Shift drop pp | CoM L1 patches | ms/image |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dense_Object | 71.78 | 100.00 | 100.00 | 100.00 | 0/0 | 36.26 | 0.000 | 12.93 |
| Thin_Skeleton | 82.03 | 100.00 | 100.00 | 100.00 | 0/0 | 64.71 | 0.000 | 11.74 |
| Hollow_Ring | 85.16 | 97.37 | 100.00 | 97.37 | 0/320 | 64.63 | 0.000 | 12.73 |
| Smooth_Gradient | 85.94 | 100.00 | 100.00 | 100.00 | 0/0 | 46.81 | 0.000 | 13.84 |
| High_Noise_Dark | 75.51 | 100.00 | 100.00 | 100.00 | 0/0 | 46.81 | 0.000 | 13.82 |
| Multi_Scale_Clusters | 81.05 | 100.00 | 100.00 | 100.00 | 0/0 | 55.76 | 0.000 | 13.78 |

Raw JSON includes every trial, seed, mask hash, IoU dispersion, missing centroids, stage timing and five shift offsets.

## Injection control

`{'empty_detected': 0, 'isolated_injected_detected': 0, 'coherent_9_patch_injected_detected': 9}`

A coherent injected texture can pass: structure consistency cannot establish semantic truth.

## Raster measurement

4000×3000 real grayscale pixels; 187,500 patches; IoU 100.00%.

| Stage | ms |
|---|---:|
| generation_ms | 163.70 |
| projection_ms | 1629.23 |
| encoding_ms | 1046.67 |
| survey_ms | 716.63 |
| end_to_end_ms | 3556.24 |

Single synthetic raster, excludes decoding and metric calculation; not a natural-image accuracy benchmark.

## Limits

No claim of GPU/XAI replacement, physical Hamiltonian, certified pruning bound, image synthesis, or 12MP millisecond performance.
Skip occurs after projection/FWHT/encoding; its cost is not zero. H8/2 is rounded, not orthonormal.
Shift uses a torus to preserve cardinality and may have zero/negative drop for periodic or incorrect masks; drop is not a pass gate.
The proposal's original shifted-mask score is stored separately as legacy_shift_iou; it is not a pure translation.
