from zipfile import ZipFile
import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from pptx_layout import arrange

@pytest.fixture
def deck(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i in range(4):
        s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(.1), Inches(.1), Inches(1 + i * .1), Inches(.5))
        s.text = f'Card {i}'
    path = tmp_path / 'source.pptx'
    prs.save(path)
    return path

def rule():
    return dict(pattern='grid', slide=1, shape_ids=[2,3,4,5], columns=2, x=1, y=1, gap_x=.2, gap_y=.3)

def test_geometry_preservation_and_preview(deck, tmp_path):
    out = tmp_path / 'out.pptx'
    before = deck.read_bytes()
    preview = arrange(deck, [rule()], dry_run=True)
    assert preview['changes'] == arrange(deck, [rule()], destination=out)['changes']
    assert deck.read_bytes() == before
    shapes = Presentation(out).slides[0].shapes
    assert [(s.left, s.top) for s in shapes] == [(Inches(1), Inches(1)), (Inches(2.5), Inches(1)), (Inches(1), Inches(1.8)), (Inches(2.5), Inches(1.8))]
    assert [(s.text,s.width,s.height) for s in shapes] == [(s.text,s.width,s.height) for s in Presentation(deck).slides[0].shapes]
    with ZipFile(deck) as a, ZipFile(out) as b:
        assert a.namelist() == b.namelist()
        assert all(a.read(n) == b.read(n) for n in a.namelist() if n != 'ppt/slides/slide1.xml')
    assert arrange(out, [rule()], dry_run=True)['change_count'] == 0

@pytest.mark.parametrize('patch', [dict(gap_x=float('nan')),dict(gap_y=-1),dict(shape_ids=[2,2]),dict(shape_ids=[99]),dict(columns=0),dict(x=99),dict(pattern='bad')])
def test_invalid_does_not_publish(deck,tmp_path,patch):
    config = rule()
    config.update(patch)
    out = tmp_path / 'bad.pptx'
    with pytest.raises(ValueError):
        arrange(deck,[config],destination=out)
    assert not out.exists()

@pytest.mark.parametrize('mode',['row','column'])
def test_sequential_preview(deck,tmp_path,mode):
    second = rule()
    second['pattern'] = mode
    out = tmp_path / 'out.pptx'
    assert arrange(deck,[rule(),second],dry_run=True)['changes'] == arrange(deck,[rule(),second],destination=out)['changes']

def test_no_overwrite(deck):
    before = deck.read_bytes()
    with pytest.raises(ValueError):
        arrange(deck,[rule()],destination=deck)
    assert deck.read_bytes() == before

def test_connected_and_rotated_shapes_rejected(deck,tmp_path):
    from pptx.enum.shapes import MSO_CONNECTOR
    prs = Presentation(deck)
    slide = prs.slides[0]
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,0,0,100,100)
    connector.begin_connect(slide.shapes[0],0)
    connected = tmp_path / 'connected.pptx'
    prs.save(connected)
    with pytest.raises(ValueError,match='routing'):
        arrange(connected,[rule()],dry_run=True)
    prs = Presentation(deck)
    prs.slides[0].shapes[0].rotation = 20
    rotated = tmp_path / 'rotated.pptx'
    prs.save(rotated)
    with pytest.raises(ValueError,match='unrotated'):
        arrange(rotated,[rule()],dry_run=True)
