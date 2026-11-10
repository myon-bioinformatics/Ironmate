import io, itertools
import pytest
from scripts.observable_choice import ObservableChoice, Prototype
from scripts.stream_phase_report import csv_spins


def test_exhaustive_index_matches_linear_kleene():
    specs = [Prototype('on',1,2,(12,)), Prototype('off',2,1), Prototype('wild'), Prototype('or',0,0,(3,))]
    for budget in (1,3,31):
        e = ObservableChoice(specs,4,node_budget=budget,leaf_size=1)
        assert e.nodes <= budget
        for active in range(16):
            for obs in range(16):
                result = e.query(active,obs)
                expected = [p.name for p in specs if e.evaluate(p,active,obs) != 'false']
                assert [c['name'] for c in result['candidates']] == expected
                probe = result['next_probe']
                if probe:
                    for value, key in ((0,'zero_survivors'),(1,'one_survivors')):
                        bit=1<<probe['bit']
                        actual=e.query((active & obs & ~bit)|(bit if value else 0),obs|bit)
                        assert len(actual['candidates']) == probe[key]


def test_unknown_not_false_and_no_false_xor_guarantee():
    e=ObservableChoice([Prototype('required',1),Prototype('dontcare')],1)
    r=e.query(0,0)
    assert r['status']=='ambiguous' and r['next_probe'] is None
    assert r['candidates'][0]['truth']=='unknown'
    assert e.query(0,1)['candidates']==[{'name':'dontcare','truth':'true'}]
    assert ObservableChoice([Prototype('on',1),Prototype('off',0,1)],1).query(0,0)['next_probe']['one_survivors']==1


def test_256_exact_classes_and_all_hidden():
    e=ObservableChoice([Prototype(str(i),i,255^i) for i in range(256)],8,leaf_size=1)
    for i in range(256):
        r=e.query(i,255)
        assert r['candidates']==[{'name':str(i),'truth':'true'}]
        assert r['bit_tests']==8
    assert len(e.query(0,0)['candidates'])==256
    assert e.query(0,0)['bit_tests']==255


def test_missing_csv_neutral_observed_and_all_missing():
    rows=list(csv_spins(io.StringIO('id,x,y\na,NULL,0\nb,,0\nc,1,0\n'),'id',['x','y'],True))
    assert [r['obs_mask'] for r in rows]==[12,12,15]
    assert all(r['spin_board']==0 for r in rows)
    assert list(csv_spins(io.StringIO('id,x\na,NULL\n'),'id',['x'],True))[0]['obs_mask']==0
    with pytest.raises(ValueError):
        list(csv_spins(io.StringIO('id,x\na,NULL\n'),'id',['x']))
    with pytest.raises(ValueError): ObservableChoice([Prototype('bad',1,1)],1)
