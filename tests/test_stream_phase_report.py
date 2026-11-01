import io
import itertools
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
