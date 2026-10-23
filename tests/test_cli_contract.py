"""Real process runs for the shared CLI contract.

Each case starts the tool the way a person or another program would, and checks
the exit status, help text, and stderr. Success payloads stay in their existing
shape. Fixable failures exit 2, name a next step, and do not print a traceback.
"""
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(argv, *, stdin=None, timeout=30):
    return subprocess.run(
        argv, cwd=ROOT, input=stdin, capture_output=True, timeout=timeout, check=False,
    )


def test_help_exits_zero_and_names_json():
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    commands = [
        [PY, '-S', 'pixel_grid.py', '--help'],
        [PY, '-S', 'photo_grid.py', '--help'],
        [PY, '-m', 'grid_tools', '--help'],
        [PY, '-m', 'grid_tools', 'make', '--help'],
        [PY, '-S', 'image_digest.py', '--help'],
        [PY, '-S', 'browser_matrix.py', '--help'],
        [PY, '-S', 'image_compare.py', '--help'],
        [PY, '-S', 'pptx_pipeline.py', '--help'],
        [PY, '-S', 'pptx_inspect.py', '--help'],
        [PY, '-S', 'ironmate_image.py', '--help'],
        [PY, '-S', 'ironmate_tests.py', '--help'],
        [PY, '-S', 'studio_ingress.py', '--help'],
        [PY, '-S', 'image_studio.py', '--help'],
        [PY, '-S', 'image_compare.py', '-h'],
        ['node', 'image_digest.cjs', '--help'],
        ['node', 'studio/render.cjs', '--help'],
        ['node', 'studio/raster.cjs', '--help'],
        ['node', 'studio/ingress.cjs', '--help'],
    ]
    for argv in commands:
        completed = run(argv)
        assert completed.returncode == 0, (argv, completed.stderr.decode())
        assert b'Traceback' not in completed.stderr
        text = completed.stdout.decode()
        assert '--help' in text or 'usage' in text.lower()


def test_fixable_failures_exit_2_without_a_traceback():
    missing = ROOT / 'no-such-ironmate.pptx'
    cases = [
        ([PY, '-S', 'pptx_inspect.py', str(missing)], b'pptx_inspect.py:'),
        ([PY, '-S', 'pptx_inspect.py', '--json', str(missing)], b'"ok": false'),
        ([PY, '-S', 'pptx_replace.py', str(missing)], b'pptx_replace.py:'),
        ([PY, '-S', 'xlsx_csv.py', '-o', 'out.xlsx', 'missing.csv'], b'xlsx_csv.py:'),
        ([PY, '-S', 'pptx_pipeline.py'], b'provide exactly one'),
        ([PY, '-S', 'pptx_pipeline.py', '--json'], b'"exit": 2'),
        ([PY, '-S', 'pixel_grid.py', '--json', '--format', 'png'], b'--json'),
        ([PY, '-m', 'grid_tools', 'make', 'cloud', '--json', '--to', 'png'], b'--json'),
        ([PY, '-S', 'studio_ingress.py', 'decode', str(missing)], b'studio_ingress.py:'),
    ]
    for argv, needle in cases:
        completed = run(argv)
        assert completed.returncode == 2, (argv, completed.returncode, completed.stderr)
        assert needle in completed.stderr, (argv, completed.stderr)
        assert b'Traceback' not in completed.stderr
        assert b'hint:' in completed.stderr or b'"hint"' in completed.stderr


def test_pixel_and_grid_json_are_real_grids():
    made = run([PY, '-S', 'pixel_grid.py', '--mask', 'cloud', '--size', '16', '--json'])
    assert made.returncode == 0, made.stderr
    grid = json.loads(made.stdout)
    assert grid['schema'] == 'ironmate-pixel-grid/1' and grid['width'] == 16
    via_module = run([PY, '-m', 'grid_tools', 'make', 'circle', '--json', '--size', '16'])
    assert via_module.returncode == 0, via_module.stderr
    assert json.loads(via_module.stdout)['mask'] == 'circle'
    after = run([PY, '-m', 'grid_tools', '--json', 'make', 'rock', '--size', '16'])
    assert after.returncode == 0, after.stderr
    assert json.loads(after.stdout)['mask'] == 'rock'


