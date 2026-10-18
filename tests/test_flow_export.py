"""Contract reuse, failure behavior and transport identity for flow exports."""
import base64
import copy
import json
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

import flow_export as f
import image_studio
import mermaid_svg
from vendor.web_ui_flow import flow_html, flow_mermaid, MAX_INPUT

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / 'examples/flow.json').read_text())
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-8 -8 320.25 200.5" width="100%" style="max-width:320.25px;background-color:transparent;"><text x="10" y="30">A &amp; B</text></svg>'


def fake_renderer(monkeypatch, svg=SVG):
    def render(markdown, directory, **kwargs):
        assert markdown == flow_mermaid(SAMPLE)
        assert json.loads(kwargs['config'].read_text())['flowchart']['htmlLabels'] is False
        out = directory / 'test.svg'
        out.write_bytes(svg)
        return '', [out]
    monkeypatch.setattr(f, 'render_mermaid', render)


def test_mermaid_is_exact_upstream_and_has_no_tool_dependency(monkeypatch):
    monkeypatch.setattr(f, 'render_mermaid', lambda *a, **k: pytest.fail('renderer called'))
    before = copy.deepcopy(SAMPLE)
    assert f.render_flow(SAMPLE, 'mermaid') == flow_mermaid(SAMPLE).encode()
    assert SAMPLE == before


@pytest.mark.parametrize('change', [lambda s: s.update(extra=True), lambda s: s.update(sources=[]),
    lambda s: s.update(steps=[{'title': '\x00'}]), lambda s: s.update(title=''),
    lambda s: s['sources'][0].update(url='https://example.com'),
    lambda s: s['steps'][0].update(note=None), lambda s: s.update(title='X'*121)])
def test_upstream_input_validation_precedes_renderer(monkeypatch, change):
    monkeypatch.setattr(f, 'render_mermaid', lambda *a, **k: pytest.fail('renderer called'))
    spec = copy.deepcopy(SAMPLE); change(spec)
    with pytest.raises(ValueError): f.render_flow(spec)


def test_byte_budget_invalid_utf8_and_nonfinite_json():
    for raw in (b' '* (MAX_INPUT+1), b'\xff', b'{', b'null'):
        with pytest.raises((ValueError, UnicodeError)): f.read_spec(raw)
    with pytest.raises(ValueError): f.render_flow({'title': math.nan}, 'mermaid')


def test_labels_stay_text_in_html_and_mermaid():
    spec = copy.deepcopy(SAMPLE)
    spec['sources'][0]['title'] = '"><img src=x onerror=alert(1)>&[x]\\'
    html = flow_html(spec); md = f.render_flow(spec, 'mermaid').decode()
    assert '<img' not in html and '&lt;img' in html
    assert '<img' not in md and '#lt;img' in md
    assert '#quot;' in md and '#amp;' in md and '#91;' in md and '#92;' in md


@pytest.mark.parametrize('scale', [0, .24, 8.1, float('inf'), float('nan'), True, '2'])
def test_scale_validation(scale):
    with pytest.raises(ValueError): f.render_flow(SAMPLE, 'mermaid', scale=scale)


def test_format_background_and_svg_dimension_validation(monkeypatch):
    for opts in ({'format':'jpeg'}, {'background':'red'}, {'background':'#FFFFFF;url(x)'}):
        with pytest.raises(ValueError): f.render_flow(SAMPLE, **opts)
    fake_renderer(monkeypatch)
    root = ET.fromstring(f.render_flow(SAMPLE, scale=2))
    assert root.attrib['width'] == '641' and root.attrib['height'] == '401'
    assert root.attrib['viewBox'] == '-8 -8 320.25 200.5'
    assert 'max-width' not in root.attrib['style'] and 'transparent' in root.attrib['style']
    for box in ('0 0 8193 1', '0 0 4097 4096', '0 0 nan 1', '0 0 -1 1', '0 0 0 2'):
        bad = SVG.replace(b'-8 -8 320.25 200.5', box.encode())
        with pytest.raises(ValueError): f._sized_svg(bad, 1)
    with pytest.raises(ValueError): f._sized_svg(b'x'*(f.MAX_SVG+1), 1)


def test_exact_limits():
    svg = SVG.replace(b'-8 -8 320.25 200.5', b'0 0 4096 4096')
    assert ET.fromstring(f._sized_svg(svg,1)).attrib['width']=='4096'
    assert f.read_spec(json.dumps(SAMPLE).encode().ljust(MAX_INPUT)) == SAMPLE


def test_png_and_both_base64_forms_have_identical_bytes(monkeypatch):
    from grid_png import to_png
    from grid_tools import make
    png = to_png(make('cloud','C01','shadow',16))
    fake_renderer(monkeypatch)
    monkeypatch.setattr(f, 'raster_svg', lambda svg, **k: png)
    assert f.render_flow(SAMPLE, 'png') == png
    assert base64.b64decode(f.render_flow(SAMPLE, 'base64'), validate=True) == png
    assert f.render_flow(SAMPLE, 'data-uri') == b'data:image/png;base64,' + base64.b64encode(png)


