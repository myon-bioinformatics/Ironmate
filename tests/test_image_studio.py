"""Cross-runtime color/mosaic oracles, editable data, local server and output contracts."""
import json
import random
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import grid_tools
import image_studio as studio

ROOT = Path(__file__).resolve().parents[1]


def node(script, data=None):
    if not shutil.which('node'):
        pytest.skip('Node.js required for browser-independent JS core checks')
    run = subprocess.run(['node', '-e', "const c=require('./studio/core.js');const fs=require('node:fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));"+script],
                         cwd=ROOT, input=json.dumps(data), text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_heatmap_keeps_values_gaps_labels_and_source_across_python_js():
    source = {'data': [{'type': 'heatmap', 'z': [[-2.123456789012345, None, 4], [0, 1, 2]],
                        'x': [2024, 2025, 2026], 'y': ['中日', '巨人'], 'zmin': -4, 'zmax': 8}],
              'layout': {'title': {'text': 'source'}}}
    scene = studio.heatmap_scene(source)
    js = node('console.log(JSON.stringify(c.matrix(input)))', source)
    for key, value in js.items():
        assert scene['layers'][0][key] == value
    assert scene['source'] == source
    assert scene['layers'][0]['z'][0][1] is None
    output = node('console.log(JSON.stringify(c.validate(input)))', scene)
    assert output == scene


@pytest.mark.parametrize('source', [[[True]], [[float('inf')]], [[2**53]], [[1e100]], [[2**1024]], [[1], [1, 2]], [], {'data': []}])
def test_rejects_invalid_or_unsafe_heatmaps(source):
    with pytest.raises(ValueError):
        studio.heatmap_scene(source)


def test_quantized_colors_match_independent_js_for_negative_constant_and_clipped_values():
    cases = [[value, -3, 7, levels] for value in (-4, -3, -2.5, 0, 1.123456789, 7, 8)
             for levels in (0, 2, 3, 8, 256)] + [[1, 1, 1, 0], [None, 0, 1, 0]]
    js = node('console.log(JSON.stringify(input.map(x=>c.heatColor(...x))))', cases)
    assert js == [studio.heat_color(*row) or 'none' for row in cases]


def test_mosaic_alpha_means_partial_edges_and_cross_runtime_png_roundtrip():
    rng = random.Random(104)
    colors = ['#%02X%02X%02X%02X' % tuple(rng.randrange(256) for _ in range(4)) for _ in range(35)]
    art = {'schema': 'ironmate-pixel-grid/1', 'width': 7, 'height': 5, 'colors': colors,
           'pixels': [list(range(i, i+7)) for i in range(0, 35, 7)]}
    raw = [v for c in colors for v in bytes.fromhex(c[1:])]
    for cell, levels in ((1, 256), (3, 256), (3, 4), (128, 2)):
        result = studio.mosaic(art, cell, levels)
        js = node('console.log(JSON.stringify([...c.mosaicRGBA(input.data,input.w,input.h,input.cell,input.levels)]))',
                  {'data': raw, 'w': 7, 'h': 5, 'cell': cell, 'levels': levels})
        expected = [v for row in result['pixels'] for idx in row for v in bytes.fromhex(result['colors'][idx][1:])]
        assert js == expected
        back = grid_tools.restore(grid_tools.encode(result, 'png', meta=True))
        assert grid_tools.cells(back) == grid_tools.cells(result)
    assert studio.mosaic(art, 3, 4) != art
    # Reprocess the original when reducing cell size; don't claim to invert a mosaic.
    assert grid_tools.cells(studio.mosaic(art, 1, 256)) == grid_tools.cells(art)


def test_transparent_rgb_does_not_pollute_block_average():
    art = {'schema': 'ironmate-pixel-grid/1', 'width': 2, 'height': 1,
           'colors': ['#FF0000FF', '#0000FF00'], 'pixels': [[0, 1]]}
    result = studio.mosaic(art, 2)
    assert result['colors'] == ['#FF000080']


def test_svg_escape_layers_and_history_roundtrip_and_branching():
    scene = studio.heatmap_scene([[1, None, 2]])
    scene['layers'].append({'id': 'text', 'kind': 'text', 'name': 'custom', 'x': 10, 'y': 20, 'w': 500,
                            'h': 100, 'opacity': .5, 'rotation': 30, 'fontSize': 40,
                            'fill': '#112233', 'text': '<script>alert(1)</script> & 🌱\n次へ'})
    result = node('''
const h=new c.History(input);let b=h.current;b.layers[0].levels=4;h.commit(b);b.layers[0].z[0][0]=999;
const saved=h.current;const undo=h.undo();h.redo();h.undo();let d=h.current;d.layers.pop();h.commit(d);
console.log(JSON.stringify({svg:c.svg(input),saved,undo,branch:h.redo()}));
''', scene)
    assert '<script>' not in result['svg'] and '&lt;script&gt;' in result['svg']
    assert '欠測' in result['svg'] and '🌱' in result['svg']
    assert result['saved']['layers'][0]['z'][0][0] == 1
    assert result['undo'] == scene
    assert len(result['branch']['layers']) == 1


def test_untrusted_scene_rejects_external_image_and_invalid_geometry():
    scene = studio.heatmap_scene([[1]])
    result = node('''
const scenes=[];const a=c.clone(input);a.layers[0].rotation=NaN;scenes.push(a);
const b=c.clone(input);b.layers[0]={...b.layers[0],kind:'image',src:'https://example.com/a.png',cell:1,levels:256};scenes.push(b);
const d=c.clone(input);d.layers.push(c.clone(d.layers[0]));scenes.push(d);
console.log(JSON.stringify(scenes.map(s=>{try{c.svg(s);return false;}catch{return true;}})));
''', scene)
    assert result == [True, True, True]


def test_cli_heatmap_and_existing_file_protection(tmp_path):
    src, out = tmp_path/'matrix.json', tmp_path/'scene.json'
    src.write_text('[[1,null,3]]')
    cmd = [sys.executable, '-S', str(ROOT/'image_studio.py'), '--heatmap', str(src), '-o', str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    assert json.loads(out.read_text())['layers'][0]['z'] == [[1, None, 3]]
    old = out.read_bytes()
    assert subprocess.run(cmd, capture_output=True).returncode != 0
    assert out.read_bytes() == old


def test_loopback_server_exposes_only_fixed_assets_no_project_files_or_posts():
    server = ThreadingHTTPServer(('127.0.0.1', 0), studio.StudioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base) as r:
            assert 'Ironmate' in r.read().decode()
            assert "connect-src 'none'" in r.headers['Content-Security-Policy']
        with urllib.request.urlopen(base+'/core.js') as r:
            assert r.headers['Content-Type'].startswith('text/javascript')
        for path in ('/../AGENTS.md', '/vendor.lock.json', '/studio.js/../../README.md'):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base+path)
            assert err.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(urllib.request.Request(base, data=b'test'))
        assert err.value.code == 501
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
