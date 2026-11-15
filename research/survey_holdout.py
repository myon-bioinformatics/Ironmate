# survey_holdout.py
# __all__: 4
"""Frozen 3-Way Survey evaluation on shape and signal families absent from tuning.

This is a synthetic profile experiment, not a natural-image benchmark. Accuracy
is an observation, never a success gate. Exceptions/invariant violations fail.
The existing engine, training fixtures and historical evidence are untouched.
"""
from __future__ import annotations

import argparse, gzip, hashlib, json, platform, random, sys
from dataclasses import asdict
from pathlib import Path

if __package__:
    from . import littlebit_jev_3way_survey as survey
else:
    import littlebit_jev_3way_survey as survey

__all__ = ["generate_case", "evaluate", "markdown_report", "main"]

# Selected by the PREVIOUS experiment, before these families were introduced.
FROZEN_CONFIG = survey.Config(deadzone_shift=3, ub_threshold=64, min_links=2, max_diff=4)
HELDOUT_SHAPES = ("concave_comb", "perforated_slab", "border_serpentine")
HELDOUT_SIGNALS = ("phase_mixture", "quantized_low_contrast", "impulsive_tail", "correlated_walk")
HEIGHT = WIDTH = 32
REFERENCE_SHAPE = "dense_reference"
REFERENCE_SIGNAL = "reference"
SEEDS = (20261020, 20261021)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def _case_seed(seed, shape, signal, trial):
    return int(_digest(["survey-family-holdout/1", seed, shape, signal, trial])[:16], 16)


def _truth(shape, trial):
    if shape not in (REFERENCE_SHAPE, *HELDOUT_SHAPES):
        raise ValueError(f"unknown shape: {shape}")
    cells = set()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if shape == REFERENCE_SHAPE:
                feature = 8 <= x <= 24 and 8 <= y <= 24
            elif shape == "concave_comb":
                feature = (4 <= x <= 6 and 4 <= y <= 27
                           or 4 <= x <= 26 and 4 <= y <= 27 and (y - 4) % 6 < 2)
            elif shape == "perforated_slab":
                hole = any(hx <= x < hx + 3 and hy <= y < hy + 3
                           for hx in (8, 16, 24) for hy in (8, 16, 24))
                feature = 3 <= x <= 28 and 3 <= y <= 28 and not hole
            else:
                # A one-cell open path, with alternating turns on both borders.
                feature = (y in (0, 8, 16, 24)
                           or x == 31 and (0 <= y <= 8 or 16 <= y <= 24)
                           or x == 0 and 8 <= y <= 16)
            if feature:
                # Predetermined shape variants, shared across signal families.
                xx = WIDTH - 1 - x if shape != REFERENCE_SHAPE and trial % 3 == 1 else x
                yy = HEIGHT - 1 - y if shape != REFERENCE_SHAPE and trial % 3 == 2 else y
                cells.add(yy * WIDTH + xx)
    return cells


def _reference_profile(feature, rng):
    # Same signal distribution as the old Dense_Object generator; control only.
    if feature:
        return ([((130 if i & 1 == 0 else 25) + rng.randint(-8, 8)) for i in range(8)],
                [((120 if i & 2 == 0 else 30) + rng.randint(-8, 8)) for i in range(8)])
    return ([50 + rng.randint(-3, 3) for _ in range(8)],
            [50 + rng.randint(-3, 3) for _ in range(8)])


def _profile(feature, signal, rng):
    if signal == "reference":
        return _reference_profile(feature, rng)
    if signal == "correlated_walk":
        profiles = []
        for _ in range(2):
            value = rng.randint(70, 100) if feature else rng.randint(45, 55)
            increments = (-12, -6, 6, 12) if feature else (-3, -1, 1, 3)
            values = [value]
            for _ in range(7):
                value = max(0, min(255, value + rng.choice(increments)))
                values.append(value)
            profiles.append(values)
        return tuple(profiles)
    if signal == "quantized_low_contrast" and feature:
        amplitude = rng.choice((1, 2, 3, 4, 6, 8))
        return ([50 + (amplitude if i & 1 == 0 else -amplitude) for i in range(8)],
                [50 + (amplitude if i & 2 == 0 else -amplitude) for i in range(8)])
    row, col = _reference_profile(feature, rng)
    if signal == "phase_mixture" and feature:
        a, b = rng.randrange(8), rng.randrange(8)
        row, col = row[a:] + row[:a], col[b:] + col[:b]
    if signal == "impulsive_tail":
        # Bernoulli contamination of EVERY coefficient, in foreground AND background.
        row, col = ([rng.choice((0, 255)) if rng.random() < 0.12 else v for v in values]
                    for values in (row, col))
    return row, col


