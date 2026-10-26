# 5-Way: topology and phase-ring experiment

Run the entire experiment from one Python file with no installed dependencies:

```sh
python -S scripts/littlebit_jev_5way_survey.py --trials 25
python -m pytest -q tests/test_five_way_survey.py
```

The default output directory is `build/five-way-survey/`. `results.json` retains
all 200 trials, seeds, truth/prediction coordinates, TP/FP/FN, thresholds,
convergence counts, topology, temporal deltas, and separate encoding/survey
timings. `report.md` includes the eight-scenario table, phase-ring comparisons,
Venn counts, eight support maps, Boolean probe traces, sufficient-support layers,
and coordinate verification of ring-suggested rotations. Each scenario/trial derives its own RNG seed
from SHA-256, independent of iteration order. Source digest and runtime environment
are recorded. Exceptions fail the command; low observed accuracy does not.

This standalone experiment complements [the original survey](three-way-survey.md).
It does not change that engine, its selected thresholds, original evidence or the
frozen holdout benchmark. It lives in Ironmate, where the supplied 3-Way and
5-Way work already exists. No Aoi research results or child trees are modified.
The same scheduled workflow runs both experiments and preserves both artifacts;
the existing pytest/JUnit workflow collects the new tests. There is no additional
daily schedule.

## Exact topology: foreground 8, background 4

`compute_bitboard_topology_and_betti` counts foreground sites V, horizontal and
vertical edges, **isolated** diagonal pairs E, and filled 2x2 faces F. A diagonal
edge is added only when both orthogonal intermediary sites are absent. The
supplied `~(right & down)` rule adds a redundant edge to a three-pixel L and
incorrectly creates a hole; the corrected rule is `~(right | down)`.

The finite image domain has no wraparound. Row masks prevent false connections
between the right edge and the next row's left edge. Input validation rejects
negative and out-of-grid boards, including booleans. Dimensions may be 1xN or Nx1.

LSB extraction and iterative bit dilation count foreground components b0.
Holes are `b1 = b0 - (V - E + F)`. Negative results are errors, never clamped to
zero. An independent pixel/queue BFS counts foreground with eight neighbors and
background with four neighbors in a padded exterior. It agrees on **all 65,536
4x4 boards**, plus seeded rectangular and degenerate grids. This establishes
correctness for these tested inputs, independently of whether the survey detects
the right pixels. Source for the dual connectivity convention:
[scikit-image Euler number documentation](https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_euler_number.html).

Neither operation is O(1) in image size. Python arbitrary precision shifts,
logical operations and popcount process multiple machine words. Flood fill also
depends on component count and propagation diameter; the iteration count is
reported. No single-clock or smartphone throughput claim is made.

## Phase rings: exact discrete alignment, approximate spatial rotations

`phase_ring_signature` projects support around the exact rational centroid into
8 or 16 angular slots and two relative Chebyshev-radius shells. Integer
`n*x - sum(x)` displacements avoid rounding the centroid; shift/add integer
scaling replaces the `*` operator. The 16-slot path compares slopes against Q16
rational approximations of tan(tau/32) and tan(3*tau/32), with exact quadrant
reflections and explicit axis slots. These approximate nearest uniform sectors;
finite rational boundaries are not exact irrational-angle comparisons. The
8-slot path retains its original coarser comparisons. The center is recorded
separately. The supplied quadrant formula mapped cardinal directions incorrectly
for a uniform cyclic shift; it is not used.

`match_phase_rings` tries all 8/16 cyclic shifts with popcount Dice ranking. It
returns the integer numerator/denominator and **all** best offsets; symmetric
shapes have ambiguous angles. Empty signatures have no inferred orientation.
Translations within the domain and quarter-turn rotations have exact signature
behavior, covered by seeded random-shape tests. The 22.5/30/45/60/67.5-degree experiment
rotates raster coordinates using floating point only in the fixture generator;
rasterization and angular quantization can change support and lower the match.
There is no guarantee for arbitrary angles. Angles are screen coordinates: +y
points down, and a best offset rotates the candidate signature toward the source.

