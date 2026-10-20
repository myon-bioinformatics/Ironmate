#!/usr/bin/env python3
"""Experimental ternary structure survey, not pixel restoration or model XAI.

Standard library only, Python 3.10+. The integer kernel (FWHT, encoding,
interaction, survey and blind reconstruction) contains no multiplication.
Raster addressing, synthetic data and metrics are outside that claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


STRIDES = (1, 2, 4)
DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
SCENARIOS = ("Dense_Object", "Thin_Skeleton", "Hollow_Ring", "Smooth_Gradient",
             "High_Noise_Dark", "Multi_Scale_Clusters")

BIT_L, BIT_R, BIT_U, BIT_D = 1, 2, 4, 8
MASK_X_AXIS = BIT_L | BIT_R  # 0b0011 (horizontal / x-axis mask)
MASK_Y_AXIS = BIT_U | BIT_D  # 0b1100 (vertical / y-axis mask)


def fwht8_add_only(values):
    """H8(x) // 2; integer rounding means this is NOT an orthonormal rotation."""
    if len(values) != 8:
        raise ValueError("FWHT requires exactly eight integers")
    out = list(values)
    step = 1
    while step < 8:
        for start in range(0, 8, step << 1):
            for i in range(start, start + step):
                a, b = out[i], out[i + step]
                out[i], out[i + step] = a + b, a - b
        step <<= 1
    return [v >> 1 for v in out]


def rotate_8bit(bits, shift):
    s = shift & 7
    return ((bits << s) | (bits >> (8 - s))) & 255


def fairyfuse_ternary_diff(ap, an, bp, bn):
    """Exact L1 distance of ternary vectors represented by disjoint masks."""
    conflict = ((ap & bn) | (an & bp)).bit_count()
    vacancy = ((ap | an) ^ (bp | bn)).bit_count()
    return (conflict << 1) + vacancy


@dataclass(frozen=True)
class Config:
    deadzone_shift: int = 2
    ub_threshold: int = 26
    min_links: int = 1
    max_diff: int = 4

    def __post_init__(self):
        if not 0 <= self.deadzone_shift <= 8 or self.ub_threshold < 0:
            raise ValueError("invalid encoding threshold")
        if not 1 <= self.min_links <= 12 or not 0 <= self.max_diff <= 28:
            raise ValueError("invalid connection threshold")


class LittleBitTernaryPatch:
    """Row/column projections; no rank decomposition or rigorous bound claimed."""
    __slots__ = ("l1_energy", "u_pos", "u_neg", "v_pos", "v_neg", "active_spins")

    def __init__(self, row_8, col_8, deadzone_shift=2):
        ru, rv = fwht8_add_only(row_8), fwht8_add_only(col_8)
        lu, lv = sum(abs(v) for v in ru[1:]), sum(abs(v) for v in rv[1:])
        self.l1_energy = lu + lv
        tu, tv = (lu >> deadzone_shift) + 3, (lv >> deadzone_shift) + 3
        up = un = vp = vn = 0
        for i in range(1, 8):
            if ru[i] > tu:
                up |= 1 << i
            elif ru[i] < -tu:
                un |= 1 << i
            if rv[i] > tv:
                vp |= 1 << i
            elif rv[i] < -tv:
                vn |= 1 << i
        self.u_pos, self.u_neg, self.v_pos, self.v_neg = up, un, vp, vn
        self.active_spins = (up | un).bit_count() + (vp | vn).bit_count()


def interaction(a, b):
    return (fairyfuse_ternary_diff(a.u_pos, a.u_neg, b.u_pos, b.u_neg)
            + fairyfuse_ternary_diff(a.v_pos, a.v_neg, b.v_pos, b.v_neg))


def row_offsets(width, height):
    offsets, offset = [], 0
    for _ in range(height):
        offsets.append(offset)
        offset += width
    return offsets


