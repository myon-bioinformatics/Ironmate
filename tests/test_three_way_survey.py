"""Independent numerical oracles and adversarial controls for the survey lab."""
import ast
import itertools
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import littlebit_jev_3way_survey as s


def test_fwht_against_dense_sign_matrix_including_negative_rounding():
    rng = random.Random(17)
    for _ in range(100):
        values = [rng.randint(-255, 255) for _ in range(8)]
        expected = [sum(v * (-1 if (i & j).bit_count() & 1 else 1)
                        for j, v in enumerate(values)) // 2 for i in range(8)]
        assert s.fwht8_add_only(values) == expected
    with pytest.raises(ValueError):
        s.fwht8_add_only([1])


def test_ternary_bit_kernel_against_scalar_distance_exhaustive():
    def masks(values):
        return (sum(1 << i for i, v in enumerate(values) if v == 1),
                sum(1 << i for i, v in enumerate(values) if v == -1))
    vectors = list(itertools.product((-1, 0, 1), repeat=3))
    for a in vectors:
        for b in vectors:
            assert s.fairyfuse_ternary_diff(*masks(a), *masks(b)) == sum(abs(x - y) for x, y in zip(a, b))


def test_integer_kernel_has_no_multiply_or_float_nodes():
    tree = ast.parse(Path(s.__file__).read_text())
    names = {"fwht8_add_only", "rotate_8bit", "fairyfuse_ternary_diff", "LittleBitTernaryPatch",
             "interaction", "row_offsets", "reconstruct_blind", "run_5way_anisotropic_fixed_point",
             "ThreeWaySurveyEngine"}
    for node in tree.body:
        if getattr(node, "name", None) in names:
            assert not any(isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div, ast.Pow))
                           for n in ast.walk(node)), node.name
            assert not any(isinstance(n, ast.Constant) and isinstance(n.value, float)
                           for n in ast.walk(node)), node.name


def test_5way_anisotropic_fixed_point_boundary_checks_and_convergence():
    w, h = 32, 32
    # Node 32 is (x=0, y=1), Node 31 is (x=31, y=0)
    history = {32: {"topo": s.BIT_L}, 31: {"topo": s.BIT_R}}
    active, shifted, steps = s.run_5way_anisotropic_fixed_point(w, h, history, max_iterations=2)
    assert 32 not in active

    cluster_history = {
        0: s.BIT_R | s.BIT_D,
        1: s.BIT_L | s.BIT_D,
        4: s.BIT_R | s.BIT_U,
        5: s.BIT_L | s.BIT_U,
    }
    active, shifted, steps = s.run_5way_anisotropic_fixed_point(4, 4, cluster_history, max_iterations=3)
    assert active == {0, 1, 4, 5}
    assert steps == 1


def test_reconstruction_requires_reciprocal_edge_and_grid_bounds():
    # 0 -> 1, but 1 -> 2 is not a reciprocal edge.
    history = {0: {"topo": 2}, 1: {"topo": 2}}
    assert s.reconstruct_blind(history, 4, 4) == set()
    history[1]["topo"] = 1
    assert s.reconstruct_blind(history, 4, 4) == {0, 1}
    # Flattening outside x=3 must not wrap to x=0 of next row.
    assert s.reconstruct_blind({3: {"topo": 2}, 4: {"topo": 1}}, 4, 4) == set()
    # Stride 4 reciprocal links use the correct direction bit.
    assert s.reconstruct_blind({0: {"topo": 1 << 9}, 4: {"topo": 1 << 8}}, 8, 8) == {0, 4}


def test_way3_roundtrips_serialized_history_without_patch_reference():
    profiles, _ = s.generate_test_scenario(32, 32, "Dense_Object", random.Random(1))
    engine = s.ThreeWaySurveyEngine(s.encode_profiles(profiles, s.Config()), 32, 32)
    result = engine.execute_survey()
    serialized = json.loads(json.dumps(result["history"]))
    history = {int(k): v for k, v in serialized.items()}
    del engine, profiles
    assert s.reconstruct_blind(history, 32, 32) == result["normal_set"]
    assert all(set(info) == {"topo", "links", "delta"} for info in history.values())


def test_shift_is_exact_permutation_including_borders():
    mask = {0, 3, 5, 15}
    shifted = s.shift_mask(mask, 4, 4, 2, 2)
    assert shifted == {10, 9, 15, 5}
    assert len(shifted) == len(mask)
    assert s.shift_mask(shifted, 4, 4, -2, -2) == mask
    assert s.shift_mask(mask, 4, 4, 0, 0) == mask


