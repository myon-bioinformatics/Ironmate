"""One-to-one JSON slide spec ↔ OOXML for the supported subset.

See docs/pptx-ooxml-mapping.md. One deck is one JSON object. Each slide has one
``objects`` array; index 0 is the back and matches ``p:spTree`` order. Shape
ids are assigned from that order and are not JSON fields. ``canonical_spec``
is the lossless form: JSON → XML → JSON of a canonical spec equals that spec,
and writing the read spec is an XML no-op under canonicalization.
"""
import copy
import math
from xml.etree import ElementTree as ET

PNS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
ANS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
EMU_PER_INCH = 914400
EMU_PER_PT = 12700

NOT_REVERSIBLE = (
    'theme',
    'slide master',
    'slide layout',
    'notes',
    'docProps',
    'thumbnails',
    'pictures',
    'charts',
    'groups',
    'OLE',
    'media',
    'built-in connectors',
    'endArrowType',
    'beginArrowType',
    'lineHead',
    'lineTail',
    'authoring connector kind',
    'inherited or theme colors',
    'ZIP compression and part order',
    'relationship ids',
    'shape ids',
    'animations',
    'transitions',
    'SmartArt',
    'roundRect adjustments',
    'core properties',
    'pptxgenjs extras',
    'xlsx',
)

_ARROW_KEYS = {'beginArrowType', 'endArrowType', 'lineHead', 'lineTail'}
_DASHES = {'solid', 'dash', 'dashDot', 'lgDash', 'lgDashDot', 'sysDash', 'sysDot'}
_ALIGNS = {'left': 'l', 'center': 'ctr', 'right': 'r', 'justify': 'just'}
_ALIGNS_XML = {value: key for key, value in _ALIGNS.items()}
_ANCHORS = {'top': 't', 'middle': 'ctr', 'bottom': 'b'}
_ANCHORS_XML = {value: key for key, value in _ANCHORS.items()}
_SHAPES = {'rect', 'roundRect', 'triangle', 'rtTriangle', 'chevron', 'downArrow', 'ellipse', 'line'}


def emu_inches(value):
    """Quantize inches onto the EMU grid. Whole inches stay ints."""
    emu = int(round(float(value) * EMU_PER_INCH))
    inches = emu / EMU_PER_INCH
    if inches == int(inches):
        return int(inches)
    return inches


def emu_points(value):
    points = int(round(float(value) * 100)) / 100
    if points == int(points):
        return int(points)
    return points


def quantize_rotation(value):
    rotated = int(round(float(value) * 60000)) / 60000
    rotated %= 360
    if rotated == int(rotated):
        return int(rotated)
    return rotated


def canon_color(value):
    if not isinstance(value, str):
        raise ValueError('color must be #RRGGBB or RRGGBB')
    raw = value[1:] if value.startswith('#') else value
    if len(raw) != 6 or any(char not in '0123456789abcdefABCDEF' for char in raw):
        raise ValueError('color must be #RRGGBB or RRGGBB')
    return raw.upper()


def _reject_arrows(value):
    if isinstance(value, dict):
        found = _ARROW_KEYS.intersection(value)
        if found:
            raise ValueError(f'built-in arrow styling is not reversible: {sorted(found)[0]}')
        for item in value.values():
            _reject_arrows(item)
    elif isinstance(value, list):
        for item in value:
            _reject_arrows(item)


def _q(prefix, local):
    return f'{{{ {"p": PNS, "a": ANS, "r": RNS}[prefix] }}}{local}'


def _sub(parent, prefix, local, attrib=None):
    return ET.SubElement(parent, _q(prefix, local), attrib or {})


def _child(parent, prefix, local):
    return parent.find(_q(prefix, local))


def _srgb(parent):
    fill = _child(parent, 'a', 'solidFill')
    if fill is None or len(fill) != 1 or fill[0].tag != _q('a', 'srgbClr'):
        return None
    value = fill[0].get('val')
    if value is None or len(value) != 6:
        return None
    return value.upper()


def _inches_from_emu(value):
    inches = int(value) / EMU_PER_INCH
    if inches == int(inches):
        return int(inches)
    return inches


