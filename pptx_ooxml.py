"""Tolerant PPTX package helpers. Surgical edits copy every untouched member."""
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pptx_mapping import ANS, PNS, RNS, _q

REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def ordered_slide_members(package):
    """Map display order to stored ZIP members."""
    presentation = ET.fromstring(package.read('ppt/presentation.xml'))
    rels = ET.fromstring(package.read('ppt/_rels/presentation.xml.rels'))
    mapping = {}
    for rel in rels.findall(REL + 'Relationship'):
        if rel.get('Type', '').endswith('/slide'):
            if rel.get('TargetMode', 'Internal') != 'Internal':
                raise ValueError('external slide relationships are unsupported')
            rid, target = rel.get('Id'), rel.get('Target', '')
            if not rid or not target or '..' in PurePosixPath(target).parts or target.startswith('/'):
                raise ValueError('invalid slide relationship target')
            if rid in mapping:
                raise ValueError('duplicate slide relationship')
            mapping[rid] = 'ppt/' + str(PurePosixPath(target))
    ids = presentation.find(_q('p', 'sldIdLst'))
    if ids is None:
        raise ValueError('slide order list missing')
    ordered = []
    for slide in ids.findall(_q('p', 'sldId')):
        rid = slide.get(_q('r', 'id'))
        if rid not in mapping:
            raise ValueError('unresolved slide relationship')
        ordered.append(mapping[rid])
    if len(ordered) != len(set(ordered)):
        raise ValueError('duplicate slide target')
    return ordered


def slide_size(package):
    root = ET.fromstring(package.read('ppt/presentation.xml'))
    size = root.find(_q('p', 'sldSz'))
    if size is None:
        raise ValueError('slide size missing')
    return int(size.get('cx')), int(size.get('cy'))


def require_package(path):
    """Open a PPTX and return its display-order slide count."""
    with ZipFile(path) as package:
        members = ordered_slide_members(package)
        names = package.namelist()
        if len(names) != len(set(names)) or any(member not in names for member in members):
            raise ValueError('invalid slide package members')
        slide_size(package)
    return len(members)


def copy_with_replacements(source, destination, replacements):
    """Write a new ZIP. ``replacements`` maps member name to replacement bytes."""
    with ZipFile(source) as original:
        names = original.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP members unsupported')
        with ZipFile(destination, 'w') as output:
            output.comment = original.comment
            for entry in original.infolist():
                output.writestr(entry, replacements.get(entry.filename, original.read(entry.filename)))


def shape_ids(payload):
    """Ids of top-level drawable children, in z-order. The group node is id 1."""
    root = ET.fromstring(payload)
    tree = root.find(_q('p', 'cSld') + '/' + _q('p', 'spTree'))
    if tree is None:
        raise ValueError('p:spTree missing')
    ids = []
    for child in list(tree):
        if child.tag in (_q('p', 'nvGrpSpPr'), _q('p', 'grpSpPr')):
            continue
        nv = child.find('.//' + _q('p', 'cNvPr'))
        if nv is None or nv.get('id') is None:
            raise ValueError('shape id missing')
        ids.append(int(nv.get('id')))
    return ids


def append_objects(payload, objects):
    """Append canonical objects without rewriting existing slide children.

    Ids continue after the highest ``p:cNvPr/@id`` already in the part. Existing
    elements, including ones outside the reversible subset, stay in place.
    """
    from pptx_mapping import write_slide_xml
    root = ET.fromstring(payload)
    tree = root.find(_q('p', 'cSld') + '/' + _q('p', 'spTree'))
    if tree is None:
        raise ValueError('p:spTree missing')
    highest = 1
    for nv in root.iter(_q('p', 'cNvPr')):
        if nv.get('id', '').isdigit():
            highest = max(highest, int(nv.get('id')))
    ids = list(range(highest + 1, highest + 1 + len(objects)))
    fragment = ET.fromstring(write_slide_xml({'objects': objects}, ids))
    source = fragment.find(_q('p', 'cSld') + '/' + _q('p', 'spTree'))
    for child in list(source):
        if child.tag not in (_q('p', 'nvGrpSpPr'), _q('p', 'grpSpPr')):
            tree.append(child)
    ET.register_namespace('p', PNS)
    ET.register_namespace('a', ANS)
    ET.register_namespace('r', RNS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), ids


def set_sld_sz(payload, cx, cy):
    root = ET.fromstring(payload)
    size = root.find(_q('p', 'sldSz'))
    if size is None:
        raise ValueError('slide size missing')
    size.set('cx', str(int(cx)))
    size.set('cy', str(int(cy)))
    ET.register_namespace('p', PNS)
    ET.register_namespace('a', ANS)
    ET.register_namespace('r', RNS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def reorder_sld_id_lst(payload, display_indexes):
    """Permute p:sldId children. ``display_indexes`` are positions in the current list."""
    root = ET.fromstring(payload)
    listing = root.find(_q('p', 'sldIdLst'))
    children = list(listing)
    if sorted(display_indexes) != list(range(len(children))):
        raise ValueError('slide display order must be a permutation')
    for child in children:
        listing.remove(child)
    for index in display_indexes:
        listing.append(children[index])
    ET.register_namespace('p', PNS)
    ET.register_namespace('a', ANS)
    ET.register_namespace('r', RNS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
