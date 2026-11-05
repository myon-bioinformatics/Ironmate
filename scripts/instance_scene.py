"""Layer 21 reference primitives. Integer arithmetic, no multiplication.

Regions are spatial evidence, not inferred copies of an OR fingerprint.
Tracking is gated greedy assignment, not Hungarian or constant time.
"""
from dataclasses import dataclass
from scripts.observable_choice import ObservableChoice


def components(board, width, height):
    """Four-connected bit masks; touching/overlapping objects remain merged."""
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError('invalid grid')
    size = sum(width for _ in range(height))
    universe = (1 << size) - 1
    if type(board) is not int or board < 0 or board & ~universe:
        raise ValueError('invalid board')
    left = sum(1 << offset for offset in range(0, size, width))
    right = left << (width - 1)
    result = []
    remaining = board
    while remaining:
        region = remaining & -remaining
        frontier = region
        while frontier:
            adjacent = ((frontier & ~right) << 1) | ((frontier & ~left) >> 1)
            adjacent |= (frontier << width) | (frontier >> width)
            frontier = adjacent & remaining & ~region
            region |= frontier
        result.append(region)
        remaining &= ~region
    return tuple(result)


def quorum_scene(prototypes, active, observed, *, width, shared=0, errors=1):
    """Candidate evidence with conservative residual; shared leaves are retained.

    Missing unobserved leaves do not spend the observed error budget. At least
    75% of all leaf bits must be measured hits. Ambiguous ownership is retained.
    No candidate implies proof of presence or unique decomposition.
    """
    index = ObservableChoice(prototypes, width, node_budget=1)
    index._mask(active)
    index._mask(observed)
    index._mask(shared)
    if type(errors) is not int or errors < 0:
        raise ValueError('invalid error budget')
    active &= observed
    candidates = []
    leaves = []
    for p in index.prototypes:
        leaf = p.must & ~shared
        total = leaf.bit_count()
        hits = (leaf & active).bit_count()
        missing = (leaf & observed & ~active).bit_count()
        stem_missing = p.must & shared & observed & ~active
        if (total and (hits << 2) >= (total << 1) + total and missing <= errors
                and not stem_missing and not p.forbid & active
                and all(c & active for c in p.clauses)):
            candidates.append(dict(name=p.name, missing_observed=missing,
                                   hidden=leaf & ~observed))
            leaves.append(leaf)
    exclusive = 0
    for i, leaf in enumerate(leaves):
        others = 0
        for j, other in enumerate(leaves):
            if i != j:
                others |= other
        exclusive |= leaf & ~others
    return dict(candidates=candidates, residual=active & ~exclusive & ~shared,
                removed=active & exclusive)


@dataclass(frozen=True)
class Detection:
    class_name: str
    fingerprint: int
    x: int
    y: int
    holes: int = 0
    phase: int = 0


class Tracker:
    """One-frame velocity prediction, births/deaths and class/distance gates.

    Equal-cost same-class crossings remain unidentifiable. No hidden frames are
    synthesized. O(P C log(P C)) assignment with Python arbitrary-size bitsets.
    """
    def __init__(self, max_distance=8):
        if type(max_distance) is not int or max_distance < 0:
            raise ValueError('invalid distance gate')
        self.max_distance = max_distance
        self.tracks = {}
        self.next_id = 0

    def update(self, detections):
        detections = tuple(detections)
        for d in detections:
            if not isinstance(d, Detection) or any(type(v) is not int for v in
                    (d.fingerprint, d.x, d.y, d.holes, d.phase)):
                raise ValueError('invalid detection')
            if d.fingerprint < 0 or d.fingerprint.bit_length() > 64 or d.holes < 0 or not 0 <= d.phase < 16:
                raise ValueError('invalid signature')
        pairs = []
        for tid, (p, vx, vy) in self.tracks.items():
            for j, d in enumerate(detections):
                distance = abs(p.x + vx - d.x) + abs(p.y + vy - d.y)
                if p.class_name != d.class_name or distance > self.max_distance:
                    continue
                delta = abs(p.phase - d.phase)
                phase = min(delta, 16 - delta)
                cost = ((p.fingerprint ^ d.fingerprint).bit_count() << 2)
                cost += distance + (abs(p.holes - d.holes) << 4) + phase
                pairs.append((cost, tid, j))
        used = 0
        next_tracks = {}
        assigned = {}
        for cost, tid, j in sorted(pairs):
            if tid in next_tracks or used & (1 << j):
                continue
            used |= 1 << j
            d = detections[j]
            p = self.tracks[tid][0]
            next_tracks[tid] = (d, d.x - p.x, d.y - p.y)
            assigned[j] = tid
        for j, d in enumerate(detections):
            if j not in assigned:
                tid = self.next_id
                self.next_id += 1
                assigned[j] = tid
                next_tracks[tid] = (d, 0, 0)
        self.tracks = next_tracks
        return tuple(assigned[j] for j in range(len(detections)))


def main():
    """JSON stdin/stdout bridge for opt-in cross-repository experiments."""
    import json
    import sys
    payload = json.load(sys.stdin)
    tracker = Tracker(payload.get('max_distance', 8))
    output = []
    for frame in payload['frames']:
        detections = [Detection(**item) for item in frame]
        output.append(list(tracker.update(detections)))
    json.dump({'track_ids': output}, sys.stdout)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