def _points_from_sz(value):
    points = int(value) / 100
    if points == int(points):
        return int(points)
    return points


def _points_from_emu(value):
    points = int(value) / EMU_PER_PT
    if points == int(points):
        return int(points)
    return points


def _bool_attr(value):
    return '1' if value else '0'


def _is_true(value):
    return value in ('1', 'true')


def _run_spec(run, *, include_empty=False):
    props = _child(run, 'a', 'rPr')
    text = _child(run, 'a', 't')
    spec = {'text': '' if text is None or text.text is None else text.text}
    if props is not None:
        if props.get('sz') is not None:
            spec['fontSize'] = _points_from_sz(props.get('sz'))
        if props.get('b') is not None:
            spec['bold'] = _is_true(props.get('b'))
        if props.get('i') is not None:
            spec['italic'] = _is_true(props.get('i'))
        color = _srgb(props)
        if color is not None:
            spec['color'] = color
        latin = _child(props, 'a', 'latin')
        if latin is not None and latin.get('typeface'):
            spec['fontFace'] = latin.get('typeface')
    if spec == {'text': ''} and not include_empty:
        return None
    return spec


def _paragraph_spec(paragraph):
    spec = {}
    props = _child(paragraph, 'a', 'pPr')
    if props is not None and props.get('algn') in _ALIGNS_XML:
        spec['align'] = _ALIGNS_XML[props.get('algn')]
    runs = []
    for run in paragraph.findall(_q('a', 'r')):
        item = _run_spec(run, include_empty=True)
        if item is not None:
            runs.append(item)
    spec['runs'] = runs
    return spec


def _paragraphs_spec(tx_body):
    if tx_body is None:
        return None
    paragraphs = [_paragraph_spec(p) for p in tx_body.findall(_q('a', 'p'))]
    paragraphs = [p for p in paragraphs if p.get('runs')]
    return paragraphs or None


def _body_options(tx_body, options):
    if tx_body is None:
        return
    body = _child(tx_body, 'a', 'bodyPr')
    if body is None:
        return
    wrap = body.get('wrap')
    if wrap in ('square', 'none'):
        options['wrap'] = wrap
    if body.get('anchor') in _ANCHORS_XML:
        options['valign'] = _ANCHORS_XML[body.get('anchor')]
    for key, attr in (('marginLeft', 'lIns'), ('marginRight', 'rIns'), ('marginTop', 'tIns'), ('marginBottom', 'bIns')):
        if body.get(attr) is not None:
            options[key] = _inches_from_emu(body.get(attr))


def _line_spec(ln):
    if ln is None or _srgb(ln) is None:
        return None
    spec = {'color': _srgb(ln)}
    if ln.get('w') is not None:
        spec['width'] = _points_from_emu(ln.get('w'))
    dash = _child(ln, 'a', 'prstDash')
    if dash is not None and dash.get('val') and dash.get('val') != 'solid':
        spec['dashType'] = dash.get('val')
    return spec


def _xfrm_options(xfrm):
    off, ext = _child(xfrm, 'a', 'off'), _child(xfrm, 'a', 'ext')
    options = {
        'x': _inches_from_emu(off.get('x')),
        'y': _inches_from_emu(off.get('y')),
        'w': _inches_from_emu(ext.get('cx')),
        'h': _inches_from_emu(ext.get('cy')),
    }
    if xfrm.get('rot') not in (None, '0'):
        options['rotate'] = quantize_rotation(int(xfrm.get('rot')) / 60000)
    if _is_true(xfrm.get('flipH')):
        options['flipH'] = True
    if _is_true(xfrm.get('flipV')):
        options['flipV'] = True
    return options


