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
Venn counts and eight support maps. Each scenario/trial derives its own RNG seed
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
scaling replaces the `*` operator. Integer slope comparisons approximate angular
sectors; they are not uniform atan2 bins. The center is recorded separately.

`match_phase_rings` tries all 8/16 cyclic shifts with popcount Dice ranking. It
returns the integer numerator/denominator and **all** best offsets; symmetric
shapes have ambiguous angles. Empty signatures have no inferred orientation.
Translations within the domain and quarter-turn rotations have exact signature
behavior, covered by seeded random-shape tests. The 30/60-degree experiment
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