The descriptor loses radial ordering, point density and connectivity. Saturated
rings and different shapes can collide. The test suite includes distinct inputs
with equal descriptors; ring scores are candidate-retrieval features, not proof
of object identity. Confirm candidates with topology and the original support or
pixels. This module does not infer a unique rotation from a circular shape.

## Integration of the supplied proposal

The integer kernel includes FWHT H8//2 (not orthonormal), ternary masks, adaptive
log-energy calibration, strides 1/2/4/8, DC slope rescue, rotate/invert/collapse
perturbations, anisotropic weights and a corner-direction bonus. The latter does
not create or observe diagonal pixels. Topology reconstruction consumes only
integer direction histories, requires reciprocal edges and bounds checks, and
locks only complete four-edge 2x2 cycles. A frozen pruning rule is iterated until
the set actually stops changing; monotone deletion guarantees termination.
Stopping after three passes or at equality before changing the threshold is not
used as evidence of convergence. A chain regression takes more than three passes.

The `*`, floating point `/`, exponentiation and float constants are excluded from
all integer-kernel definitions by an AST test. Evaluation, fixtures, rendering
and timing conversion are outside this scope. This is an operator restriction in
Python source, not a claim about interpreter internals, constant-time execution,
physical spin models or rigorous upper bounds for the heuristic candidate filter.

Energy Dice remains the proposal's AC-energy-weighted overlap. Flux-Field is an
explicit **revised experimental metric**: `(4*support_Dice + 2*halo_Dice +
edge_Dice)/7`, using symmetric one-cell halos and undirected unit edges. It is
bounded, symmetric and 100% for identical supports, including isolated points.
The supplied score assigned isolated exact matches 75% and used stale direction
bits for shifted predictions. Edges are now recomputed from each actual support.
This revision has no perceptual or XAI-fidelity validation; report IoU and FP/FN
alongside it. Sensitivity is normal score minus the score of an exact,
count-preserving (2,2) toroidal translation. Negative drops are retained.
Toroidal wrap can change topology in a finite-domain analysis, so it is not used
as a topology-invariance proof.

Venn keys are CBA: 001=A only, 010=B only, 100=C only. Eight disjoint counts sum
to the universe size. Exact inclusion, approximate inclusion (with nonzero
counterexamples), equality, empty antecedents and disjointness are separated.
This is empirical support inclusion, not causal inference or a sufficient
condition outside the observed sample. No general minimal-counterfactual or
logarithmic black-box query guarantee is claimed.

## Bit splitting: two objectives, bounded queries, explicit guarantees

```python
# blackbox is a caller-provided deterministic function: int -> bool
support = probe_bit_core(board, blackbox, objective="preserve")
deletions = probe_bit_core(board, blackbox, objective="flip")
exact = exact_deletion_counterfactual(small_board, blackbox, max_bits=12)
layers = core_shell_decomposition(board, blackbox, max_layers=8)
```

`preserve` returns a retained support that gives the same Boolean output as the
full input. `flip` returns **deleted** bits D and tests `oracle(board ^ D)` for
a changed output. Removing a sufficient support does not necessarily flip a
redundant model: in OR(A,B), either singleton is sufficient, but deleting both
is required to make the full input false. False-baseline inputs are also handled;
these APIs are not limited to True -> False.