def _read_sp(node):
    nv = _child(_child(node, 'p', 'nvSpPr'), 'p', 'cNvPr')
    props = _child(node, 'p', 'spPr')
    xfrm = _child(props, 'a', 'xfrm')
    geom = _child(props, 'a', 'prstGeom')
    if nv is None or xfrm is None or geom is None or geom.get('prst') is None:
        raise ValueError('shape is outside the reversible subset')
    options = _xfrm_options(xfrm)
    fill = _srgb(props)
    if fill is not None:
        options['fill'] = {'color': fill}
    line = _line_spec(_child(props, 'a', 'ln'))
    if line is not None:
        options['line'] = line
    tx_body = _child(node, 'p', 'txBody')
    _body_options(tx_body, options)
    paragraphs = _paragraphs_spec(tx_body)
    cnv = _child(_child(node, 'p', 'nvSpPr'), 'p', 'cNvSpPr')
    text_box = cnv is not None and _is_true(cnv.get('txBox'))
    prst = geom.get('prst')
    if prst == 'line':
        obj = {'op': 'line', 'name': nv.get('name') or '', 'options': options}
    elif text_box:
        obj = {'op': 'text', 'name': nv.get('name') or '', 'options': options}
        if paragraphs:
            obj['paragraphs'] = paragraphs
    else:
        obj = {'op': 'shape', 'name': nv.get('name') or '', 'shape': prst, 'options': options}
        if paragraphs:
            obj['paragraphs'] = paragraphs
    return obj, int(nv.get('id'))


def _read_table(node):
    nv = _child(_child(node, 'p', 'nvGraphicFramePr'), 'p', 'cNvPr')
    xfrm = _child(node, 'p', 'xfrm')
    tbl = node.find('.//' + _q('a', 'tbl'))
    if nv is None or xfrm is None or tbl is None:
        raise ValueError('graphic frame is outside the reversible subset')
    options = _xfrm_options(xfrm)
    cols = []
    grid = _child(tbl, 'a', 'tblGrid')
    for col in grid.findall(_q('a', 'gridCol')) if grid is not None else []:
        cols.append(_inches_from_emu(col.get('w')))
    if cols:
        options['colW'] = cols
    borders = []
    rows = []
    for tr in tbl.findall(_q('a', 'tr')):
        cells = []
        for tc in tr.findall(_q('a', 'tc')):
            cell = {}
            tc_pr = _child(tc, 'a', 'tcPr')
            fill = _srgb(tc_pr) if tc_pr is not None else None
            if fill is not None:
                cell['fill'] = fill
            paragraphs = _paragraphs_spec(_child(tc, 'a', 'txBody'))
            if paragraphs:
                cell['paragraphs'] = paragraphs
            if tc_pr is not None:
                for side in ('L', 'R', 'T', 'B'):
                    borders.append(_line_spec(_child(tc_pr, 'a', 'ln' + side)))
            cells.append(cell)
        rows.append({'h': _inches_from_emu(tr.get('h')), 'cells': cells})
    present = [b for b in borders if b is not None]
    if present and all(b == present[0] for b in borders):
        options['border'] = {'color': present[0]['color'], 'pt': present[0].get('width', present[0].get('pt'))}
        if 'width' in present[0]:
            options['border'] = {'color': present[0]['color'], 'pt': present[0]['width']}
    return {'op': 'table', 'name': nv.get('name') or '', 'rows': rows, 'options': options}, int(nv.get('id'))


def read_slide_xml(payload):
    """Return ``{'name', 'background', 'objects', 'ids'}`` for one slide part."""
    root = ET.fromstring(payload)
    csld = _child(root, 'p', 'cSld')
    if csld is None or _child(csld, 'p', 'spTree') is None:
        raise ValueError('p:cSld/p:spTree missing')
    slide = {'objects': [], 'ids': []}
    if csld.get('name'):
        slide['name'] = csld.get('name')
    bg = csld.find(_q('p', 'bg') + '/' + _q('p', 'bgPr'))
    color = _srgb(bg) if bg is not None else None
    if color is not None:
        slide['background'] = {'color': color}
    tree = _child(csld, 'p', 'spTree')
    for child in list(tree):
        if child.tag in (_q('p', 'nvGrpSpPr'), _q('p', 'grpSpPr')):
            continue
        if child.tag == _q('p', 'sp'):
            obj, shape_id = _read_sp(child)
        elif child.tag == _q('p', 'graphicFrame'):
            obj, shape_id = _read_table(child)
        else:
            raise ValueError('element is outside the reversible subset')
        slide['objects'].append(obj)
        slide['ids'].append(shape_id)
    return slide


