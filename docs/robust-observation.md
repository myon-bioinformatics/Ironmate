# Bounded-error sensing and temporal prediction (Layer 16 experiment)

Opt-in API: `scripts.robust_observation.BoundedErrorChoice` accepts existing
`observable_choice.Prototype` objects, but requires complete exact signatures.
Existing Kleene / OR predicate routing and CSV output remain unchanged.
No dependencies, workflow changes or production image integration are added.

```python
from scripts.observable_choice import Prototype
from scripts.robust_observation import BoundedErrorChoice, temporal_prediction

engine = BoundedErrorChoice([Prototype('zero', 0, 7), Prototype('one', 7, 0)], 3)
result = engine.query(active=1, observed=7, errors=1)
assert result['status'] == 'unique'
assert result['candidates'][0]['name'] == 'zero'
```

Query returns every code within the observed mismatch budget; ambiguity and
rejection are explicit. A unique result is conditional on membership in the
dictionary and at most `errors` flipped measured bits. The mismatch mask is a
diagnostic, not evidence that a sensor error really occurred. Unknown classes
can alias dictionary entries. Scanning all signatures prevents noisy pivots
from silently discarding a valid candidate; this is not a redundant BDD.
Runtime is linear in dictionary size for query; next-probe scoring performs
two queries per unobserved bit. It is not universally logarithmic.

For exact signatures, correcting t errors requires minimum pairwise Hamming
distance at least 2t+1 **on the observed positions**. Distance three permits
one error, not two. Full-code distance alone cannot ensure decoding after
arbitrary occlusion. Two extra probes are not a universal parity certificate.
The API preserves ambiguity rather than assuming a runner-up error of 99 when
all other candidates have been filtered out.

`next_probe(..., grid_width=4, fovea=3, costs={0: 5})` scores guaranteed
worst-case candidate reduction shifted left three bits, minus Manhattan
distance bit_length and explicit integer acquisition cost. Ties use actual
distance and then bit index. Only bits improving both possible outcomes qualify;
it can return None even if multiple observations together would help. It is a
greedy heuristic, not a guarantee of minimum total travel or monetary cost.
The caller acquires the new sensor value and updates active/observed masks.

`temporal_prediction(active, observed, previous, previous_observed,
width=4, height=4, dx=1, dy=0)` translates previous measured evidence in 2D.
Known-zero bits move with their known mask. Clipping prevents row wrapping.
Current measurements override predictions. The returned `observed_mask` is
unchanged; `prediction_mask` is separate and must never be promoted to measured
evidence. Use previous raw observations, not recursively completed predictions.
Caller must handle object association, scene cuts, stale-frame invalidation,
motion errors and nonrigid changes. No rotation or Kalman estimator is present.
Grid size is bounded to 1024 bits; the temporal implementation is a simple
per-bit reference algorithm, not an optimized shift kernel.

Verification: `python -m pytest -q tests/test_research.py` (8 tests).
Exhausts all masks and bounded flip patterns for distance-three / one-error and
distance-five / two-error codes, zero-budget parity with existing routing,
probe outcome counts, and all single-pixel translations of a 4x3 grid over
offsets -4..4 and -3..3. Includes unknown zeros, measured-zero precedence,
unidentifiable cases, invalid inputs and AST multiplication checks of the new
core. Integer addition, comparison, division/modulo and loops are used: this is
multiplication-free integer code, not literally only bitwise instructions.

The supplied eight-scenario accuracy/timing table is not reproduced by these
small synthetic correctness tests. No 99% accuracy, microsecond throughput,
two-bit immunity or C/WASM nanosecond claims are made. Unknown-class discovery
and code generation need independent datasets, ambiguity policies, and parity
checks before they can be added.
