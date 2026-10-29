"""Offline contracts for bounded setup; no package or browser install is run."""
from pathlib import Path

import pytest
import yaml

from scripts.configure_ci_apt import APT_CONFIG, CONFIG_NAME, configure, prefer_existing_archive


ROOT = Path(__file__).resolve().parents[1]
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
    assert any("fonts-noto-cjk" in s.get("run", "") for s in marp_steps)
    assert any(s.get("env", {}).get("IRONMATE_FLOW_REQUIRE_CJK") == "1" for s in marp_steps)
    clipboard = jobs["studio-clipboard"]
    assert clipboard["strategy"]["matrix"]["browser"] == ["chromium", "firefox", "webkit"]
    assert clipboard["strategy"]["fail-fast"] is False
    assert any("install --with-deps ${{ matrix.browser }}" in s.get("run", "")
               for s in clipboard["steps"])