def reconstruct_blind(history, width, height):
    """Way 3 accepts only coordinates, delta and topology; no engine or patches.

    An edge must have a reciprocal direction bit in the other surviving node.
    There is no interpolation/filling: the output is a sparse support mask.
    """
    offsets = row_offsets(width, height)
    result = set()
    for idx, info in history.items():
        x, y = idx % width, idx // width
        if not 0 <= idx < offsets[-1] + width:
            raise ValueError("history coordinate outside grid")
        for si, _stride in enumerate(STRIDES):
            for di, (dx, dy) in enumerate(DIRS):
                bit = (si << 2) + di
                if not info["topo"] & (1 << bit):
                    continue
                nx, ny = x + (dx << si), y + (dy << si)
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                neighbor = history.get(offsets[ny] + nx)
                reverse = (si << 2) + (di ^ 1)
                if neighbor is not None and neighbor["topo"] & (1 << reverse):
                    result.add(idx)
    return result


def run_5way_anisotropic_fixed_point(
    w: int,
    h: int,
    blind_history: dict[int, int] | dict[int, dict],
    anisotropy_x_shift: int = 1,
    max_iterations: int = 3
) -> tuple[set[int], set[int], int]:
    """[Way 3 -> Way 5: Blind anisotropic reconstruction & fixed-point convergence]

    Zero multiplication integer bitwise operations for fixed-point core extraction.
    Explicit grid boundary checking (0 <= nx < w, 0 <= ny < h) is enforced to prevent
    spurious row-wrap artifacts.
    Accepts history mapping where value is integer topology or dict containing 'topo'.
    """
    history_topo = {idx: (val["topo"] if isinstance(val, dict) else val)
                    for idx, val in blind_history.items()}
    offsets = row_offsets(w, h)
    active_nodes: set[int] = set(history_topo.keys())
    strides = (0, 1, 2, 3)
    dirs = ((-1, 0), (1, 0), (0, -1), (0, 1))

    converged_step = 0
    for step in range(max_iterations):
        next_nodes: set[int] = set()

        for idx in active_nodes:
            x, y = idx % w, idx // w
            topo = history_topo[idx]
            anisotropic_score = 0
            diagonal_bridges = 0

            for s_shift in strides:
                layer_bits = (topo >> (s_shift << 2)) & 0x0F
                if layer_bits == 0:
                    continue

                active_dir_flags = 0
                for d_idx, (dx, dy) in enumerate(dirs):
                    if layer_bits & (1 << d_idx):
                        nx = x + (dx << s_shift)
                        ny = y + (dy << s_shift)
                        if 0 <= nx < w and 0 <= ny < h:
                            n_flat = offsets[ny] + nx
                            if n_flat in active_nodes:
                                active_dir_flags |= (1 << d_idx)
                                if d_idx < 2:
                                    anisotropic_score += (1 << anisotropy_x_shift)
                                else:
                                    anisotropic_score += 1

                has_x = (active_dir_flags & MASK_X_AXIS) != 0
                has_y = (active_dir_flags & MASK_Y_AXIS) != 0
                if has_x and has_y:
                    diagonal_bridges += 2

            req_score = 2 + (step if step < 2 else 2)
            if (anisotropic_score + diagonal_bridges) >= req_score:
                next_nodes.add(idx)

        if next_nodes == active_nodes:
            converged_step = step + 1
            break
        active_nodes = next_nodes
        converged_step = step + 1

    shifted_nodes: set[int] = set()
    for idx in active_nodes:
        x, y = idx % w, idx // w
        sx, sy = (x + 2) % w, (y + 2) % h
        s_flat = offsets[sy] + sx
        topo = history_topo[idx]
        s_links = 0
        for d_idx, (dx, dy) in enumerate(dirs):
            if (topo & 0x0F) & (1 << d_idx):
                sn_flat = offsets[(sy + dy) % h] + ((sx + dx) % w)
                if sn_flat in active_nodes:
                    s_links += 1
        if s_links >= 2:
            shifted_nodes.add(s_flat)

    return active_nodes, shifted_nodes, converged_step


