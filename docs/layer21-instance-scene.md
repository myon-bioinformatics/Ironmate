# Layer 21 reference experiment

`scripts/instance_scene.py` reuses `ObservableChoice`/`Prototype` validation.
It provides 4-connected LSB flood-fill, observed-mask 75% leaf quorum and
velocity-predicted class-gated greedy multi-object assignment. All core scoring
uses integers, bit operations, addition/subtraction and bit counts; this is not
literally bit operations alone. No third-party packages or default app behavior
change. Run `python -S -m unittest discover -s tests -p test_instance_scene.py -v`.

Quorum candidates are hypotheses, not certified detections. Hidden bits are
excluded from evidence; observed missing leaves spend the explicit error budget.
Empty leaves cannot match. Shared candidate leaves are not erased. Residuals
exclude only exclusive candidate leaves and caller-declared shared stems.
An unknown object can still mimic a known class; no novelty guarantee follows.

Spatial components count disconnected regions, not objects. Touching or fully
overlapping same-class objects remain one component; OR fingerprints cannot
recover lost multiplicity. Caller-supplied region fingerprints and poses are
not automatically extracted from raw images. Component holes are not assigned
to individual overlapping objects. Scale/rotation normalization is upstream.

Tracking uses predicted Manhattan distance, 64-bit Hamming distance, hole count
and circular 16-sector phase distance. New detections receive fresh IDs;
unmatched tracks expire immediately. IDs are returned in input detection order.
Assignment is greedy O(P C log(P C)), not Hungarian, optimal, or O(1).
Motion prediction helps crossings only when past motion disambiguates them.
Identical observations and symmetric trajectories cannot guarantee identity.

The supplied 8-scenario accuracy table, MOTA-equivalent claims, 1,000-frame
results and microsecond numbers have not been reproduced. The regression suite
checks all 512 small spatial boards against an independent set-based reference,
quorum occlusion, shared ownership, births/deaths and a velocity crossing.
This is not an integrated Layer 1–21 master engine or a physics rollout.

Aoi can consume the JSON bridge without copying this implementation:
`python -S -m scripts.instance_scene < stream.json` with working directory set
to this repository. Input contains `frames` of Detection field dictionaries;
output is `{"track_ids": [[...], ...]}`. No network or write side effects.
