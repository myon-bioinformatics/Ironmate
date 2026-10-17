"""Independent scalar error, alpha, Pareto and CLI regression checks."""
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

import image_compare as c


def image(values):
    return len(values), 1, bytes(v for x in values for v in (x,x,x,255))


def test_metrics_and_weighted_choices_match_scalar_errors():
    ref, a, b = image([0,0]), image([0,10]), image([6,6])
    report, variants = c.analyze(ref,a,b)
    for row, variant in zip(report['candidates'],variants):
        errors=[variant[2][0],variant[2][4]]
        assert row['rgb_mae']==sum(errors)/2
        assert row['rgb_rmse']==math.sqrt(sum(x*x for x in errors)/2)
        assert row['balance_score']==pytest.approx(100*(1-(row['rgb_mae']+row['rgb_rmse'])/510))
    assert c.analyze(ref,a,b,mae_weight=1)[0]['roles']['balanced']==report['roles']['mae_priority']
    assert c.analyze(ref,a,b,mae_weight=0)[0]['roles']['balanced']==report['roles']['rmse_priority']
    for i in report['pareto_indices']:
        r=report['candidates'][i]
        assert not any(s['rgb_mae']<=r['rgb_mae'] and s['rgb_rmse']<=r['rgb_rmse'] and
                       (s['rgb_mae']<r['rgb_mae'] or s['rgb_rmse']<r['rgb_rmse']) for s in report['candidates'])
    assert report['roles']['midpoint']==5


def test_alpha_blend_does_not_leak_hidden_rgb_and_exact_match_remains_separate():
    transparent=(1,1,bytes([255,0,0,0]))
    blue=(1,1,bytes([0,0,255,255]))
    assert c.blend(transparent,blue,5)[2]==bytes([0,0,255,128])
    other_hidden=(1,1,bytes([0,255,0,0]))
    m=c.metrics(transparent,other_hidden)
    assert m['rgb_mae']==m['rgb_rmse']==0 and m['exact_rgba_pixels']==0
    assert c.read_png(c.png(blue))==blue


@pytest.mark.parametrize('kwargs',[{'steps':3},{'steps':0},{'mae_weight':float('nan')},{'mae_weight':-1}])
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises(ValueError): c.analyze(image([0]),image([1]),image([2]),**kwargs)


def test_dimensions_and_output_collision_fail_without_mutating_sources(tmp_path):
    with pytest.raises(ValueError): c.metrics(image([0]),image([0,1]))
    paths=[]
    for name,values in [('reference',[0,0]),('nearest',[0,10]),('smooth',[6,6])]:
        path=tmp_path/(name+'.png');path.write_bytes(c.png(image(values)));paths.append(path)
    before=[p.read_bytes() for p in paths]
    out=tmp_path/'variants'
    cmd=[sys.executable,'-S',str(Path(c.__file__)), '--reference',str(paths[0]),'--nearest',str(paths[1]),'--smooth',str(paths[2]),'--out',str(out)]
    run=subprocess.run(cmd,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    report=json.loads((out/'report.json').read_text())
    assert len(report['candidates'])==11 and len(report['input_sha256'])==3
    assert len(list(out.glob('variant-*.png')))==11
    for role,index in report['roles'].items():
        assert (out/(role+'.png')).read_bytes()==(out/f'variant-{index:02d}.png').read_bytes()
    assert subprocess.run(cmd,capture_output=True).returncode==2
    assert [p.read_bytes() for p in paths]==before


def test_candidate_pixel_budget_rejects_oversized_sweep():
    large=(512,512,bytes(512*512*4))
    with pytest.raises(ValueError,match='16MP'):
        c.analyze(large,large,large,steps=100)
