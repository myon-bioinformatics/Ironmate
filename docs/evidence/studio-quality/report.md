# report.md

## Purpose and reproduction

Follow-up to Ironmate #116, whose implementation was integrated into main by #119.
Base: `7088418a9bf70fd49ac5ac549879ebdcfd5e5e38`. These are diagnostic observations,
not a new image-quality benchmark or a perceptual preference claim.

```sh
# Test-only Playwright (the existing browser CI pins 1.58.2) and Chrome required.
IRONMATE_CHROME=/path/to/chrome node tests/studio_quality_browser.cjs build/studio-quality
# Reuse recorded browser sources; Python stdlib only, no image package or network.
python -S scripts/quality_experiment.py --fixtures docs/evidence/studio-quality/fixtures.json --out build/studio-quality
python -m pytest -q tests/test_quality_experiment.py tests/test_studio_shape_metrics.py tests/test_studio_image_quality.py tests/test_studio_alignment.py
```

Open `dashboard.html` for exact image pairs, sortable scores and separate CPU/score
plots (point size indicates Python allocations). `results.json` contains all samples,
recipes, hashes, scores and costs. Regeneration changes timings; pixel/score agreement
is the regression contract. There is no automatic winner or combined quality score.

## Frozen protocol

- Existing Canvas `pixel-art`, `shapes`, `gradient`, seeds 20261018 and 20261019.
  The reference generator was extracted verbatim from `studio_tradeoff_browser.cjs`
  into a shared function; the old experiment uses it too.
- Existing `docs/evidence/image-studio/demo.png`, reused byte-for-byte to avoid
  font/platform changes in the default Studio scene. This is a stored Studio output,
  not a fresh rendering of the current editor. No external image collection.
- First seed and demo: longest side 64/128; second seed: 64. Aspect ratio preserved.
  Reference preparation uses explicit nearest-neighbor floor coordinates. The
  original browser sources are included and hashed. This is a limited size sweep,
  not a claim about megapixel performance.
- Identity; +1px horizontal translation; 1/4 downsample then nearest upsample;
  5/4 enlargement and centered crop; 5px cell-average mosaic; 3×3 clamp-to-edge box
  blur; middle-third loss of a black 1px horizontal probe; 4-neighbor dilation;
  RGB inversion; +width/8 horizontal translation with clipping. All recipes are
  deterministic; seeds select source content, not a tuned perturbation strength.
  The probe case explicitly uses `original + probe` as its reference, separately
  labelled so it is not confused with untouched source material.
- Translation fill: opaque white, with production `clipped_nonfill` count and
  exact inverse-equality check. Count is relative to this fill; it is not an
  information-theoretic loss count. Enlargement/crop has its own explicit crop
  recipe; its `clipped_nonfill=0` field is a translation-only counter.

## Separate meanings of the measurements

| Family | Input / interpretation | Limit |
|---|---|---|
| Alpha IoU / Aligned IoU | alpha > 0; production RGBA comparison, radius 2 | Fully opaque sources usually have trivial full-canvas masks |
| Foreground IoU / Dice | RGB distance from white >32 after alpha compositing | Background definition matters; not a semantic object mask |
| Foreground Aligned IoU | Production comparison on proxy pixels whose alpha encodes the foreground mask | Search can clip; correction does not improve the original image; radius only 2 |
| RGBA L1 similarity | Original unaligned channels including alpha | Not perceptual color difference; invisible RGB may matter |
| Energy Dice | Reference-frozen integer forward RGB edge differences on white composite | Arbitrary experimental weighting, not independent validation; zero denominator is `null` |
| Symmetric Near Field | Mean of directed exact hits (1) and 4-neighbor hits (1/2) | One-pixel tolerance, not a standard boundary F-score or a replacement for IoU |

IoU and Dice on the same binary masks obey `Dice = 2 IoU / (1 + IoU)` and therefore
have identical rankings, including ties. Empty/empty masks follow the production
convention of 1; this does not demonstrate that a meaningful object was present.
Energy Dice leaves a zero denominator undefined (`null`), never zero-filled.
The weights are fixed from each reference, so swapping images and rebuilding the
weights would be a different experiment even though the weighted-mask formula is
symmetric with fixed weights.

CPU: median of 3 warmed `process_time_ns` measurements, with raw samples.
Memory: a separate warmed call under `tracemalloc`, peak Python allocations, not
RSS, browser memory, or total resident image storage. Prebuilt inputs, masks and
weights are excluded. The three measured API groups are foreground metrics,
alpha/RGBA/alignment, and foreground-proxy alignment; they include shared work and
are **not per-formula microbenchmarks**. They must not be added as an optimized
pipeline estimate. Transform CPU is recorded separately, single sample. IO,
reference preparation, PNG encoding and browser startup are excluded from API
cost. PNG bytes use fixed filter 0 / zlib level 9, and raw RGBA bytes are also given.
CPU model for this recorded run: AMD EPYC 9V74; Python/platform/browser versions
are in `results.json`. Timings are observations, not CI pass/fail thresholds.

## What these metrics cannot decide

There is no human preference ground truth, learned perceptual model, semantic
similarity, downstream task accuracy or COCO mAP here. Smoothing can make a mask
more similar while destroying intended pixel-art edges. Dilation can gain nearby
hits while introducing false foreground. A gradient can retain its full-canvas
mask despite a major color change. Sparse losses can be hidden by image-wide RGBA
averaging. Alignment can hide location errors and bounded-grid losses; always
read the raw IoU, displacement, recipe and image alongside it. No assertion of
restoration or reversibility follows from a high comparison score.

