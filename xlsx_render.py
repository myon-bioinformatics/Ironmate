"""Write a workbook with ExcelJS or SheetJS, then apply Ironmate's style XML."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from xlsx_ooxml import canonicalize

ROOT = Path(__file__).resolve().parent


def _tool():
    script = (ROOT / 'scripts' / 'xlsx_io.mjs').resolve()
    allow = json.loads((ROOT / 'scripts' / 'xlsx_allowlist.json').read_text(encoding='utf-8'))
    relative = script.relative_to(ROOT).as_posix()
    if relative not in allow.get('scripts', []) or not script.is_file():
        raise RuntimeError('xlsx renderer is not allowlisted')
    for package in ('exceljs', 'xlsx'):
        if not (ROOT / 'node_modules' / package / 'package.json').is_file():
            raise RuntimeError('pinned exceljs and xlsx are not installed; run npm ci from the repository root')
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required to write xlsx; install Node.js 22 and run npm ci. Ironmate does not auto-install it.')
    return node, script


def _run(engine, mode, source, dest):
    node, script = _tool()
    result = subprocess.run(
        [node, str(script), engine, mode, str(source), str(dest)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f'{engine} {mode} failed (exit {result.returncode}): {detail}')


def write_workbook(spec, engine='exceljs'):
    """Return xlsx bytes. ``engine`` is ``exceljs`` or ``sheetjs``."""
    if engine not in ('exceljs', 'sheetjs'):
        raise ValueError('engine must be exceljs or sheetjs')
    with tempfile.TemporaryDirectory(prefix='xlsx-') as directory:
        directory = Path(directory)
        spec_path = directory / 'spec.json'
        package = directory / 'book.xlsx'
        spec_path.write_text(json.dumps(spec), encoding='utf-8')
        _run(engine, 'write', spec_path, package)
        return canonicalize(package.read_bytes(), spec)


def read_workbook(payload, engine):
    """Read a workbook back through ExcelJS or SheetJS."""
    if engine not in ('exceljs', 'sheetjs'):
        raise ValueError('engine must be exceljs or sheetjs')
    with tempfile.TemporaryDirectory(prefix='xlsx-') as directory:
        directory = Path(directory)
        package = directory / 'book.xlsx'
        spec_path = directory / 'spec.json'
        package.write_bytes(payload)
        _run(engine, 'read', package, spec_path)
        return json.loads(spec_path.read_text(encoding='utf-8'))
