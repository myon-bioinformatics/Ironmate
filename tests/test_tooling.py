"""🧰 Tooling: apt setup, .d.cts declarations, the CLI contract, known-vulnerability checks, parent tools and pins, repository hygiene and the vendored files."""

import hashlib
import importlib.util
import json
import os
import pty
import py_compile
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
from scripts.configure_ci_apt import APT_CONFIG, ARCHIVES_CONFIG, CONFIG_NAME, configure, finish, main, prefer_existing_archive
from vendor import ascii_artist, markdown, nvd_nist_known_vulns as nvd, xprobe


# ═══ · ci apt setup ══════════════════════════════════════════════════════════════════════════════════════
# Offline contracts for bounded setup; no package or browser install is run.

READ_LIST = "grep -v '^#' {} | xargs echo"


def package_list(name):
    """Package names exactly as the workflow's grep reads them (whole-line # comments only)."""
    lines = (ROOT / "scripts" / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]
STOCK = ("http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\n"
         "https://archive.ubuntu.com/ubuntu/\tpriority:2\n"
         "https://security.ubuntu.com/ubuntu/\tpriority:3\n")


def test_only_existing_official_archive_priority_changes():
    original = "# runner mirrors\n\n" + STOCK
    expected = original.replace("priority:2", "priority:0")
    assert prefer_existing_archive(original) == expected
    assert prefer_existing_archive(expected) == expected


@pytest.mark.parametrize("text", [
    "", STOCK.replace("https://archive.", "http://archive."),
    STOCK.replace("\t", " "), STOCK.replace("https://archive.", " https://archive."),
    " \n" + STOCK, " # not an APT comment\n" + STOCK,
    STOCK.replace("\n", "\r"), STOCK.replace("\n", "\r\n"), STOCK.replace("\n", "\v"),
    STOCK + "https://custom.example/ubuntu/\tpriority:0\n",
    STOCK.replace("priority:2", "priority:2 arch:amd64"),
    STOCK.replace("priority:1", "priority:4"),
    STOCK.replace("https://security.ubuntu.com/ubuntu/\tpriority:3\n", ""),
    STOCK + STOCK.splitlines(keepends=True)[0],
])
def test_unknown_mirror_policies_are_untouched(text):
    assert prefer_existing_archive(text) == text


@pytest.mark.parametrize("mirrors", [
    None, STOCK, "https://custom.example/ubuntu/\n",
    STOCK.replace("\n", "\r"), STOCK.replace("\n", "\r\n"),
])
def test_configure_preserves_sources_keys_and_other_configuration(tmp_path, mirrors):
    (tmp_path / "apt.conf.d").mkdir()
    untouched = {
        "sources.list": "deb [signed-by=/keyring.gpg] https://example.test stable main\n",
        "trusted.gpg": "unchanged key fixture",
        "apt.conf.d/zz-retries": 'Acquire::Retries "3";\n',
    }
    for name, content in untouched.items():
        (tmp_path / name).write_text(content)
    if mirrors is not None:
        (tmp_path / "apt-mirrors.txt").write_bytes(mirrors.encode("utf-8"))
    configure(tmp_path)
    assert (tmp_path / "apt.conf.d" / CONFIG_NAME).read_text() == APT_CONFIG
    assert CONFIG_NAME > "zz-retries"
    for name, content in untouched.items():
        assert (tmp_path / name).read_text() == content
    if mirrors is None:
        assert not (tmp_path / "apt-mirrors.txt").exists()
    else:
        assert (tmp_path / "apt-mirrors.txt").read_bytes() == prefer_existing_archive(mirrors).encode("utf-8")


def test_configuration_failures_propagate(tmp_path):
    with pytest.raises(FileNotFoundError):
        configure(tmp_path)  # No apt.conf.d: do not pretend configuration succeeded.


def test_acquire_and_update_settings_are_bounded_and_fail_closed():
    assert APT_CONFIG.splitlines() == [
        'Acquire::Retries "1";',
        'Acquire::http::Timeout "15";',
        'Acquire::https::Timeout "15";',
        'APT::Update::Error-Mode "any";',
    ]