def _write_color(parent, color):
    _sub(_sub(parent, 'a', 'solidFill'), 'a', 'srgbClr', {'val': canon_color(color)})


def _write_line(parent, line):
    attrib = {}
    if 'width' in line:
        attrib['w'] = str(int(round(float(line['width']) * EMU_PER_PT)))
    node = _sub(parent, 'a', 'ln', attrib)
    if 'color' in line:
        _write_color(node, line['color'])
    dash = line.get('dashType')
    if dash and dash != 'solid':
        _sub(node, 'a', 'prstDash', {'val': dash})
    return node


def _write_run(paragraph, run):
    node = _sub(paragraph, 'a', 'r')
    attrib = {}
    if 'fontSize' in run:
        attrib['sz'] = str(int(round(float(run['fontSize']) * 100)))
    if 'bold' in run:
        attrib['b'] = _bool_attr(run['bold'])
    if 'italic' in run:
        attrib['i'] = _bool_attr(run['italic'])
    props = _sub(node, 'a', 'rPr', attrib)
    if 'color' in run:
        _write_color(props, run['color'])
    if run.get('fontFace'):
        _sub(props, 'a', 'latin', {'typeface': run['fontFace']})
    text = _sub(node, 'a', 't')
    text.text = '' if run.get('text') is None else str(run['text'])
    if text.text[:1].isspace() or text.text[-1:].isspace():
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return node


def _write_paragraphs(parent, paragraphs):
    body = _sub(parent, 'a', 'txBody')
    options = parent  # placeholder replaced by caller via _write_tx_body
    return body


def _write_tx_body(parent, options, paragraphs, *, prefix='p'):
    body = _sub(parent, prefix, 'txBody')
    attrib = {}
    if options.get('wrap'):
        attrib['wrap'] = options['wrap']
    if options.get('valign'):
        attrib['anchor'] = _ANCHORS[options['valign']]
    for key, attr in (('marginLeft', 'lIns'), ('marginRight', 'rIns'), ('marginTop', 'tIns'), ('marginBottom', 'bIns')):
        if key in options:
            attrib[attr] = str(int(round(float(options[key]) * EMU_PER_INCH)))
    _sub(body, 'a', 'bodyPr', attrib)
    _sub(body, 'a', 'lstStyle')
    for paragraph in paragraphs or []:
        node = _sub(body, 'a', 'p')
        if paragraph.get('align'):
            _sub(node, 'a', 'pPr', {'algn': _ALIGNS[paragraph['align']]})
        for run in paragraph.get('runs') or []:
            _write_run(node, run)
    return body


def _write_xfrm(parent, options, *, prefix='a'):
    attrib = {}
    if options.get('rotate'):
        attrib['rot'] = str(int(round(float(options['rotate']) * 60000)) % 21600000)
    if options.get('flipH'):
        attrib['flipH'] = '1'
    if options.get('flipV'):
        attrib['flipV'] = '1'
    xfrm = _sub(parent, prefix, 'xfrm', attrib)
    _sub(xfrm, 'a', 'off', {
        'x': str(int(round(float(options['x']) * EMU_PER_INCH))),
        'y': str(int(round(float(options['y']) * EMU_PER_INCH))),
    })
    _sub(xfrm, 'a', 'ext', {
        'cx': str(int(round(float(options['w']) * EMU_PER_INCH))),
        'cy': str(int(round(float(options['h']) * EMU_PER_INCH))),
    })
    return xfrm


