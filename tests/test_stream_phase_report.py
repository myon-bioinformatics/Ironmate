import io
import itertools
import json
from pathlib import Path
import pytest
from scripts import stream_phase_report as s


def test_pixels_borrowed_and_projection():
    buf = bytearray(range(64))
    p = next(s.image_patches(buf, 8, 8))
    assert p.dc_level == s.CalibratedTernaryPatch([sum(buf[y*8:y*8+8])//8 for y in range(8)], [sum(buf[x::8])//8 for x in range(8)]).dc_level
    buf[:] = bytes([100])*64
    assert next(s.image_patches(buf, 8, 8)).dc_level != p.dc_level
    rgb = bytes([255, 0, 0])*64
    assert next(s.image_patches(rgb, 8, 8, 3)).dc_level == next(s.image_patches(bytes([63])*64, 8, 8)).dc_level
    for w, h, c, data in [(7,8,1,buf), (8,8,4,buf), (8,8,1,b'')]:
        with pytest.raises(ValueError):
            list(s.image_patches(data,w,h,c))


def test_pgm_binary_separator():
    for first in (10,32,35,0):
        original = bytearray(b'P5\n# comment\n8 8\n255\n' + bytes([first])*64)
        mv,w,h = s.pgm_view(original)
        assert (w,h,len(mv),mv[0]) == (8,8,64,first)
        original[-1] = 9
        assert mv[-1] == 9
    with pytest.raises(ValueError):
        s.pgm_view(b'P5 8 8 65535\n')


def test_csv_exact_and_neutral():
    assert s.fixed100('-0.25') == -25
    assert s.fixed100('3.45') == 345
    for bad in ('NaN','1e2','1.234','','.5'):
        with pytest.raises(ValueError): s.fixed100(bad)
    rows = list(s.csv_spins(io.StringIO('id,x,c\na,-1,2\nb,0,2\nc,1,2\n'),'id',['x','c']))
    assert [(r['pos_mask'],r['neg_mask']) for r in rows] == [(0,1),(0,0),(1,0)]
    for text in ('id,x\na,\n','id,x\na\n','id,x,x\na,1,2\n'):
        with pytest.raises(ValueError): list(s.csv_spins(io.StringIO(text),'id',['x']))


def test_bfs_matches_exhaustive_overlapping_or_and_winner():
    def choose(b):
        if b & 8: return 'rival'
        return 'target' if b & 3 and b & 6 else 'source'
    for board in range(16):
        result = s.shortest_ladder(board,'target',choose,4,max_distance=4)
        exact = min((board^b).bit_count() for b in range(16) if choose(b)=='target')
        assert result['distance'] == exact
        assert choose(result['path'][-1]) == 'target'
    assert s.shortest_ladder(0,'target',choose,4,max_states=1)['status'] == 'resource_limit'
    assert s.shortest_ladder(0,'target',choose,4,max_distance=0)['status'] == 'not_found_within_bound'
    assert s.shortest_ladder(0,'target',choose,4)['distance'] == 1


def test_render_escapes():
    text = s.render_ladder([0,1],lambda b: 'x"\n``` <tag>',{0:'a"|\n```'})
    assert '&quot;' in text and '&lt;tag&gt;' in text
    assert text.count('```') == 4
    with pytest.raises(ValueError): s.render_ladder([0,3],str,{})


def test_csv_ladder_multiple_rows_reuses_setup(tmp_path, monkeypatch, capsys):
    csv_path = tmp_path / 'rows.csv'
    csv_path.write_text('id,x\na,-1\nb,0\nc,1\n', encoding='utf-8')
    spec_path = tmp_path / 'ladder.json'
    spec_path.write_text(json.dumps({'target': 'high', 'classes': [
        {'name': 'high', 'must_and': 1, 'forbid_not': 2, 'or_masks': [1]},
        {'name': 'low', 'must_and': 2}, {'name': 'neutral'}]}), encoding='utf-8')
    read_text, loads = Path.read_text, s.json.loads
    reads, parses, callbacks, mappings = [], [], [], []
    def read(path, *args, **kwargs):
        reads.append(path)
        return read_text(path, *args, **kwargs)
    def load(text, *args, **kwargs):
        parses.append(text)
        return loads(text, *args, **kwargs)
    shortest, render = s.shortest_ladder, s.render_ladder
    def search(board, target, choose, bits, **kwargs):
        callbacks.append((choose, kwargs['valid']))
        assert not kwargs['valid'](3)
        return shortest(board, target, choose, bits, **kwargs)
    def draw(path, choose, names):
        mappings.append(names)
        return render(path, choose, names)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(s.json, 'loads', load)
    monkeypatch.setattr(s, 'shortest_ladder', search)
    monkeypatch.setattr(s, 'render_ladder', draw)
    s.main(['--csv', str(csv_path), '--id-col', 'id', '--columns', 'x',
            '--ladder-spec', str(spec_path)])
    assert reads == [spec_path]
    assert len(parses) == 1
    assert len(callbacks) == len(mappings) == 3
    assert all(c[0] is callbacks[0][0] and c[1] is callbacks[0][1] for c in callbacks)
    assert all(m is mappings[0] for m in mappings)
    expected = []
    for ident, pos, neg, board, path in [('a', 0, 1, 2, [2, 0, 1]),
                                        ('b', 0, 0, 0, [0, 1]),
                                        ('c', 1, 0, 1, [1])]:
        expected.append(json.dumps(dict(id=ident, pos_mask=pos, neg_mask=neg,
                                        spin_board=board, obs_mask=3)) + '\n')
        expected.append(json.dumps(dict(status='found', path=path, distance=len(path)-1)) + '\n')
        expected.append(render(path, lambda b: {0: 'neutral', 1: 'high', 2: 'low'}[b],
                               {0: 'x_High', 1: 'x_Low'}) + '\n')
    assert capsys.readouterr().out == ''.join(expected)


@pytest.mark.parametrize('rows', ['id,x\n', 'id,x\na,0\nb,1\n'])
def test_csv_invalid_ladder_json_fails_before_output(tmp_path, capsys, rows):
    csv_path, spec_path = tmp_path / 'rows.csv', tmp_path / 'bad.json'
    csv_path.write_text(rows, encoding='utf-8')
    spec_path.write_text('{bad', encoding='utf-8')
    with pytest.raises(SystemExit) as exc:
        s.main(['--csv', str(csv_path), '--columns', 'x', '--ladder-spec', str(spec_path)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'error:' in captured.err and 'property name' in captured.err


@pytest.mark.parametrize('missing', ['', 'NULL'])
def test_csv_missing_candidates_stay_unknown_and_ladder_rejected(tmp_path, capsys, missing):
    csv_path, spec_path = tmp_path / 'rows.csv', tmp_path / 'classes.json'
    csv_path.write_text(f'id,x\na,0\nb,{missing}\nc,0\n', encoding='utf-8')
    spec_path.write_text(json.dumps({'target': 'on', 'classes': [
        {'name': 'on', 'must_and': 1}, {'name': 'off', 'forbid_not': 1}]}), encoding='utf-8')
    args = ['--csv', str(csv_path), '--id-col', 'id', '--columns', 'x',
            '--allow-missing', '--observable-spec', str(spec_path)]
    s.main(args)
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r['obs_mask'] for r in records[::2]] == [3, 0, 3]
    assert records[1]['candidates'] == records[5]['candidates'] == [{'name': 'off', 'truth': 'true'}]
    assert records[3]['candidates'] == [{'name': 'on', 'truth': 'unknown'},
                                        {'name': 'off', 'truth': 'unknown'}]
    with pytest.raises(SystemExit) as exc:
        s.main(args + ['--ladder-spec', str(spec_path)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert 'ladder requires complete observations' in captured.err
    # The complete first row is still processed before rejecting the missing row.
    assert '"status": "found"' in captured.out