def test_missing_renderer_is_explicit_and_does_not_replace_output(tmp_path):
    output = tmp_path/'keep.png'; output.write_bytes(b'keep')
    result = subprocess.run([sys.executable,'-S',str(ROOT/'flow_export.py'),str(ROOT/'examples/flow.json'),
        '--format','png','--mmdc','/nonexistent/mmdc','-o',str(output),'--force'],capture_output=True)
    assert result.returncode == 2 and b'mmdc) not installed' in result.stderr
    assert output.read_bytes()==b'keep' and result.stdout==b''


def test_python_and_node_cli_and_node_api_match_from_other_cwd(tmp_path):
    expected = f.render_flow(SAMPLE,'mermaid')
    for command in ([sys.executable,'-S',str(ROOT/'flow_export.py')], ['node',str(ROOT/'flow_export.cjs')]):
        result = subprocess.run(command+['--format','mermaid'],input=json.dumps(SAMPLE).encode(),cwd=tmp_path,capture_output=True)
        assert result.returncode==0,result.stderr
        assert result.stdout==expected
    script='const f=require(process.argv[1]); const spec=JSON.parse(process.argv[2]); process.stdout.write(f.renderFlow(spec,{format:"mermaid",python:process.argv[3]}));'
    result=subprocess.run(['node','-e',script,str(ROOT/'flow_export.cjs'),json.dumps(SAMPLE),sys.executable],cwd=tmp_path,capture_output=True)
    assert result.returncode==0,result.stderr
    assert result.stdout==expected


def test_node_api_missing_python_reports_error():
    script='const f=require("./flow_export.cjs");try{f.renderFlow({}, {python:"/missing/python"})}catch(e){console.error(e.message);process.exit(2)}'
    result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True)
    assert result.returncode==2 and b'Python process failed' in result.stderr


def test_transparent_is_passed_explicitly_to_mmdc(monkeypatch,tmp_path):
    monkeypatch.setattr(mermaid_svg.shutil,'which',lambda _: '/fake/mmdc')
    def run(cmd,**kwargs):
        assert cmd[cmd.index('-b')+1]=='transparent'
        assert cmd[cmd.index('-c')+1]=='config.json'
        assert cmd[cmd.index('-p')+1]=='browser.json'
        Path(cmd[cmd.index('-o')+1]).write_bytes(SVG)
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(mermaid_svg.subprocess,'run',run)
    mermaid_svg.render_mermaid(flow_mermaid(SAMPLE),tmp_path,background=None,config='config.json',puppeteer_config='browser.json')


def test_studio_shared_raster_rejects_oversize_before_browser(monkeypatch):
    monkeypatch.setattr(image_studio,'_find_chrome',lambda _: pytest.fail('browser started'))
    for width,height in ((8193,1),(4097,4096),(0,1)):
        svg=f'<svg width="{width}" height="{height}"/>'.encode()
        with pytest.raises(ValueError): image_studio.raster_svg(svg)


def test_missing_chrome_error(monkeypatch):
    monkeypatch.setattr(image_studio.shutil,'which',lambda _: None)
    with pytest.raises(RuntimeError,match='Chrome/Chromium'):
        image_studio._find_chrome()


def test_cli_rejects_oversize_and_preserves_destination(tmp_path):
    src=tmp_path/'input.json'; src.write_bytes(b' '*(MAX_INPUT+1))
    result=subprocess.run([sys.executable,'-S',str(ROOT/'flow_export.py'),str(src),'--format','mermaid'],capture_output=True)
    assert result.returncode==2 and result.stdout==b'' and b'256KiB' in result.stderr
    src.write_text(json.dumps(SAMPLE)); out=tmp_path/'keep'; out.write_bytes(b'keep')
    result=subprocess.run([sys.executable,'-S',str(ROOT/'flow_export.py'),str(src),'--format','mermaid','-o',str(out)],capture_output=True)
    assert result.returncode==2 and out.read_bytes()==b'keep'


@pytest.mark.parametrize('payload', [b'', b'\x89PNG\r\n\x1a\n', b'not PNG'])
def test_shared_raster_rejects_truncated_browser_output(monkeypatch,payload):
    monkeypatch.setattr(image_studio.shutil,'which',lambda _: '/fake/node')
    monkeypatch.setattr(image_studio,'_find_chrome',lambda _: '/fake/chrome')
    monkeypatch.setattr(image_studio.subprocess,'run',lambda *a,**k: SimpleNamespace(returncode=0,stdout=payload))
    with pytest.raises(RuntimeError,match='unexpected PNG dimensions'):
        image_studio.raster_svg(b'<svg width="100" height="100"/>')