def _panel(shape, signal):
    if shape == REFERENCE_SHAPE:
        return "reference" if signal == REFERENCE_SIGNAL else "signal_only"
    return "shape_only" if signal == REFERENCE_SIGNAL else "shape_and_signal"


def _validate(profiles, truth, result):
    size = WIDTH * HEIGHT
    if len(profiles) != size or not truth or not truth <= set(range(size)):
        raise ValueError("invalid holdout grid/truth fixture")
    if any(len(pair) != 2 or any(len(values) != 8 or any(type(v) is not int or not 0 <= v <= 255
               for v in values) for values in pair) for pair in profiles):
        raise ValueError("invalid holdout integer profile")
    prediction = result["normal_set"]
    if not prediction <= set(range(size)):
        raise ValueError("survey returned out-of-grid prediction")
    history = {int(k): v for k, v in json.loads(json.dumps(result["history"])).items()}
    if survey.reconstruct_blind(history, WIDTH, HEIGHT) != prediction:
        raise ValueError("serialized history does not reconstruct prediction")
    if result["skipped"] + result["candidates_count"] != size:
        raise ValueError("candidate accounting mismatch")


def generate_case(seed, shape, signal, trial):
    """Return exact integer profiles and patch-support labels; no parameter tuning."""
    if type(seed) is not int or type(trial) is not int or trial < 0:
        raise ValueError("integer seed and nonnegative integer trial required")
    if signal not in (REFERENCE_SIGNAL, *HELDOUT_SIGNALS):
        raise ValueError(f"unknown signal: {signal}")
    truth = _truth(shape, trial)
    rng = random.Random(_case_seed(seed, shape, signal, trial))
    profiles = [_profile(i in truth, signal, rng) for i in range(WIDTH * HEIGHT)]
    return profiles, truth


