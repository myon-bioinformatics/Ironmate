# Adaptive fingerprint proposal: bounded experimental API

`scripts/adaptive_fingerprint.py` implements lazy 64/256-bit pair matching,
OR coarsening, all tied alignment offsets, masked distances and lossless
64+64 bit interleaving. It is an opt-in API beside the existing two-shell
5-Way phase rings; it does not change detection, calibration or frozen evidence.

```python
from scripts.adaptive_fingerprint import adaptive_match, reduce256
ref, target = 1, 1 << 32
report = adaptive_match(reduce256(ref), reduce256(target), lambda: (ref, target))
assert report['coarse']['distance'] == 0
assert report['fine']['distance'] == 2
```

The caller retains raw features or a fine encoder callback. It is impossible to
recover lost fine features from a 64-bit fingerprint alone. No fine callback is
called for coarse distance above the configured threshold. This pair gate is
not a multiclass top-two confidence margin and cannot recognize unseen decoys.
Both identical empty signatures retain all shifts; they establish no identity.

Coarse ties contribute all local ±1 candidates. All 32 fine shifts are nevertheless
verified, with `local_missed_optimum` exposing unsafe pruning. There is no proof
that three shifts around one coarse optimum contain a fine optimum. Distinct
256-bit occupancy fingerprints can still collide; topology and original pixels
remain necessary for identity verification. Hamming margin and XOR differences
are diagnostics, not calibrated confidence or causal evidence.

`masked_distance` returns mismatches plus common observed-bit count, with an
undefined score for no overlap. Callers must enforce task-specific coverage
and align feature schemas first. Occlusion can also change centroid/radius;
a descriptor mask alone does not solve geometric misregistration. `fuse64` is
lossless storage, not learned cross-modal correspondence or a performance gain.

## Review of the supplied GeminiArgon examples

The supplied tables have no trial inputs, seeds, label traces, hardware or
measurement boundary and are not checked-in measurements. No 98–100% accuracy,
2-microsecond throughput or complete Layer 1–13 integration is established here.

- The proposed angular boundaries 1/8, 3/8, 1/2 are not equal 11.25-degree
  sectors; quadrant reflection also misplaces axes for cyclic rotation. A new
  point encoder must specify nested binning, rational-angle error and axes.
  Existing nearest-16-sector bins are not interchangeable with pair-coarsened
  32-sector bins. This API therefore accepts explicitly nested masks only.
- Chebyshev radius is not invariant under arbitrary spatial rotation. Floored
  centroids and raster rounding add errors; 3/5,4/5 rotation is about 36.87
  degrees, not 33.75. Coordinate controls must measure these separately.
- The demo always builds both resolutions and always runs fine matching. The
  callback gate added here makes lazy fine work observable in a test.
- Power-of-two axis stretching does not correct general shear or perspective,
  and can erase class-relevant aspect ratios. Bridge-vector slicing allocates;
  it is not a zero-copy image patch. Neither gives universal recovery.
- The supplied log histogram does not center data despite its docstring; ties,
  tiny samples and added observations can move quartile thresholds. Robustness
  against one outlier is not exact invariance.
- HEX formatting/splitting allocates. The shown state omits TTL and fingerprint
  dictionaries and conflates zero clauses with empty clause lists. A later
  persistence format needs schema/version, widths, complete states, strict
  validation and semantic round-trip tests. HEX is larger than raw packed bytes.
- Balanced decision trees need discriminative bits and can degrade to deep or
  ambiguous leaves; BDD size can be exponential. Ten tests for every 1000-class
  problem and sub-microsecond Python latency are not guaranteed.

## Validation and next integration boundary

Run `python -m unittest discover -s tests -p test_adaptive_fingerprint.py`.
Tests use independent per-bit rotation enumeration over 100 seeded 256-bit
pairs, a real coarse collision, lazy callback accounting, symmetry, missing
observations, malformed masks and AST operator checks. Kernel source excludes
multiplication, floating division, powers and float constants; it still uses
addition, comparisons, loops and Python objects. This is not bitwise-only
machine code, constant-time execution or a runtime instruction guarantee.

Next work requires a versioned nested point encoder, independently transformed
coordinate fixtures and multiclass holdouts with explicit coverage/abstention.
Compare lazy encoding plus full pipeline timing against always-fine encoding;
report escalation rate and retrieval errors, not invented benchmark targets.
