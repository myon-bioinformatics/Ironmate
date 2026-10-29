"""Deterministic distance-one audit at a supplied board, not global synthesis.

Each reported pair is evaluated against the complete predicate. External oracle
agreement is recorded separately. No causal/actionability or runtime guarantee.
"""


def _mask(value):
    if type(value) is not int or value < 0:
        raise ValueError('mask must be a nonnegative integer, not bool')


def evaluate_rule(board, must_and=0, or_masks=(), forbid_not=0, pair_tables=()):
    """Conjunction of AND/OR/NOT constraints and arbitrary two-bit LUT clauses.

    pair_tables contains (one_hot_a, one_hot_b, truth_code) with bit order
    00,01,10,11. Overlapping clauses are allowed and evaluated jointly.
    """
    or_masks = tuple(or_masks)
    pair_tables = tuple(pair_tables)
    for mask in (board, must_and, forbid_not):
        _mask(mask)
    for mask in or_masks:
        _mask(mask)
    for a, b, code in pair_tables:
        _mask(a)
        _mask(b)
        if not a or a & (a-1) or not b or b & (b-1) or a == b:
            raise ValueError('pair features must be distinct one-hot masks')
        if type(code) is not int or not 0 <= code <= 15:
            raise ValueError('truth code must be 0..15')
    if board & must_and != must_and or board & forbid_not:
        return False
    if any(board & mask == 0 for mask in or_masks):
        return False
    for a, b, code in pair_tables:
        state = (2 if board & a else 0) | (1 if board & b else 0)
        if not (code >> state) & 1:
            return False
    return True


def audit_boundary_twins(board, mutable_mask, predicate, *, oracle=None, max_queries=4096):
    """Enumerate all flipping one-bit neighbors within mutable_mask at board.

    Cost is 1+k predicate calls, k=popcount(mutable_mask). Optional deterministic
    bool oracle evaluates only unique reported endpoints (at most 1+k calls).
    Budget covers both predicate and oracle calls, checked before each call;
    exhaustion raises without returning a misleading complete report. Candidate
    actions obey only the supplied mutable mask, not physical/causal constraints.
    """
    _mask(board)
    _mask(mutable_mask)
    if type(max_queries) is not int or max_queries < 1:
        raise ValueError('max_queries must be a positive integer')
    counts = {'predicate': 0, 'oracle': 0}

    def query(fn, value, kind):
        if counts['predicate'] + counts['oracle'] >= max_queries:
            raise ValueError('query budget exhausted')
        counts[kind] += 1
        result = fn(value)
        if type(result) is not bool:
            raise TypeError('predicate/oracle must return bool')
        return result

    label = query(predicate, board, 'predicate')
    oracle_cache = {}

    def external(value):
        if value not in oracle_cache:
            oracle_cache[value] = query(oracle, value, 'oracle')
        return oracle_cache[value]

    pairs = []
    remaining = mutable_mask
    while remaining:
        bit = remaining & -remaining
        remaining ^= bit
        neighbor = board ^ bit
        other = query(predicate, neighbor, 'predicate')
        if other == label:
            continue
        positive, negative = (board, neighbor) if label else (neighbor, board)
        row = {'positive': positive, 'negative': negative, 'changed_bit': bit,
               'hamming_distance': 1, 'oracle_verified': None}
        if oracle is not None:
            # Both calls happen even when the first disagrees; retain evidence.
            p_label, n_label = external(positive), external(negative)
            row.update(oracle_positive=p_label, oracle_negative=n_label,
                       oracle_verified=p_label and not n_label)
        pairs.append(row)
    return {'board': board, 'label': label, 'pairs': pairs,
            'predicate_queries': counts['predicate'], 'oracle_queries': counts['oracle'],
            'complete_within_mutable_mask': True}
