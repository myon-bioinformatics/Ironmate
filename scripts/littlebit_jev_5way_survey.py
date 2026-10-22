#!/usr/bin/env python3
"""Standalone stdlib experiment: calibrated support, exact topology, phase rings.

No model queries/XAI, causal inference, or arbitrary-angle invariance is claimed.
Integer kernel ends before evaluation(); only reporting/fixtures use floats/*.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import time
from pathlib import Path

DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
SCENARIOS = ('Dense_Object', 'Thin_Skeleton', 'Hollow_Ring', 'Double_Ring',
             'Smooth_Gradient', 'High_Noise_Dark', 'Multi_Scale_Clusters',
             'Anisotropic_Matrix')


def row_offsets(w, h):
    if type(w) is not int or type(h) is not int or w <= 0 or h <= 0:
        raise ValueError('positive integer dimensions required')
    offsets, offset = [], 0
    for _ in range(h):
        offsets.append(offset)
        offset += w
    return offsets, offset


def compute_row_masks(w, h):
    offsets, total = row_offsets(w, h)
    right = left = 0
    row = (1 << (w - 1)) - 1
    for offset in offsets:
        right |= row << offset
        left |= (row << 1) << offset
    return right, left, (1 << total) - 1


def validate_board(board, universe):
    if type(board) is not int or board < 0 or board & ~universe:
        raise ValueError('board must be a nonnegative integer inside the grid')


def pack_to_bitboard(nodes, w, h):
    _, total = row_offsets(w, h)
    board = 0
    for idx in nodes:
        if type(idx) is not int or not 0 <= idx < total:
            raise ValueError('node outside grid')
        board |= 1 << idx
    return board


def unpack(board):
    result = set()
    while board:
        bit = board & -board
        result.add(bit.bit_length() - 1)
        board ^= bit
    return result


def dilate(board, w, right, left, universe, eight=True):
    horizontal = board | ((board & right) << 1) | ((board & left) >> 1)
    base = horizontal if eight else board
    return (horizontal | (base << w) | (base >> w)) & universe


def component_count(board, w, right, left, universe, eight=True):
    remaining, count, iterations = board, 0, 0
    while remaining:
        count += 1
        component = remaining & -remaining
        while True:
            iterations += 1
            expanded = dilate(component, w, right, left, universe, eight) & remaining
            if expanded == component:
                break
            component = expanded
        remaining ^= component
    return count, iterations


def compute_bitboard_topology_and_betti(board, w, h):
    """Foreground 8 / background 4 connectivity, finite non-wrapping domain.

    V counts sites, E orthogonal and isolated diagonal pairs, F full squares.
    A diagonal in a three-site L must NOT add an extra edge (a false hole).
    Python bigint shifts/popcounts scale with board length; flood fill also
    depends on component diameter. Neither holes nor components are O(1).
    """
    right, left, universe = compute_row_masks(w, h)
    validate_board(board, universe)
    r = (board >> 1) & right
    d = board >> w
    rd = (board >> (w + 1)) & right
    edges = (board & r).bit_count() + (board & d).bit_count()
    edges += (board & rd & ~(r | d)).bit_count()
    edges += (r & d & ~(board | rd)).bit_count()
    faces = (board & r & d & rd).bit_count()
    vertices = board.bit_count()
    chi = vertices - edges + faces
    b0, iterations = component_count(board, w, right, left, universe)
    b1 = b0 - chi
    if b1 < 0:
        raise AssertionError('inconsistent Euler characteristic')
    return dict(V=vertices, E=edges, F=faces, chi=chi,
                b0_clusters=b0, b1_holes=b1, flood_iterations=iterations)


def rotate_ring(bits, shift, slots=16):
    if slots not in (8, 16):
        raise ValueError('8 or 16 slots required')
    validate_board(bits, (1 << slots) - 1)
    shift %= slots
    return ((bits << shift) | (bits >> (slots - shift))) & ((1 << slots) - 1)


def integer_scale(value, count):
    """Exact integer scaling using shift/add; not a constant-time operation."""
    result = 0
    while count:
        if count & 1:
            result += value
        value <<= 1
        count >>= 1
    return result


def direction_slot(dx, dy, slots):
    """Integer octants, optionally split at slope 1/2 (approximate angles).

    Screen coordinates: +x right, +y down. Axis and diagonal ties are assigned
    symmetrically, so a quarter-turn always adds slots/4, without atan2.
    """
    ax, ay = abs(dx), abs(dy)
    if dx == 0 and dy == 0:
        return None
    quarter = slots >> 2
    if slots == 8:
        q = 0 if (ay << 1) < ax else (2 if (ax << 1) < ay else 1)
    elif slots == 16:
        if ay == 0 or (ay << 2) < ax:
            q = 0
        elif ax == 0 or (ax << 2) < ay:
            q = 4
        elif (ay << 1) < ax:
            q = 1
        elif (ax << 1) < ay:
            q = 3
        else:
            q = 2
    else:
        raise ValueError('8 or 16 slots required')
    if dx >= 0 and dy >= 0:
        return q
    if dx < 0 <= dy:
        return (quarter << 1) - q
    if dx < 0 and dy < 0:
        return (quarter << 1) + q
    return (slots - q) % slots


def phase_ring_signature(board, w, h, slots=16):
    """Lossy two-shell angular support around the EXACT rational centroid.

    n*x-sum(x) and n*y-sum(y) avoid centroid rounding and atan/float math.
    The two relative Chebyshev shells distinguish some radial collisions;
    occupancy, radial order and topology can still collide.
    """
    _, _, universe = compute_row_masks(w, h)
    validate_board(board, universe)
    if slots not in (8, 16):
        raise ValueError('8 or 16 slots required')
    nodes = unpack(board)
    n = len(nodes)
    sx = sum(i % w for i in nodes)
    sy = sum(i // w for i in nodes)
    vectors = [(integer_scale(i % w, n) - sx,
                integer_scale(i // w, n) - sy) for i in nodes]
    radius = max((max(abs(x), abs(y)) for x, y in vectors), default=0)
    rings = [0, 0]
    center = 0
    for dx, dy in vectors:
        slot = direction_slot(dx, dy, slots)
        if slot is None:
            center = 1
        else:
            shell = 0 if (max(abs(dx), abs(dy)) << 1) <= radius else 1
            rings[shell] |= 1 << slot
    return dict(slots=slots, rings=tuple(rings), center=center, count=n)


def match_phase_rings(a, b):
    """All cyclic offsets, exact rational Dice ranking; ties retained.

    A ring match is candidate retrieval, not proof of equal shapes.
    Empty signatures have no defined orientation.
    """
    if a['slots'] != b['slots']:
        raise ValueError('slot counts differ')
    slots = a['slots']
    denominator = sum(v.bit_count() for v in a['rings'] + b['rings'])
    denominator += a['center'] + b['center']
    if not a['count'] or not b['count']:
        return dict(numerator=0, denominator=denominator, shifts=[], ambiguous=True)
    best, shifts = -1, []
    for shift in range(slots):
        overlap = sum((x & rotate_ring(y, shift, slots)).bit_count()
                      for x, y in zip(a['rings'], b['rings']))
        overlap += a['center'] & b['center']
        if overlap > best:
            best, shifts = overlap, [shift]
        elif overlap == best:
            shifts.append(shift)
    return dict(numerator=best << 1, denominator=denominator,
                shifts=shifts, ambiguous=len(shifts) != 1)


def analyze_venn_and_implication_bitboard(a, b, c, universe):
    for board in (a, b, c):
        validate_board(board, universe)
    regions = {}
    for flags in range(8):
        region = universe
        for bit, board in enumerate((a, b, c)):
            region &= board if flags & (1 << bit) else universe ^ board
        regions[format(flags, '03b')] = region.bit_count()
    overlap, ab, ba = (a & b).bit_count(), (a & ~b).bit_count(), (b & ~a).bit_count()
    if not a:
        relation = 'empty_antecedent'
    elif ab == 0:
        relation = 'equal' if ba == 0 else 'A_subset_B'
    elif ba == 0 and b:
        relation = 'B_subset_A'
    elif overlap and ab <= (overlap >> 3) and ba > (ab << 1):
        relation = 'approximate_A_in_B'
    elif overlap and ba <= (overlap >> 3) and ab > (ba << 1):
        relation = 'approximate_B_in_A'
    elif not overlap and a and b:
        relation = 'mutually_exclusive'
    else:
        relation = 'partial_overlap'
    return dict(venn_counts=regions, relation_AB=relation,
                support_A=a.bit_count(), overlap_AB=overlap, counterexamples_AB=ab,
                B_without_A=ba, causal_claim=False)


def fwht8_add_only(values):
    if len(values) != 8 or any(type(v) is not int for v in values):
        raise ValueError('eight integers required')
    out = list(values)
    step = 1
    while step < 8:
        for start in range(0, 8, step << 1):
            for i in range(start, start + step):
                a, b = out[i], out[i + step]
                out[i], out[i + step] = a + b, a - b
        step <<= 1
    return [v >> 1 for v in out]


def ternary_diff(ap, an, bp, bn):
    return ((((ap & bn) | (an & bp)).bit_count() << 1)
            + ((ap | an) ^ (bp | bn)).bit_count())


class CalibratedTernaryPatch:
    def __init__(self, row, col):
        ru, rv = fwht8_add_only(row), fwht8_add_only(col)
        self.dc_level = (ru[0] + rv[0]) >> 1
        self.ac = (ru[1:], rv[1:])
        self.ac_l1 = sum(abs(v) for values in self.ac for v in values)
        self.u_pos = self.u_neg = self.v_pos = self.v_neg = self.active_spins = 0

    def quantize_spins(self, deadzone):
        masks = []
        threshold = (self.ac_l1 >> 3) + deadzone
        for values in self.ac:
            pos = neg = 0
            for i, value in enumerate(values):
                if value > threshold:
                    pos |= 1 << i
                elif value < -threshold:
                    neg |= 1 << i
            masks.extend((pos, neg))
        self.u_pos, self.u_neg, self.v_pos, self.v_neg = masks
        self.active_spins = sum(v.bit_count() for v in masks)


def spin_distance(a, b, invert=False, collapse=False):
    ap, an, avp, avn = a.u_pos, a.u_neg, a.v_pos, a.v_neg
    if invert:
        ap, an, avp, avn = an, ap, avn, avp
    if collapse:
        ap = an = avp = avn = 0
    return (ternary_diff(ap, an, b.u_pos, b.u_neg)
            + ternary_diff(avp, avn, b.v_pos, b.v_neg))


def reconstruct_fixed_point(history, w, h, anisotropy_x_shift=0):
    """Monotone pruning at a fixed threshold until equality, not three passes.

    Every edge must be reciprocal. Only complete four-edge unit squares lock.
    X/Y coexistence is a corner bonus; it does not create diagonal samples.
    """
    offsets, total = row_offsets(w, h)
    if type(anisotropy_x_shift) is not int or not 0 <= anisotropy_x_shift <= 4:
        raise ValueError('anisotropy shift must be 0..4')
    if any(type(i) is not int or not 0 <= i < total or type(t) is not int
           or t < 0 or t >> 16 for i, t in history.items()):
        raise ValueError('invalid history')
    active, iterations = set(history), 0
    while True:
        links = {}
        for idx in active:
            x, y = idx % w, idx // w
            mask = 0
            for si in range(4):
                for di, (dx, dy) in enumerate(DIRS):
                    bit = 1 << ((si << 2) + di)
                    nx, ny = x + (dx << si), y + (dy << si)
                    if history[idx] & bit and 0 <= nx < w and 0 <= ny < h:
                        nb = offsets[ny] + nx
                        if nb in active and history[nb] & (1 << ((si << 2) + (di ^ 1))):
                            mask |= bit
            links[idx] = mask
        locked = set()
        for idx in active:
            x, y = idx % w, idx // w
            r, d, rd = idx + 1, idx + w, idx + w + 1
            if x + 1 < w and y + 1 < h and {r, d, rd} <= active:
                if links[idx] & 2 and links[idx] & 8 and links[r] & 8 and links[d] & 2:
                    locked.update((idx, r, d, rd))
        nxt = set(locked)
        for idx, mask in links.items():
            score = 0
            for si in range(4):
                layer = (mask >> (si << 2)) & 15
                score += (layer & 3).bit_count() << anisotropy_x_shift
                score += (layer & 12).bit_count()
                if layer & 3 and layer & 12:
                    score += 2
            if score >= 3:
                nxt.add(idx)
        iterations += 1
        if nxt == active:
            return dict(nodes=active, topology=links, iterations=iterations, converged=True)
        active = nxt


class FiveWaySurveyEngine:
    def __init__(self, patches, width, height):
        self.offsets, total = row_offsets(width, height)
        if len(patches) != total:
            raise ValueError('patch count does not match grid')
        self.patches, self.w, self.h = patches, width, height

    def auto_calibrate(self):
        tiers = {}
        for patch in self.patches:
            tier = patch.ac_l1.bit_length()
            tiers[tier] = tiers.get(tier, 0) + 1
        n = len(self.patches)
        target = n - (n >> 2)
        accumulated = 0
        for tier, count in sorted(tiers.items()):
            accumulated += count
            if accumulated >= target:
                break
        base = 1 << tier
        thresholds = ((base >> 3) + 2, base + (base >> 2), (base >> 1) + 10)
        for patch in self.patches:
            patch.quantize_spins(thresholds[0])
        return thresholds

    def execute_5way_survey(self, anisotropy_x_shift=0, prev_frame_bitboard=None):
        """Full recomputation is the temporal correctness reference.

        XOR is reported only; unchanged rough support can hide changed spins,
        global calibration and pruning cascades. No unsafe partial reuse.
        """
        deadzone, ac_threshold, dc_threshold = self.auto_calibrate()
        candidates, slopes = set(), set()
        for idx, patch in enumerate(self.patches):
            if patch.active_spins and patch.ac_l1 >= ac_threshold:
                candidates.add(idx)
                continue
            x, y = idx % self.w, idx // self.w
            for dx, dy in DIRS:
                nx, ny = x + (dx << 2), y + (dy << 2)
                if 0 <= nx < self.w and 0 <= ny < self.h:
                    nb = self.patches[self.offsets[ny] + nx]
                    if abs(patch.dc_level - nb.dc_level) >= dc_threshold:
                        candidates.add(idx)
                        slopes.add(idx)
                        break
        history = {}
        for idx in candidates:
            patch = self.patches[idx]
            x, y = idx % self.w, idx // self.w
            resonance = topo = 0
            rot = ternary_diff(patch.u_pos, patch.u_neg,
                               ((patch.u_pos << 1) | (patch.u_pos >> 7)) & 255,
                               ((patch.u_neg << 1) | (patch.u_neg >> 7)) & 255)
            for si in range(4):
                for di, (dx, dy) in enumerate(DIRS):
                    nx, ny = x + (dx << si), y + (dy << si)
                    if not (0 <= nx < self.w and 0 <= ny < self.h):
                        continue
                    nb_idx = self.offsets[ny] + nx
                    if nb_idx not in candidates:
                        continue
                    nb = self.patches[nb_idx]
                    original = spin_distance(patch, nb)
                    delta = abs(spin_distance(patch, nb, invert=True) - original)
                    delta += abs(spin_distance(patch, nb, collapse=True) - original)
                    bonus = 4 if idx in slopes and nb_idx in slopes else 0
                    if delta + bonus >= 3:
                        resonance += delta + bonus
                        topo |= 1 << ((si << 2) + di)
            if topo and rot + resonance >= 6:
                history[idx] = topo
        result = reconstruct_fixed_point(history, self.w, self.h, anisotropy_x_shift)
        board = pack_to_bitboard(result['nodes'], self.w, self.h)
        right, left, universe = compute_row_masks(self.w, self.h)
        if prev_frame_bitboard is not None:
            validate_board(prev_frame_bitboard, universe)
        delta = board ^ prev_frame_bitboard if prev_frame_bitboard is not None else board
        result.update(bitboard=board, history=history, thresholds=(deadzone, ac_threshold, dc_threshold),
                      candidate_count=len(candidates), total_patches=len(self.patches),
                      euler_stats=compute_bitboard_topology_and_betti(board, self.w, self.h),
                      temporal_delta=delta,
                      temporal_halo=dilate(delta, self.w, right, left, universe),
                      temporal_mode='full_recompute_reference')
        return result


# Evaluation, synthetic fixtures and timings below are outside the integer kernel.
def evaluation(truth, prediction, patches, w, h):
    def dice(a, b):
        return 2 * len(a & b) / (len(a) + len(b)) if a or b else 1.0
    union = truth | prediction
    iou = len(truth & prediction) / len(union) if union else 1.0
    denominator = sum(patches[i].ac_l1 + 4 for i in truth) + sum(patches[i].ac_l1 + 4 for i in prediction)
    energy = 2 * sum(patches[i].ac_l1 + 4 for i in truth & prediction) / denominator if denominator else 1.0
    # Symmetric, bounded fuzzy spatial overlap plus reciprocal unit-edge Dice.
    # This exploratory metric is not calibrated against perception/XAI fidelity.
    def field(nodes):
        halo, edges = set(nodes), set()
        for idx in nodes:
            x, y = idx % w, idx // w
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nb = ny * w + nx
                    halo.add(nb)
                    if nb in nodes:
                        edges.add((min(idx, nb), max(idx, nb)))
        return halo, edges
    th, te = field(truth)
    ph, pe = field(prediction)
    flux = (4 * dice(truth, prediction) + 2 * dice(th, ph) + dice(te, pe)) / 7
    if not truth or not prediction:
        flux = 1.0 if not truth and not prediction else 0.0
    return dict(IoU=iou, Energy_Dice=energy, Flux_Field=flux)


def shift_nodes(nodes, w, h, dx, dy):
    """Toroidal count-preserving perturbation; can change finite-grid topology."""
    return {((i // w + dy) % h) * w + ((i % w + dx) % w) for i in nodes}


def scenario_data(name, rng, w=32, h=32):
    if name not in SCENARIOS or w != 32 or h != 32:
        raise ValueError('benchmark fixtures require a known scenario and 32x32 grid')
    patches, truth = [], set()
    for y in range(h):
        for x in range(w):
            d = max(abs(x - 16), abs(y - 16))
            if name == 'Dense_Object':
                feature = 8 <= x <= 24 and 8 <= y <= 24
            elif name == 'Thin_Skeleton':
                feature = abs(x - y) <= 1 or abs(31 - x - y) <= 1
            elif name == 'Hollow_Ring':
                feature = 6 <= d <= 9
            elif name == 'Double_Ring':
                # Two square annuli sharing a wall, exactly two holes.
                feature = (4 <= max(abs(x - 10), abs(y - 16)) <= 6
                           or 4 <= max(abs(x - 21), abs(y - 16)) <= 6)
            elif name in ('Smooth_Gradient', 'High_Noise_Dark'):
                feature = 10 <= x <= 22 and 10 <= y <= 22
            elif name == 'Multi_Scale_Clusters':
                feature = ((4 <= x <= 9 and 4 <= y <= 9) or
                           (20 <= x <= 25 and 20 <= y <= 25) or
                           (22 <= x <= 23 and 6 <= y <= 7))
            else:
                feature = y in (6, 7, 18, 19) and 4 <= x <= 27
            if feature:
                truth.add(y * w + x)
                if name == 'Smooth_Gradient':
                    row = [95 + (i << 1) + rng.randint(-2, 2) for i in range(8)]
                    col = [95 + (i << 1) + rng.randint(-2, 2) for i in range(8)]
                else:
                    row = [(135 if i & 1 == 0 else 25) + rng.randint(-6, 6) for i in range(8)]
                    col = [(125 if i & 2 == 0 else 30) + rng.randint(-6, 6) for i in range(8)]
            elif name == 'High_Noise_Dark' and rng.random() < 0.12:
                row, col = ([rng.randint(0, 140) for _ in range(8)] for _ in range(2))
            else:
                row, col = ([50 + rng.randint(-3, 3) for _ in range(8)] for _ in range(2))
            patches.append(CalibratedTernaryPatch(row, col))
    return patches, truth


def rotation_experiment():
    # Input and distractor are fixed before measuring. Raster rounding at 30/60
    # degrees is part of the approximation, and all ties/collisions are retained.
    points = {(x, y) for x in range(-6, 7) for y in range(-6, 7)
              if (x == -4 and -5 <= y <= 5) or (y == 4 and -4 <= x <= 6)
              or (x == 3 and -2 <= y <= 1)}
    def board_of(points):
        return pack_to_bitboard({(y + 16) * 32 + x + 16 for x, y in points}, 32, 32)
    source = board_of(points)
    signature = phase_ring_signature(source, 32, 32)
    rows = []
    for degrees in (0, 30, 60, 90, 180, 270):
        angle = math.radians(degrees)
        rotated = {(round(x * math.cos(angle) - y * math.sin(angle)),
                    round(x * math.sin(angle) + y * math.cos(angle))) for x, y in points}
        board = board_of(rotated)
        match = match_phase_rings(signature, phase_ring_signature(board, 32, 32))
        rows.append(dict(degrees=degrees, count=board.bit_count(), **match))
    # Deliberate saturation collision: filled square and its perimeter.
    square = pack_to_bitboard({y * 32 + x for y in range(8, 25) for x in range(8, 25)}, 32, 32)
    perimeter = pack_to_bitboard({y * 32 + x for y in range(8, 25) for x in range(8, 25)
                                 if x in (8, 24) or y in (8, 24)}, 32, 32)
    collision = match_phase_rings(phase_ring_signature(square, 32, 32),
                                 phase_ring_signature(perimeter, 32, 32))
    return dict(rotations=rows, distractor=collision,
                distractor_topology=[compute_bitboard_topology_and_betti(b, 32, 32)
                                     for b in (square, perimeter)])


def run_benchmark(trials=25, seed=20261022):
    records, measurements, boards = [], [], {}
    for name in SCENARIOS:
        previous = None
        for trial in range(trials):
            derived = int.from_bytes(hashlib.sha256(f'{seed}:{name}:{trial}'.encode()).digest()[:8], 'big')
            start = time.perf_counter_ns()
            patches, truth = scenario_data(name, random.Random(derived))
            encoded = time.perf_counter_ns()
            result = FiveWaySurveyEngine(patches, 32, 32).execute_5way_survey(
                anisotropy_x_shift=int(name == 'Anisotropic_Matrix'), prev_frame_bitboard=previous)
            ended = time.perf_counter_ns()
            prediction = result['nodes']
            metrics = evaluation(truth, prediction, patches, 32, 32)
            shifted = evaluation(truth, shift_nodes(prediction, 32, 32, 2, 2), patches, 32, 32)
            gt = compute_bitboard_topology_and_betti(pack_to_bitboard(truth, 32, 32), 32, 32)
            topology = result['euler_stats']
            records.append(dict(scenario=name, trial=trial, seed=derived, **metrics,
                                sensitivity_drop=metrics['Flux_Field'] - shifted['Flux_Field'],
                                truth_topology=gt, prediction_topology=topology,
                                topology_match=all(gt[k] == topology[k] for k in ('chi', 'b0_clusters', 'b1_holes')),
                                tp=len(truth & prediction), fp=len(prediction - truth), fn=len(truth - prediction),
                                thresholds=result['thresholds'], iterations=result['iterations'],
                                skip_count=1024 - result['candidate_count'],
                                delta_count=result['temporal_delta'].bit_count(),
                                prediction=sorted(prediction), truth=sorted(truth),
                                temporal_mode=result['temporal_mode']))
            measurements.append(dict(scenario=name, trial=trial,
                                     encoding_ns=encoded - start, survey_ns=ended - encoded,
                                     total_ns=ended - start))
            previous = result['bitboard']
        boards[name] = previous
    _, _, universe = compute_row_masks(32, 32)
    return dict(records=records, rotation=rotation_experiment(),
                venn=analyze_venn_and_implication_bitboard(
                    boards['Hollow_Ring'], boards['Dense_Object'], boards['Smooth_Gradient'], universe),
                measurements=measurements,
                environment=dict(python=platform.python_version(), platform=platform.platform()),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def render_report(report):
    lines = ['# 5-Way topology and phase-ring experiment', '',
             'Synthetic 32x32 profiles. Timings are host observations; temporal mode is full recomputation.', '',
             '| Scenario | IoU % | Energy Dice % | Flux % | Drop pp | Topology matches | Survey ms |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for name in SCENARIOS:
        rows = [r for r in report['records'] if r['scenario'] == name]
        def mean(key):
            return sum(r[key] for r in rows) / len(rows)
        ms = [r['survey_ns'] / 1e6 for r in report['measurements'] if r['scenario'] == name]
        lines.append(f'| {name} | {100*mean("IoU"):.2f} | {100*mean("Energy_Dice"):.2f} | '
                     f'{100*mean("Flux_Field"):.2f} | {100*mean("sensitivity_drop"):.2f} | '
                     f'{sum(r["topology_match"] for r in rows)}/{len(rows)} | {sum(ms)/len(ms):.3f} |')
    lines += ['', '## Phase-ring rotation observations', '',
              '| Degrees | Ring Dice % | Best cyclic offsets | Ambiguous |', '|---|---:|---|---|']
    for row in report['rotation']['rotations']:
        score = row['numerator'] / row['denominator'] if row['denominator'] else 0
        lines.append(f'| {row["degrees"]} | {100*score:.2f} | {row["shifts"]} | {row["ambiguous"]} |')
    lines += ['', 'Ring signatures are lossy; exact cyclic alignment is not arbitrary-angle shape equivalence.',
              '', '## Three-condition Venn', '', 'Bit keys are CBA (001 = A only). Inclusion is empirical, not causal.',
              '', '```json', json.dumps(report['venn'], indent=2), '```', '',
              '## Support maps', '', 'Legend: # TP, + FP, - FN, . background.']
    for name in SCENARIOS:
        row = next(r for r in reversed(report['records']) if r['scenario'] == name)
        truth, prediction = set(row['truth']), set(row['prediction'])
        lines += ['', f'### {name}', '', '```text']
        for y in range(32):
            lines.append(''.join('#' if i in truth & prediction else '+' if i in prediction
                                 else '-' if i in truth else '.' for i in range(y*32, (y+1)*32)))
        lines.append('```')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials', type=int, default=25)
    parser.add_argument('--seed', type=int, default=20261022)
    parser.add_argument('--output', type=Path, default=Path('build/five-way-survey'))
    args = parser.parse_args(argv)
    if not 1 <= args.trials <= 1000:
        parser.error('--trials must be 1..1000')
    report = run_benchmark(args.trials, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    text = render_report(report)
    (args.output / 'report.md').write_text(text, encoding='utf-8')
    print(text, end="")


if __name__ == '__main__':
    main()