def _write_sp(parent, obj, shape_id):
    options = obj.get('options') or {}
    sp = _sub(parent, 'p', 'sp')
    nv = _sub(sp, 'p', 'nvSpPr')
    _sub(nv, 'p', 'cNvPr', {'id': str(shape_id), 'name': obj.get('name') or ''})
    cnv = {'txBox': '1'} if obj['op'] == 'text' else {}
    _sub(nv, 'p', 'cNvSpPr', cnv)
    _sub(nv, 'p', 'nvPr')
    props = _sub(sp, 'p', 'spPr')
    _write_xfrm(props, options)
    prst = 'line' if obj['op'] == 'line' else ('rect' if obj['op'] == 'text' else obj['shape'])
    _sub(_sub(props, 'a', 'prstGeom', {'prst': prst}), 'a', 'avLst')
    if obj['op'] == 'line':
        _sub(props, 'a', 'noFill')
    elif 'fill' in options:
        _write_color(props, options['fill']['color'])
    if 'line' in options:
        _write_line(props, options['line'])
    if obj.get('paragraphs'):
        _write_tx_body(sp, options, obj['paragraphs'])
    return sp


def _write_table(parent, obj, shape_id):
    options = obj['options']
    frame = _sub(parent, 'p', 'graphicFrame')
    nv = _sub(frame, 'p', 'nvGraphicFramePr')
    _sub(nv, 'p', 'cNvPr', {'id': str(shape_id), 'name': obj.get('name') or ''})
    _sub(_sub(nv, 'p', 'cNvGraphicFramePr'), 'a', 'graphicFrameLocks', {'noGrp': '1'})
    _sub(nv, 'p', 'nvPr')
    _write_xfrm(frame, options, prefix='p')
    graphic = _sub(frame, 'a', 'graphic')
    data = _sub(graphic, 'a', 'graphicData', {'uri': ANS + '/table'})
    tbl = _sub(data, 'a', 'tbl')
    _sub(tbl, 'a', 'tblPr')
    grid = _sub(tbl, 'a', 'tblGrid')
    for width in options['colW']:
        _sub(grid, 'a', 'gridCol', {'w': str(int(round(float(width) * EMU_PER_INCH)))})
    for row in obj['rows']:
        tr = _sub(tbl, 'a', 'tr', {'h': str(int(round(float(row['h']) * EMU_PER_INCH)))})
        for cell in row['cells']:
            tc = _sub(tr, 'a', 'tc')
            _write_tx_body(tc, cell, cell.get('paragraphs'), prefix='a')
            tc_pr = _sub(tc, 'a', 'tcPr')
            if 'border' in options:
                border = {'color': options['border']['color'], 'width': options['border']['pt']}
                for side in ('L', 'R', 'T', 'B'):
                    _write_line(tc_pr, border).tag  # line element is ln; rename below
                    tc_pr[-1].tag = _q('a', 'ln' + side)
            if cell.get('fill'):
                _write_color(tc_pr, cell['fill'])
    return frame


def _write_connector(parent, obj, shape_id):
    """Legacy cxnSp used only by the compatibility shim. Not a spec round-trip."""
    options = obj['options']
    node = _sub(parent, 'p', 'cxnSp')
    nv = _sub(node, 'p', 'nvCxnSpPr')
    _sub(nv, 'p', 'cNvPr', {'id': str(shape_id), 'name': obj.get('name') or ''})
    cnv = _sub(nv, 'p', 'cNvCxnSpPr')
    if obj.get('start'):
        _sub(cnv, 'a', 'stCxn', {'id': str(obj['start']['id']), 'idx': str(obj['start']['idx'])})
    if obj.get('end'):
        _sub(cnv, 'a', 'endCxn', {'id': str(obj['end']['id']), 'idx': str(obj['end']['idx'])})
    _sub(nv, 'p', 'nvPr')
    props = _sub(node, 'p', 'spPr')
    _write_xfrm(props, options)
    _sub(_sub(props, 'a', 'prstGeom', {'prst': 'line'}), 'a', 'avLst')
    _sub(props, 'a', 'noFill')
    if 'line' in options:
        _write_line(props, options['line'])
    return node


