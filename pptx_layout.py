"""Reproduce row, column and grid spacing of existing native PPTX objects."""
import argparse
import json
import math
import os
from pathlib import Path
import tempfile
import tomllib
from zipfile import ZipFile

from pptx import Presentation
from lxml import etree

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
EMU = 914400


def _length(rule, key):
    value = rule.get(key)
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f'{key} must be finite inches between 0 and 100')
    return round(value * EMU)


def arrange(source, rules, *, destination=None, dry_run=False):
    """Move explicit top-level shape IDs; preserve all other ZIP member bytes.

    Rules run sequentially, including during dry-run. Grid cells use the largest
    selected width/height; gaps are edge gaps between cells, not center distances.
    """
    if not isinstance(rules, list) or not rules:
        raise ValueError('at least one layout rule required')
    if not dry_run and (destination is None or Path(destination).resolve() == Path(source).resolve()
                        or os.path.lexists(destination)):
        raise ValueError('destination must be a new file distinct from source')
    prs = Presentation(str(source))
    changes, roots = [], {}
    with ZipFile(source) as original:
        if len(original.namelist()) != len(set(original.namelist())):
            raise ValueError('duplicate ZIP members unsupported')
        for rule_index, rule in enumerate(rules):
            mode, number, ids = rule.get('pattern'), rule.get('slide'), rule.get('shape_ids')
            if mode not in ('row', 'column', 'grid'):
                raise ValueError('pattern must be row, column or grid')
            if type(number) is not int or not 1 <= number <= len(prs.slides):
                raise ValueError('slide must be a valid 1-based slide number')
            if (not isinstance(ids, list) or not ids or any(type(i) is not int or i < 1 for i in ids)
                    or len(ids) != len(set(ids))):
                raise ValueError('shape_ids must be nonempty unique positive integer IDs')
            x, y = _length(rule, 'x'), _length(rule, 'y')
            gap_x, gap_y = _length(rule, 'gap_x'), _length(rule, 'gap_y')
            columns = rule.get('columns') if mode == 'grid' else (len(ids) if mode == 'row' else 1)
            if type(columns) is not int or not 1 <= columns <= len(ids):
                raise ValueError('columns must be between 1 and selected shape count')
            member = str(prs.slides[number - 1].part.partname).lstrip('/')
            if member not in roots:
                roots[member] = etree.fromstring(original.read(member))
            tree = roots[member].find(P + 'cSld/' + P + 'spTree')
            selected = []
            for shape_id in ids:
                matches = [s for s in tree if s.find('.//' + P + 'cNvPr') is not None
                           and s.find('.//' + P + 'cNvPr').get('id') == str(shape_id)]
                if len(matches) != 1 or matches[0].tag != P + 'sp':
                    raise ValueError(f'shape {shape_id}: only top-level native shapes supported')
                shape = matches[0]
                xf = shape.find(P + 'spPr/' + A + 'xfrm')
                if (xf is None or any(xf.get(k, '0') not in ('0', 'false') for k in ('rot', 'flipH', 'flipV'))
                        or xf.find(A + 'off') is None or xf.find(A + 'ext') is None):
                    raise ValueError('explicit unrotated unflipped geometry required')
                # Moving connected objects requires routing, which this prototype does not perform.
                for tag in ('stCxn', 'endCxn'):
                    if any(c.get('id') == str(shape_id) for c in tree.findall('.//' + A + tag)):
                        raise ValueError('connected shapes require explicit connector routing')
                ext = xf.find(A + 'ext')
                width, height = int(ext.get('cx')), int(ext.get('cy'))
                if width <= 0 or height <= 0:
                    raise ValueError('positive shape dimensions required')
                selected.append((shape_id, xf.find(A + 'off'), width, height))
            cell_w = max(s[2] for s in selected)
            cell_h = max(s[3] for s in selected)
            for index, (shape_id, off, width, height) in enumerate(selected):
                left = x + (index % columns) * (cell_w + gap_x)
                top = y + (index // columns) * (cell_h + gap_y)
                if left + width > prs.slide_width or top + height > prs.slide_height:
                    raise ValueError('layout extends beyond slide bounds')
                before = [int(off.get('x')), int(off.get('y'))]
                after = [left, top]
                if before != after:
                    changes.append(dict(rule=rule_index, slide=number, shape_id=shape_id,
                                        before_emu=before, after_emu=after))
                    off.set('x', str(left))
                    off.set('y', str(top))
        if not dry_run:
            dst = Path(destination)
            with tempfile.TemporaryDirectory(prefix='.pptx-layout-', dir=dst.parent) as staging:
                staged = Path(staging) / 'complete.pptx'
                with ZipFile(staged, 'w') as output:
                    output.comment = original.comment
                    for entry in original.infolist():
                        payload = (etree.tostring(roots[entry.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                                   if entry.filename in roots else original.read(entry.filename))
                        output.writestr(entry, payload)
                Presentation(staged)
                os.link(staged, dst)
    return dict(dry_run=dry_run, change_count=len(changes), changes=changes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--rules', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    with args.rules.open('rb') as stream:
        rules = tomllib.load(stream).get('rules')
    print(json.dumps(arrange(args.source, rules, destination=args.output, dry_run=args.dry_run), indent=2))


if __name__ == '__main__':
    main()
