"""Offline checks for the pure-wheel fetch and marker gate."""
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_module as fm  # noqa: E402


def _wheel() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("cdnfake/__init__.py", "VALUE = 42\n")
        archive.writestr("cdnfake-1.0.dist-info/METADATA", "Name: cdnfake\n")
    return buf.getvalue()


def _serve(monkeypatch, wheel, sha=None, requires=None, filename="cdnfake-1.0-py3-none-any.whl"):
    meta = {
        "info": {"version": "1.0", "requires_dist": requires},
        "urls": [{
            "packagetype": "bdist_wheel",
            "filename": filename,
            "url": "https://files.example/w.whl",
            "digests": {"sha256": sha or hashlib.sha256(wheel).hexdigest()},
        }],
    }
    calls = []

    def get(url):
        calls.append(url)
        return json.dumps(meta).encode() if url.endswith("/json") else wheel

    monkeypatch.setattr(fm, "_get", get)
    return calls


def test_fetch_verifies_caches_and_imports(monkeypatch, tmp_path):
    wheel = _wheel()
    calls = _serve(monkeypatch, wheel, requires=['pytest; extra == "testing"'])
    module = fm.ensure("cdnfake", tmp_path)
    assert module.VALUE == 42 and ".whl" in module.__file__
    spec = fm.resolve("cdnfake")
    fm.fetch(spec, tmp_path)
    assert sum(not call.endswith("/json") for call in calls) == 1
    out = fm.extract(tmp_path / spec["filename"], tmp_path / "x")
    assert (out / "cdnfake" / "__init__.py").exists() and not list(out.glob("*.dist-info"))
    sys.modules.pop("cdnfake", None)


def test_rejects_bad_hash_compiled_and_runtime_deps(monkeypatch, tmp_path):
    _serve(monkeypatch, _wheel(), sha="0" * 64)
    with pytest.raises(SystemExit, match="sha256"):
        fm.fetch(fm.resolve("cdnfake"), tmp_path)
    _serve(monkeypatch, _wheel(), filename="cdnfake-1.0-cp312-cp312-manylinux_2_17_x86_64.whl")
    with pytest.raises(SystemExit, match="pure-Python"):
        fm.resolve("cdnfake")
    _serve(monkeypatch, _wheel(), requires=["pluggy>=1"])
    with pytest.raises(SystemExit, match="runtime dependencies"):
        fm.resolve("cdnfake")


def test_only_https():
    with pytest.raises(ValueError, match="https"):
        fm._get("http://pypi.org/pypi/pypdf/json")


def test_typing_extensions_marker_is_inactive_on_python_3_11_and_newer(monkeypatch):
    assert sys.version_info >= (3, 11)
    _serve(monkeypatch, _wheel(), requires=['typing_extensions>=4.0; python_version < "3.11"'])
    assert fm.resolve("cdnfake")["version"] == "1.0"


def test_typing_extensions_marker_applies_below_python_3_11(monkeypatch):
    _serve(monkeypatch, _wheel(), requires=['typing_extensions>=4.0; python_version < "3.11"'])
    env = {"python_version": "3.10", "python_full_version": "3.10.0"}
    with pytest.raises(SystemExit, match="typing_extensions"):
        fm.resolve("cdnfake", env=env)


def test_python_3_9_is_below_3_11_as_a_version_not_as_text():
    env = fm.marker_environment({"python_version": "3.9"})
    assert fm.marker_applies('python_version < "3.11"', env)
    assert not fm.marker_applies('python_version < "3.11"', fm.marker_environment({"python_version": "3.11"}))
    assert not fm.marker_applies('python_version < "3.11"', fm.marker_environment({"python_version": "3.12"}))


def test_extra_or_marker_follows_the_environment(monkeypatch):
    _serve(monkeypatch, _wheel(), requires=['foo>=1; python_version >= "3.11" or extra == "dev"'])
    with pytest.raises(SystemExit, match="runtime dependencies"):
        fm.resolve("cdnfake")
    _serve(monkeypatch, _wheel(), requires=['foo>=1; python_version < "3.11" or extra == "dev"'])
    assert fm.resolve("cdnfake")["version"] == "1.0"
    assert not fm.marker_applies('extra == "brotli"', fm.marker_environment())


def test_pypdf_requires_dist_sample_has_no_active_dependency_here():
    info = {"requires_dist": [
        'typing_extensions>=4.0; python_version < "3.11"',
        'brotli>=1.2.0; extra == "brotli"',
        'cryptography>3.0; extra == "crypto"',
        'Pillow>=8.0.0; extra == "image"',
    ]}
    assert fm.runtime_requirements(info) == []
    below = fm.runtime_requirements(info, {"python_version": "3.10", "python_full_version": "3.10.0"})
    assert below == ['typing_extensions>=4.0; python_version < "3.11"']


def test_release_comparison_and_fail_closed_complex_versions(monkeypatch):
    env = fm.marker_environment({"python_version": "3.12"})
    assert fm.marker_applies('python_version == "3.12.0"', env)
    assert fm.marker_applies('python_version ~= "3.12"', fm.marker_environment({"python_version": "3.13"}))
    assert not fm.marker_applies('python_version ~= "3.12.1"', fm.marker_environment({"python_version": "3.13.0"}))
    assert fm.marker_applies('python_version != "abc"', env)
    assert not fm.marker_applies('python_version == "abc"', env)
    assert not fm.marker_applies('python_version < "abc"', env)
    assert fm.marker_applies('"3.11" > python_version', fm.marker_environment({"python_version": "3.10"}))
    assert fm.marker_applies('extra == "Brotli_X"', fm.marker_environment({"extra": "brotli.x"}))
    _serve(monkeypatch, _wheel(), requires=['foo>=1; python_version >= "3.11a1"'])
    with pytest.raises(SystemExit, match="runtime dependencies"):
        fm.resolve("cdnfake")
