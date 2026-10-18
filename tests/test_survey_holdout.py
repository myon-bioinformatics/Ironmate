# test_survey_holdout.py
# __all__: 0
"""Frozen observations and independent fixture/metric checks, not accuracy gates."""
import gzip, hashlib, json, random, subprocess, sys
from dataclasses import asdict
from pathlib import Path

import pytest

from scripts import littlebit_jev_3way_survey as survey
from scripts import survey_holdout as holdout

__all__ = []
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/evidence/survey-holdout/summary.json"


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def _scalar_metrics(truth, prediction):
    # Deliberately do not call the engine's set-based metrics implementation.
    counts = dict.fromkeys(("tp", "fp", "fn", "tn"), 0)
    for idx in range(1024):
        key = ("tp" if idx in prediction else "fn") if idx in truth else ("fp" if idx in prediction else "tn")
        counts[key] += 1
    union = counts["tp"] + counts["fp"] + counts["fn"]
    counts["iou"] = counts["tp"] / union if union else 1.0
    return counts


@pytest.fixture(scope="module")
def report():
    return holdout.evaluate()


def test_settings_are_frozen_from_prior_evidence_and_seeds_are_new(monkeypatch):
    prior = json.loads((ROOT / "docs/evidence/three-way-survey/summary.json").read_text())
    assert asdict(holdout.FROZEN_CONFIG) == prior["config"] == {
        "deadzone_shift": 3, "ub_threshold": 64, "min_links": 2, "max_diff": 4,
    }
    assert set(holdout.SEEDS).isdisjoint({20261017, *prior["test_seeds"]})
    def no_tuning(*args, **kwargs):
        pytest.fail("held-out evaluator must not tune")
    monkeypatch.setattr(survey, "tune", no_tuning)
    assert len(holdout.evaluate(trials=1, seeds=(20261020,))["records"]) == 20


def test_factorial_panels_and_frozen_observations(report):
    expected = json.loads(SNAPSHOT.read_text())
    assert len(report["records"]) == 120
    assert {p: sum(r["panel"] == p for r in report["records"]) for p in
            ("reference", "shape_only", "signal_only", "shape_and_signal")} == {
                "reference": 6, "shape_only": 18, "signal_only": 24, "shape_and_signal": 72,
            }
    assert report["summary"] == expected["summary"]
    for key in ("engine_sha256", "harness_sha256", "records_sha256", "config", "strides", "seeds"):
        assert report[key] == expected[key], key
    actual_records = [{k: v for k, v in r.items() if k not in ("profiles", "truth", "prediction")}
                      for r in report["records"]]
    assert actual_records == expected["records"]
    # Poor accuracy must remain visible, not be xfailed, discarded or made 100%.
    assert any(r["iou"] == 0 and r["outcome"] == "observed_mismatch" for r in report["records"])
    assert any(r["fp"] > 0 and r["fn"] > 0 for r in report["records"])


def test_new_shape_families_are_not_old_masks_or_each_other():
    old_masks = [survey.generate_test_scenario(32, 32, name, random.Random(0))[1]
                 for name in survey.SCENARIOS]
    for trial in range(3):
        new = []
        for shape in holdout.HELDOUT_SHAPES:
            _, truth = holdout.generate_case(20261020, shape, "reference", trial)
            assert truth not in old_masks and truth not in new
            new.append(truth)
        assert [len(mask) for mask in new] == [232, 595, 149]
    # Specific geometric controls: reentrant bay, nine holes, and border turns.
    _, comb = holdout.generate_case(20261020, "concave_comb", "reference", 0)
    assert 7 * 32 + 6 in comb and 7 * 32 + 7 not in comb
    _, slab = holdout.generate_case(20261020, "perforated_slab", "reference", 0)
    for x in (8, 16, 24):
        for y in (8, 16, 24):
            assert y * 32 + x not in slab and y * 32 + x - 1 in slab
    _, path = holdout.generate_case(20261020, "border_serpentine", "reference", 0)
    assert {0, 31, 8 * 32, 8 * 32 + 31, 16 * 32, 24 * 32 + 31} <= path


def test_control_signal_exactly_matches_original_distribution():
    seed = holdout._case_seed(20261020, "dense_reference", "reference", 0)
    expected = survey.generate_test_scenario(32, 32, "Dense_Object", random.Random(seed))
    assert holdout.generate_case(20261020, "dense_reference", "reference", 0) == expected


def test_signal_families_have_intended_distinct_support():
    low, truth = holdout.generate_case(20261020, "dense_reference", "quantized_low_contrast", 0)
    assert {abs(v - 50) for idx in truth for vector in low[idx] for v in vector} == {1, 2, 3, 4, 6, 8}
    phase, _ = holdout.generate_case(20261020, "dense_reference", "phase_mixture", 0)
    assert any(phase[idx][0][0] < phase[idx][0][1] for idx in truth)
    impulsive, _ = holdout.generate_case(20261020, "dense_reference", "impulsive_tail", 0)
    for cells in (truth, set(range(1024)) - truth):
        assert {0, 255} <= {v for idx in cells for vector in impulsive[idx] for v in vector}
    walks, _ = holdout.generate_case(20261020, "dense_reference", "correlated_walk", 0)
    differences = {b - a for idx in truth for vector in walks[idx] for a, b in zip(vector, vector[1:])}
    assert differences == {-12, -6, 6, 12}