def test_workflow_keeps_coverage_budgets_and_setup_failure_visibility():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    setup_runs = []
    for job_id, budget, install_name, setup_budget in [
        ("marp-integration", 15, "Install Japanese fonts for diagram evidence", 5),
        ("studio-clipboard", 25, "Install isolated test-only Playwright and browser", 10),
    ]:
        job = jobs[job_id]
        assert job["timeout-minutes"] == budget
        steps = job["steps"]
        setup_index = next(i for i, s in enumerate(steps) if s.get("name") == "Bound apt dependency setup")
        install_index = next(i for i, s in enumerate(steps) if s.get("name") == install_name)
        assert setup_index < install_index
        assert steps[install_index]["timeout-minutes"] == setup_budget
        setup_runs.append(steps[setup_index]["run"])
        assert all(not step.get("continue-on-error", False) for step in steps)
    assert setup_runs[0] == setup_runs[1]
    assert "sudo python3 -S scripts/configure_ci_apt.py" in setup_runs[0]
    assert "sudo apt-config dump" in setup_runs[0]
    marp_steps = jobs["marp-integration"]["steps"]
    fonts = next(s for s in marp_steps if s.get("name") == "Install Japanese fonts for diagram evidence")
    # shell: bash adds pipefail, so a missing or empty list fails the step instead of installing nothing.
    assert fonts["shell"] == "bash"
    assert "scripts/apt-ci-fonts.txt" in fonts["run"] and "--no-install-recommends" in fonts["run"]
    assert package_list("apt-ci-fonts.txt") == ["fonts-noto-cjk"]
    # LibreOffice (for UNO) is a test-lane dependency only: minimal apt set, bounded, after the apt setup.
    uno_index = next(i for i, s in enumerate(marp_steps) if s.get("name") == "Install minimal LibreOffice for the UNO check")
    uno_install = marp_steps[uno_index]
    assert uno_index > next(i for i, s in enumerate(marp_steps) if s.get("name") == "Bound apt dependency setup")
    assert uno_install["timeout-minutes"] == 5
    assert uno_install["shell"] == "bash"
    assert "--no-install-recommends" in uno_install["run"] and "scripts/apt-ci-uno.txt" in uno_install["run"]
    assert package_list("apt-ci-uno.txt") == ["python3-uno", "libreoffice-impress"]
    assert any(s.get("env", {}).get("IRONMATE_RUN_UNO_INTEGRATION") == "1"
               and "tests/test_uno_roundtrip.py" in s.get("run", "") for s in marp_steps)
    assert any(s.get("env", {}).get("IRONMATE_FLOW_REQUIRE_CJK") == "1" for s in marp_steps)
    clipboard = jobs["studio-clipboard"]
    assert clipboard["strategy"]["matrix"]["browser"] == ["chromium", "firefox", "webkit"]
    assert clipboard["strategy"]["fail-fast"] is False
    assert any("install --with-deps ${{ matrix.browser }}" in s.get("run", "")
               for s in clipboard["steps"])


def run_list_reader(path):
    """Run the workflow's list reader under bash's -eo pipefail, with echo instead of apt-get."""
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", READ_LIST.format(path)],
                          capture_output=True, text=True)


@pytest.mark.parametrize("name", ["apt-ci-fonts.txt", "apt-ci-uno.txt"])
def test_list_reader_passes_exactly_the_listed_packages(name):
    result = run_list_reader(ROOT / "scripts" / name)
    assert result.returncode == 0
    assert result.stdout.split() == package_list(name)


@pytest.mark.parametrize("content", [None, "", "# only a comment\n", "# a\n# b\n"])
def test_missing_or_empty_list_fails_instead_of_installing_nothing(tmp_path, content):
    path = tmp_path / "list.txt"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert run_list_reader(path).returncode != 0


def test_archives_option_points_apt_at_the_cache_directory_and_records_what_was_restored(tmp_path):
    (tmp_path / "etc" / "apt.conf.d").mkdir(parents=True)
    archives = tmp_path / "apt-archives"
    archives.mkdir()
    (archives / "b_1_amd64.deb").write_bytes(b"b")
    (archives / "a_1_amd64.deb").write_bytes(b"a")
    configure(tmp_path / "etc", archives)
    config = (tmp_path / "etc" / "apt.conf.d" / CONFIG_NAME).read_text()
    assert config == APT_CONFIG + ARCHIVES_CONFIG.format(archives.resolve())
    assert (archives / "partial").is_dir()
    assert (tmp_path / "apt-archives.restored").read_text() == "a_1_amd64.deb\nb_1_amd64.deb\n"


@pytest.mark.parametrize("added, expected", [(False, False), (True, True)])
def test_finish_cleans_up_and_reports_only_a_changed_deb_set(tmp_path, added, expected):
    (tmp_path / "etc" / "apt.conf.d").mkdir(parents=True)
    archives = tmp_path / "apt-archives"
    archives.mkdir()
    (archives / "a_1_amd64.deb").write_bytes(b"a")
    configure(tmp_path / "etc", archives)
    (archives / "lock").write_text("")
    (archives / "partial" / "half.deb").write_bytes(b"")
    if added:
        (archives / "b_1_amd64.deb").write_bytes(b"b")
    calls = []
    assert finish(archives, run=lambda cmd, **kw: calls.append((cmd, kw))) is expected
    assert calls == [(["apt-get", "autoclean", "-qq"], {"check": True, "timeout": 120})]
    assert sorted(p.name for p in archives.iterdir()) == ["a_1_amd64.deb"] + (["b_1_amd64.deb"] if added else [])


