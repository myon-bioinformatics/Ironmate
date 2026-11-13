"""🎨 Image Studio and its neighbours: the studio, comparison, digest, ironmate_image, alignment, candidate selection, CSS, delivery, quality, ingress, shape metrics, workspace, browser matrix and flow export."""

import base64
import copy
import functools
import importlib.util
import json
import math
import random
import re
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
import browser_matrix as bm
import flow_export as f
import flow_workspace as w
import grid_tools
import grid_tools as g
import image_compare as c
import image_compare as compare
import image_digest as digest
import image_studio
import image_studio as s
import image_studio as studio
import ironmate_image as im
import studio_ingress as ingress
from browser_matrix import encode_png
from flow_export import render_flow
from grid_tools import encode, make
from ironlib import mermaid_svg, studio_candidate_selection as selection
from ironlib.pptx_spec import arrow_geometry
from ironlib.studio_alignment import invert_translation, translate_rgba
from ironlib.studio_image_quality import compare_rgba
from ironlib.studio_shape_metrics import metrics
from photo_grid import decode_png
from scripts import quality_selection_experiment as study
from studio_ingress import MAX_BYTES, decode, parse_shelf
from vendor.ascii_artist import FLOW_MAX_INPUT as MAX_INPUT, flow_html, flow_mermaid


# ═══ · image studio ══════════════════════════════════════════════════════════════════════════════════════
# Cross-runtime color/mosaic oracles, editable data, local server and output contracts.

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
    # fetch-guard: a stuck loopback server fails this test in 10 s instead of hanging CI.
    get = functools.partial(urllib.request.urlopen, timeout=10)
    try:
        with get(base) as r:
            assert 'Ironmate' in r.read().decode()
            assert "connect-src 'none'" in r.headers['Content-Security-Policy']
        with get(base+'/core.js') as r:
            assert r.headers['Content-Type'].startswith('text/javascript')
        for path, mime in (('/brand/icon.svg', 'image/svg+xml'),
                           ('/brand/favicon-16.png', 'image/png'),
                           ('/brand/favicon.ico', 'image/x-icon'),
                           ('/brand/manifest.webmanifest', 'application/manifest+json')):
            with get(base + path) as r:
                assert r.headers['Content-Type'].startswith(mime)
                assert r.read() == studio.public_assets()[path.lstrip('/')]
        for path in ('/../AGENTS.md', '/vendor.lock.json', '/studio.js/../../README.md'):
            with pytest.raises(urllib.error.HTTPError) as err:
                get(base+path)
            assert err.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as err:
            get(urllib.request.Request(base, data=b'test'))
        assert err.value.code == 501
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


# ═══ · image compare ═════════════════════════════════════════════════════════════════════════════════════
# Independent scalar error, alpha, Pareto and CLI regression checks.

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


# ═══ · image digest ══════════════════════════════════════════════════════════════════════════════════════
# image_digest: any rows x cols of images with a status -> one small self-contained page.

__all__ = []


def png(path, w, h, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(w, h, bytes(color) * (w * h)))


def spec(**extra):
    return {"schema": "ironmate-image-digest-input/1", "title": "Run 1", "rows": ["home", "hub"],
            "cols": ["Linux-chromium-desktop", "macOS-webkit-iphone"], "meta": {"build": "abc123", "link": "https://example.test/run"},
            "cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "s/home-l.png", "status": "pass"},
                      {"row": "home", "col": "macOS-webkit-iphone", "image": "s/home-i.png", "status": "fail",
                       "notes": ["320px:overlap"]},
                      {"row": "hub", "col": "Linux-chromium-desktop", "status": "pass"}], **extra}


@pytest.fixture
def base(tmp_path):
    png(tmp_path / "s/home-l.png", 384, 800, (200, 30, 30, 255))
    png(tmp_path / "s/home-i.png", 1152, 1992, (30, 30, 200, 255))
    return tmp_path


def test_one_page_with_thumbnails_statuses_and_summary(base, tmp_path):
    page, summary, info = digest.build(spec(), base)
    assert info["tile"] == [64, 128] and info["fits"] and info["statuses"] == {"fail": 1, "pass": 2}
    assert page.count("data:image/png;base64,") == 2 and 'class="s-fail"' in page and "not run" in page
    assert "build abc123" in page and 'href="https://example.test/run"' in page and "<script" not in page
    assert summary.startswith("<!-- ironmate-image-digest -->\n### Run 1")
    assert "2/4 passed; build abc123. [Link](https://example.test/run)" in summary
    assert "| home | 1/2 | macOS-webkit-iphone (320px:overlap) |" in summary
    assert "| hub | 1/2 | macOS-webkit-iphone (not run) |" in summary
    digest.write(tmp_path / "out", page, summary, info)
    assert json.loads((tmp_path / "out/digest.json").read_text())["bytes"] == len(page.encode())
    with pytest.raises(ValueError, match="new or empty"):
        digest.write(tmp_path / "out", page, summary, info)


def test_thumbnails_are_quartered_until_the_page_fits(tmp_path):
    import random
    random.seed(1)
    noise = bytes(random.randrange(256) if i % 4 != 3 else 255 for i in range(256 * 512 * 4))  # incompressible
    (tmp_path / "n.png").write_bytes(encode_png(256, 512, noise))
    rows = [f"r{i}" for i in range(4)]
    big = {"schema": "ironmate-image-digest-input/1", "rows": rows, "cols": ["c"],
           "cells": [{"row": r, "col": "c", "image": "n.png", "status": "pass"} for r in rows]}
    _, _, roomy = digest.build(big, tmp_path, max_bytes=1_000_000)
    _, _, tight = digest.build(big, tmp_path, max_bytes=60_000)
    assert roomy["tile"] == [64, 128] and roomy["bytes"] > 60_000
    assert tight["tile"] == [32, 64] and tight["fits"]  # one halving each way = a quarter of the pixels