def write_slide_xml(slide, ids=None):
    """Serialize one canonical slide spec to a slide part payload."""
    _reject_arrows(slide)
    root = ET.Element(_q('p', 'sld'))
    attrib = {'name': slide['name']} if slide.get('name') else {}
    csld = _sub(root, 'p', 'cSld', attrib)
    if slide.get('background'):
        _write_color(_sub(_sub(csld, 'p', 'bg'), 'p', 'bgPr'), slide['background']['color'])
    tree = _sub(csld, 'p', 'spTree')
    nv = _sub(tree, 'p', 'nvGrpSpPr')
    _sub(nv, 'p', 'cNvPr', {'id': '1', 'name': ''})
    _sub(nv, 'p', 'cNvGrpSpPr')
    _sub(nv, 'p', 'nvPr')
    grp = _sub(_sub(tree, 'p', 'grpSpPr'), 'a', 'xfrm')
    _sub(grp, 'a', 'off', {'x': '0', 'y': '0'})
    _sub(grp, 'a', 'ext', {'cx': '0', 'cy': '0'})
    _sub(grp, 'a', 'chOff', {'x': '0', 'y': '0'})
    _sub(grp, 'a', 'chExt', {'cx': '0', 'cy': '0'})
    objects = objects_in_z_order(slide)
    if ids is None:
        ids = list(range(2, len(objects) + 2))
    if len(ids) != len(objects):
        raise ValueError('shape id count must match objects')
    for obj, shape_id in zip(objects, ids):
        if obj['op'] == 'connector':
            _write_connector(tree, obj, shape_id)
        elif obj['op'] == 'table':
            _write_table(tree, obj, shape_id)
        elif obj['op'] in ('shape', 'text', 'line'):
            _write_sp(tree, obj, shape_id)
        else:
            raise ValueError(f'unsupported object op: {obj["op"]}')
    _sub(_sub(root, 'p', 'clrMapOvr'), 'a', 'masterClrMapping')
    ET.register_namespace('p', PNS)
    ET.register_namespace('a', ANS)
    ET.register_namespace('r', RNS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _canon_run(run):
    spec = {'text': '' if run.get('text') is None else str(run['text'])}
    if 'fontSize' in run:
        spec['fontSize'] = emu_points(run['fontSize'])
    for key in ('bold', 'italic'):
        if key in run:
            if not isinstance(run[key], bool):
                raise ValueError(f'{key} must be a boolean')
            spec[key] = run[key]
    if 'color' in run:
        spec['color'] = canon_color(run['color'])
    if run.get('fontFace'):
        spec['fontFace'] = run['fontFace']
    return spec


def _canon_paragraphs(paragraphs):
    if not paragraphs:
        return None
    result = []
    for paragraph in paragraphs:
        if isinstance(paragraph, str):
            paragraph = {'runs': [{'text': paragraph}]}
        item = {'runs': [_canon_run(run) for run in paragraph.get('runs') or []]}
        if paragraph.get('align'):
            if paragraph['align'] not in _ALIGNS:
                raise ValueError('align must be left, center, right, or justify')
            item['align'] = paragraph['align']
        if item['runs']:
            result.append(item)
    return result or None


def _canon_options(options, *, line=False):
    _reject_arrows(options)
    spec = {key: emu_inches(options[key]) for key in ('x', 'y', 'w', 'h') if key in options}
    if 'rotate' in options and float(options['rotate']) % 360 != 0:
        spec['rotate'] = quantize_rotation(options['rotate'])
    if options.get('flipH') is True:
        spec['flipH'] = True
    if options.get('flipV') is True:
        spec['flipV'] = True
    if 'fill' in options and not line:
        spec['fill'] = {'color': canon_color(options['fill']['color'])}
    if 'line' in options:
        style = {}
        if 'color' in options['line']:
            style['color'] = canon_color(options['line']['color'])
        if 'width' in options['line']:
            style['width'] = emu_points(options['line']['width'])
        if options['line'].get('dashType') and options['line']['dashType'] != 'solid':
            if options['line']['dashType'] not in _DASHES:
                raise ValueError('dashType is not supported')
            style['dashType'] = options['line']['dashType']
        if style:
            spec['line'] = style
    if options.get('wrap'):
        spec['wrap'] = options['wrap']
    if options.get('valign'):
        if options['valign'] not in _ANCHORS:
            raise ValueError('valign must be top, middle, or bottom')
        spec['valign'] = options['valign']
    for key in ('marginLeft', 'marginRight', 'marginTop', 'marginBottom'):
        if key in options:
            spec[key] = emu_inches(options[key])
    if 'colW' in options:
        spec['colW'] = [emu_inches(v) for v in options['colW']]
    if 'border' in options:
        spec['border'] = {'color': canon_color(options['border']['color']), 'pt': emu_points(options['border']['pt'])}
    return spec


def _cell_paragraphs(cell):
    if 'paragraphs' in cell:
        return _canon_paragraphs(cell['paragraphs'])
    if 'text' in cell:
        paragraphs = []
        for line in str(cell['text']).split('\n'):
            run = {'text': line}
            for key in ('bold', 'italic', 'color', 'fontSize', 'fontFace'):
                if key in cell:
                    run[key] = cell[key]
            paragraphs.append({'runs': [run], **({'align': cell['align']} if 'align' in cell else {})})
        return _canon_paragraphs(paragraphs)
    return None


def canonical_object(obj):
    _reject_arrows(obj)
    op = obj.get('op')
    if op == 'connector':
        raise ValueError('authoring connector kind is not a reversible object; expand it to a line and triangle')
    if op not in ('shape', 'text', 'line', 'table'):
        raise ValueError(f'unsupported object op: {op}')
    spec = {'op': op, 'name': obj.get('name') or '', 'options': _canon_options(obj.get('options') or {}, line=op == 'line')}
    if op == 'shape':
        if obj.get('shape') not in _SHAPES or obj.get('shape') == 'line':
            raise ValueError('shape must be a supported prstGeom')
        spec['shape'] = obj['shape']
    paragraphs = _canon_paragraphs(obj.get('paragraphs'))
    if paragraphs and op != 'line':
        spec['paragraphs'] = paragraphs
    if op == 'table':
        rows = []
        for row in obj.get('rows') or []:
            cells = []
            for cell in row.get('cells') or []:
                item = {}
                if cell.get('fill'):
                    item['fill'] = canon_color(cell['fill'] if isinstance(cell['fill'], str) else cell['fill']['color'])
                body = _cell_paragraphs(cell)
                if body:
                    item['paragraphs'] = body
                cells.append(item)
            rows.append({'h': emu_inches(row['h']), 'cells': cells})
        spec['rows'] = rows
    return spec


def objects_in_z_order(slide):
    """Return the single object list for one slide.

    Index 0 is the back. That index order is ``p:spTree`` child order and the
    order PptxGenJS would add shapes. Optional ``behind`` is prepended and
    ``inFront`` is appended; both are conveniences, not stored fields.
    """
    if not isinstance(slide, dict):
        raise ValueError('a slide is one object with an objects array')
    for key in ('back', 'front', 'items'):
        if key in slide:
            raise ValueError('z-order is the objects array (spTree order); behind and inFront normalize into that array')
    for key in ('behind', 'inFront', 'objects'):
        if key in slide and not isinstance(slide[key], list):
            raise ValueError(f'{key} must be an array')
    return [*(slide.get('behind') or []), *(slide.get('objects') or []), *(slide.get('inFront') or [])]


def canonical_spec(spec):
    """Return the lossless subset form of one deck JSON object, or one slide."""
    _reject_arrows(spec)
    if isinstance(spec, list):
        raise ValueError('a deck is one JSON object with slides[], not a list of slide documents')
    if 'slides' in spec:
        if not isinstance(spec['slides'], list):
            raise ValueError('slides must be an array')
        return {
            'width': emu_inches(spec.get('width', 10)),
            'height': emu_inches(spec.get('height', 7.5)),
            'slides': [canonical_spec(slide) for slide in spec['slides']],
        }
    slide = {'objects': [canonical_object(obj) for obj in objects_in_z_order(spec)]}
    if spec.get('name'):
        slide['name'] = spec['name']
    if spec.get('background'):
        slide['background'] = {'color': canon_color(spec['background']['color'])}
    return slide


def describe_slide(payload):
    """Best-effort drawable list. Unknown elements are ``{'op': 'opaque'}``.

    The reversible reader raises on those elements. Package inspection and the
    compatibility shim still need to walk Marp slides that contain pictures.
    """
    root = ET.fromstring(payload)
    csld = _child(root, 'p', 'cSld')
    tree = _child(csld, 'p', 'spTree') if csld is not None else None
    if tree is None:
        raise ValueError('p:cSld/p:spTree missing')
    drawables = []
    reversible = True
    for child in list(tree):
        if child.tag in (_q('p', 'nvGrpSpPr'), _q('p', 'grpSpPr')):
            continue
        if child.tag == _q('p', 'sp'):
            try:
                obj, shape_id = _read_sp(child)
                drawables.append({**obj, 'id': shape_id})
            except ValueError:
                reversible = False
                drawables.append({'op': 'opaque', 'id': _maybe_id(child), 'name': _maybe_name(child), 'text': _texts(child)})
        elif child.tag == _q('p', 'graphicFrame'):
            try:
                obj, shape_id = _read_table(child)
                drawables.append({**obj, 'id': shape_id})
            except ValueError:
                reversible = False
                drawables.append({'op': 'opaque', 'id': _maybe_id(child), 'name': _maybe_name(child), 'text': ''})
        elif child.tag == _q('p', 'pic'):
            reversible = False
            drawables.append({'op': 'picture', 'id': _maybe_id(child), 'name': _maybe_name(child)})
        elif child.tag == _q('p', 'cxnSp'):
            reversible = False
            drawables.append(_connector_drawable(child))
        else:
            reversible = False
            drawables.append({'op': 'opaque', 'id': _maybe_id(child), 'name': _maybe_name(child), 'text': ''})
    background = None
    bg = csld.find(_q('p', 'bg') + '/' + _q('p', 'bgPr')) if csld is not None else None
    color = _srgb(bg) if bg is not None else None
    if color is not None:
        background = {'color': color}
    return {'name': csld.get('name') if csld is not None else None, 'background': background,
            'drawables': drawables, 'reversible': reversible}


def _maybe_id(node):
    nv = node.find('.//' + _q('p', 'cNvPr'))
    if nv is not None and str(nv.get('id', '')).isdigit():
        return int(nv.get('id'))
    return None


def _maybe_name(node):
    nv = node.find('.//' + _q('p', 'cNvPr'))
    return '' if nv is None or not nv.get('name') else nv.get('name')


def _texts(node):
    return '\n'.join((item.text or '') for item in node.findall('.//' + _q('a', 't')))


def _connector_drawable(node):
    nv = node.find('.//' + _q('p', 'cNvPr'))
    props = _child(node, 'p', 'spPr')
    xfrm = _child(props, 'a', 'xfrm') if props is not None else None
    options = _xfrm_options(xfrm) if xfrm is not None and _child(xfrm, 'a', 'off') is not None else {'x': 0, 'y': 0, 'w': 0, 'h': 0}
    line = _line_spec(_child(props, 'a', 'ln')) if props is not None else None
    if line:
        options['line'] = line
    start = node.find('.//' + _q('a', 'stCxn'))
    end = node.find('.//' + _q('a', 'endCxn'))
    obj = {'op': 'connector', 'id': int(nv.get('id')) if nv is not None and str(nv.get('id', '')).isdigit() else None,
           'name': '' if nv is None else (nv.get('name') or ''), 'options': options}
    if start is not None:
        obj['start'] = {'id': int(start.get('id')), 'idx': int(start.get('idx') or 0)}
    if end is not None:
        obj['end'] = {'id': int(end.get('id')), 'idx': int(end.get('idx') or 0)}
    return obj


def public_slide(slide):
    """Drop derived ids from a reader result."""
    return {key: value for key, value in slide.items() if key != 'ids'}


def normalized_xml(payload):
    return ET.canonicalize(payload.decode() if isinstance(payload, bytes) else payload)


def xml_round_trip(slide):
    """Write, read, and write a slide. Both specs and both payloads match."""
    spec = canonical_spec(slide)
    first = write_slide_xml(spec)
    read = public_slide(read_slide_xml(first))
    if read != spec:
        raise AssertionError('JSON → XML → JSON did not match the canonical spec')
    second = write_slide_xml(read)
    if normalized_xml(first) != normalized_xml(second):
        raise AssertionError('XML → JSON → XML was not stable')
    return spec