def test_finish_without_a_restore_record_reports_a_change(tmp_path):
    archives = tmp_path / "apt-archives"
    archives.mkdir()
    assert finish(archives, run=lambda cmd, **kw: None) is True


def test_cli_rejects_unknown_arguments():
    with pytest.raises(SystemExit) as error:
        main(["--archives"])
    assert "usage" in str(error.value)


def test_workflow_restores_apt_downloads_everywhere_but_saves_them_only_from_main():
    jobs = yaml.safe_load((ROOT / ".github/workflows/mcp-tests.yml").read_text())["jobs"]
    for job_id in ("marp-integration", "studio-clipboard"):
        steps = jobs[job_id]["steps"]
        names = [s.get("name") for s in steps]
        restore = steps[names.index("Restore apt downloads (written only by main)")]
        setup = names.index("Bound apt dependency setup")
        finish_step = steps[names.index("Make apt downloads cacheable (main only)")]
        save = steps[names.index("Save apt downloads (main only, when they changed)")]
        assert names.index("Restore apt downloads (written only by main)") < setup < names.index(finish_step["name"])
        assert restore["uses"].startswith("actions/cache/restore@") and "if" not in restore
        assert '--archives "$RUNNER_TEMP/apt-archives"' in steps[setup]["run"]
        assert finish_step["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
        assert '--finish "$RUNNER_TEMP/apt-archives" | tee -a "$GITHUB_OUTPUT"' in finish_step["run"]
        assert finish_step["shell"] == "bash"  # pipefail, so tee cannot hide a failure
        assert save["uses"].startswith("actions/cache/save@")
        assert save["if"] == "steps.apt_cache.outputs.changed == 'true'"
        assert save["with"]["key"] == restore["with"]["key"]
        assert restore["with"]["key"].startswith(restore["with"]["restore-keys"])


# ═══ · cjs declarations ══════════════════════════════════════════════════════════════════════════════════
# Every Node API (*.cjs that exports something) has a .d.cts declaring exactly its exports.
#
# Names only; CI type-checks the declarations themselves with tsc. CLI-only scripts
# (studio/raster.cjs, studio/render.cjs) run on load and export nothing, so they are
# never required here and must not have a declaration.

ALL = sorted(p for p in [*ROOT.glob("*.cjs"), *ROOT.glob("studio/*.cjs"), *ROOT.glob("scripts/*.cjs")])
MODULES = [p for p in ALL if "module.exports" in p.read_text(encoding="utf-8")]
SCRIPTS = [p for p in ALL if p not in MODULES]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_declarations_match_exports():
    script = "process.stdout.write(JSON.stringify(process.argv.slice(1).map(f => Object.keys(require(f)))))"
    exports = json.loads(subprocess.run(["node", "-e", script, *map(str, MODULES)], capture_output=True, text=True,
                                        timeout=60, check=True).stdout)
    for script_path in SCRIPTS:
        assert not script_path.with_suffix(".d.cts").exists(), f"{script_path.name} is a CLI script"
    checked = 0
    for module, names in zip(MODULES, exports):
        types = module.with_suffix(".d.cts")
        assert types.exists(), f"{module.relative_to(ROOT)} exports {names} but has no {types.name}"
        declared = set(re.findall(r"^export (?:function|const) (\w+)", types.read_text(encoding="utf-8"), re.M))
        assert declared == set(names), module.name
        checked += 1
    assert checked >= 4


# ═══ · cli contract ══════════════════════════════════════════════════════════════════════════════════════
# Real process runs for the shared CLI contract.
#
# Each case starts the tool the way a person or another program would, and checks
# the exit status, help text, and stderr. Success payloads stay in their existing
# shape. Fixable failures exit 2, name a next step, and do not print a traceback.

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


# ═══ · nvd nist known vulns ══════════════════════════════════════════════════════════════════════════════
# Smoke-check the retained upstream NVD consumer without network access.

def test_nvd_consumer_reads_completion_record():
    row = {"schema": nvd.SCHEMA_VERSION, "kind": "query_complete",
           "query": {"cpe_name": "cpe:2.3:a:example:example:1:*:*:*:*:*:*:*"}, "cve_count": 0}
    assert nvd.parse_jsonl(json.dumps(row)) == [row]


def test_upstream_fixture_remains_consumable():
    from pathlib import Path
    rows = nvd.read_jsonl(Path(__file__).parent / "fixtures/nvd_summary.jsonl")
    assert rows[-1]["kind"] == "query_complete"


# ═══ · parent tools ══════════════════════════════════════════════════════════════════════════════════════
# Offline compatibility of canonical parent tools with adjacent vendored GHI.

__all__ = []

import hashlib, json, subprocess, sys
VENDOR = ROOT / "vendor"


def test_parent_tools_match_recorded_bytes():
    entries = json.loads((ROOT / "vendor.lock.json").read_text())["files"]
    for entry in entries:
        if entry["repository"] == "myon-bioinformatics/myon-bioinformatics":
            data = (ROOT / entry["destination"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == entry["blob_sha"]


def test_gh_ops_help_is_standalone():
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "gh_ops.py"), "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "git-push" in result.stdout


def test_git_push_dry_run_uses_actual_adjacent_identity_without_network(tmp_path):
    # A deliberately unusable remote and guarded real Git runner keep this offline.
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True,
                              text=True, check=True, timeout=15)
    git("init", "--initial-branch=refresh")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "fixture")
    git("remote", "add", "origin", "https://invalid.invalid/never/pushed.git")
    head = git("rev-parse", "HEAD").stdout.strip()
    code = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import gh_ops
