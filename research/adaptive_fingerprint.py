"""Experimental nested occupancy fingerprints; no identity/rotation guarantee.

Coarse 64-bit = 4 shells x 16 slots. Fine 256-bit = 8 x 32.
These layouts are distinct from the existing two-shell phase-ring API.
"""


def unsigned(value, width):
    if type(value) is not int or value < 0 or value.bit_length() > width:
        raise ValueError('unsigned mask of the specified width required')
    return value


def reduce256(fine):
    """OR adjacent angular slots and radial shells; deliberately lossy."""
    unsigned(fine, 256)
    coarse = 0
    while fine:
        bit = fine & -fine
        index = bit.bit_length() - 1
        coarse |= 1 << (((index >> 6) << 4) | ((index & 31) >> 1))
        fine ^= bit
    return coarse


def rotate(board, slots, shells, shift):
    shift %= slots
    mask = (1 << slots) - 1
    result = 0
    for shell in range(shells):
        base = shell << (slots.bit_length() - 1)
        ring = (board >> base) & mask
        result |= (((ring << shift) | (ring >> (slots - shift))) & mask) << base
    return result


def best_alignment(a, b, slots, shells, shifts):
    best, winners = None, []
    for shift in shifts:
        distance = (a ^ rotate(b, slots, shells, shift)).bit_count()
        if best is None or distance < best:
            best, winners = distance, [shift]
        elif distance == best:
            winners.append(shift)
    return {'distance': best, 'shifts': tuple(winners)}


def adaptive_match(ref64, tgt64, fine_loader, threshold=2):
    """Lazy pair gate, not a multiclass confidence/unknown detector.

    fine_loader returns (ref256, tgt256) only when coarse distance <= threshold.
    All 32 fine shifts are checked: local three-shift proposals are diagnostic
    only, since lossy coarsening cannot certify their global optimality.
    """
    unsigned(ref64, 64)
    unsigned(tgt64, 64)
    if type(threshold) is not int or not 0 <= threshold <= 64:
        raise ValueError('threshold must be in 0..64')
    coarse = best_alignment(ref64, tgt64, 16, 4, range(16))
    result = {'coarse': coarse, 'escalated': False, 'fine': None,
              'local_candidates': (), 'local_missed_optimum': None}
    if coarse['distance'] > threshold:
        return result
    ref, tgt = fine_loader()
    unsigned(ref, 256)
    unsigned(tgt, 256)
    if reduce256(ref) != ref64 or reduce256(tgt) != tgt64:
        raise ValueError('fine fingerprints must reduce to the supplied coarse masks')
    candidates = tuple(sorted({((s << 1) + delta) & 31
                               for s in coarse['shifts'] for delta in (-1, 0, 1)}))
    local = best_alignment(ref, tgt, 32, 8, candidates)
    fine = best_alignment(ref, tgt, 32, 8, range(32))
    result.update(escalated=True, fine=fine, local_candidates=candidates,
                  local_missed_optimum=local['distance'] != fine['distance'])
    return result


def masked_distance(a, b, observed_a, observed_b, width=256):
    """Unknown differs from zero. No common observations => undefined score.

    Masks must already share an aligned coordinate/feature schema. Return exact
    integers; callers retain coverage rather than treating tiny overlap as proof.
    """
    if type(width) is not int or not 1 <= width <= 256:
        raise ValueError('width must be in 1..256')
    for value in (a, b, observed_a, observed_b):
        unsigned(value, width)
    common = observed_a & observed_b
    count = common.bit_count()
    return {'mismatches': ((a ^ b) & common).bit_count(),
            'observed': count, 'defined': count != 0, 'width': width}


def fuse64(a, b):
    """Lossless interleave only; bit indices need explicit semantic alignment."""
    unsigned(a, 64)
    unsigned(b, 64)
    out = 0
    for i in range(64):
        out |= ((a >> i) & 1) << (i << 1)
        out |= ((b >> i) & 1) << ((i << 1) | 1)
    return out
