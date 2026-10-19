"""Cross-protocol regressions; independent counts and frozen examples, no CPU thresholds."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

import image_compare as compare
import studio_candidate_selection as selection
from scripts import quality_selection_experiment as study

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'docs/evidence/studio-quality'


def image(values):
    return len(values),1,bytes(c for v in values for c in (v,v,v,255))


def test_legacy_policy_reuses_saved_original_choices_and_keeps_default_schema():
    folder = ROOT/'docs/evidence/studio-delivery/tradeoff-original'
    saved = json.loads((folder/'report.json').read_text())
    fresh,_ = compare.analyze(*(study.load_image(folder/(k+'.png'))
                               for k in ('reference','nearest','smooth')))
    assert fresh['roles'] == saved['roles']
    assert fresh['pareto_indices'] == saved['pareto_indices']
    for actual,expected in zip(fresh['candidates'],saved['candidates']):
        for key,value in actual.items():
            assert value == expected[key]
    assert 'quality' not in fresh


def test_rgb_error_objectives_keep_legacy_choices_including_ties():
    report,images = compare.analyze(image([0,0]),image([0,10]),image([6,6]))
    selection.enrich_sweep(report,images,image([0,0]))
    rows = report['quality']['candidates']
    for metric,role in [('rgb_mae','mae_priority'),('rgb_rmse','rmse_priority'),('balance_score','balanced')]:
        assert selection.select_quality(rows,metric)['selected_index'] == report['roles'][role]
    # MAE equal, RMSE different: preserve the established secondary error policy.
    tied = [dict(rows[0],index=0,rgb_mae=5,rgb_rmse=8,balance_score=90),
            dict(rows[0],index=1,rgb_mae=5,rgb_rmse=6,balance_score=90)]
    assert selection.select_quality(tied,'rgb_mae')['selected_index'] == 1
    assert selection.select_quality(tied,'balance_score')['selected_index'] == 1
    assert selection.select_quality(tied,'iou')['tied_indices'] == [0,1]


def test_opaque_mae_rgba_redundancy_and_hidden_rgb_are_distinct():
    a,b = image([0,12,255]),image([255,30,245])
    row = selection.diagnostic_row(a,b,0)
    errors = [255,18,10]
    assert row['rgb_mae'] == sum(errors)/3
    assert row['rgb_rmse'] == math.sqrt(sum(x*x for x in errors)/3)
    assert row['rgba_similarity'] == pytest.approx(1-3*row['rgb_mae']/1020)
    assert row['alpha_iou'] == 1
    hidden_a = (1,1,bytes([255,0,0,0]))
    hidden_b = (1,1,bytes([0,255,0,0]))
    hidden = selection.diagnostic_row(hidden_a,hidden_b,0)
    assert hidden['rgb_mae'] == 0 and hidden['rgba_similarity'] < 1


def test_same_dimensions_are_insufficient_for_pooling_and_duplicates_rejected():
    row = selection.diagnostic_row(image([0]),image([1]),0)
    other = selection.diagnostic_row(image([2]),image([1]),1)
    for fn in (selection.summarize,selection.rank_relations,selection.pareto_indices,selection.select_quality):
        with pytest.raises(ValueError,match='same reference'):
            fn([row,other])
        with pytest.raises(ValueError,match='unique'):
            fn([row,row])


def test_undefined_axes_constraints_and_strict_pareto_no_fallback():
    rows = [selection.diagnostic_row(image([255]),image([255]),i) for i in (0,1)]
    assert selection.select_quality(rows,'energy_dice')['selected_index'] is None
    assert selection.pareto_indices(rows)['undefined_indices'] == [0,1]
    assert selection.pareto_indices(rows,('rgb_mae','rgb_rmse'))['indices'] == [0,1]
    assert selection.select_quality(rows,max_source_clipped_nonfill=0)['selected_index'] is None
    rows[1]['source_clipped_nonfill'] = 0
    assert selection.select_quality(rows,max_source_clipped_nonfill=0)['selected_index'] == 1
    for bad in (-1,0.5,True):
        with pytest.raises(ValueError):
            selection.select_quality(rows,max_missing_foreground=bad)
    worse = dict(rows[0],index=2,rgb_mae=1,rgb_rmse=2)
    assert selection.pareto_indices([rows[0],worse],('rgb_mae','rgb_rmse'))['indices'] == [0]
    invalid = dict(rows[0],rgb_mae=float('nan'))
    with pytest.raises(ValueError,match='finite'):
        selection.select_quality([invalid],'rgb_mae')


def test_registration_perfect_score_does_not_clear_raw_missing_constraint():
    white,black = (255,255,255,255),(0,0,0,255)
    ref = [white]*64; ref[27] = black
    candidate = [white]*64; candidate[28] = black
    as_image = lambda p:(8,8,bytes(c for pixel in p for c in pixel))
    row = selection.diagnostic_row(as_image(ref),as_image(candidate),0)
    assert row['iou'] == 0 and row['aligned_iou'] == 1
    assert row['missing_foreground'] == 1
    assert selection.select_quality([row],'aligned_iou',max_missing_foreground=0)['selected_index'] is None


@pytest.fixture(scope='module')
def joined():
    return study.recorded_groups(EVIDENCE)


def test_all_110_cases_joined_on_exact_reference_and_reversals_reproduced(joined):
    rows = [r for g in joined for r in g['candidates']]
    assert len(rows) == 110
    assert all(r['alpha_iou'] == 1 for r in rows)
    assert sum(g['rank_relations']['iou']['pairs'] for g in joined) == 396
    for metric,count in [('rgba_similarity',37),('energy_dice',32),('near_field',7),('aligned_iou',10),('dice',0)]:
        assert sum(g['rank_relations'][metric]['reversed'] for g in joined) == count
    assert sum(g['mae_relations']['rgba_similarity']['reversed'] for g in joined) == 0
    for group in joined:
        assert len({r['reference_key'] for r in group['candidates']}) == 1
        selected = group['selection']['legacy']['roles'].values()
        assert all(group['candidates'][i]['kind'] != 'identity' for i in selected)
    shapes = next(g for g in joined if g['scenario']=='shapes' and '128x128:' in g['reference_key'] and len(g['candidates'])>1)
    by_kind = {r['kind']:r for r in shapes['candidates']}
    blur,dilate = by_kind['blur'],by_kind['contour_dilate']
    assert blur['iou'] > dilate['iou'] and blur['rgba_similarity'] < dilate['rgba_similarity']
    assert blur['rgb_mae'] > dilate['rgb_mae']


def test_saved_alignment_loss_and_crop_unknown_provenance_remain_visible(joined):
    rows = [r for g in joined for r in g['candidates']]
    row = next(r for r in rows if r['id']=='studio-demo-None-128-shift_1px')
    assert row['aligned_iou'] == 1
    assert row['source_clipped_nonfill'] == 72
    assert row['source_inverse_exact'] is False
    # Registration has its own different provenance; it cannot certify the forward transform.
    assert isinstance(row['registration_clipped_nonfill'],int)
    crop = next(r for r in rows if r['kind']=='enlarge_crop')
    assert crop['source_clipped_nonfill'] is None and crop['crop_discarded_canvas_pixels'] > 0


def test_reused_evidence_rejects_wrong_pixels_and_wrong_scores():
    saved = json.loads((EVIDENCE/'results.json').read_text())['cases'][0]
    ref,candidate = (study.load_image(EVIDENCE/saved[k]) for k in ('reference_png','candidate_png'))
    wrong = copy.deepcopy(saved);wrong['foreground']['IoU'] = -1
    with pytest.raises(ValueError,match='disagree'):
        selection.diagnostic_row(ref,candidate,0,recorded=wrong)


def test_quality_cli_selected_png_constraints_and_no_output_on_bad_policy(tmp_path):
    paths=[]
    for name,values in [('reference',[0,0]),('nearest',[0,10]),('smooth',[6,6])]:
        p=tmp_path/(name+'.png');p.write_bytes(compare.png(image(values)));paths.append(p)
    out=tmp_path/'variants'
    cmd=[sys.executable,'-S',str(ROOT/'image_compare.py'),'--reference',str(paths[0]),
         '--nearest',str(paths[1]),'--smooth',str(paths[2]),'--out',str(out),
         '--quality','--select-by','near_field','--max-missing-foreground','0']
    run=subprocess.run(cmd,capture_output=True,text=True)
    assert run.returncode == 0,run.stderr
    report=json.loads((out/'report.json').read_text())
    chosen=report['quality']['selection']['selected_index']
    assert (out/'quality_selected.png').read_bytes() == (out/f'variant-{chosen:02d}.png').read_bytes()
    assert report['quality']['selection']['objective'] == 'near_field'
    bad=tmp_path/'invalid'
    cmd[cmd.index(str(out))]=str(bad)
    cmd.remove('--quality')
    assert subprocess.run(cmd,capture_output=True).returncode == 2
    assert not bad.exists()


def test_quality_cost_guard_does_not_change_legacy_sweep():
    ref=(1024,1024,bytes(1024*1024*4))
    with pytest.raises(ValueError,match='1MP'):
        selection.enrich_sweep({'background_rgb':[255,255,255]},[ref,ref],ref)


def test_frozen_sweep_evidence_reproduces_candidates_scores_and_choices():
    recorded = json.loads((ROOT/'docs/evidence/studio-quality-selection/results.json').read_text())
    fresh = study.resampling_sweeps(EVIDENCE)
    assert len(fresh) == 4
    for actual,expected in zip(fresh,recorded['sweeps']):
        assert actual['name'] == expected['name']
        assert actual['pixel_sha256'] == expected['pixel_sha256']
        assert actual['roles'] == expected['roles']
        assert actual['pareto_indices'] == expected['pareto_indices']
        assert actual['quality']['summary'] == expected['quality']['summary']
        for a,b in zip(actual['quality']['candidates'],expected['quality']['candidates']):
            assert {k:v for k,v in a.items() if k != 'diagnostic_cpu_ms'} == {k:v for k,v in b.items() if k != 'diagnostic_cpu_ms'}
    # Frozen nontrivial selection differences: these are reference-specific, not preferences.
    selected=fresh[0]['quality']['summary']['by_metric']
    assert [selected[m]['selected_index'] for m in ('rgb_mae','rgb_rmse','balance_score','iou','energy_dice','near_field')] == [0,9,8,3,3,3]
    shapes=next(s for s in fresh if s['name']=='synthetic-reduction-shapes')
    assert shapes['roles']['balanced'] == 10
    assert shapes['quality']['summary']['by_metric']['energy_dice']['selected_index'] == 2
    for s in fresh:
        assert all(r['diagnostic_cpu_ms'] >= 0 for r in s['quality']['candidates'])
