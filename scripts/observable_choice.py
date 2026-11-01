"""Bounded bit decision index, strong Kleene predicates, next observations.

Not a reduced ordered BDD, probabilistic classifier or imputation oracle.
Core matching/index/probe operations use integers and no multiplication.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Prototype:
    name: str
    must: int = 0
    forbid: int = 0
    clauses: tuple = ()


class ObservableChoice:
    def __init__(self, prototypes, width, node_budget=4095, leaf_size=2):
        if type(width) is not int or not 1 <= width <= 256 or node_budget < 1 or leaf_size < 1:
            raise ValueError('invalid index limits')
        self.width, self.universe = width, (1 << width)-1
        self.prototypes = tuple(prototypes)
        if len({p.name for p in self.prototypes}) != len(self.prototypes):
            raise ValueError('duplicate class names')
        for p in self.prototypes:
            for mask in (p.must, p.forbid, *p.clauses):
                self._mask(mask)
            if p.must & p.forbid or any(not (clause & ~p.forbid) for clause in p.clauses):
                raise ValueError('unsatisfiable prototype')
        self.nodes = 0
        def build(ids, used):
            self.nodes += 1
            if len(ids) <= leaf_size or self.nodes + 2 > node_budget:
                return (0, ids)
            best = None
            for b in range(width):
                bit = 1 << b
                if used & bit:
                    continue
                one = tuple(i for i in ids if not self.prototypes[i].forbid & bit)
                zero = tuple(i for i in ids if not self.prototypes[i].must & bit)
                # Don't-care prototypes survive both outcomes. Require progress.
                worst = max(len(one), len(zero))
                if worst >= len(ids):
                    continue
                key = (worst, len(one)+len(zero), b)
                if best is None or key < best[0]:
                    best = key, bit, zero, one
            if best is None:
                return (0, ids)
            _, bit, zero, one = best
            # Reserve the sibling root while constructing the first subtree.
            self.nodes += 1
            left = build(zero, used | bit)
            self.nodes -= 1
            return (bit, left, build(one, used | bit))
        self.root = build(tuple(range(len(self.prototypes))), 0)

    def _mask(self, value):
        if type(value) is not int or value < 0 or value & ~self.universe:
            raise ValueError('mask outside declared width')

    def evaluate(self, proto, active, observed):
        """Strong Kleene AND of required literals and positive OR clauses."""
        active &= observed
        if proto.must & observed & ~active or proto.forbid & active:
            return 'false'
        unknown = bool((proto.must | proto.forbid) & ~observed)
        for clause in proto.clauses:
            if clause & active:
                continue
            if not clause & ~observed:
                return 'false'
            unknown = True
        return 'unknown' if unknown else 'true'

    def query(self, active, observed):
        self._mask(active)
        self._mask(observed)
        active &= observed  # garbage in unobserved bits has no evidential value
        pending, ids, tests = [self.root], set(), 0
        while pending:
            node = pending.pop()
            bit = node[0]
            if not bit:
                ids.update(node[1])
                continue
            tests += 1
            if not observed & bit:
                pending.extend(node[1:])
            else:
                pending.append(node[2] if active & bit else node[1])
        survivors = [(i, self.evaluate(self.prototypes[i], active, observed)) for i in sorted(ids)]
        survivors = [(i, state) for i, state in survivors if state != 'false']
        indices = [i for i, _ in survivors]
        return dict(status='rejected' if not indices else 'unique' if len(indices)==1 else 'ambiguous',
                    candidates=[dict(name=self.prototypes[i].name, truth=state) for i,state in survivors],
                    bit_tests=tests, candidates_evaluated=len(ids),
                    next_probe=self.next_probe(indices, active, observed))

    def next_probe(self, indices, active, observed):
        """Greedy minimax candidate counts, including don't-care survivors.

        Exact one-step branch counts; no claim of globally optimal query depth.
        """
        if len(indices) <= 1:
            return None
        best = None
        for b in range(self.width):
            bit = 1 << b
            if observed & bit:
                continue
            counts = tuple(sum(self.evaluate(self.prototypes[i],
                               (active & ~bit) | (bit if value else 0), observed | bit) != 'false'
                               for i in indices) for value in (0,1))
            key = (max(counts), sum(counts), b)
            if key[0] < len(indices) and (best is None or key < best[0]):
                best = key, dict(bit=b, zero_survivors=counts[0], one_survivors=counts[1])
        return None if best is None else best[1]