def test_shift_drop_can_be_zero_or_negative_and_is_not_forced_positive():
    full = set(range(16))
    assert s.shift_mask(full, 4, 4, 2, 2) == full
    truth, wrong = {10}, {0}
    before = s.metrics(truth, wrong, 4, 4)["iou"]
    after = s.metrics(truth, s.shift_mask(wrong, 4, 4, 2, 2), 4, 4)["iou"]
    assert before - after == -1


def test_metrics_counts_subpatch_centroid_and_missing_are_honest():
    m = s.metrics({0, 1}, {1, 2}, 4, 4)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 13)
    assert m["iou"] == pytest.approx(1 / 3)
    assert m["com_error_patch"] == 1
    assert s.centroid({0, 1}, 4) == (0.5, 0)
    assert s.metrics({0}, set(), 4, 4)["com_error_patch"] is None
    assert s.metrics(set(), set(), 4, 4)["iou"] == 1


def test_real_raster_projection_exposes_checkerboard_nullspace():
    flat = [[128 for _ in range(8)] for _ in range(8)]
    checker = [[255 if (x + y) % 2 else 1 for x in range(8)] for y in range(8)]
    a, _, _ = s.project_raster(flat)
    b, _, _ = s.project_raster(checker)
    assert a == b  # Distinct pixels, identical row/column means: cannot restore.
    assert s.encode_profiles(a, s.Config())[0].active_spins == 0
    assert s.encode_profiles(b, s.Config())[0].active_spins == 0
    with pytest.raises(ValueError):
        s.project_raster([[1, 2]])


def test_existing_pixel_grid_roundtrip_keeps_survey_structure():
    from grid_tools import resize
    from pixel_grid import render
    art = render("cloud", "C01", "shadow", 32)
    back = resize(resize(art, 64, backend="stdlib"), 32, backend="stdlib")
    assert art["pixels"] == back["pixels"]
    def structure(artifact):
        rows = [[255 if v else 0 for v in row] for row in artifact["pixels"]]
        profiles, width, height = s.project_raster(rows)
        return s.ThreeWaySurveyEngine(s.encode_profiles(profiles, s.Config()), width, height).execute_survey()["normal_set"]
    assert structure(art) == structure(back)


def test_injection_is_actually_rerun_and_connected_noise_can_pass():
    control = s.injection_control(s.Config())
    assert control["empty_detected"] == control["isolated_injected_detected"] == 0
    assert control["coherent_9_patch_injected_detected"] == 9


def test_real_raster_runner_uses_pixels_and_reports_projection_cost():
    result = s.raster_benchmark(s.Config(), 64, 64)
    assert result["patch_count"] == 64
    assert result["iou"] == 1
    assert result["projection_ms"] > 0
    assert result["decoder_included"] is False


def test_reproducible_test_seed_independent_of_scenario_order():
    first = s.generate_test_scenario(32, 32, "High_Noise_Dark", random.Random(s.scenario_seed(18, "High_Noise_Dark", 0)))
    second = s.generate_test_scenario(32, 32, "High_Noise_Dark", random.Random(s.scenario_seed(18, "High_Noise_Dark", 0)))
    assert first == second
    assert s.scenario_seed(18, "High_Noise_Dark", 0) != s.scenario_seed(19, "High_Noise_Dark", 0)


@pytest.mark.parametrize("args", [(0, 4), (4, 0), (-1, 4)])
def test_engine_rejects_invalid_grid(args):
    with pytest.raises(ValueError):
        s.ThreeWaySurveyEngine([], *args)


def test_import_does_not_run_benchmark(tmp_path):
    code = ("import importlib.util,sys; "
            f"s=importlib.util.spec_from_file_location('survey', {str(Path(s.__file__).resolve())!r}); "
            "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)")
    run = subprocess.run([sys.executable, "-S", "-c", code], cwd=tmp_path, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "" and list(tmp_path.iterdir()) == []


def test_cli_writes_machine_readable_trials_and_visuals_with_stdlib_only(tmp_path):
    run = subprocess.run([sys.executable, "-S", str(Path(s.__file__).resolve()),
                          "--trials", "1", "--train-trials", "1", "--width", "16", "--height", "16",
                          "--output", str(tmp_path)], text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    report = json.loads((tmp_path / "results.json").read_text())
    assert report["test_seeds"] == [20261018, 20261019]
    assert len(report["training_search"]) == 12
    assert len(list(tmp_path.glob("*.svg"))) == 6
    for experiment in report["experiments"].values():
        assert len(experiment["trials"]) == 12
        for row in experiment["trials"]:
            assert row["sensitivity"]["0,0"] == row["iou"]
            assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == 256
    assert (tmp_path / "report.md").read_text() == run.stdout.rstrip() + "\n"