@pytest.mark.parametrize("change", [
    {"schema": "x"}, {"rows": []}, {"rows": ["a", "a"]}, {"cols": ["\x01"]},
    {"cells": [{"row": "nope", "col": "Linux-chromium-desktop"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "../etc/passwd"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "/abs.png"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "status": "Pass!"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop"}, {"row": "home", "col": "Linux-chromium-desktop"}]},
    {"meta": {"link": "javascript:alert(1)"}}, {"title": ""},
])
def test_invalid_input_is_rejected(base, change):
    with pytest.raises(ValueError):
        digest.build(spec(**change), base)


def test_escaping(base):
    page, summary, _ = digest.build(spec(title="<b>t</b>", rows=["<i>", "hub"],
                                         cells=[{"row": "<i>", "col": "Linux-chromium-desktop", "status": "pass",
                                                 "notes": ["<script>"]}]), base)
    assert "<i>" not in page.split("</style>")[1] and "&lt;script&gt;" in page


def test_cli_and_node_entry_point(base, tmp_path, capsys):
    (base / "input.json").write_text(json.dumps(spec()), encoding="utf-8")
    assert digest.main([str(base / "input.json"), "--out", str(tmp_path / "cli")]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] == 2
    assert digest.main([str(base / "input.json"), "--out", str(tmp_path / "x"), "--tile", "big"]) == 2
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    run = subprocess.run(["node", "--test", "tests/image_digest.test.cjs"], cwd=ROOT, capture_output=True, text=True,
                         env={**__import__("os").environ, "DIGEST_PNG": str(base / "s/home-l.png")}, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr


def single_spec(image='a.png'):
    return {'schema': digest.SCHEMA, 'rows': ['home'], 'cols': ['chromium'],
            'cells': [{'row': 'home', 'col': 'chromium', 'image': image, 'status': 'pass'}]}


def symlink(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f'symlink unavailable: {error}')


@pytest.mark.parametrize('parent_link', [False, True])
def test_external_symlink_is_rejected_before_open(tmp_path, monkeypatch, parent_link):
    root, outside = tmp_path / 'input', tmp_path / 'outside'
    root.mkdir()
    png(outside / 'a.png', 1, 1, (1, 2, 3, 255))
    symlink(root / 'linked', outside if parent_link else outside / 'a.png', directory=parent_link)
    monkeypatch.setattr(Path, 'open', lambda *a, **k: pytest.fail('external image must not be opened'))
    with pytest.raises(ValueError, match='inside the input directory'):
        digest.build(single_spec('linked/a.png' if parent_link else 'linked'), root)


def test_in_root_symlinks_and_symlinked_root_are_allowed(tmp_path):
    root = tmp_path / 'input'
    png(root / 'shots/a.png', 1, 1, (1, 2, 3, 255))
    symlink(root / 'a.png', root / 'shots/a.png')
    symlink(root / 'nested', root / 'shots', directory=True)
    symlink(tmp_path / 'root-alias', root, directory=True)
    for image in ('shots/a.png', 'a.png', 'nested/a.png'):
        page, _, info = digest.build(single_spec(image), tmp_path / 'root-alias')
        assert 'data:image/png;base64,' in page and info['fits']


def test_missing_and_non_regular_image_are_rejected(tmp_path):
    (tmp_path / 'folder').mkdir()
    with pytest.raises(ValueError, match='regular file'):
        digest.build(single_spec('folder'), tmp_path)
    symlink(tmp_path / 'dangling', tmp_path / 'absent')
    with pytest.raises(OSError):
        digest.build(single_spec('dangling'), tmp_path)


@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_32mib_boundary_is_enforced_before_open_and_decode(tmp_path, monkeypatch, delta):
    image = tmp_path / 'a.png'
    length = digest.MAX_IMAGE_BYTES + delta
    with image.open('wb') as stream:
        stream.truncate(length)  # sparse: no need to construct a huge PNG
    original_open, reads, decodes = Path.open, [], []

    class Reader:
        def __enter__(self):
            self.stream = original_open(image, 'rb')
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            reads.append(size)
            assert size == digest.MAX_IMAGE_BYTES + 1
            return self.stream.read(size)

    def decode(raw, **kwargs):
        decodes.append(len(raw))
        return 1, 1, [bytes((1, 2, 3, 255))]

    def open_image(*args, **kwargs):
        assert delta <= 0, 'oversize must be rejected before opening the file'
        return Reader()

    monkeypatch.setattr(Path, 'open', open_image)
    monkeypatch.setattr(digest, 'decode_png', decode)
    if delta > 0:
        with pytest.raises(ValueError, match='larger than 32MiB'):
            digest.build(single_spec(), tmp_path)
        assert not reads and not decodes
    else:
        digest.build(single_spec(), tmp_path)
        assert reads == [digest.MAX_IMAGE_BYTES + 1] and decodes == [length]


def test_bounded_read_rejects_growth_before_decode(tmp_path, monkeypatch):
    png(tmp_path / 'a.png', 1, 1, (1, 2, 3, 255))
    original_open, reads = Path.open, []
    monkeypatch.setattr(digest, 'MAX_IMAGE_BYTES', 100)

    class GrowingReader:
        def __enter__(self):
            self.stream = original_open(tmp_path / 'a.png', 'rb')
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            reads.append(size)
            return b'x' * size  # simulates growth after both stat checks

    monkeypatch.setattr(Path, 'open', lambda *a, **k: GrowingReader())
    monkeypatch.setattr(digest, 'decode_png', lambda *a, **k: pytest.fail('oversize must not be decoded'))
    with pytest.raises(ValueError, match='larger than 32MiB'):
        digest.build(single_spec(), tmp_path)
    assert reads == [101]


def test_markdown_cells_remain_literal_single_line_text(tmp_path):
    row, col = r'row|[x]*_`\\', 'env|<b>test</b>'
    value = {'schema': digest.SCHEMA, 'rows': [row, 'missing|row'], 'cols': [col],
             'cells': [{'row': row, 'col': col, 'status': 'fail',
                        'notes': ['a|b\r\n| injected | row |\t<script>x</script>', r'[x](url)*_`\\']}]}
    _, summary, _ = digest.build(value, tmp_path)
    table = summary.split('| Row |', 1)[1]
    assert len(table.splitlines()) == 4
    assert all(line.count('|') == 4 for line in table.splitlines()[1:])
    assert '&#124;' in summary and '&lt;script&gt;' in summary and '<b>' not in summary
    assert r'\[x\]' in summary and r'\*\_\`' in summary
    assert '\r' not in summary and '\t' not in summary


@pytest.mark.parametrize('kind', ['new', 'empty', 'file', 'nonempty', 'file-link', 'dir-link', 'broken-link'])
def test_output_path_contract(tmp_path, kind):
    out = tmp_path / 'out'
    if kind in ('empty', 'nonempty'):
        out.mkdir()
        if kind == 'nonempty':
            (out / 'keep').write_text('keep')
    elif kind == 'file':
        out.write_text('keep')
    elif kind.endswith('link'):
        target = tmp_path / 'target'
        if kind == 'dir-link':
            target.mkdir()
        elif kind == 'file-link':
            target.write_text('keep')
        symlink(out, target, directory=kind == 'dir-link')
    if kind in ('new', 'empty'):
        digest.write(out, 'html', 'markdown', {'schema': digest.OUT_SCHEMA})
        assert sorted(p.name for p in out.iterdir()) == ['digest.html', 'digest.json', 'summary.md']
    else:
        with pytest.raises(ValueError, match='new or empty directory'):
            digest.write(out, 'html', 'markdown', {})
        if kind == 'file':
            assert out.read_text() == 'keep'
        if kind == 'nonempty':
            assert (out / 'keep').read_text() == 'keep'
        if kind == 'dir-link':
            assert not list(target.iterdir())


def test_repeated_shrinking_reads_and_decodes_each_real_image_once(tmp_path, monkeypatch):
    import random
    noise = random.Random(17).randbytes(256 * 512 * 4)
    (tmp_path / 'a.png').write_bytes(encode_png(256, 512, noise))
    symlink(tmp_path / 'alias.png', tmp_path / 'a.png')
    value = single_spec()
    value['rows'] = ['r1', 'r2', 'r3', 'r4']
    value['cells'] = [{'row': row, 'col': 'chromium', 'image': 'alias.png' if i % 2 else 'a.png',
                       'status': 'pass'} for i, row in enumerate(value['rows'])]
    original_open, original_decode, original_page = Path.open, digest.decode_png, digest.page_html
    opens, decodes, passes = [], [], []

    def open_image(path, *a, **k):
        opens.append(path)
        return original_open(path, *a, **k)

    def decode(raw, **kwargs):
        decodes.append(len(raw))
        return original_decode(raw, **kwargs)

    def page(data, thumbs, tile):
        passes.append(tile)
        return original_page(data, thumbs, tile)

    monkeypatch.setattr(Path, 'open', open_image)
    monkeypatch.setattr(digest, 'decode_png', decode)
    monkeypatch.setattr(digest, 'page_html', page)
    page, _, info = digest.build(value, tmp_path, tile=(256, 512), max_bytes=60_000)
    assert len(opens) == len(decodes) == 1
    assert len(passes) >= 3 and passes[0] == (256, 512)
    assert info['fits'] and info['bytes'] == len(page.encode('utf-8')) <= 60_000


def test_minimum_tile_reports_an_unavoidable_budget_overrun(tmp_path):
    value = single_spec(None)
    value['cols'] = [f'env-{i}' for i in range(1000)]
    value['cells'] = []
    _, _, info = digest.build(value, tmp_path, max_bytes=20_000)
    assert info['tile'] == [16, 32] and info['fits'] is False and info['bytes'] > 20_000


def test_browser_test_kit_adapter_contract(tmp_path):
    png(tmp_path / 'shots/home.png', 1, 1, (1, 2, 3, 255))
    value = {'schema': digest.SCHEMA, 'rows': ['flutter-home', 'flutter-hub'],
             'cols': ['Linux-chromium-desktop', 'macOS-webkit-iphone'],
             'meta': {'build': 'c' * 40, 'link': 'https://github.com/example/repo/actions/runs/1'},
             'cells': [{'row': 'flutter-home', 'col': 'Linux-chromium-desktop', 'status': 'pass'},
                       {'row': 'flutter-home', 'col': 'macOS-webkit-iphone', 'status': 'fail',
                        'notes': ['320px:overlap:#a:#b']},
                       {'row': 'flutter-hub', 'col': 'Linux-chromium-desktop', 'status': 'unknown',
                        'image': 'shots/home.png', 'notes': ['no record']}]}
    page, _, info = digest.build(value, tmp_path)
    summary = digest.summary_markdown(digest.validate(value), marker='<!-- platform-apps-digest -->')
    digest.write(tmp_path / 'out', page, summary, info)
    assert summary.startswith('<!-- platform-apps-digest -->\n')
    assert '1/4 passed' in summary and '320px:overlap:#a:#b' in summary and 'no record' in summary
    assert info['schema'] == 'ironmate-image-digest/1' and (info['rows'], info['cols']) == (2, 2)
    assert info['passed'] == 1 and info['statuses'] == {'fail': 1, 'pass': 1, 'unknown': 1}
    assert page.count('data:image/png;base64,') == 1 and 'not run' in page
    assert info['bytes'] == (tmp_path / 'out/digest.html').stat().st_size
    assert (tmp_path / 'out/summary.md').stat().st_size <= 60_000


@pytest.mark.parametrize('tile', [(64, 128), [64, 128], (65, 129)])
def test_tile_dimensions_accept_tuples_and_lists(tmp_path, tile):
    assert digest.build(single_spec(None), tmp_path, tile=tile)[2]['tile'] == list(tile)


@pytest.mark.parametrize('tile', [None, [], [64], [64, 128, 256], [True, 128], [0, 32]])
def test_invalid_tile_has_clear_error(tmp_path, tile):
    with pytest.raises(ValueError, match='tile must be within'):
        digest.build(single_spec(None), tmp_path, tile=tile)


# ═══ · ironmate image ════════════════════════════════════════════════════════════════════════════════════
# High-level facade: fit_to_limit always fits, matches the real CLI, raises FitError when impossible.

def _cli(*args, ok=True):
    out = subprocess.run([sys.executable, '-m', 'grid_tools', *args], cwd=ROOT, capture_output=True, timeout=120)
    assert (out.returncode == 0) == ok, out.stderr
    return out


@pytest.fixture
def art_png(tmp_path):
    p = tmp_path / 'art.png'
    p.write_bytes(g.encode(g.make('circle', 'C03', 'shadow', 24), 'png', 4))   # 96x96, cell 4, meta
    return p


@pytest.fixture
def noisy_png(tmp_path):
    rnd = random.Random(7)
    art = g.make('cloud', 'C01', 'normal', 32)
    art = dict(art, colors=art['colors'] + ['#%08X' % rnd.getrandbits(32) for _ in range(60)])
    art['pixels'] = [[rnd.randrange(len(art['colors'])) for _ in row] for row in art['pixels']]
    p = tmp_path / 'noisy.png'
    p.write_bytes(g.encode(art, 'png', 1, meta=False))
    return p


@pytest.mark.parametrize('data_uri', [False, True])
@pytest.mark.parametrize('prefer', ['lossless', 'largest'])
def test_fit_always_within_limit_and_matches_cli(art_png, noisy_png, data_uri, prefer):
    for src in (art_png, noisy_png):
        full = im.fit_to_limit(src, max_chars=10 ** 7, data_uri=data_uri).chars
        for limit in sorted({full, full - 1, full // 2, full // 3, 900, 400}):
            try:
                r = im.fit_to_limit(src, max_chars=limit, data_uri=data_uri, prefer=prefer)
            except im.FitError:
                continue
            assert r.chars == len(r.text) <= limit and r.bytes == len(r.data)
            assert base64.b64decode(r.text.split(',')[-1]) == r.data
            args = r.command.replace('INPUT', str(src)).split()[3:]
            assert _cli(*args).stdout.rstrip(b'\n').decode() == r.text          # same bytes as the real CLI
            if limit == full:
                assert r.ratio == '1' and r.meta_used
            if prefer == 'lossless' and src == art_png and limit >= 900:
                assert r.lossless
            out = _cli('fit', str(src), '--limit-chars', str(limit), '--prefer', prefer,
                       *(['--data-uri'] if data_uri else []))
            assert out.stdout.rstrip(b'\n').decode() == r.text
            assert json.loads(out.stderr)['ratio'] == r.ratio


def test_bytes_limit_and_meta_drop(noisy_png):
    full = im.fit_to_limit(noisy_png, max_bytes=10 ** 7).bytes
    r = im.fit_to_limit(noisy_png.read_bytes(), max_bytes=full)
    assert r.bytes <= full and r.ratio == '1' and r.meta_used
    bare = len(im.to_png(noisy_png, meta=False))
    r = im.fit_to_limit(noisy_png, max_bytes=bare)          # full size only fits without meta -> dropped
    assert r.bytes <= bare and not r.meta_used and r.warnings and r.ratio == '1'
    assert r.data == g.encode(g.restore(noisy_png.read_bytes(), 32), 'png', meta=False)


def test_impossible_raises_one_error(art_png):
    with pytest.raises(im.FitError, match='cannot fit'):
        im.fit_to_limit(art_png, max_bytes=20)
    out = _cli('fit', str(art_png), '--limit-bytes', '20', ok=False)
    assert out.returncode == 2 and b'cannot fit' in out.stderr
    with pytest.raises(ValueError, match='exactly one'):
        im.fit_to_limit(art_png)


def test_inputs_and_helpers_roundtrip(art_png):
    data = art_png.read_bytes()
    b64 = base64.b64encode(data).decode()
    for src in (art_png, str(art_png), data, b64, 'data:image/png;base64,' + b64):
        assert im.load(src) == g.restore(data)
    art = im.load(data)
    assert im.from_base64(im.to_base64(art)) == art
    assert im.from_base64(im.to_base64(art, data_uri=True)) == art
    assert im.load(json.dumps(art)) == art
    small = im.resize(data, 12)
    assert small['width'] == 12 and im.resize(small, 24)['width'] == 24


def test_jpeg_input_with_pillow():
    Image = pytest.importorskip('PIL.Image')
    import io
    img = Image.new('RGB', (64, 48))
    img.putdata([(x * 4, y * 5, (x * y) % 256) for y in range(48) for x in range(64)])
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=80)
    r = im.fit_to_limit(buf.getvalue(), max_chars=6000)
    assert r.chars <= 6000 and im.from_base64(r.text)['width'] == r.width


def test_python_c_one_liners(art_png):
    code = ("import ironmate_image as im;r=im.fit_to_limit(%r,max_chars=1500,data_uri=True);"
            "print(r.ratio, r.chars, r.meta_used)" % str(art_png))
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    ratio, chars, _ = out.stdout.decode().split()
    assert int(chars) <= 1500
    code = "import ironmate_image as im;s=im.to_base64(%r);print(im.from_base64(s)['width'])" % str(art_png)
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == b'24'


def test_parse_shelf_facade(art_png):
    b64 = im.to_base64(art_png)
    items = im.parse_shelf([b64, 'plain text note'])
    assert len(items) == 2 and items[0]['type'] == 'image' and items[1]['type'] == 'text'


# ═══ · studio alignment ══════════════════════════════════════════════════════════════════════════════════

CLEAR = (0, 0, 0, 0)
RED = (255, 0, 0, 255)


class AlignmentTests(unittest.TestCase):
    def test_roundtrip_when_content_stays_inside(self):
        src = [CLEAR] * 64
        src[2 * 8 + 2] = RED
        shifted = translate_rgba(8, 8, src, 1, -1)
        self.assertEqual(shifted["clipped_nonfill"], 0)
        restored = invert_translation(8, 8, shifted["pixels"], 1, -1)
        self.assertEqual(restored["pixels"], src)

    def test_clipped_content_cannot_be_recovered(self):
        src = [CLEAR] * 64
        src[3 * 8 + 7] = RED
        shifted = translate_rgba(8, 8, src, 1, 0)
        self.assertEqual(shifted["clipped_nonfill"], 1)
        restored = invert_translation(8, 8, shifted["pixels"], 1, 0)
        self.assertNotEqual(restored["pixels"], src)

    def test_zero_translation_is_identity(self):
        src = [CLEAR] * 64
        src[0] = RED
        self.assertEqual(translate_rgba(8, 8, src, 0, 0)["pixels"], src)


# ═══ · studio candidate selection ════════════════════════════════════════════════════════════════════════
# Cross-protocol regressions; independent counts and frozen examples, no CPU thresholds.

EVIDENCE = ROOT/'docs/evidence/studio-quality'


def image_studio_candidate_selection(values):
    return len(values),1,bytes(c for v in values for c in (v,v,v,255))


def test_legacy_policy_reuses_saved_original_choices_and_keeps_default_schema():
    folder = ROOT/'docs/evidence/studio-delivery/tradeoff-original'
    saved = json.loads((folder/'report.json').read_text())
    fresh,_ = compare.analyze(*(study.load_image(folder/(k+'.png'))
                               for k in ('reference','nearest','smooth')))
    assert fresh['roles'] == saved['roles']
    assert fresh['pareto_indices'] == saved['pareto_indices']
    for actual,expected in zip(fresh['candidates'],saved['candidates']):
        for key,value in actual.items():
            assert value == expected[key]
    assert 'quality' not in fresh


def test_rgb_error_objectives_keep_legacy_choices_including_ties():
    report,images = compare.analyze(image_studio_candidate_selection([0,0]),image_studio_candidate_selection([0,10]),image_studio_candidate_selection([6,6]))
    selection.enrich_sweep(report,images,image_studio_candidate_selection([0,0]))
    rows = report['quality']['candidates']
    for metric,role in [('rgb_mae','mae_priority'),('rgb_rmse','rmse_priority'),('balance_score','balanced')]:
        assert selection.select_quality(rows,metric)['selected_index'] == report['roles'][role]
    # MAE equal, RMSE different: preserve the established secondary error policy.
    tied = [dict(rows[0],index=0,rgb_mae=5,rgb_rmse=8,balance_score=90),
            dict(rows[0],index=1,rgb_mae=5,rgb_rmse=6,balance_score=90)]
    assert selection.select_quality(tied,'rgb_mae')['selected_index'] == 1
    assert selection.select_quality(tied,'balance_score')['selected_index'] == 1
    assert selection.select_quality(tied,'iou')['tied_indices'] == [0,1]


def test_opaque_mae_rgba_redundancy_and_hidden_rgb_are_distinct():
    a,b = image_studio_candidate_selection([0,12,255]),image_studio_candidate_selection([255,30,245])
    row = selection.diagnostic_row(a,b,0)
    errors = [255,18,10]
    assert row['rgb_mae'] == sum(errors)/3
    assert row['rgb_rmse'] == math.sqrt(sum(x*x for x in errors)/3)
    assert row['rgba_similarity'] == pytest.approx(1-3*row['rgb_mae']/1020)
    assert row['alpha_iou'] == 1
    hidden_a = (1,1,bytes([255,0,0,0]))
    hidden_b = (1,1,bytes([0,255,0,0]))
    hidden = selection.diagnostic_row(hidden_a,hidden_b,0)
    assert hidden['rgb_mae'] == 0 and hidden['rgba_similarity'] < 1


def test_same_dimensions_are_insufficient_for_pooling_and_duplicates_rejected():
    row = selection.diagnostic_row(image_studio_candidate_selection([0]),image_studio_candidate_selection([1]),0)
    other = selection.diagnostic_row(image_studio_candidate_selection([2]),image_studio_candidate_selection([1]),1)
    for fn in (selection.summarize,selection.rank_relations,selection.pareto_indices,selection.select_quality):
        with pytest.raises(ValueError,match='same reference'):
            fn([row,other])
        with pytest.raises(ValueError,match='unique'):
            fn([row,row])


def test_undefined_axes_constraints_and_strict_pareto_no_fallback():
    rows = [selection.diagnostic_row(image_studio_candidate_selection([255]),image_studio_candidate_selection([255]),i) for i in (0,1)]
    assert selection.select_quality(rows,'energy_dice')['selected_index'] is None
    assert selection.pareto_indices(rows)['undefined_indices'] == [0,1]
    assert selection.pareto_indices(rows,('rgb_mae','rgb_rmse'))['indices'] == [0,1]
    assert selection.select_quality(rows,max_source_clipped_nonfill=0)['selected_index'] is None
    rows[1]['source_clipped_nonfill'] = 0
    assert selection.select_quality(rows,max_source_clipped_nonfill=0)['selected_index'] == 1
    for bad in (-1,0.5,True):
        with pytest.raises(ValueError):
            selection.select_quality(rows,max_missing_foreground=bad)
    worse = dict(rows[0],index=2,rgb_mae=1,rgb_rmse=2)
    assert selection.pareto_indices([rows[0],worse],('rgb_mae','rgb_rmse'))['indices'] == [0]
    invalid = dict(rows[0],rgb_mae=float('nan'))
    with pytest.raises(ValueError,match='finite'):
        selection.select_quality([invalid],'rgb_mae')


def test_registration_perfect_score_does_not_clear_raw_missing_constraint():
    white,black = (255,255,255,255),(0,0,0,255)
    ref = [white]*64; ref[27] = black
    candidate = [white]*64; candidate[28] = black
    as_image = lambda p:(8,8,bytes(c for pixel in p for c in pixel))
    row = selection.diagnostic_row(as_image(ref),as_image(candidate),0)
    assert row['iou'] == 0 and row['aligned_iou'] == 1
    assert row['missing_foreground'] == 1
    assert selection.select_quality([row],'aligned_iou',max_missing_foreground=0)['selected_index'] is None


@pytest.fixture(scope='module')
def joined():
    return study.recorded_groups(EVIDENCE)


def test_all_110_cases_joined_on_exact_reference_and_reversals_reproduced(joined):
    rows = [r for g in joined for r in g['candidates']]
    assert len(rows) == 110
    assert all(r['alpha_iou'] == 1 for r in rows)
    assert sum(g['rank_relations']['iou']['pairs'] for g in joined) == 396
    for metric,count in [('rgba_similarity',37),('energy_dice',32),('near_field',7),('aligned_iou',10),('dice',0)]:
        assert sum(g['rank_relations'][metric]['reversed'] for g in joined) == count
    assert sum(g['mae_relations']['rgba_similarity']['reversed'] for g in joined) == 0
    for group in joined:
        assert len({r['reference_key'] for r in group['candidates']}) == 1
        selected = group['selection']['legacy']['roles'].values()
        assert all(group['candidates'][i]['kind'] != 'identity' for i in selected)
    shapes = next(g for g in joined if g['scenario']=='shapes' and '128x128:' in g['reference_key'] and len(g['candidates'])>1)
    by_kind = {r['kind']:r for r in shapes['candidates']}
    blur,dilate = by_kind['blur'],by_kind['contour_dilate']
    assert blur['iou'] > dilate['iou'] and blur['rgba_similarity'] < dilate['rgba_similarity']
    assert blur['rgb_mae'] > dilate['rgb_mae']


def test_saved_alignment_loss_and_crop_unknown_provenance_remain_visible(joined):
    rows = [r for g in joined for r in g['candidates']]
    row = next(r for r in rows if r['id']=='studio-demo-None-128-shift_1px')
    assert row['aligned_iou'] == 1
    assert row['source_clipped_nonfill'] == 72
    assert row['source_inverse_exact'] is False
    # Registration has its own different provenance; it cannot certify the forward transform.
    assert isinstance(row['registration_clipped_nonfill'],int)
    crop = next(r for r in rows if r['kind']=='enlarge_crop')
    assert crop['source_clipped_nonfill'] is None and crop['crop_discarded_canvas_pixels'] > 0


def test_reused_evidence_rejects_wrong_pixels_and_wrong_scores():
    saved = json.loads((EVIDENCE/'results.json').read_text())['cases'][0]
    ref,candidate = (study.load_image(EVIDENCE/saved[k]) for k in ('reference_png','candidate_png'))
    wrong = copy.deepcopy(saved);wrong['foreground']['IoU'] = -1
    with pytest.raises(ValueError,match='disagree'):
        selection.diagnostic_row(ref,candidate,0,recorded=wrong)


def test_quality_cli_selected_png_constraints_and_no_output_on_bad_policy(tmp_path):
    paths=[]
    for name,values in [('reference',[0,0]),('nearest',[0,10]),('smooth',[6,6])]:
        p=tmp_path/(name+'.png');p.write_bytes(compare.png(image_studio_candidate_selection(values)));paths.append(p)
    out=tmp_path/'variants'
    cmd=[sys.executable,'-S',str(ROOT/'image_compare.py'),'--reference',str(paths[0]),
         '--nearest',str(paths[1]),'--smooth',str(paths[2]),'--out',str(out),
         '--quality','--select-by','near_field','--max-missing-foreground','0']
    run=subprocess.run(cmd,capture_output=True,text=True)
    assert run.returncode == 0,run.stderr
    report=json.loads((out/'report.json').read_text())
    chosen=report['quality']['selection']['selected_index']
    assert (out/'quality_selected.png').read_bytes() == (out/f'variant-{chosen:02d}.png').read_bytes()
    assert report['quality']['selection']['objective'] == 'near_field'
    bad=tmp_path/'invalid'
    cmd[cmd.index(str(out))]=str(bad)
    cmd.remove('--quality')
    assert subprocess.run(cmd,capture_output=True).returncode == 2
    assert not bad.exists()


def test_quality_cost_guard_does_not_change_legacy_sweep():
    ref=(1024,1024,bytes(1024*1024*4))
    with pytest.raises(ValueError,match='1MP'):
        selection.enrich_sweep({'background_rgb':[255,255,255]},[ref,ref],ref)


def test_frozen_sweep_evidence_reproduces_candidates_scores_and_choices():
    recorded = json.loads((ROOT/'docs/evidence/studio-quality-selection/results.json').read_text())
    fresh = study.resampling_sweeps(EVIDENCE)
    assert len(fresh) == 4
    for actual,expected in zip(fresh,recorded['sweeps']):
        assert actual['name'] == expected['name']
        assert actual['pixel_sha256'] == expected['pixel_sha256']
        assert actual['roles'] == expected['roles']
        assert actual['pareto_indices'] == expected['pareto_indices']
        assert actual['quality']['summary'] == expected['quality']['summary']
        for a,b in zip(actual['quality']['candidates'],expected['quality']['candidates']):
            assert {k:v for k,v in a.items() if k != 'diagnostic_cpu_ms'} == {k:v for k,v in b.items() if k != 'diagnostic_cpu_ms'}
    # Frozen nontrivial selection differences: these are reference-specific, not preferences.
    selected=fresh[0]['quality']['summary']['by_metric']
    assert [selected[m]['selected_index'] for m in ('rgb_mae','rgb_rmse','balance_score','iou','energy_dice','near_field')] == [0,9,8,3,3,3]
    shapes=next(s for s in fresh if s['name']=='synthetic-reduction-shapes')
    assert shapes['roles']['balanced'] == 10
    assert shapes['quality']['summary']['by_metric']['energy_dice']['selected_index'] == 2
    for s in fresh:
        assert all(r['diagnostic_cpu_ms'] >= 0 for r in s['quality']['candidates'])


# ═══ · studio css ════════════════════════════════════════════════════════════════════════════════════════
# The studio stylesheets are scripts/build_studio_css.py's output (PySaiyanWeBoo pysaiyanweboo + the studio's layout).

def _generator():
    spec = importlib.util.spec_from_file_location('build_studio_css', ROOT / 'scripts' / 'build_studio_css.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_studio_stylesheets_match_the_generator():
    import pysaiyanweboo
    module = _generator()
    bundles = module.bundles()
    assert {p.relative_to(ROOT).as_posix() for p in bundles} == {
        'studio/style.css', 'studio/tools/tools.css', 'studio/brand/gallery.css', 'studio/slides/slides.css'}
    for target, options in bundles.items():
        assert pysaiyanweboo.check_bundle(target, **options) == [], target.relative_to(ROOT)
        assert target.read_text(encoding='utf-8').startswith('/* web-ui-bundle/1 commit=')
    for name in ('studio/style.css', 'studio/tools/tools.css', 'studio/brand/gallery.css'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert '/* css/components.css */' in text and 'body[data-ui-theme="ironmate"]{--ui-bg:#edf0ec;' in text
        assert '.ui-elements button,' in text and 'cdn.' not in text
    assert '/* css/' not in (ROOT / 'studio/slides/slides.css').read_text(encoding='utf-8')  # loaded after style.css
    assert module.main(['--check']) == 0
    assert pysaiyanweboo.check_theme(module.IRONMATE) == []  # the brand palette reads at WCAG AA on both grounds


def test_studio_pages_opt_into_the_components_and_palette():
    for name in ('studio/index.html', 'studio/tools/index.html', 'studio/brand/index.html'):
        assert '<body class="ui-elements" data-ui-theme="ironmate">' in (ROOT / name).read_text(encoding='utf-8'), name
    import image_studio
    slides = image_studio.public_assets()['slides/index.html'].decode('utf-8')
    assert '<body class="ui-elements" data-ui-theme="ironmate" data-mode="slides">' in slides


# ═══ · studio delivery ═══════════════════════════════════════════════════════════════════════════════════
# Pages allowlist, Flutter transport and independent arrow geometry checks.

def test_build_site_contains_only_public_client_assets_and_relative_paths(tmp_path):
    target=s.build_site(tmp_path/'Ironmate')
    assert {p.name for p in target.iterdir()}=={'index.html','core.js','studio.js','style.css','.nojekyll','tools','slides','brand'}
    brand_files = {
        'index.html', 'gallery.css', 'mono.svg', 'dark-green.svg', 'famicom.svg',
        'gameboy.svg', 'pixel-3d.svg', 'manifest.webmanifest', 'apple-touch-icon.png',
        'app-192.png', 'app-512.png', 'app-maskable-512.png', 'icon.svg',
        'heatmap.svg', 'hero.svg', 'favicon.ico', 'favicon-16.png', 'favicon-32.png',
        'favicon-48.png', 'icon-192.png', 'example-demo.gif', 'example-stamp-demo.gif',
    }
    assert {p.relative_to(target/'brand').as_posix() for p in (target/'brand').rglob('*')} == brand_files
    for name in brand_files:
        assert (target/'brand'/name).is_file()
        assert (target/'brand'/name).read_bytes() == (ROOT/'studio/brand'/name).read_bytes()
    for page in ('index.html', 'tools/index.html', 'slides/index.html', 'brand/index.html'):
        html = (target/page).read_text()
        assert 'src="/' not in html and 'href="/' not in html
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


# ═══ · studio image quality ══════════════════════════════════════════════════════════════════════════════

def grid(coords, width=8, height=8, color=(255, 0, 0, 255)):
    pixels = [(0, 0, 0, 0)] * (width * height)
    for x, y in coords:
        pixels[y * width + x] = color
    return pixels


class ImageQualityTests(unittest.TestCase):
    def test_identical(self):
        a = grid({(1, 1), (1, 2)})
        m = compare_rgba(8, 8, a, a)
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Aligned_IoU"], 1)
        self.assertEqual(m["RGBA_L1_Similarity"], 1)
        self.assertEqual((m["Alignment_dx"], m["Alignment_dy"]), (0, 0))

    def test_shift_and_realign(self):
        a = grid({(1, 1), (1, 2)})
        b = grid({(2, 1), (2, 2)})
        m = compare_rgba(8, 8, a, b)
        self.assertEqual(m["IoU"], 0)
        self.assertEqual(m["Aligned_IoU"], 1)
        self.assertEqual((m["Alignment_dx"], m["Alignment_dy"]), (-1, 0))
        self.assertGreater(m["RGBA_L1_Similarity"], 0)

    def test_missing_pixel(self):
        a = grid({(1, 1), (1, 2)})
        b = grid({(1, 1)})
        m = compare_rgba(8, 8, a, b)
        self.assertLess(m["IoU"], 1)
        self.assertLess(m["Aligned_IoU"], 1)

    def test_color_difference_not_hidden_by_mask(self):
        a = grid({(1, 1)}, color=(255, 0, 0, 255))
        b = grid({(1, 1)}, color=(0, 0, 255, 255))
        m = compare_rgba(8, 8, a, b)
        self.assertEqual(m["IoU"], 1)
        self.assertLess(m["RGBA_L1_Similarity"], 1)


# ═══ · studio ingress ════════════════════════════════════════════════════════════════════════════════════

PNG = bytes.fromhex("89504e470d0a1a0a") + b"payload"


class PortableIngressTests(unittest.TestCase):
    def test_raw_and_uri(self):
        b64 = base64.b64encode(PNG).decode()
        self.assertEqual(decode(b64), ("image/png", PNG))
        self.assertEqual(decode("data:image/png;base64," + b64), ("image/png", PNG))

    def test_mismatch(self):
        with self.assertRaises(ValueError):
            decode("data:image/jpeg;base64," + base64.b64encode(PNG).decode())

    def test_limit(self):
        with self.assertRaises(ValueError):
            decode(base64.b64encode(PNG).decode(), max_bytes=len(PNG) - 1)

    def test_padding(self):
        with self.assertRaises(ValueError):
            decode(base64.b64encode(PNG + b"x").decode().rstrip("="))

    def test_parse_shelf(self):
        b64 = base64.b64encode(PNG).decode()
        items = [
            "data:image/png;base64," + b64,
            "plain text note",
            {"text": b64, "label": "Custom PNG"},
        ]
        parsed = parse_shelf(items)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["type"], "image")
        self.assertEqual(parsed[0]["mime"], "image/png")
        self.assertEqual(parsed[0]["data"], PNG)
        self.assertEqual(parsed[1]["type"], "text")
        self.assertIsNone(parsed[1]["data"])
        self.assertEqual(parsed[2]["type"], "image")
        self.assertEqual(parsed[2]["label"], "Custom PNG")

    def test_parse_shelf_limits(self):
        with self.assertRaises(ValueError):
            parse_shelf(["item"] * 21)

    def test_aggregate_inclusive_boundary_and_remaining_decode_budget(self):
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        for delta in (-1, 0, 1):
            with self.subTest(delta=delta), patch.object(ingress, "decode", wraps=decode) as spy:
                budget = 2 * len(PNG) + delta
                if delta < 0:
                    with self.assertRaises(ValueError):
                        parse_shelf([uri, uri], max_bytes=budget)
                else:
                    self.assertEqual(len(parse_shelf([uri, uri], max_bytes=budget)), 2)
                self.assertEqual([call.kwargs["max_bytes"] for call in spy.call_args_list],
                                 [budget, budget - len(PNG)])

    def test_refuses_before_base64_allocation_even_with_rounded_length(self):
        # All three sizes have the same encoded length: the exact byte check is required.
        for remaining in (len(PNG) - 1, len(PNG) - 2):
            with self.subTest(remaining=remaining), patch.object(ingress.base64, "b64decode") as decoder:
                with self.assertRaises(ValueError):
                    decode(base64.b64encode(PNG).decode(), max_bytes=remaining)
                decoder.assert_not_called()

    def test_real_32mib_aggregate_boundary(self):
        encoded = base64.b64encode(PNG).decode()
        note = "n" * (MAX_BYTES - len(PNG))
        self.assertEqual(len(parse_shelf([note, encoded])), 2)
        with self.assertRaises(ValueError):
            parse_shelf([note + "x", encoded])
        with self.assertRaises(ValueError):
            parse_shelf([note, encoded, encoded])

    def test_explicit_image_errors_never_become_notes(self):
        b64 = base64.b64encode(PNG).decode()
        cases = ["data:image/jpeg;base64," + b64,
                 "data:text/plain;base64," + b64,
                 "data:image/png;base64,%%%", "data:image/png,broken", "data:",
                 "data:image/png;base64,", b64[:-1] + "!",
                 {"type": "image", "text": "broken"}, {"type": "image", "data": ""},
                 {"mime": "image/jpeg", "text": b64}, {"mime": "image/gif", "text": b64}]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                parse_shelf(["existing note", item])
        with self.assertRaises(ValueError):
            parse_shelf([b64], max_bytes=len(PNG) - 1)

    def test_notes_count_utf8_and_full_shelf_rejects_more_images(self):
        self.assertEqual(parse_shelf(["🌱", "abc"], max_bytes=7)[1]["text"], "abc")
        with self.assertRaises(ValueError):
            parse_shelf(["🌱", "abcd"], max_bytes=7)
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        with self.assertRaises(ValueError):
            parse_shelf([uri, uri], max_bytes=len(PNG))
        self.assertEqual(len(parse_shelf(["note"] * 20)), 20)
        self.assertEqual(parse_shelf(["\ufeff " + uri])[0]["type"], "image")


# ═══ · studio shape metrics ══════════════════════════════════════════════════════════════════════════════

class ShapeMetricTests(unittest.TestCase):
    def test_identical_even_isolated_pixel(self):
        m = metrics(8, 8, {12}, {12})
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Symmetric_Near_Field"], 1)

    def test_symmetry(self):
        a, b = {8, 9, 10}, {9, 10, 11}
        x, y = metrics(8, 8, a, b), metrics(8, 8, b, a)
        self.assertEqual(x, y)

    def test_near_miss(self):
        m = metrics(8, 8, {8, 16}, {9, 17})
        self.assertEqual(m["IoU"], 0)
        self.assertGreater(m["Symmetric_Near_Field"], 0)

    def test_disjoint_far(self):
        m = metrics(8, 8, {0}, {63})
        self.assertEqual(m["Symmetric_Near_Field"], 0)

    def test_weighted_zero_undefined(self):
        m = metrics(8, 8, {0}, {1}, [0] * 64)
        self.assertIsNone(m["Energy_Dice"])

    def test_empty(self):
        m = metrics(8, 8, set(), set())
        self.assertEqual(m["IoU"], 1)
        self.assertEqual(m["Symmetric_Near_Field"], 1)


# ═══ · studio workspace ══════════════════════════════════════════════════════════════════════════════════
# Browser-independent workspace contract and HTML control regression.

class _Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.setdefault(attrs["id"], []).append(tag)


def test_studio_html_contains_unique_controls_used_by_initialization():
    parser = _Controls()
    parser.feed((ROOT / "studio/index.html").read_text())
    script = (ROOT / "studio/studio.js").read_text()
    required = set(re.findall(r'\$\("([a-z][a-z0-9-]*)"\)', script))
    assert required
    assert all(len(parser.ids.get(name, [])) == 1 for name in required)
    for name in ("save", "save-workspace", "trim-history"):
        assert parser.ids[name] == ["button"]
    assert parser.ids["open-workspace"] == ["input"]


def test_shared_workspace_contracts_in_node():
    if not shutil.which("node"):
        pytest.skip("Node.js required for browser-independent workspace contracts")
    result = subprocess.run(["node", "--test", "tests/studio_workspace.test.cjs"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ═══ · browser matrix ════════════════════════════════════════════════════════════════════════════════════
# browser_matrix: browser-test-kit screenshots -> one sheet, tiles and a report.

def png_browser_matrix(width, height, color):
    return bm.encode_png(width, height, bytes(color) * (width * height))


def tree(root, shots):
    for (page, env, name), (w, h, color) in shots.items():
        path = root / 'platform-app-x' / page / env / f'{name}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_browser_matrix(w, h, color))


def test_sheet_report_and_tiles_from_a_btk_tree(tmp_path):
    red, blue = (255, 0, 0, 255), (0, 0, 255, 255)
    tree(tmp_path / 'in', {
        ('flutter-home', 'Linux-chromium-desktop', 'width-384'): (384, 800, red),
        ('flutter-home', 'macOS-webkit-iphone', 'width-384'): (1152, 1992, red),   # 3x DPR, shorter viewport
        ('flutter-home', 'Windows-firefox-desktop', 'width-384'): (384, 800, blue),
        ('flutter-hub', 'Linux-chromium-desktop', 'width-384'): (384, 800, blue),
        ('flutter-hub', 'Linux-chromium-desktop', 'initial'): (1280, 800, blue),
    })
    shots = bm.find_shots(tmp_path / 'in')
    assert sorted(shots) == [('flutter-home', 'Linux-chromium-desktop'), ('flutter-home', 'Windows-firefox-desktop'),
                             ('flutter-home', 'macOS-webkit-iphone'), ('flutter-hub', 'Linux-chromium-desktop')]
    report, sheet, tiles = bm.build(shots, tile_w=40, tile_h=80)
    assert report['schema'] == 'ironmate-browser-matrix/1' and report['reference'] == 'Linux-chromium-desktop'
    assert report['pages'] == ['flutter-home', 'flutter-hub']
    assert report['missing'] == [{'page': 'flutter-hub', 'env': 'Windows-firefox-desktop'},
                                 {'page': 'flutter-hub', 'env': 'macOS-webkit-iphone'}]
    cells = {(c['page'], c['env']): c for c in report['cells']}
    assert cells['flutter-home', 'macOS-webkit-iphone']['width'] == 1152
    assert cells['flutter-home', 'Linux-chromium-desktop']['difference']['rgb_mae'] == 0
    # Same color, but the iPhone viewport is shorter: the bottom is padded white.
    assert 0 < cells['flutter-home', 'macOS-webkit-iphone']['difference']['rgb_mae'] < 50
    assert cells['flutter-home', 'Windows-firefox-desktop']['difference']['rgb_mae'] == pytest.approx(170, abs=0.5)
    assert sheet[:2] == (3 * 40 + 4 * bm.GAP, 2 * 80 + 3 * bm.GAP)
    assert tiles['flutter-home', 'Linux-chromium-desktop'][2][:4] == bytes(red)

    out = tmp_path / 'out'
    bm.write(out, report, sheet, tiles)
    w, h, rows = decode_png((out / 'sheet.png').read_bytes())
    assert (w, h) == sheet[:2]
    first_tile = bytes(rows[bm.GAP])[bm.GAP * 4:bm.GAP * 4 + 4]
    assert first_tile == bytes(red)
    assert json.loads((out / 'report.json').read_text(encoding='utf-8')) == report
    page = (out / 'index.html').read_text(encoding='utf-8')
    assert 'tiles/flutter-home/macOS-webkit-iphone.png' in page and 'no screenshot' in page and 'reference' in page
    with pytest.raises(ValueError, match='empty directory'):
        bm.write(out, report, sheet, tiles)
    (tmp_path / 'empty').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'empty', target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic link'):
        bm.write(tmp_path / 'link', report, sheet, tiles)
    assert not any((tmp_path / 'empty').iterdir())


def test_reference_choice_and_input_errors(tmp_path):
    tree(tmp_path, {('p', 'macOS-webkit-desktop', 'width-384'): (24, 40, (0, 0, 0, 255))})
    shots = bm.find_shots(tmp_path)
    assert bm.build(shots, tile_w=16, tile_h=16, expected_envs=['Linux-chromium-desktop'])[0]['reference'] == 'macOS-webkit-desktop'
    with pytest.raises(ValueError, match='reference environment'):
        bm.build(shots, tile_w=16, tile_h=16, reference='Linux-chromium-desktop', expected_envs=['Linux-chromium-desktop'])
    for size in ((8, 16), (16, 2000), (16.0, 16)):
        with pytest.raises(ValueError, match='tile size'):
            bm.build(shots, tile_w=size[0], tile_h=size[1])
    # 8 px multiples are the default, not a rule: a device-sized tile and another gap work too.
    report, sheet, _ = bm.build(shots, tile_w=195, tile_h=422, gap=5)
    assert report['tile'] == {'width': 195, 'height': 422, 'gap': 5, 'fit': 'width, then crop or pad white'}
    assert sheet[:2] == (195 + 2 * 5, 422 + 2 * 5)
    assert bm.build(shots, tile_w=16, tile_h=16, gap=0)[1][:2] == (16, 16)
    for gap in (-1, 65, 8.0):
        with pytest.raises(ValueError, match='gap'):
            bm.build(shots, tile_w=16, tile_h=16, gap=gap)
    with pytest.raises(ValueError, match='no screenshots'):
        bm.build({})
    with pytest.raises(ValueError, match='plain file stem'):
        bm.find_shots(tmp_path, '../x')
    (tmp_path / 'again' / 'p' / 'macOS-webkit-desktop').mkdir(parents=True)
    (tmp_path / 'again' / 'p' / 'macOS-webkit-desktop' / 'width-384.png').write_bytes(png_browser_matrix(4, 4, (0, 0, 0, 255)))
    with pytest.raises(ValueError, match='two screenshots'):
        bm.find_shots(tmp_path)


def test_cli(tmp_path, capsys):
    tree(tmp_path / 'in', {('p', 'Linux-chromium-desktop', 'initial'): (64, 32, (10, 20, 30, 255))})
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'out'), '--shot', 'initial', '--tile', '32x32']) == 0
    assert json.loads(capsys.readouterr().out) == {'pages': 1, 'envs': 1, 'cells': 1, 'missing': 0,
                                                   'reference': 'Linux-chromium-desktop', 'out': str(tmp_path / 'out')}
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'o2'), '--tile', 'big']) == 2
    assert bm.main([str(tmp_path / 'in'), '--out', str(tmp_path / 'o3')]) == 2  # no width-384 shots
    assert 'no screenshots' in capsys.readouterr().err


def test_name_conventions_select_before_duplicate_detection(tmp_path):
    tree(tmp_path, {
        ('home', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('home', 'Windows-firefox-desktop', 'width-384'): (16, 16, (4, 5, 6, 255)),
        ('detail', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
    })
    duplicate = tmp_path / 'duplicate' / 'home' / 'Windows-firefox-desktop' / 'width-384.png'
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b'bad png, must not decode')
    result = bm.find_shots(tmp_path, pages=('home', 'detail'), environments=('Linux-*', '*-webkit-*'))
    assert list(result) == [('detail', 'Linux-chromium-desktop'), ('home', 'Linux-chromium-desktop')]
    assert bm.find_shots(tmp_path, pages=('HOME',)) == {}
    with pytest.raises(ValueError, match='two screenshots'):
        bm.find_shots(tmp_path)


def test_native_list_is_read_only_and_filtered_build_uses_same_selection(tmp_path, capsys):
    source, output = tmp_path / 'input', tmp_path / 'output'
    tree(source, {
        ('home', 'Linux-chromium-desktop', 'initial'): (16, 16, (1, 2, 3, 255)),
        ('home', 'macOS-webkit-iphone', 'initial'): (16, 16, (4, 5, 6, 255)),
    })
    args = [str(source), '--shot', 'initial', '--page', 'home', '--env', 'Linux-*']
    assert bm.main(args + ['--list']) == 0
    listing = json.loads(capsys.readouterr().out)['shots']
    assert [(r['page'], r['env']) for r in listing] == [('home', 'Linux-chromium-desktop')]
    assert not output.exists()
    assert bm.main(args + ['--out', str(output), '--tile', '16x16']) == 0
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert report['pages'] == ['home'] and report['envs'] == ['Linux-chromium-desktop']
    assert len(report['cells']) == len(listing)


def test_list_does_not_decode_candidate_pngs(tmp_path, capsys):
    path = tmp_path / 'home' / 'Linux-chromium-desktop' / 'width-384.png'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not png')
    assert bm.main([str(tmp_path), '--list']) == 0
    assert json.loads(capsys.readouterr().out)['shots'][0]['path'] == str(path)
    assert bm.main([str(tmp_path / 'missing'), '--list']) == 2
    assert 'directory' in capsys.readouterr().err


@pytest.mark.parametrize('options,error', [
    ({'pages': 'home'}, TypeError), ({'environments': ['']}, ValueError), ({'pages': [1]}, ValueError),
])
def test_bad_selection_rules(tmp_path, options, error):
    with pytest.raises(error):
        bm.find_shots(tmp_path, **options)


@pytest.mark.parametrize('options', [[], ['--list', '--out', 'unused']])
def test_list_and_output_cli_contract(tmp_path, options):
    with pytest.raises(SystemExit) as error:
        bm.main([str(tmp_path), *options])
    assert error.value.code == 2


def test_patterned_dpr_images_and_completely_missing_environment(tmp_path):
    # Replicate each source pixel into a 3x3 block: equal CSS content at DPR 1/3.
    w, h = 32, 64
    source = bytes(c for y in range(h) for x in range(w)
                   for c in ((255, 0, 0, 255) if (x // 4 + y // 4) % 2 else (0, 0, 255, 255)))
    large = b''.join(source[y*w*4+x*4:y*w*4+x*4+4] * 3
                     for y in range(h) for _ in range(3) for x in range(w))
    shots = {}
    for env, image in [('Linux-chromium-desktop', (w, h, source)),
                       ('macOS-webkit-iphone', (w*3, h*3, large))]:
        path = tmp_path / (env + '.png')
        path.write_bytes(bm.encode_png(*image))
        shots['p', env] = path
    report, sheet, tiles = bm.build(shots, tile_w=16, tile_h=32,
                                   expected_pages=['p', 'never-captured'],
                                   expected_envs=['Windows-firefox-desktop'])
    assert all(c['difference']['rgb_mae'] == c['difference']['rgb_rmse'] == 0 for c in report['cells'])
    assert all(c['fit']['cropped_rows'] == c['fit']['padded_rows'] == 0 for c in report['cells'])
    assert len(report['missing']) == 4  # includes an entirely absent page and environment
    out = tmp_path / 'empty'
    out.mkdir()
    bm.write(out, report, sheet, tiles)
    assert 'no screenshot' in (out / 'index.html').read_text()


@pytest.mark.parametrize('kind', ['file', 'dangling', 'nonempty', 'child-link'])
def test_output_protection_preserves_existing_targets(tmp_path, kind):
    out, target = tmp_path / 'out', tmp_path / 'target'
    target.mkdir()
    marker = target / 'keep'
    marker.write_bytes(b'unchanged')
    if kind == 'file':
        out.write_bytes(b'unchanged')
    elif kind == 'dangling':
        out.symlink_to(tmp_path / 'absent', target_is_directory=True)
    else:
        out.mkdir()
        if kind == 'nonempty':
            (out / 'keep').write_bytes(b'unchanged')
        else:
            (out / 'tiles').symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        bm.write(out, {}, (16, 16, bytes(16*16*4)), {})
    assert marker.read_bytes() == b'unchanged'
    assert list(target.iterdir()) == [marker]
    if kind == 'dangling':
        assert not (tmp_path / 'absent').exists()


def test_bad_library_cell_names_fail_before_any_output(tmp_path):
    with pytest.raises(ValueError, match='plain path'):
        bm.write(tmp_path / 'out', {}, (16, 16, bytes(16*16*4)), {('../escape', 'env'): None})
    assert not (tmp_path / 'out').exists()


def test_exclude_globs_drop_after_include_and_before_duplicate_detection(tmp_path, capsys):
    tree(tmp_path, {
        ('home', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('home', 'Windows-firefox-desktop', 'width-384'): (16, 16, (4, 5, 6, 255)),
        ('detail', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
    })
    duplicate = tmp_path / 'duplicate' / 'home' / 'Windows-firefox-desktop' / 'width-384.png'
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b'bad png, must not decode')
    result = bm.find_shots(tmp_path, exclude_environments=('Windows-*',))
    assert list(result) == [('detail', 'Linux-chromium-desktop'), ('home', 'Linux-chromium-desktop')]
    assert list(bm.find_shots(tmp_path, exclude_pages=('home',))) == [('detail', 'Linux-chromium-desktop')]
    assert bm.find_shots(tmp_path, pages=('detail',), exclude_pages=('d*',)) == {}
    with pytest.raises(TypeError, match='exclude_pages and exclude_environments'):
        bm.find_shots(tmp_path, exclude_pages='home')
    with pytest.raises(TypeError, match='exclude_pages and exclude_environments'):
        bm.find_shots(tmp_path, exclude_environments='Windows-*')
    with pytest.raises(ValueError, match='exclude_pages/exclude_environments'):
        bm.find_shots(tmp_path, exclude_environments=('',))
    with pytest.raises(ValueError, match='exclude_pages/exclude_environments'):
        bm.find_shots(tmp_path, exclude_pages=('',))
    assert bm.main([str(tmp_path), '--list', '--exclude-env', 'Windows-*', '--exclude-page', 'detail']) == 0
    assert [row['page'] for row in json.loads(capsys.readouterr().out)['shots']] == ['home']


def test_exclude_globs_match_whole_names_not_substrings(tmp_path):
    tree(tmp_path, {
        ('home', 'Linux-chromium', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('home', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('homepage', 'Linux-chromium', 'width-384'): (16, 16, (1, 2, 3, 255)),
        ('homepage', 'Linux-chromium-desktop', 'width-384'): (16, 16, (1, 2, 3, 255)),
    })
    assert list(bm.find_shots(tmp_path, exclude_pages=('home',))) == [
        ('homepage', 'Linux-chromium'), ('homepage', 'Linux-chromium-desktop')]
    assert list(bm.find_shots(tmp_path, exclude_environments=('Linux-chromium',))) == [
        ('home', 'Linux-chromium-desktop'), ('homepage', 'Linux-chromium-desktop')]


# ═══ · flow export ═══════════════════════════════════════════════════════════════════════════════════════
# Contract reuse, failure behavior and transport identity for flow exports.

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


def test_shared_raster_png_byte_limit_is_inclusive(monkeypatch):
    import struct
    monkeypatch.setattr(image_studio.shutil,'which',lambda _: '/fake/node')
    monkeypatch.setattr(image_studio,'_find_chrome',lambda _: '/fake/chrome')
    prefix=b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',100,100)
    limit=32*1024*1024
    payload=prefix+b'\0'*(limit-len(prefix))
    monkeypatch.setattr(image_studio.subprocess,'run',lambda *a,**k: SimpleNamespace(returncode=0,stdout=payload))
    assert len(image_studio.raster_svg(b'<svg width="100" height="100"/>'))==limit
    payload+=b'x'
    with pytest.raises(ValueError,match='32MiB'):
        image_studio.raster_svg(b'<svg width="100" height="100"/>')


# ═══ · flow workspace ════════════════════════════════════════════════════════════════════════════════════
# Canonical JSON edits, source retention and regeneration transactions.

RAW = (ROOT / 'examples/flow.json').read_bytes()
PATCH = [{'path': '/steps/0/title', 'value': '編集済み & <text>'},
         {'path': '/steps/1/note', 'value': '再描画'}]


def cli(*args):
    return subprocess.run([sys.executable, '-S', str(ROOT/'flow_workspace.py'), *map(str,args)],
                          capture_output=True, timeout=20)


def test_original_bytes_roundtrip_and_detached_state():
    raw = ('  ' + RAW.decode() + '\n\n').encode()
    state = w.import_flow(raw)
    before = copy.deepcopy(state)
    updated = w.patch_workspace(state, PATCH)
    assert state == before
    assert updated['original_json'].encode() == raw
    assert updated['spec']['steps'][0]['title'] == PATCH[0]['value']
    assert w.read_workspace(w.workspace_bytes(updated)) == updated
    updated['spec']['steps'][0]['note'] = 'aliased?'
    assert state == before
    # Missing fields are preserved in the original, while defaults are explicit in the working spec.
    minimal = b'{"title":"A","sources":[{"title":"B"}],"steps":[{"title":"C"}]}'
    assert w.import_flow(minimal)['original_json'].encode() == minimal
    assert w.import_flow(minimal)['spec']['steps'][0]['note'] == ''


@pytest.mark.parametrize('ops', [
    [{'path':'/title','value':'new'}, {'path':'/steps/99/title','value':'bad'}],
    [{'path':'/steps/01/title','value':'bad'}],
    [{'path':'/sources/0/url','value':'bad'}],
    [{'path':'/steps/0/note','value':None}],
    [{'path':'/steps/0/title','value':'\n'}],
    [{'path':'/steps/0/title','value':''}],
    [{'path':'/title','value':'a'*121}],
    [{'path':'/title','value':'ok','extra':0}],
    [{'path':'/title','value':'ok'}]*65,
    {}, None,
])
def test_invalid_batch_is_atomic(ops):
    state = w.import_flow(RAW); before = w.workspace_bytes(state)
    with pytest.raises(ValueError): w.patch_workspace(state, ops)
    assert w.workspace_bytes(state) == before


def test_patch_child_utf8_preserves_non_ascii_labels():
    """The isolated ascii_artist flow-patch child uses -I -S; -X utf8 keeps stdout UTF-8 on Windows."""
    state = w.import_flow(RAW)
    value = '日本語ラベル & <text>'
    updated = w.patch_workspace(state, [{'path': '/steps/0/title', 'value': value}])
    assert updated['spec']['steps'][0]['title'] == value
    assert '統合フロー' in state['original_json']


def test_empty_and_maximum_batch():
    state = w.import_flow(RAW)
    assert w.patch_workspace(state, []) == state
    ops = [{'path':'/title','value':str(n)} for n in range(64)]
    assert w.patch_workspace(state, ops)['spec']['title'] == '63'


def test_patch_then_regenerate_reuses_existing_renderer_and_failure_is_atomic(monkeypatch):
    state = w.import_flow(RAW); before = w.workspace_bytes(state)
    updated, markdown = w.patch_and_render(state, PATCH, 'mermaid')
    assert markdown == render_flow(updated['spec'], 'mermaid')
    assert markdown != render_flow(state['spec'], 'mermaid')
    assert b'&lt;' not in markdown and b'#lt;' in markdown
    def fail(*args, **kwargs): raise RuntimeError('renderer failed')
    monkeypatch.setattr(w, 'render_flow', fail)
    with pytest.raises(RuntimeError, match='renderer failed'):
        w.patch_and_render(state, PATCH)
    assert w.workspace_bytes(state) == before


def test_cli_persistence_and_failed_operations_never_replace_files(tmp_path):
    source = tmp_path/'source.json'; source.write_bytes(RAW)
    state = tmp_path/'work.json'; patch = tmp_path/'patch.json'
    assert cli('import',source,'-o',state).returncode == 0
    original = state.read_bytes()
    patch.write_text(json.dumps(PATCH))
    assert cli('patch',state,patch,'-o',state,'--force').returncode == 0
    edited = state.read_bytes(); assert edited != original
    assert cli('original',state).stdout == RAW
    assert json.loads(cli('spec',state).stdout)['steps'][0]['title'] == PATCH[0]['value']
    output = tmp_path/'flow.md'
    assert cli('render',state,'--format','mermaid','-o',output).returncode == 0
    assert output.read_bytes() == w.render_workspace(w.read_workspace(edited),'mermaid')
    patch.write_text('[{"path":"/title","value":"new"},{"path":"/steps/99/title","value":"bad"}]')
    result = cli('patch',state,patch,'-o',state,'--force')
    assert result.returncode == 2 and result.stdout == b'' and state.read_bytes() == edited
    output.write_bytes(b'keep')
    result = cli('render',state,'--format','png','--mmdc','/missing/mmdc','-o',output,'--force')
    assert result.returncode == 2 and output.read_bytes() == b'keep'
    patch.write_bytes(b'\xff')
    assert cli('patch',state,patch,'-o',state,'--force').returncode == 2
    assert state.read_bytes() == edited


@pytest.mark.parametrize('raw', [b'\xff', b' '* (w.MAX_WORKSPACE+1), b'{}', b'null',
    b'{"schema":"ironmate-flow/2","original_json":"{}","spec":{}}'],
    ids=["malformed_utf8", "oversize", "missing_keys", "null", "wrong_schema"])
def test_invalid_workspace(raw):
    with pytest.raises(ValueError): w.read_workspace(raw)


def test_python_node_workspace_api(tmp_path):
    state = w.import_flow(RAW)
    expected = w.patch_workspace(state, PATCH)
    script = '''const w=require(process.argv[1]);const v=JSON.parse(process.argv[2]);
const original=JSON.stringify(v);const imported=w.importFlow(v.original_json,{python:process.argv[3]});
const next=w.patchWorkspace(imported,JSON.parse(process.argv[4]),{python:process.argv[3]});
if(JSON.stringify(v)!==original)throw Error('mutated');
const image=w.renderWorkspace(next,{format:'mermaid',python:process.argv[3]});
process.stdout.write(JSON.stringify({workspace:next,image:image.toString('utf8')}));'''
    result = subprocess.run(['node','-e',script,str(ROOT/'flow_workspace.cjs'),json.dumps(state),
                             sys.executable,json.dumps(PATCH)],cwd=tmp_path,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert actual['workspace'] == expected
    assert actual['image'].encode() == w.render_workspace(expected,'mermaid')
    invalid_script = '''const w=require(process.argv[1]);const v=JSON.parse(process.argv[2]);
const before=JSON.stringify(v);try{w.patchWorkspace(v,[{path:'/title',value:'new'},
{path:'/steps/99/title',value:'bad'}],{python:process.argv[3]});process.exit(1)}
catch(e){if(JSON.stringify(v)!==before)process.exit(1)}'''
    result=subprocess.run(['node','-e',invalid_script,str(ROOT/'flow_workspace.cjs'),json.dumps(state),sys.executable],
                          capture_output=True,timeout=20)
    assert result.returncode == 0,result.stderr


def test_vendor_runtime_is_one_merged_commit_and_license_is_exact():
    """The flow contract, its patch CLI and the sample come from one merged ascii_artist commit; web-ui no longer has flow code."""
    import hashlib
    lock=json.loads((ROOT/'vendor.lock.json').read_text())
    assert not [x for x in lock['files'] if x['repository'].endswith('/PySaiyanWeBoo')]
    flow={x['destination']: x for x in lock['files'] if x['repository'].endswith('/ascii_artist')}
    assert {flow[d]['commit'] for d in ('vendor/ascii_artist.py','examples/flow.json')} == {'001de63c23396e3ea6333867a169df2c60a50244'}
    assert flow['examples/flow.json']['source'] == 'examples/pr-flow.json' and 'vendor/ascii_artist-LICENSE' in flow
    for entry in flow.values():
        data=(ROOT/entry['destination']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == entry['blob_sha']


@pytest.mark.parametrize('path,value,accepted', [
    ('/steps/0/note',None,False), ('/sources_label',None,False),
    ('/steps/0/title','😀'*120,True), ('/steps/0/title','😀'*121,False),
    ('/sources/0/note','😀'*240,True), ('/sources/0/note','😀'*241,False),
    ('/steps/0/title','\ufeff',True), ('/steps/0/title','\x85',False),
    ('/steps/0/title','\ud800',False),
], ids=['null_note','null_sources_label','title_120_emoji','title_121_emoji',
        'note_240_emoji','note_241_emoji','feff_label','blank_nel','lone_surrogate'])
def test_patch_boundaries(path,value,accepted):
    state=w.import_flow(RAW); before=w.workspace_bytes(state)
    operations=[{'path':'/title','value':'first valid edit'}, {'path':path,'value':value}]
    if accepted:
        assert w.patch_workspace(state,operations)['spec']['title'] == 'first valid edit'
    else:
        with pytest.raises(ValueError): w.patch_workspace(state,operations)
    assert w.workspace_bytes(state)==before


if __name__ == "__main__":
    unittest.main()
