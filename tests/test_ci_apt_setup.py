"""Offline contracts for bounded setup; no package or browser install is run."""
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.configure_ci_apt import APT_CONFIG, CONFIG_NAME, configure, prefer_existing_archive


ROOT = Path(__file__).resolve().parents[1]
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
    workflow = yaml.safe_load((ROOT / ".github/workflows/mcp-tests.yml").read_text())
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
