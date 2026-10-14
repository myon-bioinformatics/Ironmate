"""Pipeline contract tests without invoking a browser or installing Node."""
from pathlib import Path
import pytest
import pptx_pipeline

def test_pipeline_reuses_conversion_and_inspection(monkeypatch, tmp_path):
    seen = {}
    def fake_convert(source, output, *, marp):
        seen["markdown"] = Path(source).read_text(encoding="utf-8")
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": [{"status": "unknown"}]})
    result = pptx_pipeline.run(text="# Hello\n", output=tmp_path / "slide.pptx")
    assert seen["markdown"] == "# Hello\n"
    assert result["inspection"]["slides"][0]["status"] == "unknown"

def test_mermaid_source_is_preserved(monkeypatch, tmp_path):
    fence = chr(96) * 3
    source = fence + "mermaid\nflowchart LR\n A[Start] --> B[End]\n" + fence + "\n"
    captured = []
    def fake_convert(path, output, *, marp):
        captured.append(Path(path).read_text(encoding="utf-8"))
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": []})
    pptx_pipeline.run(text=source, output=tmp_path / "diagram.pptx")
    assert captured == [source]

def test_empty_input_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        pptx_pipeline.run(text=" ", output=tmp_path / "slide.pptx")

def test_markdown_marp_native_enrichment_chain(monkeypatch,tmp_path):
    from pptx import Presentation
    calls=[]
    def fake_marp(source,output,*,marp):
        calls.append(Path(source).read_text())
        prs=Presentation();prs.slides.add_slide(prs.slide_layouts[6]);prs.save(output)
        return dict(slides=1,backend='marp',output=str(output))
    monkeypatch.setattr(pptx_pipeline,'convert',fake_marp)
    config=dict(pattern='flow',slide=1,x=1,y=1,width=8,height=3,gap=.4,
                items=[dict(title='A'),dict(title='B')])
    output=tmp_path/'enriched.pptx'
    result=pptx_pipeline.run(text='# Markdown\n',output=output,enrich_patterns=[config])
    assert calls==['# Markdown\n']
    assert result['conversion']['backend']=='marp'
    assert result['conversion']['output']==str(output)
    assert result['enrichment']['added_shapes']==9
    assert result['inspection']['slides'][0]['editable_runs']>0
    assert not list(tmp_path.glob('ironmate-enrich-*'))


def test_enrichment_failure_leaves_no_final_output(monkeypatch,tmp_path):
    from pptx import Presentation
    def fake_marp(source,output,*,marp):
        prs=Presentation();prs.slides.add_slide(prs.slide_layouts[6]);prs.save(output)
        return dict(slides=1)
    monkeypatch.setattr(pptx_pipeline,'convert',fake_marp)
    output=tmp_path/'bad.pptx'
    with pytest.raises(ValueError):
        pptx_pipeline.run(text='# Input',output=output,enrich_patterns=[dict(pattern='invalid')])
    assert not output.exists()
    assert not list(tmp_path.glob('ironmate-enrich-*'))

def test_cli_enrichment_resolves_csv_relative_to_toml(monkeypatch,tmp_path,capsys):
    from pptx import Presentation
    def fake_marp(source,output,*,marp):
        prs=Presentation();prs.slides.add_slide(prs.slide_layouts[6]);prs.save(output)
        return dict(slides=1,backend='marp')
    monkeypatch.setattr(pptx_pipeline,'convert',fake_marp)
    config_dir=tmp_path/'config';config_dir.mkdir()
    (config_dir/'data.csv').write_text('Key,Value\na,b\n')
    config=config_dir/'patterns.toml'
    config.write_text('[[patterns]]\npattern="table"\nslide=1\nx=1\ny=1\nwidth=8\nheight=3\ncsv="data.csv"\n')
    output=tmp_path/'out.pptx'
    pptx_pipeline.main(['--text','# Markdown','--enrich',str(config),'-o',str(output)])
    assert Presentation(output).slides[0].shapes[-1].table.cell(1,1).text=='b'
    assert '"enrichment"' in capsys.readouterr().out

@pytest.mark.parametrize('suffix,content',[('.csv','Name,Detail\nA,one\nB,two\n'),('.md','| Name | Detail |\n| --- | --- |\n| A | one |\n| B | two |\n')])
def test_direct_table_input_to_diagram(tmp_path,suffix,content):
    path=tmp_path/('data'+suffix);path.write_text(content)
    table=pptx_pipeline.table_pattern(path)
    assert table['rows']==[['Name','Detail'],['A','one'],['B','two']]
    cards=pptx_pipeline.table_pattern(path,pattern='cards',columns=2)
    assert cards['items']==[dict(title='A',body='Detail: one'),dict(title='B',body='Detail: two')]

def test_markdown_reuses_vendor_live_table_parser(tmp_path):
    path=tmp_path/'data.md'
    path.write_text('```\n| Wrong | X |\n| --- | --- |\n| nope | x |\n```\n\n| Name | Detail |\n| --- | --- |\n| A | a\\|b |\n')
    assert pptx_pipeline.table_pattern(path)['rows']==[['Name','Detail'],['A','a|b']]

