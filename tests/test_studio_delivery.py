"""Pages allowlist, Flutter transport and independent arrow geometry checks."""
import base64
import copy
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import image_studio as s
from grid_tools import encode, make
from pptx_spec import arrow_geometry
from tests.test_image_studio import node

ROOT = Path(__file__).resolve().parents[1]


def test_build_site_contains_only_public_client_assets_and_relative_paths(tmp_path):
    target=s.build_site(tmp_path/'Ironmate')
    assert {p.name for p in target.iterdir()}=={'index.html','core.js','studio.js','style.css','.nojekyll','tools'}
    text=(target/'index.html').read_text()
    assert "Content-Security-Policy" in text and 'Base64 / 渡す' in text
    for name in ('core.js','studio.js','style.css'):
        assert (target/name).read_bytes()==(ROOT/'studio'/name).read_bytes()
        assert f'"{name}"' in text
    assert 'src="/' not in text and 'href="/' not in text
    (target/'keep.txt').write_text('local')
    with pytest.raises(FileExistsError): s.build_site(target)
    assert (target/'keep.txt').read_text()=='local'


def test_base64_payload_is_standard_padded_png_and_existing_decoder_accepts_it():
    from photo_grid import decode_base64
    png=encode(make('cloud','C01','shadow',16),'png')
    payload=node('console.log(JSON.stringify(c.pngPayload(input)))',list(png))
    assert payload['bytes']==len(png) and payload['mimeType']=='image/png'
    assert payload['dataUri']=='data:image/png;base64,'+payload['base64']
    assert base64.b64decode(payload['base64'],validate=True)==png
    assert decode_base64(payload['dataUri'])==png
    assert len(payload['base64'])==4*((len(png)+2)//3)
    assert len(png)<32*1024*1024


def test_vector_export_scales_viewbox_without_resampling_scene():
    scene=s.heatmap_scene([[0,1]])
    original=copy.deepcopy(scene)
    text=node('console.log(JSON.stringify(c.svg(input,undefined,4)))',scene)
    root=ET.fromstring(text)
    assert root.attrib['width']=='5120' and root.attrib['height']=='2880'
    assert root.attrib['viewBox']=='0 0 1280 720'
    assert scene==original
    assert node('try{c.svg(input,undefined,8);console.log(false)}catch{console.log(true)}',scene)


def test_seeded_arrow_geometry_matches_existing_pptx_middle_head_contract():
    rng=random.Random(20261017)
    cases=[]
    for i in range(80):
        angle=rng.uniform(-math.pi,math.pi)
        w,h,head=rng.uniform(25,600),rng.uniform(25,100),rng.uniform(2,24)
        cases.append([w,h,head,'middle'])
    results=node('console.log(JSON.stringify(input.map(x=>c.arrowGeometry(...x))))',cases)
    for case,g in zip(cases,results):
        w,h,head,_=case
        geom=arrow_geometry({'x':-.5,'y':h/2-.5,'w':1,'h':1},
                            {'x':w-.5,'y':h/2-.5,'w':1,'h':1},mode='center',head=head)
        assert g['line']==[0,h/2,w,h/2]
        assert sum(p[0] for p in g['points'][1:])/2==pytest.approx(w/2-head/2)
        assert g['points'][0]==pytest.approx([w/2+head/2,h/2])
        assert geom['head']['options']['x']+geom['head']['options']['w']/2==pytest.approx(w/2,abs=2e-6)
        assert geom['head']['options']['y']+geom['head']['options']['h']/2==pytest.approx(h/2,abs=2e-6)
        # Independent rotations over all quadrants preserve tip alignment and length.
        angle=rng.uniform(-math.pi,math.pi)
        dx,dy=w*math.cos(angle),w*math.sin(angle)
        geom=arrow_geometry({'x':-.5,'y':-.5,'w':1,'h':1},
                            {'x':dx-.5,'y':dy-.5,'w':1,'h':1},mode='center',head=head)
        assert geom['distance']==pytest.approx(w,abs=1e-6)
        assert geom['rotate']==pytest.approx((math.degrees(angle)+90)%360,abs=1e-4)


def test_clock_arrow_and_monochrome_are_separate_svg_primitives():
    scene=s.heatmap_scene([[1]])
    b={'x':0,'y':0,'w':160,'h':160,'rotation':0,'opacity':1,'fill':'#123456','stroke':'#345678','strokeWidth':3}
    scene['layers']=[dict(b,id='clock',kind='clock',hour=3,minute=0),
                     dict(b,id='arrow',kind='arrow',headSize=28,headPlacement='tip'),
                     dict(b,id='face)evil',kind='text',text='(・∀・) ❤️',fontSize=40,mono=True)]
    svg=node('console.log(JSON.stringify(c.svg(input)))',scene)
    root=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
    assert len(root.findall('.//s:line',ns))==15 # 12 ticks + 2 hands + arrow shaft
    assert len(root.findall('.//s:polygon',ns))==1
    assert not root.findall('.//s:marker',ns)
    mask=root.find('.//s:mask',ns)
    assert mask.attrib['mask-type']=='alpha' and ')' not in mask.attrib['id']
    lines=root.findall('.//s:g',ns)[0].findall('s:line',ns)
    assert float(lines[-2].attrib['x2'])>80 and float(lines[-2].attrib['y2'])==pytest.approx(80)
    assert float(lines[-1].attrib['x2'])==pytest.approx(80) and float(lines[-1].attrib['y2'])<80


def test_cli_svg_needs_no_browser_and_preserves_existing_destination(tmp_path):
    src,out=tmp_path/'scene.json',tmp_path/'scene.svg'
    src.write_text(json.dumps(s.heatmap_scene([[1,None]])))
    cmd=[sys.executable,'-S',str(ROOT/'image_studio.py'),'--render',str(src),'--format','svg','--scale','2','-o',str(out)]
    p=subprocess.run(cmd,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert ET.fromstring(out.read_text()).attrib['width']=='2560'
    before=out.read_bytes()
    assert subprocess.run(cmd,capture_output=True).returncode==2
    assert out.read_bytes()==before


def test_cli_mosaic_uses_original_pixel_dimensions_without_modifying_source():
    png=encode(make('cloud','C01','shadow',16),'png')
    scene=s.heatmap_scene([[1]])
    scene['layers']=[{'id':'image','kind':'image','name':'dot-art','x':0,'y':0,'w':160,'h':160,'rotation':0,'opacity':1,
                      'src':'data:image/png;base64,'+base64.b64encode(png).decode(),'cell':3,'levels':4,'sampling':'smooth'}]
    original=copy.deepcopy(scene)
    processed=s._processed_scene(scene)
    assert scene==original and processed['layers'][0]['src']!=scene['layers'][0]['src']
    from photo_grid import decode_png
    assert decode_png(base64.b64decode(processed['layers'][0]['src'].split(',')[1]))[:2]==(16,16)


def test_beginner_arrowhead_is_rotated_black_alpha_mask_and_style_is_validated():
    scene=s.heatmap_scene([[1]])
    scene['layers']=[{'id':'arrow)mask','kind':'arrow','x':0,'y':0,'w':200,'h':80,
                     'rotation':0,'opacity':1,'fill':'none','stroke':'#D59C22','strokeWidth':4,
                     'headSize':40,'headPlacement':'middle','headStyle':'beginner'}]
    svg=node('console.log(JSON.stringify(c.svg(input)))',scene)
    root=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
    mask=root.find('.//s:mask',ns)
    text=mask.find('s:text',ns)
    assert text.text=='🔰' and text.attrib['transform']=='rotate(-90 50 50)'
    assert mask.attrib['mask-type']=='alpha' and ')' not in mask.attrib['id']
    head=root.find('.//s:svg',ns)
    assert head.attrib['x']=='80' and head.attrib['y']=='20'
    assert head.find('s:rect',ns).attrib['fill']=='#000000'
    assert len(root.findall('.//s:line',ns))==1 and not root.findall('.//s:polygon',ns)
    scene['layers'][0]['headStyle']='external-url'
    assert node('try{c.validate(input);console.log(false)}catch{console.log(true)}',scene)
