# test_image_digest.py
# __all__: 0
"""image_digest: any rows x cols of images with a status -> one small self-contained page."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import image_digest as digest
from browser_matrix import encode_png

__all__ = []

ROOT = Path(__file__).resolve().parents[1]


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
