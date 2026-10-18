"""Opt-in real renderer check, run in the existing Marp/browser CI lane."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from flow_export import render_flow
from photo_grid import decode_png

ROOT = Path(__file__).resolve().parents[1]


def test_real_flow_formats_and_node_api():
    if os.environ.get('IRONMATE_RUN_FLOW_INTEGRATION') != '1':
        pytest.skip('optional real flow renderer integration not enabled')
    spec = json.loads((ROOT/'examples/flow.json').read_text())
    opts = dict(mmdc=os.environ.get('IRONMATE_MMDC_BIN','mmdc'),
                chrome=os.environ.get('IRONMATE_CHROME'),
                puppeteer_config=os.environ.get('IRONMATE_PUPPETEER_CONFIG'))
    directory = ROOT/'build/test-results/flow-export'; directory.mkdir(parents=True,exist_ok=True)
    outputs = {}
    for fmt, ext in (('mermaid','md'),('svg','svg'),('png','png'),('base64','base64.txt'),('data-uri','data-uri.txt')):
        outputs[fmt] = render_flow(spec,fmt,**opts)
        (directory/('sample.'+ext)).write_bytes(outputs[fmt])
    assert base64.b64decode(outputs['base64'],validate=True)==outputs['png']
    assert outputs['data-uri']==b'data:image/png;base64,'+outputs['base64']
    w,h,rows=decode_png(outputs['png'],max_pixels=16777216)
    alphas=[r[i] for r in rows for i in range(3,len(r),4)]
    assert 0 in alphas and 255 in alphas
    opaque=render_flow(spec,'png',background='#FFFFFF',**opts)
    (directory/'sample-white.png').write_bytes(opaque)
    _,_,white_rows=decode_png(opaque,max_pixels=16777216)
    assert all(r[i]==255 for r in white_rows for i in range(3,len(r),4))
    scaled=render_flow(spec,'png',scale=2,**opts)
    (directory/'sample-2x.png').write_bytes(scaled)
    from xml.etree import ElementTree as ET
    box=[float(x) for x in ET.fromstring(outputs['svg']).attrib['viewBox'].split()]
    import math
    assert decode_png(scaled,max_pixels=16777216)[:2]==(math.ceil(box[2]*2),math.ceil(box[3]*2))
    script='const f=require("./flow_export.cjs");const fs=require("node:fs");process.stdout.write(f.renderFlow(JSON.parse(fs.readFileSync(0,"utf8")),JSON.parse(process.argv[1])));'
    node_opts=dict(format='png',mmdc=opts['mmdc'],chrome=opts['chrome'],puppeteerConfig=opts['puppeteer_config'],python=sys.executable)
    result=subprocess.run(['node','-e',script,json.dumps(node_opts)],input=json.dumps(spec).encode(),cwd=ROOT,capture_output=True,timeout=180)
    assert result.returncode==0,result.stderr
    assert result.stdout==outputs['png']
    malicious=json.loads(json.dumps(spec))
    malicious['sources'][0]['title']='"><img src="https://invalid.example/x" onerror="window.__flow_injected=1">'
    (directory/'escaped.svg').write_bytes(render_flow(malicious,'svg',**opts))
    (directory/'report.json').write_text(json.dumps(dict(width=w,height=h,transparent_pixels=alphas.count(0),
        opaque_pixels=alphas.count(255),node_png_matches=True,base64_png_matches=True,data_uri_png_matches=True,
        png_sha256=hashlib.sha256(outputs['png']).hexdigest(),
        source_sha256=hashlib.sha256((ROOT/'examples/flow.json').read_bytes()).hexdigest()),indent=2)+'\n')