def test_fixture_and_outcome_oracles_for_every_case(report):
    truths = {}
    for row in report["records"]:
        profiles, truth, prediction = row["profiles"], set(row["truth"]), set(row["prediction"])
        assert len(profiles) == 1024
        assert len(prediction) == len(row["prediction"])
        assert truth <= set(range(1024)) and prediction <= set(range(1024))
        assert all(len(pair) == 2 and all(len(vector) == 8 and all(type(v) is int and 0 <= v <= 255
                   for v in vector) for vector in pair) for pair in profiles)
        assert row["input_sha256"] == _fingerprint(profiles)
        assert row["truth_sha256"] == _fingerprint(sorted(truth))
        assert row["prediction_sha256"] == _fingerprint(sorted(prediction))
        for key, value in _scalar_metrics(truth, prediction).items():
            assert row[key] == value
        assert row["candidate_count"] + row["skipped"] == 1024
        assert (row["outcome"] == "exact") == (prediction == truth)
        # Signal/seed changes never move the labels in a shape panel.
        key = (row["shape"], row["trial"])
        assert truths.setdefault(key, truth) == truth
        if not prediction:
            assert row["precision"] is None and row["com_error_patch"] is None


def test_seed_and_order_independence():
    cases = [(20261020, "concave_comb", "phase_mixture", 0),
             (20261021, "perforated_slab", "impulsive_tail", 2)]
    forward = {case: holdout.generate_case(*case) for case in cases}
    reverse = {case: holdout.generate_case(*case) for case in reversed(cases)}
    assert forward == reverse
    changed = holdout.generate_case(20261021, "concave_comb", "phase_mixture", 0)
    assert forward[cases[0]][0] != changed[0]
    assert forward[cases[0]][1] == changed[1]


def test_h8_integer_loss_and_isolated_legitimate_support_remain_counterexamples():
    assert survey.fwht8_add_only([1, 0, 0, 0, 0, 0, 0, 0]) == [0] * 8
    config = holdout.FROZEN_CONFIG
    profiles = [([50] * 8, [50] * 8) for _ in range(64)]
    profiles[27] = ([130, 25] * 4, [120, 120, 30, 30] * 2)
    result = survey.ThreeWaySurveyEngine(survey.encode_profiles(profiles, config), 8, 8).execute_survey(config)
    assert result["normal_set"] == set()
    # The identical measurement cannot decide whether an isolated patch is truth or noise.
    assert survey.metrics({27}, result["normal_set"], 8, 8)["fn"] == 1
    assert survey.metrics(set(), result["normal_set"], 8, 8)["fp"] == 0


@pytest.mark.parametrize("kwargs", [{"trials": 0}, {"trials": 21}, {"trials": True},
                                    {"seeds": ()}, {"seeds": (1, 1)}, {"seeds": (True,)}])
def test_evaluator_rejects_invalid_requests(kwargs):
    with pytest.raises(ValueError):
        holdout.evaluate(**kwargs)


def test_invalid_fixtures_and_engine_errors_fail_instead_of_becoming_accuracy_results(monkeypatch):
    with pytest.raises(ValueError, match="unknown shape"):
        holdout.generate_case(1, "not_a_shape", "reference", 0)
    with pytest.raises(ValueError, match="unknown signal"):
        holdout.generate_case(1, "dense_reference", "not_a_signal", 0)
    original = holdout.generate_case
    def invalid_fixture(*args):
        profiles, truth = original(*args)
        profiles[0][0][0] = 300
        return profiles, truth
    monkeypatch.setattr(holdout, "generate_case", invalid_fixture)
    with pytest.raises(ValueError, match="invalid holdout integer profile"):
        holdout.evaluate(trials=1)
    monkeypatch.setattr(holdout, "generate_case", original)
    def broken_engine(*args, **kwargs):
        raise RuntimeError("engine error must propagate")
    monkeypatch.setattr(survey.ThreeWaySurveyEngine, "execute_survey", broken_engine)
    with pytest.raises(RuntimeError, match="must propagate"):
        holdout.evaluate(trials=1)


def test_stdlib_cli_preserves_full_replayable_inputs_and_rejects_invalid_trial_count(tmp_path):
    command = [sys.executable, "-S", str(Path(holdout.__file__).resolve()), "--trials", "1", "--output", str(tmp_path)]
    run = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    raw_bytes = gzip.decompress((tmp_path / "results.json.gz").read_bytes())
    raw, summary = json.loads(raw_bytes), json.loads((tmp_path / "summary.json").read_text())
    assert hashlib.sha256(raw_bytes).hexdigest() == summary["raw_results_sha256"]
    assert _fingerprint(raw["records"]) == raw["records_sha256"]
    assert len(raw["records"]) == 40
    # Replay the persisted inputs, rather than regenerating from a seed.
    config = survey.Config(**raw["config"])
    for row in raw["records"]:
        result = survey.ThreeWaySurveyEngine(survey.encode_profiles(row["profiles"], config),
                                             raw["width"], raw["height"]).execute_survey(config)
        assert sorted(result["normal_set"]) == row["prediction"]
    assert (tmp_path / "report.md").read_text() == run.stdout
    assert "observed_mismatch" in raw_bytes.decode()
    invalid = subprocess.run(command + ["--trials", "0"], capture_output=True, text=True)
    assert invalid.returncode != 0 and "trials must be 1..20" in invalid.stderr


def test_import_does_not_execute_experiment(tmp_path):
    code = f"import sys; sys.path.insert(0, {str(ROOT)!r}); from scripts import survey_holdout"
    run = subprocess.run([sys.executable, "-S", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "" and list(tmp_path.iterdir()) == []