The complement-splitting reducer accepts a reduction only after testing the
**current** full candidate. It eventually tests single-bit reductions and
certifies **1-minimality**: deleting any one witness bit loses the target
predicate. On arbitrary nonmonotone functions this need not be subset-minimal,
and even with monotonicity it need not be a globally smallest-cardinality
witness. The source implements its own complement-only reducer; the terminology
follows [Zeller's delta debugging account](https://www.debuggingbook.org/html/DeltaDebugger.html).
No source code from that implementation is copied.

The supplied recursive probe uses both original opposite halves as backgrounds.
For `f(B) = contains({0,3}) or contains({1,2})`, it picks bit 0 using the old
{2,3} background and bit 2 using the old {0,1} background. The combined {0,2}
is false, despite the full input being true. This concrete failure is retained
in the JSON simulation and regression test.

The deletion strategy starts from the all-deleted endpoint. If that endpoint
does not flip, status is `no_full_deletion_flip`, **not** "no counterfactual".
Even parity illustrates why: deleting every one of two bits preserves True,
while deleting either single bit makes False. The separate exact small-support
search enumerates deletion masks by increasing cardinality and proves the
minimum when complete. Its worst-case work is exponential, with a default
12-bit limit and a hard configurable query budget.

A per-run memoized Boolean oracle counts **actual callback calls**, including
baseline, endpoints and certification; cache hits and phases are separate.
Every input/output is retained in runtime `results.json`, while the checked-in
summary retains trace hashes, counts and witnesses. The oracle must be pure,
deterministic and return a real bool; scores, stochastic outputs and interactions
with unrepresented background features have no guarantee here. Oracle errors
propagate. Budget exhaustion returns an explicitly uncertified partial witness
or no witness, never a minimum claim.

In the fixed 64-bit simulation, a high-index single decisive bit takes six split
calls plus two baseline/endpoint calls, **eight total**; the low-index counterpart
takes 14 total because branch order differs. All 64 features being required to
preserve True takes **128 calls**. With 64 redundant alternatives, flipping the
OR output requires all 64 deletions and likewise takes 128 calls. Therefore the
universal six-call/O(log N) claim does not hold. Full three-bit truth tables
(256 deterministic functions) are checked against exhaustive oracles, separately
from the larger hand-defined controls. This simulation does not explain a
trained image model or demonstrate that a high-energy decoy is causally irrelevant.

## Sufficient-support layers and local instance rings

Core-shell decomposition repeatedly extracts a True-producing sufficient
support from the residual domain and removes it. Complete layers are disjoint
and each is certified 1-minimal. Ordering depends on deterministic bit order;
it is not a calibrated importance rank or a graph k-core decomposition. A false
residual is `residual_unclassified`: its features may still matter jointly with
a removed layer. No residual is automatically labeled a decoy. Constant-True
oracles, layer limits and query budgets have explicit termination statuses.

`component_phase_rings` returns a descriptor per 8-connected component. A control
rotates three separated components independently by 1/16, 5/16 and 12/16 turns
and retains all-to-all candidate comparisons. It does not infer tracking IDs,
resolve symmetric shapes or prove instance correspondence without further data.

Ring alignment now also suggests an actual coordinate transform for separate
verification. `rotate_support_slots` uses a fixed Q14 sine/cosine coefficient
**lookup table**, shift/add scaling, exact-centroid rational arithmetic and
integer raster rounding; its runtime kernel calls no trigonometric functions
and uses no `*` operator. It reports crops and merged points. These are still
approximate real rotations, even though the lookup is exact as integer code.

Eight support-only controls report initial IoU/Flux and the range of actual
coordinate Flux scores for **all tied ring shifts**. No ground truth selects a
favorable tied candidate. A ring descriptor score is never renamed a corrected
Flux score. L-shape quarter-turn correction reaches 100% in the fixed control;
symmetry, arbitrary rotations, scale changes and decoys can leave ambiguity or
worse geometry scores. The high energy of a feature and its Boolean relevance
are independent in these separate synthetic controls.

## Temporal XOR and observed limits

XOR reports changes between successive **final** supports and a masked one-cell
halo. The engine deliberately performs a full reference recomputation. Reusing
only the rough-support XOR is unsound: unchanged support can conceal changed
spin signs/DC levels; calibration depends on the entire frame; strides reach
eight cells; pruning can cascade arbitrarily far. ORing the entire previous
support into the gate also prevents skipping it. Previous empty support is
represented by integer 0, independently of `None` (no previous frame).

This implementation establishes the reference for a future verified incremental
algorithm; it does not implement or claim the proposed 0.3ms incremental search.
Tests check moving/noisy inputs and unchanged supports against the full result.
No timing threshold is used as a correctness gate.

The default 75th-percentile calibration is retained without tuning to the test
scenarios. When foreground occupies more than a quarter of the grid, its energy
can become the estimated background tier. DC slope rescue can also activate
background around a feature. These are algorithmic failure observations, not
bugs in the topology counter. The checked-in [CPU report](evidence/five-way-survey/report.md)
and [trial summary](evidence/five-way-survey/summary.json) preserve the actual
measurements, including empty detections and wrong predicted topology. They
supersede no original holdout evidence. Seeds reuse the supplied date and shapes
are synthetic, so this run is not an independent real-image validation.

## Consolidating the overlapping proposals

[PR #157](https://github.com/myon-bioinformatics/Ironmate/pull/157) is the
integration candidate for the overlapping
[PR #156](https://github.com/myon-bioinformatics/Ironmate/pull/156). The comparison
used #156 at `aff11622991b6fa3f75c8b9a9876fccb97edac8f` and #157's implementation
at `a9c6f783694194ac91be43216925be7268683393`. This is a consolidation decision,
not a claim that either proposal has already merged.

The following useful #156 concepts are retained in this implementation:

- The shift/add FWHT, ternary masks and logarithmic DC/AC calibration.
- Strides 1/2/4/8, DC slope rescue, perturbation histories, anisotropy and
  the corner-direction bonus.
- Fixed-point reconstruction and 2x2 cycle preservation, with reciprocal edges,
  all four cycle edges and actual convergence required.
- Bitboard topology and component counts, with the corrected isolated-diagonal
  rule and explicit foreground-8/background-4 convention.
- Eight synthetic scenario families, IoU and energy-weighted Dice, spatial
  sensitivity controls, three-condition Venn counts and temporal XOR diagnostics.
- A dependency-free CLI and daily benchmark artifact, using the existing
  `.github/workflows/verify_3way_survey.yml` schedule at 23:00 UTC (08:00 JST).
  Do not also add #156's `verify_5way_survey.yml`: that would duplicate the run.

The original unsafe rough-support temporal gate, three-pass stopping rule,
three-edge cycle lock and false-hole diagonal rule are not carried forward.
Neither are the O(1) topology claim, approximate inclusion described as a
sufficient cause, or the old asymmetric Flux score presented as a validated
accuracy measure. The reasons and replacements are documented above; the
[original proposal source](https://github.com/myon-bioinformatics/Ironmate/blob/aff11622991b6fa3f75c8b9a9876fccb97edac8f/scripts/littlebit_jev_5way_survey.py)
remains an immutable comparison reference rather than a second active engine.
The standalone experimental API is not a drop-in compatibility layer for #156's
return-field names; runtime evidence retains full support coordinates instead of
only a final integer center-of-mass and last-trial topology.

The benchmark protocols are not identical. #156 used a single shared RNG stream
and a 12x12 `High_Noise_Dark` truth square (coordinates 10..21 inclusive). This
implementation uses independently derived per-trial seeds and a 13x13 truth
square (10..22). Therefore the two outputs must not be presented as a paired
before/after accuracy or speed improvement. The resonance rule also uses an
actual collapse-distance delta rather than #156's half-active-spin proxy;
calibration removes the 16-bucket cap and rounds the 75% rank differently on
grids not divisible by four. This is a revised experiment, not output-equivalent
code. No fixture or threshold was retuned during consolidation, and the
checked-in evidence remains unchanged.

An independent 200-trial rerun reproduced the checked-in detector records,
all 400 truth/prediction coordinate hashes, and the complete detector,
counterfactual and rotation-pipeline digests. It still yielded 25/200 predicted
topology matches and scenario mean IoU of 0–38.08%. These are research baselines,
not 95% detection accuracy, a GPU substitute or a 0.3ms incremental-search result.

## Complete two-input truth-table restriction

`classify_pairwise_boolean_4bit_lut(base_board, bit_a, bit_b, oracle_fn)`
queries 00, 01, 10, 11 exactly once each and returns all 16 possible operator
names, including constants and projections. Inputs require distinct one-hot
features and an actual bool-returning deterministic oracle. Errors propagate.
The selected background is returned explicitly. Four calls classify only this
restriction: changing another feature can change XOR into constant TRUE.
This is not identification of a global clause, a causal rule, or evidence for
NPB outcomes. No greedy feature consumption or automatic repair is performed.
Python calls and tuple lookup are not a one-clock latency guarantee.

Verification: `python -m unittest discover -s tests -p test_boolean_4bit_lut.py`.
Independent Boolean operator functions cover every code; other controls cover
background dependence, sparse feature positions, invalid input and oracle errors.
The supplied crossing/fingerprint/repair benchmark percentages have not been
reproduced by this addition. Junction separation remains a separate experiment.

### Octal / hexadecimal interchange

4 bits have 16 possible values; this is separate from an 8-bit width or base 8.
Hex digits encode four bits each, octal digits three. Internal masks stay as
integers, so inference never needs a string conversion. Python already provides
`int(text, 8/16)`, `oct(value)` and `hex(value)`; the convenience entry below
uses these builtins rather than a second arithmetic conversion implementation.
Parsing/formatting cost grows with digit count; no speedup claim is made.

```sh
python -S scripts/littlebit_jev_5way_survey.py --convert 16 8 0xff
# 0o377
python -S scripts/littlebit_jev_5way_survey.py --convert 8 16 0o377
# 0xff
```

The same `convert_bitboard_radix(text, from_base, to_base)` API handles LUT
codes, 8-bit values and 64-bit masks without truncation. It accepts unsigned
Python integer text (optional prefix/underscores/whitespace), rejects malformed
or negative values, and normalizes prefixes/case/leading zeroes. Numeric value,
not original spelling or width, survives the round trip. The CLI exits before
benchmarking or writing reports. Conversion is opt-in, outside the hot path.


### Signed exact numbers (separate from unsigned bitboards)

The CLI now uses `convert_radix_number`, with exact `Fraction` intermediates;
`convert_bitboard_radix` retains its unsigned integer contract. Supported inputs:
signed integers, radix points, integer numerator/denominator pairs, and an
optional `@` exponent. Examples:

| Input | Meaning | Converted output |
|---|---|---|
| `-0x1.8` (base 16) | minus three halves | `-0o1.4` |
| `0x1@-2` (base 16) | 1 times 16 to power -2 | `0o0.002` |
| `0o1/0o3` (base 8) | one third | `0x1/0x3` |

Exponent digits after `@` are signed **decimal integers**, while the exponent's
base is the selected input radix (8 or 16). Hex `e` remains a digit, never an
exponent marker. Decimal mantissa input/base 10 is not supported. For negative
CLI input use e.g. `--convert 16 8 ' -0x1.8'` (leading space keeps argparse from
interpreting it as an option; the parser strips whitespace).

Finite expansions are rendered exactly with radix points; other rationals
remain reduced fractions, avoiding recurring-digit loops and rounding. Output
normalizes spelling and does not preserve trailing zeroes. No float is used.
Input text is capped at 4096 characters and exponent magnitude at 4096 to avoid
accidental huge allocations. Zero denominators and malformed values are errors.
Integer builtins and shifts handle base conversion; general fraction reduction
uses stdlib Fraction and has extra arithmetic/GCD cost. This is an optional
interchange layer, not a multiplication-free fraction arithmetic engine or a
measured speed optimization. Reuse parsed values rather than repeatedly
formatting/parsing in inference loops.

## Optional lossless representation adapters

`scripts/bit_representation.py` is a standalone stdlib interchange layer, separate
from the multiplication-free image kernel and its octal/hex CLI. No image
threshold, detector, fingerprint algorithm, or inference path is changed.

- `fingerprint64_to_bytes` / `fingerprint64_from_bytes`: a strict unsigned
  64-bit value becomes exactly eight **big-endian** bytes. Leading zero bytes
  are preserved; negative, oversized and wrong-length inputs are errors.
  This is packing, not compression or a self-describing file format. Callers
  must retain the fingerprint algorithm/version separately.
- `integer_to_digits` / `digits_to_integer`: bases **2..256**, including
  3, 7, 11, 13, 17, 23, 32, 64 and 128. The project-specific record is
  `(sign, digits)` where sign is -1/0/+1 and digits are a most-significant-first
  tuple. Base is external metadata; no universal alphabet or guessed radix.
  Tuple storage is not compact binary packing and base 64 digits are not the
  standardized Base64 transfer encoding. Base 256 digit values match byte
  values, but only the explicit byte adapter packs them.
- `integer_to_balanced_ternary` / `balanced_ternary_to_integer`: exact positional
  signed trits -1/0/+1, most significant first. Example: 2 -> `(1, -1)` because
  3 - 1 = 2. These are positional digits, not an image's spatial three-state
  spin mask; changing notation does not change the detector.
- `rational_to_digits` / `rational_from_digits`: reduced exact numerator and
  denominator records in any supported base. No rounding or recurring expansion
  is needed. This does not remove quantization/resampling error when mapping
  rational coordinates onto image pixels.
- `digits_to_tokens` / `tokens_to_digits`: optional custom symbol/emoji alphabet.
  Token boundaries remain an explicit tuple, so multi-codepoint emoji and
  overlapping token spellings are not concatenated ambiguously. The exact
  alphabet/order must accompany the representation. No Unicode normalization
  is implicit. For balanced trits, map -1/0/+1 to digit indices 0/1/2 first.

```python
from scripts.bit_representation import (
    fingerprint64_to_bytes, fingerprint64_from_bytes,
    integer_to_digits, digits_to_integer, integer_to_balanced_ternary,
    rational_to_digits, rational_from_digits, digits_to_tokens,
)
raw = fingerprint64_to_bytes(0x0123456789abcdef)  # exactly 8 bytes
assert fingerprint64_from_bytes(raw) == 0x0123456789abcdef
sign, digits = integer_to_digits(255, 16)          # (1, (15, 15))
assert digits_to_integer(sign, digits, 16) == 255
assert integer_to_balanced_ternary(2) == (1, -1)
n, d = rational_to_digits(1, 3, 7)
assert rational_from_digits(n, d, 7).denominator == 3
assert digits_to_tokens((0, 1, 2), ('➖', '⚪', '➕')) == ('➖', '⚪', '➕')
```

A symbol's information capacity is not its UTF-8 storage size: emoji can consume
multiple bytes/codepoints. Substitution does not give smaller storage or faster
arithmetic. Adapters use standard integer divmod/multiply and Fraction reduction;
they are not a multiplication-free engine and no speed improvement is claimed.
Keep masks/integers in the hot path, convert once at interchange boundaries,
and use the eight-byte adapter for fingerprint storage. Generic base conversion
cost grows with digit count; arbitrary precision does not mean constant time.

Checks: `python -m pytest -q tests/test_bit_representation.py` covers every base
2..256, independently reconstructed signed large integers, all balanced values
-4096..4096, a byte-order known vector and 64-bit bounds, exact rationals, and
multi-codepoint/overlapping custom tokens with invalid-input rejection.

### 32-bit limbs, fingerprint batches and RGB8

The representation adapter additionally exposes:

| API | Contract |
|---|---|
| `integer_to_u32_limbs` / `u32_limbs_to_integer` | Unsigned base-2^32 digits, **least-significant first**; zero `(0,)` |
| `add_u32_limbs` | Unsigned limb addition, carry propagated exactly, no overflow wrap; canonical leading-zero removal |
| `fingerprints64_to_bytes` / `fingerprints64_from_bytes` | Concatenated big-endian 8-byte records, order/duplicates/zeroes preserved; empty batches allowed |
| `rgb8_to_integer` / `integer_to_rgb8` | Raw RGB channels and `0xRRGGBB` unsigned 24-bit integer |
| `rgb8_to_bytes` / `rgb8_from_bytes` | Exactly three bytes in R, G, B order |

Limb order is deliberately distinct from the generic most-significant-first
digit API: it allows addition to propagate carry from index zero. For example,
`0x123456789abcdef0` becomes `(0x9abcdef0, 0x12345678)` and adding one to
`(0xffffffff, 0xffffffff)` yields `(0, 0, 1)`. Negative limb values, bools and
out-of-range values are rejected. Signed integer adapters remain available
separately; limbs are not a two's-complement signed protocol. No new general
big-integer multiplication/division engine replaces Python's integer runtime.
This is an interchange/reference addition API, not a measured acceleration.

Fingerprint batches are raw packed records, not compression or a self-describing
archive: callers retain count (or infer byte length / 8), algorithm version and
context separately. These are 64-bit masks only; larger spatial bitboards must
not be truncated to fit. Batch decoding materializes a tuple; large streams can
be split into chunks at eight-byte boundaries by the caller. A 10,000-mask test
packs to exactly 80,000 bytes and restores every value. This length does not
include Python object overhead or external metadata.

RGB packing is exact storage only, without alpha, gamma/color-space conversion,
resampling or channel-wise arithmetic. Do not add packed RGB integers to blend
colors: carries can cross channel boundaries. Channels outside 0..255 raise an
error rather than silently clipping or wrapping. Pixel layout/width/height,
row stride, color space and alpha semantics are caller metadata.

```python
from scripts.bit_representation import (
    integer_to_u32_limbs, add_u32_limbs, u32_limbs_to_integer,
    fingerprints64_to_bytes, fingerprints64_from_bytes,
    rgb8_to_integer, rgb8_to_bytes, rgb8_from_bytes,
)
assert u32_limbs_to_integer(add_u32_limbs((0xffffffff,), (1,))) == 1 << 32
assert fingerprints64_from_bytes(fingerprints64_to_bytes((0, 7, 0))) == (0, 7, 0)
assert rgb8_to_integer(18, 52, 86) == 0x123456
assert rgb8_from_bytes(rgb8_to_bytes(18, 52, 86)) == (18, 52, 86)
```

Tests compare limb reconstruction/addition with independent Python big integers,
including long carry chains and a 4097-bit value. Known byte vectors establish
byte/channel ordering independently of round trips; every 8-bit channel value
is exercised, and malformed widths/ranges/types are rejected.

### Base64 transport budgets reuse the image facade

Existing `ironmate_image.fit_to_limit` and `python -m grid_tools fit` already
try candidate sizes (including 3/4), encode PNGs, and verify the actual Base64
length. Reuse them rather than a second image-resize engine:

```sh
python -c "import ironmate_image as im; print(im.fit_to_limit('input.png', max_chars=20000).text)"
python -m grid_tools fit input.png --limit-chars 20000 -o output.b64
```

Base64 of n bytes has exactly `4 * ((n + 2) // 3)` characters before wrappers.
`size_estimate.base64_chars` now uses only integer arithmetic, avoiding float
rounding/overflow even for large size metadata. `bytes_for_chars` provides the
inverse byte budget; data URI mode includes the PNG prefix. JSON/envelope and
newline overhead must be budgeted separately. These helpers measure size only,
not allocate an image of the reported length.

A 3/4 file-byte reduction approximately offsets 4/3 Base64 expansion, but
scaling both dimensions by 3/4 retains about 9/16 as many pixels, not 3/4.
PNG/JPEG byte size is not proportional to pixel area, so exact encoded output
must be measured. Existing fitting selects among discrete candidates; its
lossless preference refers to preserving dot-art cells, not arbitrary natural
image fidelity or global optimality. Downsampling can lose information and
metadata may be dropped with a warning; no silent universal compensation or
fixed 3/4 shrink is added. Where binary transport is allowed, raw image bytes
avoid Base64 expansion without altering image dimensions.