The regression suite independently counts TP/FP/FN for the IoU/Dice relationship,
constructs a ranking reversal for near-field tolerance, verifies clipping and
undefined cases, regenerates all recorded transformations from the original
sources, recomputes all foreground metrics and RGBA errors, and checks a saved
registration case. CPU and allocation values are checked structurally, not pinned.

## Recorded observations (110 cases)

All 110 alpha-mask IoUs and Aligned IoUs are 1 because both inputs are opaque,
including white translation fill. This is a diagnostic failure of that mask choice,
not evidence of unchanged image quality. Foreground results below use threshold 32.

| Source / longest side | Change | Raw IoU | Aligned IoU | Near field | RGBA similarity |
|---|---|---:|---:|---:|---:|
| shapes / 128 | +1px | 0.938076 | 1.000000 | 0.984024 | 0.991368 |
| shapes / 128 | blur | 0.942143 | 0.942143 | 0.985536 | 0.994022 |
| shapes / 128 | contour dilation | 0.919567 | 0.926711 | 0.979892 | 0.994780 |
| pixel-art / 128 | enlargement/crop | 1.000000 | 1.000000 | 1.000000 | 0.835019 |
| pixel-art / 128 | RGB inversion | 1.000000 | 1.000000 | 1.000000 | 0.649226 |
| gradient / 128 | edge clipping | 0.875000 | 0.875000 | 0.939453 | 0.955485 |
| Studio demo / 128×72 | +1px | 0.845125 | 1.000000 | 0.958031 | 0.984300 |

The shapes translation has displacement (-1,0), with no nonwhite clipped pixels.
The Studio-demo translation also aligns perfectly under the foreground mask, but
clips 72 nonwhite pixels and is not exactly invertible. Its near-white background
is below the foreground threshold. A perfect Aligned IoU therefore does not even
guarantee an exact inverse under this mask.

**Agreement.** Every identity scores 1 in all defined comparison columns. IoU and
Dice rankings agree by construction. At 128px, the pixel-art 1/4 down/up sample is
also exactly identical in RGBA: its 8px cells happen to align with the sampling
lattice. This is a conditional property of this fixture and recipe, not general
lossless downsampling. Dilation on already full foreground masks is a no-op.

**Rank reversals.** Compare only variants with the exact same reference hash,
within scenario/seed/size; exclude identity/probe mismatches automatically. Across
396 eligible variant pairs, strict IoU ordering reverses versus Near Field in 7
pairs, Energy Dice in 32, Aligned IoU in 10, and RGBA in 37 (product of signed
score differences < -1e-12; ties excluded). These are descriptive counts, not
statistical evidence or tuning targets.

- shapes / 64, seed 20261018: shift IoU **0.881757** > blur **0.876475**, but
  Near Field shift **0.968582** < blur **0.969119**. Tolerance changes the ordering.
- shapes / 128: blur ranks above shift by raw IoU (0.942143 > 0.938076), while
  aligned shift ranks above blur (1 > 0.942143). Registration changes the question.
- shapes / 128: dilation RGBA **0.994780** > blur **0.994022**, while dilation
  IoU **0.919567** < blur **0.942143**. Pixel error and foreground coverage disagree.
- shapes / 64: down/up Energy Dice **0.828047** > mosaic **0.821176**, while
  down/up IoU **0.748457** < mosaic **0.760504**. Reference weighting matters.

**Undecidable / insensitive.** Pixel-art and gradient full-foreground masks retain
IoU/Dice/Near Field = 1 under several color/spatial distortions. Gradient edge
clipping has Energy Dice = 1 although 2,048 nonwhite pixels are clipped: its edge
weights give the discarded region no weight. No Energy Dice denominator was zero
in these 110 cases; an explicit uniform-image regression verifies `null` behavior.
A thin-line loss in shapes / 128 has RGBA similarity 0.999039 despite a real gap;
large white/background regions dilute image-wide errors. None of these results
establish human preference or a best reconstruction method.

## Compute / storage tradeoffs

Matched square fixtures only, seed 20261018, three scenarios × ten changes;
median across those 30 per-case medians. Memory is median per-case peak, in MiB.
The demo and second seed are excluded from this size comparison.

| Measured API group | 64px CPU ms | 128px CPU ms | 64px peak MiB | 128px peak MiB |
|---|---:|---:|---:|---:|
| Foreground metrics (IoU/Dice/Energy/Near Field together) | 1.524 | 6.309 | 0.907 | 3.626 |
| Alpha/RGBA/registration together | 46.158 | 186.380 | 1.730 | 6.980 |
| Foreground proxy/registration together | 43.878 | 178.816 | 1.605 | 6.479 |

The radius-2 registration groups enumerate 25 displacements and are substantially
more expensive than the mask-metrics group. Increasing square dimensions from 64
to 128 quadruples pixel count; the observed CPU/memory growth is roughly fourfold.
This small sweep cannot establish broader complexity or production latency.
Across the complete dataset, candidate PNGs range from 229–2,612 bytes at longest
side 64, and 432–5,768 at 128. Raw square RGBA storage is 16,384 / 65,536 bytes;
PNG size also depends on texture/compressibility, so fewer bytes is not proof of
better quality. The dashboard retains separate score plots and cost columns;
there is no weighted composite that could conceal these disagreements.
