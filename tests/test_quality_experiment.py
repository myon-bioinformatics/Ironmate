# test_quality_experiment.py
# __all__: 0
__all__ = []

import hashlib, json, random
from pathlib import Path

import pytest

from scripts import quality_experiment as q
from studio_alignment import invert_translation
from studio_shape_metrics import metrics

ROOT = Path(__file__).resolve().parents[1]


def test_iou_dice_monotonic_equivalence_independent_counts():
    rng=random.Random(20261018)
    scores=[]
    for _ in range(100):
        a={i for i in range(64) if rng.random()<.3}; b={i for i in range(64) if rng.random()<.3}
        tp=sum(i in a and i in b for i in range(64)); fp=sum(i not in a and i in b for i in range(64)); fn=sum(i in a and i not in b for i in range(64))
        m=metrics(8,8,a,b)
        expected=tp/(tp+fp+fn) if tp+fp+fn else 1
        assert m['IoU']==expected
        assert m['Dice']==pytest.approx(2*expected/(1+expected))
        scores.append(m)
    assert sorted(range(100),key=lambda i:scores[i]['IoU'])==sorted(range(100),key=lambda i:scores[i]['Dice'])


def test_tolerance_can_reverse_area_ranking():
    # One long thin line displaced by one pixel versus sparse exact hits.
    a={y*16+4 for y in range(2,14)}
    near={i+1 for i in a}; partial=set(sorted(a)[::3])
    n=metrics(16,16,a,near); p=metrics(16,16,a,partial)
    assert n['IoU']<p['IoU']
    # Mean of exact directed hit 1 and recall 1/3 = 2/3; use a far false positive
    # population to reduce partial tolerance while retaining positive IoU.
    partial |= {y*16+14 for y in range(2,14)}
    p=metrics(16,16,a,partial)
    assert n['IoU']<p['IoU'] and n['Symmetric_Near_Field']>p['Symmetric_Near_Field']


def test_alpha_masks_cannot_judge_color_and_alignment_is_not_position_improvement():
    white=(255,255,255,255); ref=[white]*64;ref[27]=(20,30,40,255)
    _,colored,_=q.perturb(8,8,ref,'color_change')
    result=q.evaluate(8,8,ref,colored,repeats=1)
    assert result['alpha']['IoU']==result['alpha']['Aligned_IoU']==1
    assert result['rgba_similarity']<1
    _,moved,recipe=q.perturb(8,8,ref,'shift_1px')
    result=q.evaluate(8,8,ref,moved,repeats=1)
    assert result['foreground']['IoU']==0
    assert result['foreground']['Aligned_IoU']==1
    assert (result['foreground']['Alignment_dx'],result['foreground']['Alignment_dy'])==(-1,0)
    assert recipe['inverse_exact']


def test_clipped_pixels_cannot_be_recovered():
    pixels=[(255,255,255,255)]*64;pixels[7]=(1,2,3,255)
    _,out,r=q.perturb(8,8,pixels,'edge_clip')
    assert r['clipped_nonfill']==1 and not r['inverse_exact']
    assert invert_translation(8,8,out,r['dx'],0,fill=(255,255,255,255))['pixels']!=pixels


def test_undefined_energy_remains_null_and_identity_has_no_nan():
    ref=[(255,255,255,255)]*64
    value=q.evaluate(8,8,ref,ref,repeats=1)
    assert value['foreground']['Energy_Dice'] is None
    assert 'null' in json.dumps(value,allow_nan=False)
    assert value['foreground']['IoU']==value['rgba_similarity']==1


def test_seeded_perturbations_png_roundtrip_and_source_preserved():
    pixels=[(x*13,y*17,80,255) for y in range(8) for x in range(8)]
    original=list(pixels)
    for kind in ['identity','shift_1px','shrink_expand','enlarge_crop','mosaic','blur','thin_line_loss','contour_dilate','color_change','edge_clip']:
        a,b,r=q.perturb(8,8,pixels,kind)
        assert (a,b,r)==q.perturb(8,8,pixels,kind)
        assert pixels==original and len(a)==len(b)==64
        w,h,rows=q.decode_png(q._png(8,8,b))
        assert (w,h)==(8,8) and b==[tuple(row[i:i+4]) for row in rows for i in range(0,len(row),4)]
    _,_,recipe=q.perturb(8,8,pixels,'thin_line_loss')
    assert recipe['reference_variant']!='original'


def test_checked_in_evidence_recomputes_scores_without_timing_assertions():
    folder=ROOT/'docs/evidence/studio-quality'
    report=json.loads((folder/'results.json').read_text())
    assert len(report['cases'])==110
    for c in report['cases']:
        def read(name):
            w,h,rows=q.decode_png((folder/c[name]).read_bytes())
            assert (w,h)==(c['width'],c['height'])
            return [tuple(row[i:i+4]) for row in rows for i in range(0,len(row),4)]
        a,b=read('reference_png'),read('candidate_png')
        assert hashlib.sha256(bytes(x for p in a for x in p)).hexdigest()==c['reference_sha256']
        assert hashlib.sha256(bytes(x for p in b for x in p)).hexdigest()==c['candidate_sha256']
        fixture=next(f for f in json.loads((folder/'fixtures.json').read_text())['fixtures'] if f['name']==c['scenario'] and f['seed']==c['seed'])
        source=(folder/fixture['file']).read_bytes()
        assert hashlib.sha256(source).hexdigest()==c['source_sha256']
        sw,sh,srows=q.decode_png(source)
        original=[tuple(row[i:i+4]) for row in srows for i in range(0,len(row),4)]
        scaled=q._resize(original,sw,sh,c['width'],c['height'])
        ra,rb,recipe=q.perturb(c['width'],c['height'],scaled,c['recipe']['kind'],c['seed'])
        assert (ra,rb,recipe)==(a,b,c['recipe'])
        m=metrics(c['width'],c['height'],q._mask(a),q._mask(b),q._energy(a,c['width'],c['height']))
        for k,v in m.items(): assert c['foreground'][k]==v
        expected=1-sum(abs(x-y) for p,r in zip(a,b) for x,y in zip(p,r))/(len(a)*1020)
        assert c['rgba_similarity']==expected
        assert c['png_bytes']==(folder/c['candidate_png']).stat().st_size
        for group in c['cost'].values():
            assert len(group['cpu_ms_samples'])==3 and group['cpu_ms_median']>=0
            assert group['python_peak_allocated_bytes']>=0
        if c['recipe']['kind']=='identity':
            assert c['foreground']['IoU']==c['foreground']['Aligned_IoU']==c['rgba_similarity']==1
            assert c['foreground']['Alignment_L1_Pixels']==0
    # Recompute expensive registration on a representative saved case only.
    c=next(c for c in report['cases'] if c['scenario']=='shapes' and c['recipe']['kind']=='shift_1px')
    a,b=read('reference_png'),read('candidate_png')
    fresh=q.evaluate(c['width'],c['height'],a,b,repeats=1)
    assert fresh['foreground']==c['foreground'] and fresh['alpha']==c['alpha']
