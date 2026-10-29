"""Bounded symbolic boundary synthesis for evaluate_rule's conjunction grammar.

Cubes are (required-one mask, required-zero mask). No board-space scan, random
search, multiplication or floating point is used. Covers can grow exponentially.
"""
from scripts.boundary_twins import _mask, evaluate_rule


def synthesize_boundary_twins(mutable_mask, *, fixed_board=0, must_and=0,
                              or_masks=(), forbid_not=0, pair_tables=(),
                              max_steps=100000):
    """Return one verified edge per sensitive mutable bit, not all edges.

    Bits outside mutable_mask equal fixed_board; its mutable bits are ignored.
    Completeness means existence per bit in this fixed-background subspace.
    Budget exhaustion raises; use audit_boundary_twins explicitly as a local
    fallback (its empty result cannot establish global absence).
    """
    _mask(mutable_mask)
    _mask(fixed_board)
    or_masks, pair_tables = tuple(or_masks), tuple(pair_tables)
    rule = dict(must_and=must_and, or_masks=or_masks,
                forbid_not=forbid_not, pair_tables=pair_tables)
    evaluate_rule(0, **rule)  # validate even contradictory/empty domains
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError('max_steps must be a positive integer')
    steps = 0

    def tick():
        nonlocal steps
        steps += 1
        if steps > max_steps:
            raise ValueError('symbolic synthesis budget exhausted')

    def intersect(a, b):
        tick()
        one, zero = a[0] | b[0], a[1] | b[1]
        return None if one & zero else (one, zero)

    def bits(mask):
        while mask:
            bit = mask & -mask
            mask ^= bit
            yield bit

    support = must_and | forbid_not
    for mask in or_masks:
        support |= mask
    for a, b, _ in pair_tables:
        support |= a | b
    frozen = support & ~mutable_mask
    cover = [(must_and | (fixed_board & frozen),
              forbid_not | (frozen & ~fixed_board))]
    if cover[0][0] & cover[0][1]:
        cover = []

    def constrain(options):
        nonlocal cover
        joined = set()
        for cube in cover:
            for option in options:
                result = intersect(cube, option)
                if result is not None:
                    joined.add(result)
        cover = sorted(joined)

    for mask in or_masks:
        constrain([(bit, 0) for bit in bits(mask)])
    for a, b, code in pair_tables:
        constrain([((a if state & 2 else 0) | (b if state & 1 else 0),
                    (a if not state & 2 else 0) | (b if not state & 1 else 0))
                   for state in range(4) if code & (1 << state)])

    def subtract(cube, removed):
        # Disjoint residual cubes for cube \\ removed, splitting only free bits.
        overlap = intersect(cube, removed)
        if overlap is None:
            return [cube]
        residual = []
        one, zero = cube
        for bit in bits((removed[0] | removed[1]) & ~(one | zero)):
            tick()
            if removed[0] & bit:
                residual.append((one, zero | bit))
                one |= bit
            else:
                residual.append((one | bit, zero))
                zero |= bit
        return residual

    pairs = []
    for bit in bits(mutable_mask & support):
        # Positive region minus the region whose bit-flipped board is positive.
        flipped = [(one ^ (bit if (one | zero) & bit else 0),
                    zero ^ (bit if (one | zero) & bit else 0))
                   for one, zero in cover]
        witness = None
        for cube in cover:
            residual = [cube]
            for removed in flipped:
                residual = [piece for item in residual for piece in subtract(item, removed)]
                if not residual:
                    break
            if residual:
                witness = (fixed_board & ~mutable_mask) | residual[0][0]
                break
        if witness is not None:
            negative = witness ^ bit
            if not (evaluate_rule(witness, **rule) and
                    not evaluate_rule(negative, **rule) and
                    (witness ^ negative).bit_count() == 1):
                raise AssertionError('invalid synthesized boundary')
            pairs.append(dict(positive=witness, negative=negative, changed_bit=bit,
                              hamming_distance=1, oracle_verified=None))
    return dict(pairs=pairs, complete_sensitive_bits=True,
                all_boundary_edges=False, symbolic_steps=steps)