assert pathlib.Path(gh_ops.gh_identity.__file__).resolve() == pathlib.Path(sys.argv[1], 'gh_identity.py').resolve()
actual_run = gh_ops.gh_identity._git_run
calls = []
def local_only(cwd, args, **kwargs):
    assert args[0] in {'branch', 'check-ref-format', 'rev-parse', 'remote'}
    assert kwargs.get('inherit_auth') is False
    calls.append(args[0])
    return actual_run(cwd, args, **kwargs)
gh_ops.gh_identity._git_run = local_only
receipt = gh_ops.git_push(cwd=sys.argv[2], write=False, timeout=10)
assert calls == ['branch', 'check-ref-format', 'rev-parse', 'remote']
print(json.dumps(receipt))
"""
    result = subprocess.run([sys.executable, "-S", "-c", code, str(VENDOR), str(tmp_path)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["ok"] and receipt["dry_run"]
    assert receipt["pushed"] is False
    assert receipt["head_sha"] == head
    assert receipt["branch"] == "refresh"
    assert receipt["mutation_status"] == receipt["verification_status"] == "not_attempted"
    assert "invalid.invalid" not in result.stdout
    assert not git("for-each-ref", "refs/remotes/").stdout


def test_gh_workflow_invalid_inputs_remain_private_and_fail_closed():
    marker = "private-test-input-not-a-real-secret"
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "gh_workflow.py"),
                             "owner/repo", "ci.yml", "--inputs", marker],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "preflight_failed"
    assert receipt["error"] == "invalid_argument"
    assert receipt["hint"]
    assert marker not in result.stdout + result.stderr


def test_ci_status_help_exposes_opt_in_options():
    # Help is offline; actual CI observation has a separately tracked pre-existing
    # vendored GHI lookup issue and is not claimed to be validated here.
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "ci_status.py"), "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "--explain" in result.stdout
    assert "--ci-check" in result.stdout


# ═══ · parent workflow pins ══════════════════════════════════════════════════════════════════════════════
# Local rollout contract; adopted vendor locks are deliberately independent.

PARENT = "myon-bioinformatics/myon-bioinformatics"
PARENT_WORKFLOW_PIN = "9e3da7ae1846e9604ebc24bb5178f7de094a4e77"


def test_parent_workflow_references_use_reviewed_rollout_commit():
    pins = []
    for path in sorted((ROOT / ".github/workflows").glob("*")):
        if path.suffix not in (".yml", ".yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        # Capture mutable and shortened references too, rather than ignoring them.
        pins.extend(re.findall(r"uses:\s*['\"]?" + re.escape(PARENT) + r"/[^\s@'\"]+@([^\s'\"]+)", text))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.fullmatch(r"\s+repository:\s*['\"]?" + re.escape(PARENT) + r"['\"]?\s*", line):
                block = lines[i + 1:i + 12]
                if any(re.fullmatch(r"\s+path:\s*['\"]?\.vendor-sync-tools['\"]?\s*", item) for item in block):
                    continue
                refs = [re.fullmatch(r"\s+ref:\s*(.+?)\s*$", item) for item in block]
                ref_match = next((m for m in refs if m), None)
                if ref_match is None:
                    pins.append(None)
                    continue
                ref = ref_match.group(1).strip().strip("'").strip('"')
                if "${{" in ref:
                    continue
                pins.append(ref)
    assert pins, "shared parent references must remain observable"
    assert set(pins) == {PARENT_WORKFLOW_PIN}, pins


# ═══ · repository hygiene ════════════════════════════════════════════════════════════════════════════════
# Repository-wide source hygiene checks.

EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "build", "dist",
}


def repository_python_sources():
    """Prefer tracked sources; fall back for source archives without Git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return sorted(
            path
            for path in ROOT.rglob("*.py")
            if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        )
    return [ROOT / line for line in result.stdout.splitlines() if line]


