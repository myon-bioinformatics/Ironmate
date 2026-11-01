"""Opt-in bounded-error observations and one-step temporal predictions.

Integer-only scoring; no multiplication in this module. No image, timing,
arbitrary rotation, or statistical accuracy guarantee is implied.
"""
from scripts.observable_choice import ObservableChoice


def _natural(value):
    if type(value) is not int or value < 0:
        raise ValueError('expected nonnegative integer')


class BoundedErrorChoice:
    """Exact signatures only; use ObservableChoice for partial/OR predicates.

    A unique result is certified only under the caller's known-dictionary and
    total observed-error budget assumptions. Unknown classes may alias a code.
    Exhaustive scan deliberately avoids irreversible noisy-pivot pruning.
    """
    def __init__(self, prototypes, width):
        self.index = ObservableChoice(prototypes, width, node_budget=1)
        self.width = width
        self.universe = self.index.universe
        self.prototypes = self.index.prototypes
        if any(p.clauses or (p.must | p.forbid) != self.universe
               for p in self.prototypes):
            raise ValueError('bounded errors require complete exact signatures')

    def query(self, active, observed, errors=1):
        self.index._mask(active)
        self.index._mask(observed)
        _natural(errors)
        candidates = []
        for p in self.prototypes:
            mismatch = (active ^ p.must) & observed
            if mismatch.bit_count() <= errors:
                candidates.append(dict(name=p.name, errors=mismatch.bit_count(),
                                       mismatch_mask=mismatch))
        return dict(status='rejected' if not candidates else
                    'unique' if len(candidates) == 1 else 'ambiguous',
                    candidates=candidates)

    def next_probe(self, active, observed, errors=1, *, grid_width,
                   fovea=0, costs=None):
        """Greedy worst-case reduction, discounted by travel and acquisition.

        Compare only bits guaranteeing progress for both outcomes under the
        error budget. Ties favor smaller actual movement, then lower bit index.
        Costs are explicit nonnegative integer score units, not physical units.
        No recommendation means abstain, not classification success.
        """
        result = self.query(active, observed, errors)
        if type(grid_width) is not int or not 1 <= grid_width <= self.width:
            raise ValueError('invalid grid width')
        if type(fovea) is not int or not 0 <= fovea < self.width:
            raise ValueError('invalid fovea')
        costs = {} if costs is None else costs
        for bit, cost in costs.items():
            if type(bit) is not int or not 0 <= bit < self.width:
                raise ValueError('invalid cost bit')
            _natural(cost)
        count = len(result['candidates'])
        best = None
        for b in range(self.width):
            bit = 1 << b
            if observed & bit:
                continue
            counts = tuple(len(self.query((active & ~bit) | (bit if v else 0),
                                         observed | bit, errors)['candidates'])
                           for v in (0, 1))
            reduction = count - max(counts)
            if reduction <= 0:
                continue
            distance = (abs(b % grid_width - fovea % grid_width)
                        + abs(b // grid_width - fovea // grid_width))
            gain = (reduction << 3) - distance.bit_length() - costs.get(b, 0)
            key = (-gain, distance, b)
            if best is None or key < best[0]:
                best = key, dict(bit=b, zero_survivors=counts[0],
                                 one_survivors=counts[1], distance=distance,
                                 score=gain, acquisition_cost=costs.get(b, 0))
        return None if best is None else best[1]


def temporal_prediction(active, observed, previous, previous_observed, *,
                        width, height, dx=0, dy=0):
    """Translate previous *measured* bits; return separate predicted evidence.

    Known zeroes move with the known mask. Off-grid bits are discarded, never
    wrapped. Caller must associate the same object and invalidate stale frames;
    do not feed prediction_mask back as previous_observed. No motion estimation.
    """
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 1024 or not 1 <= height <= 1024):
        raise ValueError('invalid grid')
    if type(dx) is not int or type(dy) is not int:
        raise ValueError('integer translation required')
    size = sum(width for _ in range(height))
    if size > 1024:
        raise ValueError('grid exceeds 1024 bits')
    universe = (1 << size) - 1
    for mask in (active, observed, previous, previous_observed):
        if type(mask) is not int or mask < 0 or mask & ~universe:
            raise ValueError('mask outside grid')
    predicted = known = 0
    for b in range(size):
        if not previous_observed & (1 << b):
            continue
        x, y = b % width + dx, b // width + dy
        if 0 <= x < width and 0 <= y < height:
            target = sum(width for _ in range(y)) + x
            known |= 1 << target
            if previous & (1 << b):
                predicted |= 1 << target
    prediction_mask = known & ~observed & universe
    return dict(board=(active & observed) | (predicted & prediction_mask),
                observed_mask=observed, prediction_mask=prediction_mask)