def supplied_reconstruction(history, width, height):
    """Original proposal's occupancy-only check and differently filtered shift.

    Kept ONLY for reproducing the proposal; do not use its shifted mask as a
    translation sensitivity measurement.
    """
    offsets = row_offsets(width, height)
    normal, shifted = set(), set()
    for idx, info in history.items():
        x, y = idx % width, idx // width
        sx, sy = (x + 2) % width, (y + 2) % height
        links = shifted_links = 0
        for si, _stride in enumerate(STRIDES):
            for di, (dx, dy) in enumerate(DIRS):
                if info["topo"] & (1 << ((si << 2) + di)):
                    nx, ny = x + (dx << si), y + (dy << si)
                    # Reproduce the original flattening, including row wrap.
                    flat = ny * width + nx
                    links += flat in history
                    snx, sny = (sx + (dx << si)) % width, (sy + (dy << si)) % height
                    shifted_links += offsets[sny] + snx in history
        if links >= 1:
            normal.add(idx)
        if shifted_links >= 2:
            shifted.add(offsets[sy] + sx)
    return normal, shifted


class ThreeWaySurveyEngine:
    def __init__(self, patches, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("positive dimensions required")
        self.offsets = row_offsets(width, height)
        if len(patches) != self.offsets[-1] + width:
            raise ValueError("patch count does not match grid")
        self.patches, self.w, self.h = patches, width, height

    def execute_survey(self, config=Config(), supplied=False, strides=STRIDES):
        candidates = {i: p for i, p in enumerate(self.patches)
                      if p.active_spins and p.l1_energy >= config.ub_threshold}
        history = {}
        for idx, p in candidates.items():
            x, y = idx % self.w, idx // self.w
            rotation = (fairyfuse_ternary_diff(p.u_pos, p.u_neg,
                                             rotate_8bit(p.u_pos, 1), rotate_8bit(p.u_neg, 1))
                        + fairyfuse_ternary_diff(p.v_pos, p.v_neg,
                                               rotate_8bit(p.v_pos, 3), rotate_8bit(p.v_neg, 3)))
            resonance = topology = links = 0
            for si, stride in enumerate(STRIDES):
                if stride not in strides:
                    continue
                for di, (dx, dy) in enumerate(DIRS):
                    nx, ny = x + (dx << si), y + (dy << si)
                    if not (0 <= nx < self.w and 0 <= ny < self.h):
                        continue
                    nb = candidates.get(self.offsets[ny] + nx)
                    if nb is None:
                        continue
                    original = interaction(p, nb)
                    inverted = (fairyfuse_ternary_diff(p.u_neg, p.u_pos, nb.u_pos, nb.u_neg)
                                + fairyfuse_ternary_diff(p.v_neg, p.v_pos, nb.v_pos, nb.v_neg))
                    collapse = nb.active_spins
                    # Supplied version used collapse/2 without subtracting original.
                    delta = abs(inverted - original)
                    delta += (collapse >> 1) if supplied else abs(collapse - original)
                    if delta >= 3 and (supplied or original <= config.max_diff):
                        resonance += delta
                        topology |= 1 << ((si << 2) + di)
                        links += 1
            if links >= (1 if supplied else config.min_links) and rotation + resonance >= 8:
                history[idx] = {"delta": rotation + resonance, "topo": topology, "links": links}
        if supplied:
            normal, legacy_shift = supplied_reconstruction(history, self.w, self.h)
        else:
            normal, legacy_shift = reconstruct_blind(history, self.w, self.h), None
        return {"normal_set": normal, "history": history,
                "skipped": len(self.patches) - len(candidates),
                "candidates_count": len(candidates), "legacy_shift": legacy_shift}


# Everything below is data preparation/evaluation, outside the integer kernel.
def shift_mask(mask, width, height, dx, dy):
    """Exact toroidal translation, preserving count; GT remains fixed."""
    return {((i // width + dy) % height) * width + (i % width + dx) % width for i in mask}


def centroid(mask, width):
    if not mask:
        return None
    return (sum(i % width for i in mask) / len(mask),
            sum(i // width for i in mask) / len(mask))


def metrics(truth, prediction, width, height):
    tp, fp, fn = len(truth & prediction), len(prediction - truth), len(truth - prediction)
    tn = width * height - tp - fp - fn
    union = tp + fp + fn
    center, target = centroid(prediction, width), centroid(truth, width)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "iou": tp / union if union else 1.0,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "com_error_patch": sum(abs(a - b) for a, b in zip(center, target))
            if center is not None and target is not None else None}


def scenario_seed(seed, scenario, trial):
    data = f"{seed}:{scenario}:{trial}".encode("ascii")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def generate_test_scenario(width, height, scenario, rng):
    """Proposal's six profile fixtures, not 8x8 raster patches or natural images."""
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    profiles, truth = [], set()
    for y in range(height):
        for x in range(width):
            if scenario == "Dense_Object":
                feature = width // 4 <= x <= width * 3 // 4 and height // 4 <= y <= height * 3 // 4
            elif scenario == "Thin_Skeleton":
                feature = abs(x - y) <= 1 or abs(width - 1 - x - y) <= 1
            elif scenario == "Hollow_Ring":
                dist = abs(x - (width >> 1)) + abs(y - (height >> 1))
                feature = width // 4 <= dist <= width // 4 + 3
            elif scenario in ("Smooth_Gradient", "High_Noise_Dark"):
                feature = width // 3 <= x <= width * 2 // 3 and height // 3 <= y <= height * 2 // 3
            else:
                feature = ((4 <= x <= 14 and 4 <= y <= 14)
                           or (width - 12 <= x <= width - 5 and height - 12 <= y <= height - 5)
                           or (width // 2 <= x <= width // 2 + 2 and 4 <= y <= 6))
            if feature:
                truth.add(y * width + x)
                if scenario == "Smooth_Gradient":
                    row = [40 + (i << 3) + rng.randint(-4, 4) for i in range(8)]
                    col = [100 - (i << 3) + rng.randint(-4, 4) for i in range(8)]
                else:
                    row = [(130 if i & 1 == 0 else 25) + rng.randint(-8, 8) for i in range(8)]
                    col = [(120 if i & 2 == 0 else 30) + rng.randint(-8, 8) for i in range(8)]
            elif scenario == "High_Noise_Dark" and rng.random() < 0.12:
                row, col = ([rng.randint(0, 140) for _ in range(8)],
                            [rng.randint(0, 140) for _ in range(8)])
            else:
                row, col = ([50 + rng.randint(-3, 3) for _ in range(8)],
                            [50 + rng.randint(-3, 3) for _ in range(8)])
            profiles.append((row, col))
    return profiles, truth


def encode_profiles(profiles, config):
    return [LittleBitTernaryPatch(row, col, config.deadzone_shift) for row, col in profiles]


def project_raster(rows):
    """8x8 non-overlapping blocks -> integer row/column means; discard no border.

    Opposite checkerboard detail can cancel in both projections. This adapter
    makes that information loss explicit, rather than calling it factorization.
    """
    height, width = len(rows), len(rows[0]) if rows else 0
    if not width or width % 8 or height % 8 or any(len(r) != width for r in rows):
        raise ValueError("rectangular raster with dimensions divisible by eight required")
    profiles = []
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            row = [sum(rows[y + j][x:x + 8]) >> 3 for j in range(8)]
            col = [sum(rows[y + j][x + i] for j in range(8)) >> 3 for i in range(8)]
            profiles.append((row, col))
    return profiles, width // 8, height // 8


def mean_present(values):
    present = [v for v in values if v is not None]
    return statistics.mean(present) if present else None


def evaluate(config, seeds, trials, width=32, height=32, supplied=False, strides=STRIDES):
    records = []
    for seed in seeds:
        for scenario in SCENARIOS:
            for trial in range(trials):
                start = time.perf_counter()
                profiles, truth = generate_test_scenario(
                    width, height, scenario, random.Random(scenario_seed(seed, scenario, trial)))
                generated = time.perf_counter()
                patches = encode_profiles(profiles, config)
                encoded = time.perf_counter()
                result = ThreeWaySurveyEngine(patches, width, height).execute_survey(config, supplied, strides)
                surveyed = time.perf_counter()
                normal = result["normal_set"]
                row = {"seed": seed, "scenario": scenario, "trial": trial,
                       **metrics(truth, normal, width, height),
                       "skip_rate": result["skipped"] / len(patches),
                       "generation_ms": (generated - start) * 1000,
                       "encoding_ms": (encoded - generated) * 1000,
                       "survey_ms": (surveyed - encoded) * 1000,
                       "end_to_end_ms": (surveyed - start) * 1000,
                       "sensitivity": {f"{dx},{dy}": metrics(truth, shift_mask(normal, width, height, dx, dy),
                                                            width, height)["iou"]
                                       for dx, dy in ((0, 0), (1, 0), (2, 2), (4, 4), (-2, -2))},
                       "prediction_sha256": hashlib.sha256(json.dumps(sorted(normal)).encode()).hexdigest()}
                row["sensitivity_drop"] = row["iou"] - row["sensitivity"]["2,2"]
                row["legacy_shift_iou"] = (metrics(truth, result["legacy_shift"], width, height)["iou"]
                                           if supplied else None)
                records.append(row)
    return records


def aggregate(records):
    out = []
    for scenario in SCENARIOS:
        rows = [r for r in records if r["scenario"] == scenario]
        summary = {"scenario": scenario, "trials": len(rows)}
        for field in ("iou", "precision", "recall", "skip_rate", "com_error_patch",
                      "sensitivity_drop", "generation_ms", "encoding_ms", "survey_ms", "end_to_end_ms",
                      "legacy_shift_iou"):
            summary[field] = mean_present([r[field] for r in rows])
        summary["missing_com"] = sum(r["com_error_patch"] is None for r in rows)
        for field in ("tp", "fp", "fn", "tn"):
            summary[field] = sum(r[field] for r in rows)
        summary["iou_min"] = min(r["iou"] for r in rows)
        summary["iou_stdev"] = statistics.pstdev(r["iou"] for r in rows)
        summary["sensitivity"] = {key: statistics.mean(r["sensitivity"][key] for r in rows)
                                  for key in rows[0]["sensitivity"]}
        out.append(summary)
    return out


def tune(trials, width, height):
    """Choose once on TRAIN seed only, then freeze before held-out evaluation."""
    # Deliberately small exhaustive search; max_diff is fixed, no test-set feedback.
    search = []
    for deadzone in (2, 3):
        for threshold in (26, 64):
            for links in (1, 2, 3):
                config = Config(deadzone, threshold, links)
                records = evaluate(config, (20261017,), trials, width, height)
                score = statistics.mean(r["iou"] for r in records)
                search.append({"config": asdict(config), "train_macro_iou": score})
    best = max(search, key=lambda row: row["train_macro_iou"])
    return Config(**best["config"]), search


def injection_control(config, width=8, height=8):
    """Actually inject a coherent pattern into empty background before rerun."""
    flat = ([50 for _ in range(8)], [50 for _ in range(8)])
    edge = ([130 if i & 1 == 0 else 25 for i in range(8)],
            [120 if i & 2 == 0 else 30 for i in range(8)])
    profiles = [flat for _ in range(width * height)]
    clean = ThreeWaySurveyEngine(encode_profiles(profiles, config), width, height).execute_survey(config)
    # A single spike, then a connected artificial texture: no ground-truth input to engine.
    profiles[3 * width + 3] = edge
    isolated = ThreeWaySurveyEngine(encode_profiles(profiles, config), width, height).execute_survey(config)
    for y in range(2, 5):
        for x in range(2, 5):
            profiles[y * width + x] = edge
    cluster = ThreeWaySurveyEngine(encode_profiles(profiles, config), width, height).execute_survey(config)
    return {"empty_detected": len(clean["normal_set"]),
            "isolated_injected_detected": len(isolated["normal_set"]),
            "coherent_9_patch_injected_detected": len(cluster["normal_set"])}


def render_svg(path, width, height, truth, prediction):
    """Exact colored grid comparison (no ASCII art needed)."""
    cells = []
    for idx in sorted(truth | prediction):
        color = "#169b62" if idx in truth & prediction else ("#d44848" if idx in prediction else "#e6ae24")
        cells.append(f'<rect x="{idx % width}" y="{idx // width}" width="1" height="1" fill="{color}"/>')
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
                    'width="512" height="512" shape-rendering="crispEdges">'
                    f'<rect width="{width}" height="{height}" fill="#eee"/>' + "".join(cells) + '</svg>', encoding="utf-8")


def raster_benchmark(config, width=4000, height=3000):
    """One real 12MP grayscale raster, not a natural-image or decoder benchmark."""
    start = time.perf_counter()
    rows = [bytearray([50]) * width for _ in range(height)]
    # Align synthetic textured object with complete blocks; truth is patch support.
    x0, x1 = (width // 4 // 8) * 8, (width * 3 // 4 // 8) * 8
    y0, y1 = (height // 4 // 8) * 8, (height * 3 // 4 // 8) * 8
    for y in range(y0, y1):
        rows[y][x0:x1] = bytes(130 if x & 1 == 0 else 25 for x in range(x0, x1))
    generated = time.perf_counter()
    profiles, w, h = project_raster(rows)
    projected = time.perf_counter()
    patches = encode_profiles(profiles, config)
    encoded = time.perf_counter()
    result = ThreeWaySurveyEngine(patches, w, h).execute_survey(config)
    surveyed = time.perf_counter()
    truth = {y * w + x for y in range(y0 // 8, y1 // 8) for x in range(x0 // 8, x1 // 8)}
    return {"width_pixels": width, "height_pixels": height, "patch_count": len(patches),
            **metrics(truth, result["normal_set"], w, h),
            "generation_ms": (generated - start) * 1000,
            "projection_ms": (projected - generated) * 1000,
            "encoding_ms": (encoded - projected) * 1000,
            "survey_ms": (surveyed - encoded) * 1000,
            "end_to_end_ms": (surveyed - start) * 1000,
            "skipped": result["skipped"], "decoder_included": False}


def markdown_report(report):
    lines = ["# 3-Way Survey CPU experiment", "",
             "Synthetic row/column profiles, not natural images. IoU measures patch support, not restored pixels.",
             "", f"Runtime: `{report['runtime']}`", "",
             f"Train seed: 20261017; held-out seeds: {report['test_seeds']}; "
             f"trials/scenario/seed: {report['trials']}; grid: {report['width']}×{report['height']} patches.",
             f"Frozen config: `{report['config']}`. Selection objective: train mean IoU; test labels never tune thresholds.",
             "", "Values below are averages; FP/FN are totals across trials. Time includes generation + encoding + survey.", ""]
    for name, result in report["experiments"].items():
        lines += [f"## {name}", "", "| Scenario | Skip% | IoU% | Precision% | Recall% | FP/FN | Shift drop pp | CoM L1 patches | ms/image |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in result["summary"]:
            fmt = lambda v: f"{v * 100:.2f}" if v is not None else "None"
            com = f"{r['com_error_patch']:.3f}" if r['com_error_patch'] is not None else "None"
            lines.append(f"| {r['scenario']} | {fmt(r['skip_rate'])} | {fmt(r['iou'])} | "
                         f"{fmt(r['precision'])} | {fmt(r['recall'])} | {r['fp']}/{r['fn']} | "
                         f"{fmt(r['sensitivity_drop'])} | {com} | {r['end_to_end_ms']:.2f} |")
        lines += ["", "Raw JSON includes every trial, seed, mask hash, IoU dispersion, missing centroids, stage timing and five shift offsets.", ""]
    lines += ["## Injection control", "", f"`{report['injection_control']}`", "",
              "A coherent injected texture can pass: structure consistency cannot establish semantic truth.", "",
              "## Raster measurement", ""]
    raster = report.get("large_raster")
    if raster is None:
        lines += ["Not requested (use --large-raster).", ""]
    else:
        lines += [f"{raster['width_pixels']}×{raster['height_pixels']} real grayscale pixels; "
                  f"{raster['patch_count']:,} patches; IoU {raster['iou'] * 100:.2f}%.", "",
                  "| Stage | ms |", "|---|---:|"]
        for field in ("generation_ms", "projection_ms", "encoding_ms", "survey_ms", "end_to_end_ms"):
            lines.append(f"| {field} | {raster[field]:.2f} |")
        lines += ["", "Single synthetic raster, excludes decoding and metric calculation; not a natural-image accuracy benchmark.", ""]
    lines += ["## Limits", "", "No claim of GPU/XAI replacement, physical Hamiltonian, certified pruning bound, image synthesis, or 12MP millisecond performance.",
              "Skip occurs after projection/FWHT/encoding; its cost is not zero. H8/2 is rounded, not orthonormal.",
              "Shift uses a torus to preserve cardinality and may have zero/negative drop for periodic or incorrect masks; drop is not a pass gate.",
              "The proposal's original shifted-mask score is stored separately as legacy_shift_iou; it is not a pure translation."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--train-trials", type=int, default=4)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--height", type=int, default=32)
    parser.add_argument("--output", type=Path, default=Path("build/three-way-survey"))
    parser.add_argument("--large-raster", action="store_true", help="also measure a synthetic 4000x3000 pixel raster")
    args = parser.parse_args(argv)
    if not (1 <= args.trials <= 1000 and 1 <= args.train_trials <= 100
            and 16 <= args.width <= 128 and 16 <= args.height <= 128):
        parser.error("trials 1..1000, train-trials 1..100, dimensions 16..128 required")
    config, search = tune(args.train_trials, args.width, args.height)
    seeds = (20261018, 20261019)
    report = {"schema": "ironmate-three-way-survey/1", "runtime": f"{sys.version.split()[0]} {platform.platform()} {platform.machine()}",
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "trials": args.trials, "width": args.width, "height": args.height,
              "test_seeds": seeds, "config": asdict(config), "training_search": search,
              "experiments": {}, "injection_control": injection_control(config)}
    report["large_raster"] = raster_benchmark(config) if args.large_raster else None
    for name, chosen, supplied, strides in (
            ("supplied_reference", Config(), True, STRIDES),
            ("corrected_default", Config(), False, STRIDES),
            ("corrected_tuned", config, False, STRIDES),
            ("corrected_tuned_stride1", config, False, (1,))):
        records = evaluate(chosen, seeds, args.trials, args.width, args.height, supplied, strides)
        report["experiments"][name] = {"config": asdict(chosen), "strides": strides,
                                       "summary": aggregate(records), "trials": records}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    text = markdown_report(report)
    (args.output / "report.md").write_text(text, encoding="utf-8")
    for scenario in SCENARIOS:
        profiles, truth = generate_test_scenario(args.width, args.height, scenario,
                                               random.Random(scenario_seed(seeds[0], scenario, 0)))
        prediction = ThreeWaySurveyEngine(encode_profiles(profiles, config), args.width, args.height).execute_survey(config)["normal_set"]
        render_svg(args.output / f"{scenario}.svg", args.width, args.height, truth, prediction)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
