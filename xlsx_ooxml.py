"""Apply and read the supported workbook subset in xlsx XML.

ExcelJS writes values, formulas, sheet names, and autofilter. After the writer,
this module sets ``xl/styles.xml`` and each cell's style index so the package
carries 罫線, number formats, and alignment. Reading the XML back is the check
that does not need Excel or a browser.
"""
import io
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from xlsx_spec import column_name

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
_BUILTINS = {
    0: 'General',
    1: '0',
    2: '0.00',
    3: '#,##0',
    4: '#,##0.00',
    9: '0%',
    10: '0.00%',
    11: '0.00E+00',
    49: '@',
}
_BUILTIN_IDS = {code: index for index, code in _BUILTINS.items()}


def _q(tag):
    return f'{{{NS}}}{tag}'


def _serialize(root):
    """Write default spreadsheet tags, without a namespace prefix on every element."""
    saved = dict(ET._namespace_map)
    try:
        ET.register_namespace('', NS)
        ET.register_namespace('r', RNS)
        ET.register_namespace('mc', 'http://schemas.openxmlformats.org/markup-compatibility/2006')
        ET.register_namespace('x14ac', 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac')
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)
    finally:
        ET._namespace_map.clear()
        ET._namespace_map.update(saved)


def _escape(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def _style_key(cell):
    if not cell:
        return ('General', '', '')
    return (cell.get('z') or 'General', cell.get('border') or '', cell.get('align') or '')


def _styles_xml(keys):
    formats = []
    next_id = 164
    ids = {}
    for code, _border, _align in keys:
        if code in ids or code == 'General':
            continue
        if code in _BUILTIN_IDS:
            ids[code] = _BUILTIN_IDS[code]
        else:
            ids[code] = next_id
            formats.append((next_id, code))
            next_id += 1
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             f'<styleSheet xmlns="{NS}">']
    if formats:
        parts.append(f'<numFmts count="{len(formats)}">')
        for fmt_id, code in formats:
            parts.append(f'<numFmt numFmtId="{fmt_id}" formatCode="{_escape(code)}"/>')
        parts.append('</numFmts>')
    parts.append(
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border>'
        '<left style="thin"><color rgb="FF000000"/></left>'
        '<right style="thin"><color rgb="FF000000"/></right>'
        '<top style="thin"><color rgb="FF000000"/></top>'
        '<bottom style="thin"><color rgb="FF000000"/></bottom>'
        '<diagonal/>'
        '</border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(keys)}">'
    )
    for code, border, align in keys:
        attrs = [
            f'numFmtId="{ids.get(code, 0)}"', 'fontId="0"', 'fillId="0"',
            f'borderId="{1 if border else 0}"', 'xfId="0"',
        ]
        if code != 'General':
            attrs.append('applyNumberFormat="1"')
        if border:
            attrs.append('applyBorder="1"')
        if align:
            attrs.append('applyAlignment="1"')
        inner = f'<alignment horizontal="{align}"/>' if align else ''
        parts.append(f'<xf {" ".join(attrs)}>{inner}</xf>')
    parts.append(
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '</styleSheet>'
    )
    return ''.join(parts).encode('utf-8')


def _sheet_parts(archive):
    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    targets = {}
    for rel in rels:
        if rel.tag == f'{{{PKG}}}Relationship':
            targets[rel.get('Id')] = rel.get('Target')
    found = []
    for sheet in workbook.iter(_q('sheet')):
        target = targets[sheet.get(f'{{{RNS}}}id')]
        target = target.lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        found.append((sheet.get('name'), target))
    return found


def _content_cell(element):
    formula = element.find(_q('f'))
    if formula is not None and (formula.text or '').strip():
        return True
    if element.find(_q('v')) is not None or element.find(_q('is')) is not None:
        return True
    return False


def _rewrite_sheet(payload, sheet):
    root = ET.fromstring(payload)
    sheet_data = root.find(_q('sheetData'))
    if sheet_data is None:
        raise ValueError(f'{sheet["name"]} has no sheetData')
    old = {}
    for row in list(sheet_data):
        for cell in list(row):
            ref = cell.get('r')
            if ref:
                old[ref] = cell
        sheet_data.remove(row)
    keys = []
    index = {}
    rows = sheet['rows']
    for row in rows:
        for cell in row:
            key = _style_key(cell)
            if key not in index:
                index[key] = len(keys)
                keys.append(key)
    if ('General', '', '') not in index:
        keys.insert(0, ('General', '', ''))
        index = {key: position for position, key in enumerate(keys)}
    width = len(rows[0])
    height = len(rows)
    for row_number, row in enumerate(rows, 1):
        row_el = ET.SubElement(sheet_data, _q('row'), {'r': str(row_number)})
        for column, cell in enumerate(row, 1):
            ref = f'{column_name(column)}{row_number}'
            node = old.pop(ref, None)
            if node is None:
                if cell and ('v' in cell or 'f' in cell):
                    raise ValueError(f'{sheet["name"]} {ref} is missing from the workbook writer')
                if not cell or _style_key(cell) == ('General', '', ''):
                    continue
                node = ET.Element(_q('c'))
            elif cell and ('v' in cell or 'f' in cell) and not _content_cell(node):
                raise ValueError(f'{sheet["name"]} {ref} has no value in the workbook writer')
            node.set('r', ref)
            node.set('s', str(index[_style_key(cell)]))
            row_el.append(node)
    ref = f'A1:{column_name(width)}{height}'
    dimension = root.find(_q('dimension'))
    if dimension is None:
        root.insert(0, ET.Element(_q('dimension'), {'ref': ref}))
    else:
        dimension.set('ref', ref)
    for child in list(root):
        if child.tag == _q('autoFilter'):
            root.remove(child)
    if sheet.get('autofilter'):
        if sheet['autofilter'] != ref:
            raise ValueError('autofilter ref does not cover the sheet')
        filter_el = ET.Element(_q('autoFilter'), {'ref': ref})
        children = list(root)
        for position, child in enumerate(children):
            if child.tag == _q('sheetData'):
                root.insert(position + 1, filter_el)
                break
    return _serialize(root), keys