def test_image_tools_share_output_flags_and_node_digest(tmp_path):
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    from browser_matrix import encode_png
    shot = tmp_path / 'page' / 'Linux-chromium-desktop' / 'initial.png'
    shot.parent.mkdir(parents=True)
    shot.write_bytes(encode_png(8, 8, bytes((10, 20, 30, 255)) * 64))
    listed = run([PY, '-S', 'browser_matrix.py', str(tmp_path), '--list', '--shot', 'initial'])
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)['shots'][0]['page'] == 'page'
    out = tmp_path / 'matrix'
    built = run([PY, '-S', 'browser_matrix.py', str(tmp_path), '-o', str(out), '--shot', 'initial', '--tile', '16x16'])
    assert built.returncode == 0, built.stderr
    assert (out / 'report.json').is_file()
    assert b'"pages": 1' in built.stdout

    base = tmp_path / 'digest-in'
    base.mkdir()
    (base / 'a.png').write_bytes(shot.read_bytes())
    spec = {
        'schema': 'ironmate-image-digest-input/1', 'title': 'CLI',
        'rows': ['home'], 'cols': ['chromium'],
        'cells': [{'row': 'home', 'col': 'chromium', 'image': 'a.png', 'status': 'pass'}],
    }
    spec_path = base / 'input.json'
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    digest_out = tmp_path / 'digest'
    py = run([PY, '-S', 'image_digest.py', str(spec_path), '--output', str(digest_out)])
    assert py.returncode == 0, py.stderr
    info = json.loads(py.stdout)
    assert info['passed'] == 1 and (digest_out / 'digest.html').is_file()
    node_out = tmp_path / 'digest-node'
    node = run(['node', 'image_digest.cjs', str(spec_path), '--out', str(node_out), '--tile', '32x64'])
    assert node.returncode == 0, node.stderr
    assert json.loads(node.stdout)['tile'] == [32, 64]
    legacy = run(['node', 'image_digest.cjs', str(spec_path), str(tmp_path / 'legacy')])
    assert legacy.returncode == 0, legacy.stderr
    missing = run(['node', 'image_digest.cjs', '--json'])
    assert missing.returncode == 2 and b'"ok":false' in missing.stderr
    assert b'Traceback' not in missing.stderr


def test_ironmate_image_and_ingress_round_trip(tmp_path):
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    png = tmp_path / 'cloud.png'
    made = run([PY, '-S', 'pixel_grid.py', '--mask', 'cloud', '--size', '16', '--format', 'png', '-o', str(png)])
    assert made.returncode == 0, made.stderr
    loaded = run([PY, '-S', 'ironmate_image.py', 'load', str(png)])
    assert loaded.returncode == 0, loaded.stderr
    art = json.loads(loaded.stdout)
    assert art['width'] == 16 and art['schema'] == 'ironmate-pixel-grid/1'
    resized = run([PY, '-S', 'ironmate_image.py', 'resize', str(png), '32'])
    assert resized.returncode == 0, resized.stderr
    assert json.loads(resized.stdout)['width'] == 32
    text = run([PY, '-S', 'ironmate_image.py', 'to-base64', str(png)])
    assert text.returncode == 0 and text.stdout.strip()
    back = run([PY, '-S', 'ironmate_image.py', 'from-base64', '-'], stdin=text.stdout)
    assert back.returncode == 0, back.stderr
    assert json.loads(back.stdout)['width'] == 16
    refused = run([PY, '-S', 'ironmate_image.py', '--json', 'load', str(tmp_path / 'missing.png')])
    assert refused.returncode == 2 and b'"hint"' in refused.stderr

    raw = b'\x89PNG\r\n\x1a\npayload'
    encoded = tmp_path / 'clip.txt'
    encoded.write_text(__import__('base64').b64encode(raw).decode(), encoding='ascii')
    decoded = run([PY, '-S', 'studio_ingress.py', 'decode', str(encoded)])
    assert decoded.returncode == 0, decoded.stderr
    body = json.loads(decoded.stdout)
    assert body == {'ok': True, 'mime': 'image/png', 'bytes': len(raw)}
    node = run(['node', 'studio/ingress.cjs', 'decode', str(encoded)])
    assert node.returncode == 0, node.stderr
    assert json.loads(node.stdout)['bytes'] == len(raw)
    bad = run(['node', 'studio/ingress.cjs', '--json', 'decode', str(tmp_path / 'nope.txt')])
    assert bad.returncode == 2 and b'"ok":false' in bad.stderr