DEPENDENCY_MANIFESTS = ("pyproject.toml",)
_DEPENDENCY_CAP = re.compile(r"(==|<=|~=|(?<!>)<(?!=))")


def dependency_cap_failures(text):
    """Flag exact pins and upper bounds on dependency lines."""
    failures = []
    for number, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]
        if _DEPENDENCY_CAP.search(code):
            failures.append(number)
    return failures


def workflow_structure_escape_failures(text):
    """Find #42-style escaped newlines that splice YAML list entries."""
    failures = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r'^\s*-\s+["\'][^"\']+["\']\\n\s+-\s+', line):
            failures.append(number)
    return failures


class RepositoryHygieneTest(unittest.TestCase):
    def test_repository_python_files_compile(self):
        sources = repository_python_sources()
        self.assertTrue(sources, "no Python sources discovered")
        failures = []
        with tempfile.TemporaryDirectory() as directory:
            cache_root = Path(directory)
            for path in sources:
                relative = path.relative_to(ROOT)
                cache = cache_root / relative.with_suffix(".pyc")
                cache.parent.mkdir(parents=True, exist_ok=True)
                try:
                    py_compile.compile(str(path), cfile=str(cache), doraise=True)
                except py_compile.PyCompileError as exc:
                    failures.append(f"{relative}: {exc.msg}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_workflow_files_have_no_spliced_list_entries(self):
        """Catch the exact #42 list-entry corruption without banning valid \\n data."""
        failures = []
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
            for number in workflow_structure_escape_failures(path.read_text(encoding="utf-8")):
                failures.append(f"{path.relative_to(ROOT)}:{number}: escaped newline joins list entries")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_workflow_structure_escape_detector_is_narrow(self):
        # One backslash + n is the #42 corruption: two YAML list entries were spliced.
        broken = '      - "a.py"\\n      - "b.py"'
        # Two backslashes are different data and must not be confused with that corruption.
        double_backslash = '      - "a.py"\\\\n      - "b.py"'
        legitimate = "      run: printf 'a\\\\nb'"
        self.assertEqual(workflow_structure_escape_failures(broken), [1])
        self.assertEqual(workflow_structure_escape_failures(double_backslash), [])
        self.assertEqual(workflow_structure_escape_failures(legitimate), [])

    def test_python_dependency_manifests_keep_lower_bounds_only(self):
        failures = []
        for relative in DEPENDENCY_MANIFESTS:
            for number in dependency_cap_failures((ROOT / relative).read_text(encoding="utf-8")):
                failures.append(f"{relative}:{number}: exact pin or upper bound")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
            if "pip install" in path.read_text(encoding="utf-8"):
                failures.append(f"{path.relative_to(ROOT)}: pip install")
        self.assertEqual(failures, [], "\n".join(failures))
        for relative in (
            ".github/workflows/ci.yml",
            ".github/workflows/pptx-review.yml",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3", text)
            self.assertIn("uv run --locked ", text)

    def test_dependency_cap_detector_accepts_lower_bounds(self):
        self.assertEqual(dependency_cap_failures('pillow>=10\npytest>=8\n'), [])
        self.assertEqual(dependency_cap_failures("pillow>=10,<13"), [1])
        self.assertEqual(dependency_cap_failures("playwright==1.63.0"), [1])
        self.assertEqual(dependency_cap_failures("pypdf>=6,<7"), [1])
        self.assertEqual(dependency_cap_failures("numpy~=1.26"), [1])
        self.assertEqual(dependency_cap_failures("numpy<=2"), [1])

    def test_repository_python_sources_falls_back_without_git(self):
        with mock.patch("tests.test_tooling.subprocess.run", side_effect=FileNotFoundError):
            sources = repository_python_sources()
        self.assertIn(ROOT / "tests" / "test_tooling.py", sources)
        self.assertTrue(all(path.suffix == ".py" for path in sources))


# ═══ · vendor automation ═════════════════════════════════════════════════════════════════════════════════
# Regression checks for vendor verification CI wiring.

WORKFLOW = ".github/workflows/mcp-tests.yml"
CI_WORKFLOW = ".github/workflows/ci.yml"
WORKFLOWS = (WORKFLOW, CI_WORKFLOW)
PIN = "26c442bc51b8a2837fe2556782b2937f396932af"


def _workflow(workflow=WORKFLOW):
    import yaml

    return yaml.load((ROOT / workflow).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _lock_files(root=ROOT):
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    return lock["files"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_vendor_ci_verifies_lock_without_auto_updates(workflow):
    ci = _workflow(workflow)
    assert {"push", "pull_request"} <= set(ci["on"])
    assert "schedule" not in ci["on"]
    assert "workflow_dispatch" not in ci["on"]
    assert ci.get("permissions", {"contents": "read"}) == {"contents": "read"}
    jobs = ci["jobs"]
    assert "resolve-vendor" not in jobs
    assert "test-locked" not in jobs
    job = jobs["test"]
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    steps = job["steps"]
    text = (ROOT / workflow).read_text(encoding="utf-8")
    assert "vendor_sync.py promote" not in text
    assert "vendor_sync.py update" not in text
    assert "sync_vendor_provenance" not in text
    verify = next(i for i, s in enumerate(steps) if s.get("name") == "Verify checked-in vendor copies")
    recreate = next(
        i for i, s in enumerate(steps) if s.get("name") == "Recreate locked vendor files from GitHub"
    )
    tests = [i for i, s in enumerate(steps) if "pytest " in s.get("run", "")]
    assert tests and verify < recreate < min(tests)
    pins = [
        s["with"]["ref"]
        for s in steps
        if s.get("with", {}).get("repository") == "myon-bioinformatics/myon-bioinformatics"
    ]
    expected_pin = "${{ steps.parent-vendor-tools.outputs.sha }}" if workflow == WORKFLOW else PIN
    assert pins == [expected_pin]
    for step in steps:
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"
        assert not any(x in step.get("run", "") for x in ("|| true", "|| :", "set +e", "git push", "git commit", "gh pr"))
        assert "continue-on-error" not in step
    assert not any(x in text for x in ("secrets.", "VENDOR_UPDATE_TOKEN", "VENDOR_UPDATES_ENABLED", "GH_TOKEN"))


def test_canonical_vendor_evidence_membership_is_derived_from_lock():
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    destinations = [entry["destination"] for entry in lock["files"]]
    assert len(destinations) == len(set(path.casefold() for path in destinations))
    locked = sorted(["vendor.lock.json", *destinations], key=lambda p: (p.casefold(), p))
    assert set(locked) == {"vendor.lock.json", *(entry["destination"] for entry in lock["files"])}
    assert all((ROOT / path).is_file() for path in locked)


def test_parent_vendor_sync_checkout_resolves_parent_main_at_runtime():
    # `uses:` cannot take an expression, so the reusable-workflow references keep the reviewed
    # rollout pin (see test_parent_workflow_pins.py). Only the vendor_sync checkout follows main.
    text = (ROOT / WORKFLOW).read_text(encoding="utf-8")
    steps = _workflow()["jobs"]["test"]["steps"]
    resolve = next(i for i, s in enumerate(steps) if s.get("id") == "parent-vendor-tools")
    fetch = next(
        i
        for i, s in enumerate(steps)
        if s.get("with", {}).get("repository") == "myon-bioinformatics/myon-bioinformatics"
    )
    assert resolve < fetch
    assert "parent_vendor_tools_resolve.py --emit-github-actions" in steps[resolve]["run"]
    assert steps[resolve]["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    assert "steps.parent-vendor-tools.outputs.sha" in text
    assert "974da5eb9593df652b132e4b0f1a679f67422566" not in text
    assert "14ef53c8316015d1350e62ff9cce3301103e65a7" not in text


def test_parent_vendor_sync_checkout_is_pinned():
    text = (ROOT / CI_WORKFLOW).read_text(encoding="utf-8")
    assert PIN in text
    assert "974da5eb9593df652b132e4b0f1a679f67422566" not in text
    assert "14ef53c8316015d1350e62ff9cce3301103e65a7" not in text


def test_vendor_catalog_audit_resolves_parent_main_at_runtime():
    path = ROOT / ".github/workflows/vendor-catalog-audit.yml"
    text = path.read_text(encoding="utf-8")
    assert PIN not in text
    assert "parent_vendor_tools_resolve.py" in text
    assert "GITHUB_TOKEN" in text
    assert "steps.parent-vendor-tools.outputs.sha" in text
    script = (ROOT / "scripts/parent_vendor_tools_resolve.py").read_text(encoding="utf-8")
    assert "api.github.com/repos/" in script
    assert "ls-remote" in script and "--symref" in script
    assert "638801160" in script
    assert "octolytics" not in text


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_workflow_stages_locked_vendor_evidence(tmp_path, workflow):
    lock_path = tmp_path / "vendor.lock.json"
    shutil.copyfile(ROOT / "vendor.lock.json", lock_path)
    for entry in _lock_files():
        dest = tmp_path / entry["destination"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry["destination"], dest)
    tools = ROOT / ".vendor-sync-tools"  # the parent checkout ci.yml makes
    if not (tools / "vendor_stage.py").is_file():
        pytest.skip("parent vendor tools checkout not present")
    steps = _workflow(workflow)["jobs"]["test"]["steps"]
    stage = next(s for s in steps if s.get("name") == "Stage canonical vendor evidence")
    assert stage["if"] == "always()"
    command = stage["run"].replace(
        "python -S .vendor-sync-tools/vendor_stage.py",
        shlex.quote(sys.executable) + " -S " + shlex.quote(str(tools / "vendor_stage.py")),
    )
    result = subprocess.run(
        [shutil.which("bash"), "-e", "-c", command],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    output = tmp_path / "build/vendor-evidence-test"
    meta = json.loads((output / "vendor-evidence.json").read_text())
    sources = {"vendor.lock.json"} | {e["destination"] for e in _lock_files()}
    assert meta["kind"] == "locked" and set(meta["locked"]) == sources
    assert meta.get("legacy") == []
    assert set(meta["sha256"]) == sources
    expected = sources | {"vendor-evidence.json"}
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == expected
    for name in sources:
        data = (output / name).read_bytes()
        assert data == (tmp_path / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"][name]


# ═══ · vendor catalog snapshot ═══════════════════════════════════════════════════════════════════════════
# Parent vendor catalog snapshot: visibility does not imply enrollment.

def test_catalog_is_complete_and_explicit():
    catalog = json.loads((ROOT / "vendor-catalog.json").read_text(encoding="utf-8"))
    assert catalog["schema"] == "vendor-catalog/1"
    tools = catalog["tools"]
    assert len(tools) == 30
    assert len({(item["repository"], item.get("source")) for item in tools}) == len(tools)
    assert any(item["repository"] == "myon-bioinformatics/cli_args" for item in tools)
    assert any(item.get("default_enrollment", {}).get("enrollment") == "skipped" for item in tools)


def test_catalog_enrollment_is_explicit_and_complete():
    catalog = json.loads((ROOT / "vendor-catalog.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    assert len(lock["files"]) == 55  # web-ui's six flow copies and its LICENSE left with the flow code (now ascii_artist)
    locked = {(entry["repository"], entry["source"]) for entry in lock["files"]}
    for item in catalog["tools"]:
        if item.get("default_enrollment", {}).get("enrollment") == "skipped":
            continue
        source = item.get("source", item["repository"].split("/")[1] + ".py")
        assert (item["repository"], source) in locked
    assert ("myon-bioinformatics/cli_args", "cli_args.py") in locked
    assert len({entry["destination"] for entry in lock["files"]}) == 55
    assert ("myon-bioinformatics/Aoi", "scripts/fetch_module.py") in locked
    assert ("myon-bioinformatics/Aoi", "LICENSE") in locked


# ═══ · vendor integrity ══════════════════════════════════════════════════════════════════════════════════
# Check every retained source and license against the consumer lock.

def test_all_locked_files_match_recorded_identity():
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "vendor.lock.json").read_text())
    assert lock["schema"] == "vendor-lock/1"
    for entry in lock["files"]:
        path = root / entry["destination"]
        assert not path.is_symlink(), entry["destination"]
        data = path.read_bytes()
        blob = b"blob " + str(len(data)).encode() + b"\0" + data
        assert hashlib.sha1(blob).hexdigest() == entry["blob_sha"], entry["destination"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["destination"]


# ═══ · vendor lock ═══════════════════════════════════════════════════════════════════════════════════════

def test_vendor_lock_matches_checked_in_bytes() -> None:
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    for entry in lock["files"]:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["ref"]), entry["destination"]
        assert entry["ref"] == entry["commit"], entry["destination"]
        data = (ROOT / entry["destination"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert blob == entry["blob_sha"], entry["destination"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["destination"]


# ═══ · vendor markdown nul ═══════════════════════════════════════════════════════════════════════════════
# Upstream markdown#62 regressions through Ironmate's vendored emitter.

@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("keep \x00PH0\x00 here and `code`", "<p>keep \ufffdPH0\ufffd here and <code>code</code></p>\n"),
        ("only \x00PH0\x00 text", "<p>only \ufffdPH0\ufffd text</p>\n"),
        ("```\n\x00\n```", "<pre><code>\ufffd\n</code></pre>\n"),
    ],
)
def test_vendored_markdown_and_web_ui_replace_input_nul(source, expected):
    html = markdown.markdown_to_html(source)
    assert html == expected
    assert "\x00" not in html

    document = markdown.markdown_to_web_ui_v1(source)
    assert expected in document
    assert "\x00" not in document


# ═══ · vendor mermaid bridge ═════════════════════════════════════════════════════════════════════════════
# Contract tests for reusing vendor Markdown's opaque Mermaid helpers.

VENDOR_MERMAID_BRIDGE_VENDOR = ROOT / "vendor" / "markdown.py"


def vendor_markdown():
    spec = importlib.util.spec_from_file_location("ironmate_vendor_markdown", VENDOR_MERMAID_BRIDGE_VENDOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mermaid_flowchart_roundtrip_without_custom_parser():
    markdown = vendor_markdown()
    source = 'flowchart LR\n  A["Box A"] --> B["Box B"]\n  B --> C["Box C"]'
    fenced = markdown.mermaid_block(source)
    assert markdown.extract_mermaid_blocks(fenced) == [source]
    assert fenced.count("mermaid") == 1


def test_mermaid_opaque_source_does_not_claim_editable_pptx():
    markdown = vendor_markdown()
    source = 'flowchart RL\n  C["Box C"] --> A["Box A"]'
    fenced = markdown.mermaid_block(source)
    assert markdown.extract_mermaid_blocks(fenced) == [source]
    # Mermaid edges are diagram source, not a PPTX edge-anchor contract.
    assert "RL" in fenced and "C" in fenced


# ═══ · vendor modules ════════════════════════════════════════════════════════════════════════════════════
# Integration checks for pinned vendored sibling utilities.

class VendorModuleIntegrationTest(unittest.TestCase):
    def test_vendor_ascii_artist_smoke(self):
        self.assertEqual(ascii_artist.generate_square(2), "**\n**")
        self.assertTrue(hasattr(ascii_artist, "to_web_ui_v1_html"))

    def test_vendor_markdown_smoke(self):
        self.assertTrue(hasattr(markdown, "markdown_to_web_ui_v1"))
        html = markdown.markdown_to_web_ui_v1(
            "# Hello\n",
            title="Ironmate",
            theme="modern",
        )
        self.assertIn('class="ui-page"', html)
        self.assertIn('class="ui-panel"', html)

    def test_generated_consumer_examples_remain_text_safe(self):
        markdown_html = markdown.markdown_to_web_ui_v1(
            "body",
            title="<unsafe>",
        )
        ascii_html = ascii_artist.to_web_ui_v1_html(
            "<unsafe> & text",
            title="<ascii>",
        )
        self.assertIn("&lt;unsafe&gt;", markdown_html)
        self.assertNotIn("<unsafe>", markdown_html)
        self.assertIn("&lt;unsafe&gt; &amp; text", ascii_html)
        self.assertIn("&lt;ascii&gt;", ascii_html)


# ═══ · vendor xprobe node floor ══════════════════════════════════════════════════════════════════════════
# Consumer regression for the canonical single-file xprobe Node contract.

@pytest.mark.parametrize("major", [24, 25])
@pytest.mark.parametrize("explicit", [False, True])
def test_old_node_reports_found_version_without_running_backend(monkeypatch, major, explicit):
    path = "/fake/node"
    probes = []

    def version_probe(command, **kwargs):
        assert tuple(command) == (path, "--version")
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 5.0
        probes.append(command)
        return subprocess.CompletedProcess(command, 0, f"v{major}.0.0\n".encode(), b"")

    def unexpected_backend(*args, **kwargs):
        pytest.fail("a rejected Node runtime must never execute the backend")

    monkeypatch.setattr(shutil, "which", lambda name: path if name == "node" else None)
    monkeypatch.setattr(subprocess, "run", version_probe)
    monkeypatch.setattr(subprocess, "Popen", unexpected_backend)
    monkeypatch.setattr(xprobe, "_NODE_LAUNCH", xprobe._stdlib_node_launch())
    with pytest.raises(RuntimeError, match=rf"Node 26\+.*found Node {major}"):
        xprobe._node_load("yaml-failsafe", "a: 1\n", path if explicit else None, 30)
    assert len(probes) == 1


def test_xprobe_lock_uses_accepted_canonical_source():
    import json
    from pathlib import Path

    lock = json.loads((Path(__file__).resolve().parents[1] / "vendor.lock.json").read_text())
    entry = next(item for item in lock["files"] if item["destination"] == "vendor/xprobe.py")
    assert entry["ref"] == entry["commit"] == "1ffbb7b984075c683690bbe4e9deb06199cdfe94"
    assert entry["blob_sha"] == "7595fe5eb7fd2e375b82e7c702079f6496a3276d"


if __name__ == "__main__":
    unittest.main()