def canonicalize(payload, spec):
    """Return xlsx bytes whose styles match ``spec`` without changing cell values."""
    with ZipFile(io.BytesIO(payload)) as archive:
        parts = _sheet_parts(archive)
        if [name for name, _path in parts] != [sheet['name'] for sheet in spec['sheets']]:
            raise ValueError('workbook sheet names do not match the spec')
        if 'xl/styles.xml' not in archive.namelist():
            raise ValueError('workbook has no styles part')
        replacements = {}
        style_keys = [('General', '', '')]
        for sheet, (_name, path) in zip(spec['sheets'], parts):
            xml, keys = _rewrite_sheet(archive.read(path), sheet)
            for key in keys:
                if key not in style_keys:
                    style_keys.append(key)
            replacements[path] = xml
        # Style indexes were assigned per sheet. Rebuild once for the whole book
        # and patch the s attributes to the shared list.
        shared = {key: str(position) for position, key in enumerate(style_keys)}
        for sheet, (_name, path) in zip(spec['sheets'], parts):
            root = ET.fromstring(replacements[path])
            for cell in root.iter(_q('c')):
                ref = cell.get('r')
                row_number, column = _address_numbers(ref)
                source = sheet['rows'][row_number - 1][column - 1]
                cell.set('s', shared[_style_key(source)])
            replacements[path] = _serialize(root)
        replacements['xl/styles.xml'] = _styles_xml(style_keys)
        buffer = io.BytesIO()
        with ZipFile(buffer, 'w') as output:
            for entry in archive.infolist():
                output.writestr(entry, replacements.get(entry.filename, archive.read(entry.filename)))
    return buffer.getvalue()


def _address_numbers(ref):
    match = re.fullmatch(r'([A-Z]+)([1-9]\d*)', ref)
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - 64
    return int(match.group(2)), column


def _shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    values = []
    for item in root.findall(_q('si')):
        values.append(''.join(text.text or '' for text in item.iter(_q('t'))))
    return values


def _xf_table(styles):
    formats = dict(_BUILTINS)
    for fmt in styles.iter(_q('numFmt')):
        formats[int(fmt.get('numFmtId'))] = fmt.get('formatCode')
    borders = []
    for border in styles.find(_q('borders')).findall(_q('border')):
        sides = {side: border.find(_q(side)) for side in ('left', 'right', 'top', 'bottom')}
        thin = all(node is not None and node.get('style') == 'thin' for node in sides.values())
        black = thin and all((node.find(_q('color')).get('rgb') or '').upper() == 'FF000000' for node in sides.values())
        borders.append('thin' if black else '')
    xfs = []
    for xf in styles.find(_q('cellXfs')).findall(_q('xf')):
        code = formats.get(int(xf.get('numFmtId') or 0), 'General')
        border_id = int(xf.get('borderId') or 0)
        alignment = xf.find(_q('alignment'))
        align = alignment.get('horizontal') if alignment is not None else ''
        xfs.append((code, borders[border_id] if border_id < len(borders) else '', align or ''))
    return xfs


def _cell_value(element, strings):
    formula = element.find(_q('f'))
    if formula is not None and formula.text:
        return {'f': formula.text}
    kind = element.get('t')
    if kind == 'inlineStr':
        text = ''.join(node.text or '' for node in element.iter(_q('t')))
        return {'v': text} if text != '' else {}
    value = element.find(_q('v'))
    if value is None or value.text is None:
        return {}
    if kind == 's':
        return {'v': strings[int(value.text)]}
    if kind in (None, 'n'):
        text = value.text
        if re.fullmatch(r'-?\d+', text):
            return {'v': int(text)}
        return {'v': float(text)}
    return {'v': value.text}


def read_spec(payload):
    """Read the supported subset back from workbook XML."""
    with ZipFile(io.BytesIO(payload)) as archive:
        styles = _xf_table(ET.fromstring(archive.read('xl/styles.xml')))
        strings = _shared_strings(archive)
        sheets = []
        for name, path in _sheet_parts(archive):
            root = ET.fromstring(archive.read(path))
            found = {}
            max_row = max_column = 0
            dimension = root.find(_q('dimension'))
            if dimension is not None and dimension.get('ref'):
                end = dimension.get('ref').split(':')[-1]
                max_row, max_column = _address_numbers(end)
            for cell in root.iter(_q('c')):
                ref = cell.get('r')
                row_number, column = _address_numbers(ref)
                max_row = max(max_row, row_number)
                max_column = max(max_column, column)
                item = _cell_value(cell, strings)
                xf = styles[int(cell.get('s') or 0)]
                code, border, align = xf
                if code and code != 'General':
                    item['z'] = code
                if border:
                    item['border'] = border
                if align:
                    item['align'] = align
                found[(row_number, column)] = item or None
            rows = []
            for row_number in range(1, max_row + 1):
                rows.append([found.get((row_number, column)) or None for column in range(1, max_column + 1)])
            sheet = {'name': name, 'rows': rows}
            auto = root.find(_q('autoFilter'))
            if auto is not None and auto.get('ref'):
                sheet['autofilter'] = auto.get('ref')
            sheets.append(sheet)
    return {'sheets': sheets}