def evaluate(trials=3, seeds=SEEDS):
    """Reference, shape-only, signal-only and crossed panels; retain all outcomes.

    Full inputs/labels/predictions are stored so replay need not trust a future RNG
    or generator version. Timings are deliberately excluded from regression data.
    """
    if type(trials) is not int or not 1 <= trials <= 20:
        raise ValueError("trials must be 1..20")
    seeds = tuple(seeds)
    if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("distinct integer seeds required")
    records = []
    for shape in (REFERENCE_SHAPE, *HELDOUT_SHAPES):
        for signal in (REFERENCE_SIGNAL, *HELDOUT_SIGNALS):
            for seed in seeds:
                for trial in range(trials):
                    profiles, truth = generate_case(seed, shape, signal, trial)
                    result = survey.ThreeWaySurveyEngine(
                        survey.encode_profiles(profiles, FROZEN_CONFIG), WIDTH, HEIGHT
                    ).execute_survey(FROZEN_CONFIG)
                    _validate(profiles, truth, result)
                    prediction = sorted(result["normal_set"])
                    observed = survey.metrics(truth, set(prediction), WIDTH, HEIGHT)
                    records.append({"shape": shape, "signal": signal, "panel": _panel(shape, signal),
                                    "seed": seed, "trial": trial,
                                    "derived_seed": _case_seed(seed, shape, signal, trial),
                                    "input_sha256": _digest(profiles), "truth_sha256": _digest(sorted(truth)),
                                    "prediction_sha256": _digest(prediction), **observed,
                                    "outcome": "observed_mismatch" if observed["fp"] or observed["fn"] else "exact",
                                    "candidate_count": result["candidates_count"], "skipped": result["skipped"],
                                    "profiles": profiles, "truth": sorted(truth), "prediction": prediction})
    summary = []
    for shape in (REFERENCE_SHAPE, *HELDOUT_SHAPES):
        for signal in (REFERENCE_SIGNAL, *HELDOUT_SIGNALS):
            rows = [r for r in records if r["shape"] == shape and r["signal"] == signal]
            summary.append({"shape": shape, "signal": signal, "panel": _panel(shape, signal),
                            "cases": len(rows), "mean_iou": sum(r["iou"] for r in rows) / len(rows),
                            "min_iou": min(r["iou"] for r in rows),
                            "exact_cases": sum(r["outcome"] == "exact" for r in rows),
                            **{key: sum(r[key] for r in rows) for key in ("tp", "fp", "fn", "tn")}})
    return {"schema": "ironmate-survey-family-holdout/1", "config": asdict(FROZEN_CONFIG),
            "strides": list(survey.STRIDES), "width": WIDTH, "height": HEIGHT,
            "trials_per_seed": trials, "seeds": list(seeds),
            "runtime": f"{sys.version.split()[0]} {platform.platform()} {platform.machine()}",
            "engine_sha256": hashlib.sha256(Path(survey.__file__).read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "records_sha256": _digest(records), "summary": summary, "records": records}


def markdown_report(report):
    lines = ["# report.md", "", "# Frozen shape/signal-family holdout", "",
             "Synthetic row/column profiles; patch-support IoU, not pixel restoration or natural-image generalization.",
             "", f"Config: {report['config']}; strides: {report['strides']} (no tuning).",
             f"Seeds: {report['seeds']}; trials/seed/pair: {report['trials_per_seed']}; "
             f"grid: {report['width']}x{report['height']}; cases: {len(report['records'])}.",
             f"Engine SHA-256: {report['engine_sha256']}",
             f"Harness SHA-256: {report['harness_sha256']}",
             f"Records SHA-256: {report['records_sha256']}", "",
             "Reference uses the original dense shape/signal; shape-only and signal-only controls isolate each change.",
             "Families were absent from the original six-scenario generator/tuning. These results now form a regression set, not a reusable unseen validation set.",
             "", "| Panel | Shape | Signal | Cases | Mean IoU | Minimum IoU | FP | FN | Exact cases |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in report["summary"]:
        lines.append(f"| {row['panel']} | {row['shape']} | {row['signal']} | {row['cases']} | "
                     f"{row['mean_iou']:.6f} | {row['min_iou']:.6f} | {row['fp']} | {row['fn']} | {row['exact_cases']} |")
    lines += ["", "## Interpretation and failure policy", "",
              "Phase mixtures change neighboring ternary signs; low amplitudes can fall below the frozen energy/deadzone gates; bounded 0/255 impulsive contamination alters foreground and background; random walks change AC structure. Misses and false positives are retained observations.",
              "An accuracy mismatch is not a harness failure. Invalid fixtures, non-finite serialization, broken accounting/history, or engine exceptions fail execution. No all-100%-IoU, positive-shift-drop or runtime gate is imposed.",
              "The CLI writes build/survey-holdout/results.json.gz with every profile, label and prediction, seeds and hashes. The raw archive is generated, not checked in beside this report. summary.json retains per-case fingerprints and outcomes. Gzip uses mtime=0; floating-point timing is absent.",
              "Reproduce the default archive and report: python -S scripts/survey_holdout.py --trials 3 --output build/survey-holdout. Preserve the archive separately for replay independent of future generator versions.",
              "The prior H8//2 rounding, projection collision and connected false-pattern counterexamples remain unchanged. No engine changes, new scheduled CI or Aoi implementation changes are included."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("build/survey-holdout"))
    args = parser.parse_args(argv)
    if not 1 <= args.trials <= 20:
        parser.error("trials must be 1..20")
    report = evaluate(args.trials)
    # Serialize before writing; errors cannot masquerade as a successful report.
    data = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    summary = {**report, "records": [{k: v for k, v in r.items() if k not in ("profiles", "truth", "prediction")}
                                    for r in report["records"]]}
    summary["raw_results_sha256"] = hashlib.sha256(data).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json.gz").write_bytes(gzip.compress(data, mtime=0))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    text = markdown_report(report)
    (args.output / "report.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
