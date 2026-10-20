#!/usr/bin/env python3
"""Count PDF pages with ``PdfReader.pages`` without a pip-installed pypdf.

One command fetches the pure wheel (sha256 checked), runs the same call
``pptx_preview.py`` uses, installs that wheel into a fresh venv, runs the
call again, and compares the two results. Playwright is not imported.
``typing_extensions`` is not expected on Python 3.11 or newer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_OUTPUT_FIELDS = ("pages", "mediabox", "version", "pdf_sha256")


def one_page_pdf() -> bytes:
    """A one-page PDF built with the standard library."""
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n",
    ]
    body = bytearray(header)
    offsets = []
    for obj in objects:
        offsets.append(len(body))
        body.extend(obj)
    xref_at = len(body)
    size = len(objects) + 1
    body.extend(f"xref\n0 {size}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode())
    return bytes(body)


def observe_pdf(pdf) -> dict:
    """Run the preview page-count call and record the page geometry around it."""
    from pypdf import PdfReader
    import pypdf

    pdf = Path(pdf)
    # Same call as pptx_preview.render_preview_html.
    pages = len(PdfReader(pdf, strict=True).pages)
    reader = PdfReader(pdf, strict=True)
    if len(reader.pages) != pages:
        raise RuntimeError("PdfReader.pages length changed between reads")
    box = reader.pages[0].mediabox if pages else []
    return {
        "pages": pages,
        "mediabox": [str(box[i]) for i in range(4)] if pages else [],
        "version": pypdf.__version__,
        "origin": Path(pypdf.__file__).as_posix(),
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    }


def page_output(observation: dict) -> dict:
    return {key: observation[key] for key in PAGE_OUTPUT_FIELDS}


def _run(command: list[str], pythonpath: str | None) -> dict:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    else:
        env.pop("PYTHONPATH", None)
    completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SystemExit(f"page count failed: {detail}")
    return json.loads(completed.stdout)


def compare(cache: Path) -> dict:
    """Fetch pypdf, count pages from the wheel, install it, and compare."""
    installed = importlib.util.find_spec("pypdf")
    if installed is not None:
        raise SystemExit(f"pypdf is already installed ({installed.origin})")
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import fetch_module

    spec = fetch_module.resolve("pypdf")
    wheel = fetch_module.fetch(spec, cache)
    with tempfile.TemporaryDirectory(prefix="cdn-pypdf-") as temporary:
        directory = Path(temporary)
        pdf = directory / "one-page.pdf"
        pdf.write_bytes(one_page_pdf())
        script = str(Path(__file__).resolve())
        wheel_obs = _run([sys.executable, script, "count", str(pdf)], str(wheel))
        venv = directory / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=120)
        py = venv / "bin" / "python"
        subprocess.run(
            [str(py), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)],
            check=True,
            timeout=180,
        )
        if sys.version_info >= (3, 11):
            probe = subprocess.run([str(py), "-c", "import typing_extensions"], capture_output=True, timeout=30)
            if probe.returncode == 0:
                raise SystemExit("typing_extensions was installed on Python >= 3.11")
        installed_obs = _run([str(py), script, "count", str(pdf)], None)
    if ".whl/" not in wheel_obs["origin"]:
        raise SystemExit(f"wheel run did not import from the wheel: {wheel_obs['origin']}")
    if "site-packages" not in installed_obs["origin"] or ".whl/" in installed_obs["origin"]:
        raise SystemExit(f"installed run did not import from site-packages: {installed_obs['origin']}")
    if wheel_obs["pages"] != 1 or installed_obs["pages"] != 1:
        raise SystemExit(f"expected one page, got wheel={wheel_obs['pages']} installed={installed_obs['pages']}")
    if page_output(wheel_obs) != page_output(installed_obs):
        raise SystemExit("page output mismatch:\n" + json.dumps({"wheel": wheel_obs, "installed": installed_obs}, indent=1))
    return {"wheel": wheel_obs, "installed": installed_obs, "spec": spec}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    count = sub.add_parser("count")
    count.add_argument("pdf")
    compare_cmd = sub.add_parser("compare")
    compare_cmd.add_argument("--cache", default="build/cdn-cache")
    args = parser.parse_args(argv)
    if args.command == "count":
        print(json.dumps(observe_pdf(args.pdf)))
        return 0
    result = compare(Path(args.cache))
    spec = result["spec"]
    print(f"pypdf {spec['version']} sha256={spec['sha256']}")
    for kind in ("wheel", "installed"):
        row = result[kind]
        print(f"{kind} pages={row['pages']} mediabox={row['mediabox']} origin={row['origin']}")
    print("match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