def test_direct_csv_cli_needs_no_toml(monkeypatch,tmp_path,capsys):
    from pptx import Presentation
    def fake_marp(source,output,*,marp):
        prs=Presentation();prs.slides.add_slide(prs.slide_layouts[6]);prs.save(output)
        return dict(slides=1,backend='marp')
    monkeypatch.setattr(pptx_pipeline,'convert',fake_marp)
    path=tmp_path/'data.csv';path.write_text('Name,Detail\nA,one\nB,two\n')
    output=tmp_path/'out.pptx'
    pptx_pipeline.main(['--text','# Base','--table',str(path),'--table-pattern','flow','-o',str(output)])
    assert len(Presentation(output).slides[0].shapes)==9
    assert '"enrichment"' in capsys.readouterr().out

@pytest.mark.parametrize('content',['no table','| H |\n| --- |\n','```\n| H |\n| --- |\n| x |\n```'])
def test_missing_live_markdown_body_is_rejected(tmp_path,content):
    path=tmp_path/'data.md';path.write_text(content)
    with pytest.raises(ValueError):pptx_pipeline.table_pattern(path)


# Native patterns and preservation contracts (same pipeline).
from zipfile import ZipFile
import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from pptx_pipeline import enrich, load_patterns

@pytest.fixture
def deck(tmp_path):
    prs=Presentation()
    for _ in range(2):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        s=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,Inches(.2),Inches(.2))
        s.text='Keep me'
    source=tmp_path/'input.pptx'
    prs.save(source)
    return source

def spec(mode):
    result=dict(pattern=mode,slide=1,x=.5,y=1,width=9,height=4,gap=.25,
                items=[dict(title=f'Item {i}',body='Line 1\nLine 2',label='1–3') for i in range(3)])
    if mode=='table':
        result['rows']=[['A','B'],['a','b'],['c','d']]
    return result

@pytest.mark.parametrize('mode',['cards','regions','flow','agenda','table'])
def test_native_objects_preview_and_preservation(deck,tmp_path,mode):
    before=deck.read_bytes()
    out=tmp_path/'out.pptx'
    planned=enrich(deck,[spec(mode)],dry_run=True)
    actual=enrich(deck,[spec(mode)],destination=out)
    assert planned['patterns']==actual['patterns']
    assert deck.read_bytes()==before
    slide=Presentation(out).slides[0]
    assert slide.shapes[0].text=='Keep me'
    assert all(s.left>=0 and s.top>=0 and s.left+s.width<=Inches(10) and s.top+s.height<=Inches(7.5) for s in slide.shapes)
    assert not any(s.shape_type==13 for s in slide.shapes)
    assert len({s.shape_id for s in slide.shapes})==len(slide.shapes)
    if mode=='table':
        table=slide.shapes[-1].table
        assert table.cell(1,1).text=='b'
        table.cell(1,1).text='edited'
    else:
        texts=[s.text for s in slide.shapes if s.has_text_frame]
        assert any('Item 0' in t for t in texts)
        arrows = [s for s in slide.shapes if s.name.endswith('-arrow')]
        assert len(arrows)==(2 if mode=='flow' else 0)
        for arrow in arrows:
            assert arrow.height == 0
            assert arrow._element.xpath('.//a:tailEnd')[0].get('type') == 'triangle'
    with ZipFile(deck) as a,ZipFile(out) as b:
        assert a.namelist()==b.namelist()
        assert all(a.read(n)==b.read(n) for n in a.namelist() if n!='ppt/slides/slide1.xml')

@pytest.mark.parametrize('patch',[dict(x=float('nan')),dict(gap=-.2),dict(width=30),dict(columns=0),dict(items=[]),dict(pattern='bad'),dict(font_size=3),dict(accent='red'),dict(slide=99)])
def test_invalid_no_publication(deck,tmp_path,patch):
    config=spec('cards');config.update(patch)
    out=tmp_path/'bad.pptx'
    with pytest.raises(ValueError):enrich(deck,[config],destination=out)
    assert not out.exists()

def test_multiple_patterns_same_slide(deck,tmp_path):
    out=tmp_path/'multi.pptx'
    a=spec('cards');a['height']=1
    b=spec('agenda');b['height']=3;b['y']=3
    result=enrich(deck,[a,b],destination=out)
    assert len(Presentation(out).slides[0].shapes)==1+result['added_shapes']

def test_no_overwrite_and_later_error(deck,tmp_path):
    before=deck.read_bytes()
    with pytest.raises(ValueError):enrich(deck,[spec('cards')],destination=deck)
    bad=spec('table');bad['rows']=[['a'],['b','c']]
    out=tmp_path/'bad.pptx'
    with pytest.raises(ValueError):enrich(deck,[spec('cards'),bad],destination=out)
    assert not out.exists() and deck.read_bytes()==before

