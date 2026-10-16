"""Create a PPTX with the pinned PptxGenJS package, then overlay canonical slide XML.

The Node script is allowlisted and does not edit OOXML. Ironmate owns the
JSON ↔ XML mapping, so the slide parts written here are the reversible subset
rather than PptxGenJS's extra run properties.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from pptx_mapping import EMU_PER_INCH, canonical_spec, public_slide, read_slide_xml, write_slide_xml
from pptx_ooxml import copy_with_replacements, ordered_slide_members, reorder_sld_id_lst, set_sld_sz

ROOT = Path(__file__).resolve().parent


def _renderer():
    script = (ROOT / 'scripts' / 'pptxgen_render.mjs').resolve()
    allow = json.loads((ROOT / 'scripts' / 'pptxgen_allowlist.json').read_text(encoding='utf-8'))
    relative = script.relative_to(ROOT).as_posix()
    if relative not in allow.get('scripts', []) or not script.is_file():
        raise RuntimeError('pptxgenjs renderer is not allowlisted')
    if not (ROOT / 'node_modules' / 'pptxgenjs' / 'package.json').is_file():
        raise RuntimeError('pinned pptxgenjs is not installed; run npm ci from the repository root')
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required to create a PPTX; install Node.js 22 and run npm ci. Ironmate does not auto-install it.')
    return node, script


def _package_bytes(spec, slide_payloads, *, display=None):
    """Run PptxGenJS for the package shell, then replace slide parts.

    ``spec`` is what Node sees (slide count, size, background). ``slide_payloads``
    are the OOXML slide parts Ironmate owns, in creation order.
    """
    node, script = _renderer()
    with tempfile.TemporaryDirectory(prefix='pptxgen-') as directory:
        directory = Path(directory)
        spec_path, package = directory / 'spec.json', directory / 'deck.pptx'
        spec_path.write_text(json.dumps(spec), encoding='utf-8')
        result = subprocess.run([node, str(script), str(spec_path), str(package)], cwd=ROOT,
                                capture_output=True, text=True, check=False, timeout=60)
        if result.returncode != 0 or not package.is_file():
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f'PptxGenJS render failed (exit {result.returncode}): {detail}')
        cx = int(round(float(spec['width']) * EMU_PER_INCH))
        cy = int(round(float(spec['height']) * EMU_PER_INCH))
        replacements = {}
        with ZipFile(package) as archive:
            presentation = set_sld_sz(archive.read('ppt/presentation.xml'), cx, cy)
            if display is not None and list(display) != list(range(len(slide_payloads))):
                presentation = reorder_sld_id_lst(presentation, display)
            replacements['ppt/presentation.xml'] = presentation
            members = ordered_slide_members(archive)
            if len(members) != len(slide_payloads):
                raise RuntimeError('PptxGenJS slide count did not match the spec')
            for member, payload in zip(members, slide_payloads):
                replacements[member] = payload
        overlaid = directory / 'overlaid.pptx'
        copy_with_replacements(package, overlaid, replacements)
        return overlaid.read_bytes()


def render_bytes(spec, *, display=None):
    """Return PPTX bytes for a canonical deck spec.

    ``display`` is a permutation of creation indexes. Slide files stay in
    creation order; only ``p:sldIdLst`` changes.
    """
    spec = canonical_spec(spec)
    shell = {'width': spec['width'], 'height': spec['height'],
             'slides': [{'background': slide['background']} if slide.get('background') else {} for slide in spec['slides']]}
    payloads = [write_slide_xml(slide) for slide in spec['slides']]
    return _package_bytes(shell, payloads, display=display)


def write_new_package(path, spec, *, display=None):
    path = Path(path)
    data = render_bytes(spec, display=display)
    path.write_bytes(data)
    return path


def read_package_spec(path):
    """Read a deck back into the public slide spec (display order, no shape ids)."""
    with ZipFile(path) as package:
        from pptx_ooxml import slide_size
        cx, cy = slide_size(package)
        slides = [public_slide(read_slide_xml(package.read(member))) for member in ordered_slide_members(package)]
    return {'width': cx / EMU_PER_INCH, 'height': cy / EMU_PER_INCH, 'slides': slides}