def test_render_does_not_wait_on_a_terminal_and_validates_a_file(tmp_path):
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    node = shutil.which('node')
    master, slave = pty.openpty()
    proc = subprocess.Popen([node, 'studio/render.cjs'], cwd=ROOT, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    chunks = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunks.append(os.read(master, 4096))
            except OSError:
                break
        if proc.poll() is not None and not ready:
            break
    else:
        proc.kill()
    proc.wait(timeout=5)
    os.close(master)
    chunk = b''.join(chunks)
    assert proc.returncode == 2
    assert b'stdin is a terminal' in chunk and b'hint:' in chunk and b'Traceback' not in chunk

    empty = run(['node', 'studio/render.cjs'], stdin=b'')
    assert empty.returncode == 2 and b'scene JSON' in empty.stderr
    scene = {
        'scene': {
            'schema': 'ironmate-image-studio/1', 'width': 64, 'height': 64,
            'background': 'none', 'layers': [],
        },
        'mode': 'validate',
    }
    path = tmp_path / 'scene.json'
    path.write_text(json.dumps(scene), encoding='utf-8')
    checked = run(['node', 'studio/render.cjs', str(path)])
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['schema'] == 'ironmate-image-studio/1'
    drawn = run(['node', 'studio/render.cjs'], stdin=json.dumps({**scene, 'mode': 'svg'}).encode())
    assert drawn.returncode == 0, drawn.stderr
    assert drawn.stdout.startswith(b'<svg')


def test_raster_rejects_a_bad_argument_list_before_chrome():
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    missing = run(['node', 'studio/raster.cjs'])
    assert missing.returncode == 2 and b'CHROME' in missing.stderr and b'Traceback' not in missing.stderr
    bad = run(['node', 'studio/raster.cjs', 'chrome', 'page.html', 'profile', 'nope', '10'])
    assert bad.returncode == 2 and b'positive integers' in bad.stderr


def test_test_catalog_lists_pytest_and_runs_ingress():
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    listed = run([PY, '-S', 'ironmate_tests.py', 'list'])
    assert listed.returncode == 0, listed.stderr
    catalog = json.loads(listed.stdout)
    assert catalog['ok'] is True
    assert catalog['python']['pytest'][1:3] == ['-m', 'pytest']
    assert 'not heavy and not network' in catalog['python']['pytest']
    assert catalog['python']['locked'][:4] == ['uv', 'run', '--locked', 'python']
    assert any(entry['id'] == 'studio-ingress' and entry['needs'] == [] for entry in catalog['node'])
    text = run([PY, '-S', 'ironmate_tests.py', 'list', '--text'])
    assert text.returncode == 0 and b'pytest' in text.stdout and b'studio-ingress' not in text.stdout
    assert b'node --test tests/studio_ingress.test.cjs' in text.stdout
    ran = run([PY, '-S', 'ironmate_tests.py', 'run', 'studio-ingress'], timeout=60)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    blocked = run([PY, '-S', 'ironmate_tests.py', 'run', 'image-digest'])
    assert blocked.returncode == 2 and b'DIGEST_PNG' in blocked.stderr
    unknown = run([PY, '-S', 'ironmate_tests.py', 'run', 'no-such-id'])
    assert unknown.returncode == 2 and b'unknown test id' in unknown.stderr