def test_cli(deck,tmp_path,capsys):
    config=tmp_path/'spec.toml'
    config.write_text('[[patterns]]\npattern="agenda"\nslide=1\nx=1\ny=1\nwidth=8\nheight=3\n[[patterns.items]]\ntitle="Overview"\nbody="Description"\n')
    assert enrich(deck,load_patterns(config),dry_run=True)['added_shapes']==2

def test_optional_config_roundtrip(tmp_path):
    import tomllib
    from pathlib import Path
    prs=Presentation()
    for _ in range(4):prs.slides.add_slide(prs.slide_layouts[6])
    source=tmp_path/'blank.pptx';prs.save(source)
    config_path=tmp_path/'patterns.toml'
    config_path.write_text('# Existing four-slide deck; choose free regions. Agenda is deferred.\n[[patterns]]\npattern = "cards"\nslide = 1\nx = 0.5\ny = 1.2\nwidth = 9.0\nheight = 4.0\ncolumns = 3\n[[patterns.items]]\ntitle = "Observation"\nbody = "Record the current state."\n[[patterns.items]]\ntitle = "Comparison"\nbody = "Use consistent conditions."\n[[patterns.items]]\ntitle = "Decision"\nbody = "Describe the evidence."\n\n[[patterns]]\npattern = "regions"\nslide = 2\nx = 0.5\ny = 1.2\nwidth = 9.0\nheight = 4.0\naccent = "#000000"\n[[patterns.items]]\ntitle = "Input"\nbody = "Collect data."\n[[patterns.items]]\ntitle = "Process"\nbody = "Transform data."\n[[patterns.items]]\ntitle = "Output"\nbody = "Present results."\n\n[[patterns]]\npattern = "flow"\nslide = 3\nx = 0.5\ny = 1.2\nwidth = 9.0\nheight = 3.0\ngap = 0.4\n[[patterns.items]]\ntitle = "Receive"\nbody = "Validate input."\n[[patterns.items]]\ntitle = "Transform"\nbody = "Apply explicit rules."\n[[patterns.items]]\ntitle = "Check"\nbody = "Verify the output."\n[[patterns.items]]\ntitle = "Publish"\nbody = "Save a new file."\n\n[[patterns]]\npattern = "table"\nslide = 4\nx = 0.5\ny = 1.2\nwidth = 9.0\nheight = 3.0\ncsv = "comparison.csv"\n# Monochrome defaults apply without color options.\n# Optional overrides:\n# header_fill = "#222222"\n# header_text = "#FFFFFF"\n# row_fills = ["#FFFFFF", "#F2F2F2"]\n# border_color = "#B3B3B3"\n')
    (tmp_path/'comparison.csv').write_text('Criterion,Option A,Option B\nInput,Text,Image\nOutput,Report,Grid\n')
    patterns=load_patterns(config_path)
    out=tmp_path/'examples.pptx'
    result=enrich(source,patterns,destination=out)
    assert [p['pattern'] for p in result['patterns']]==['cards','regions','flow','table']
    assert all(len(slide.shapes)>0 for slide in Presentation(out).slides)

def test_csv_values_and_explicit_table_colors(deck,tmp_path):
    path=tmp_path/'comparison.csv'
    path.write_text('\ufeffCriterion,Value\n"quoted, field",日本語\nNext,42\n',encoding='utf-8')
    config=spec('table');del config['rows']
    config.update(csv=str(path),header_fill='#202633',row_fills=['#FFFFFF','#EAF1F8'])
    out=tmp_path/'csv.pptx'
    enrich(deck,[config],destination=out)
    table=Presentation(out).slides[0].shapes[-1].table
    assert table.cell(1,0).text=='quoted, field'
    assert table.cell(1,1).text=='日本語'
    assert str(table.cell(0,0).fill.fore_color.rgb)=='202633'
    assert str(table.cell(1,0).fill.fore_color.rgb)=='FFFFFF'
    assert str(table.cell(2,0).fill.fore_color.rgb)=='EAF1F8'
    assert len(table.cell(0,0)._tc.xpath('./a:tcPr/a:lnL'))==1

@pytest.mark.parametrize('patch',[dict(row_fills=[]),dict(row_fills=['wrong']),dict(header_fill='bad')])
def test_invalid_table_colors(deck,tmp_path,patch):
    config=spec('table');config.update(patch)
    with pytest.raises(ValueError):enrich(deck,[config],dry_run=True)

def test_default_table_is_neutral_grayscale(deck,tmp_path):
    out=tmp_path/'gray.pptx'
    enrich(deck,[spec('table')],destination=out)
    table=Presentation(out).slides[0].shapes[-1].table
    assert str(table.cell(0,0).fill.fore_color.rgb)=='222222'
    assert str(table.cell(1,0).fill.fore_color.rgb)=='FFFFFF'
    assert str(table.cell(2,0).fill.fore_color.rgb)=='F2F2F2'
