"""CSV bytes to a canonical workbook spec.

Encodings are detected here. The workbook file stores Unicode, so Excel does
not have to guess Shift_JIS when it opens the xlsx.
"""
import csv
import io
import re
from pathlib import Path

_UNSUPPORTED = {'merge', 'merges', 'mergeCells', 'image', 'images', 'drawing', 'conditional', 'conditionalFormatting'}
_ALIGN = {'left', 'center', 'right'}
_ENCODINGS = ('auto', 'utf-8', 'utf-8-sig', 'shift_jis', 'cp932')
_NUMBER = re.compile(r'-?(?:0|[1-9]\d*)(?:\.\d+)?\Z')
_ADDRESS = re.compile(r'([A-Z]+)([1-9]\d*)\Z')


def decode_csv_bytes(data, encoding='auto'):
    """Return ``(text, encoding)``.

    UTF-8, with or without a BOM, wins when the bytes are valid UTF-8. That is
    the file Excel on Japanese Windows otherwise opens as Shift_JIS. Invalid
    UTF-8 is decoded as Shift_JIS or CP932. When those two disagree, CP932
    (the Windows mapping Excel writes) is used.
    """
    if encoding not in _ENCODINGS:
        raise ValueError('encoding must be auto, utf-8, utf-8-sig, shift_jis, or cp932')
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError('CSV input must be bytes')
    data = bytes(data)
    if encoding != 'auto':
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            raise ValueError(f'CSV is not valid {encoding}') from exc
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig'), 'utf-8-sig'
    try:
        return data.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        pass
    shift = cp = None
    try:
        shift = data.decode('shift_jis')
    except UnicodeDecodeError:
        pass
    try:
        cp = data.decode('cp932')
    except UnicodeDecodeError:
        pass
    if shift is None and cp is None:
        raise ValueError('CSV encoding is not UTF-8, UTF-8 with BOM, Shift_JIS, or CP932')
    if cp is None:
        return shift, 'shift_jis'
    if shift is None or shift != cp:
        return cp, 'cp932'
    return shift, 'shift_jis'


def column_name(index):
    if index < 1:
        raise ValueError('column index starts at 1')
    name = ''
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def parse_address(address):
    match = _ADDRESS.fullmatch(str(address).strip().upper())
    if not match:
        raise ValueError(f'cell address {address!r} is invalid')
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - 64
    return int(match.group(2)), column


def _reject(value):
    if isinstance(value, dict):
        found = _UNSUPPORTED.intersection(value)
        if found:
            name = sorted(found)[0]
            raise ValueError(f'{name} is outside the xlsx subset')
        for item in value.values():
            _reject(item)
    elif isinstance(value, list):
        for item in value:
            _reject(item)


def _number(text):
    if not _NUMBER.fullmatch(text):
        return None
    digits = text[1:] if text.startswith('-') else text
    whole = digits.split('.', 1)[0]
    if len(whole) > 15:
        return None
    if '.' in text:
        return float(text)
    return int(text)


def _cell_from_field(text, column, *, borders):
    if column.get('clear'):
        style_border = False
        num_fmt = None
        align = None
    else:
        style_border = borders and column.get('border', True) is not False
        num_fmt = column.get('numFmt')
        align = column.get('align')
        if align is not None and align not in _ALIGN:
            raise ValueError('align must be left, center, or right')
        if num_fmt is not None and not isinstance(num_fmt, str):
            raise ValueError('numFmt must be a format string')
    cell = {}
    if text.startswith('='):
        formula = text[1:].strip()
        if not formula:
            raise ValueError('a formula cell is empty')
        cell['f'] = formula
    elif text != '':
        number = _number(text)
        cell['v'] = text if number is None else number
    if num_fmt and ('v' in cell or 'f' in cell) and not (isinstance(cell.get('v'), str) and num_fmt != '@'):
        cell['z'] = num_fmt
    if align and ('v' in cell or 'f' in cell):
        cell['align'] = align
    if style_border:
        cell['border'] = 'thin'
    return cell or None


def _rectangular(rows):
    if not rows or not any(any(field != '' for field in row) for row in rows):
        raise ValueError('CSV has no cells')
    width = max(len(row) for row in rows)
    if width < 1 or width > 256 or len(rows) > 10000:
        raise ValueError('CSV must be 1..256 columns and at most 10000 rows')
    return [row + [''] * (width - len(row)) for row in rows]


def _check_sheet_name(name):
    if not isinstance(name, str) or not name or len(name) > 31:
        raise ValueError('sheet name must be 1..31 characters')
    if any(char in name for char in '\\/?*[]:'):
        raise ValueError(f'sheet name {name!r} contains a character Excel rejects')
    return name


def sheet_from_csv(name, data, *, borders=False, autofilter=False, columns=None, formulas=None, encoding='auto'):
    """Build one sheet from CSV bytes or text."""
    if isinstance(data, str):
        text, detected = data, 'utf-8'
    else:
        text, detected = decode_csv_bytes(data, encoding)
    table = _rectangular(list(csv.reader(io.StringIO(text, newline=''))))
    styles = list(columns or [])
    for column in styles:
        if not isinstance(column, dict):
            raise ValueError('column format must be an object')
        _reject(column)
    grid = []
    for row in table:
        grid.append([
            _cell_from_field(field, styles[index] if index < len(styles) else {}, borders=borders)
            for index, field in enumerate(row)
        ])
    for item in formulas or []:
        if not isinstance(item, dict) or 'cell' not in item or 'formula' not in item:
            raise ValueError('formula entries need cell and formula')
        _reject(item)
        formula = str(item['formula']).strip()
        if formula.startswith('='):
            formula = formula[1:].strip()
        if not formula:
            raise ValueError('a formula cell is empty')
        row_number, column = parse_address(item['cell'])
        if row_number > len(grid) or column > len(grid[0]):
            raise ValueError(f'formula {item["cell"]} is outside the CSV')
        current = dict(grid[row_number - 1][column - 1] or {})
        current.pop('v', None)
        current['f'] = formula
        grid[row_number - 1][column - 1] = current or None
    sheet = {'name': _check_sheet_name(name), 'rows': grid, 'encoding': detected}
    if autofilter:
        sheet['autofilter'] = f'A1:{column_name(len(grid[0]))}{len(grid)}'
    return sheet


def canonical_sheet(sheet):
    """Drop the encoding tag. Cell objects keep only stored fields."""
    rows = []
    for row in sheet['rows']:
        line = []
        for cell in row:
            if not cell:
                line.append(None)
                continue
            item = {}
            if 'f' in cell:
                item['f'] = cell['f']
            elif 'v' in cell:
                item['v'] = cell['v']
            if cell.get('z'):
                item['z'] = cell['z']
            if cell.get('align'):
                item['align'] = cell['align']
            if cell.get('border'):
                item['border'] = cell['border']
            line.append(item or None)
        rows.append(line)
    result = {'name': sheet['name'], 'rows': rows}
    if sheet.get('autofilter'):
        result['autofilter'] = sheet['autofilter']
    return result


def workbook_from_sheets(sheets):
    names = [sheet['name'] for sheet in sheets]
    if len(names) != len(set(names)):
        raise ValueError('sheet names must be unique')
    if not sheets:
        raise ValueError('at least one sheet is required')
    return {'sheets': [canonical_sheet(sheet) for sheet in sheets]}


def workbook_from_spec(spec, base):
    """Load a JSON spec. CSV paths are relative to ``base``."""
    if not isinstance(spec, dict):
        raise ValueError('workbook spec must be an object')
    _reject(spec)
    sheets = spec.get('sheets')
    if not isinstance(sheets, list) or not sheets:
        raise ValueError('at least one sheet is required')
    built = []
    base = Path(base)
    for entry in sheets:
        if not isinstance(entry, dict) or 'name' not in entry:
            raise ValueError('each sheet needs a name')
        borders = bool(entry['borders']) if 'borders' in entry else bool(spec.get('borders'))
        autofilter = bool(entry['autofilter']) if 'autofilter' in entry else bool(spec.get('autofilter'))
        if 'csv' in entry and 'rows' in entry:
            raise ValueError('use either csv or rows, not both')
        if 'csv' in entry:
            path = base / entry['csv']
            data = path.read_bytes()
        elif 'rows' in entry:
            buffer = io.StringIO(newline='')
            csv.writer(buffer, lineterminator='\n').writerows(entry['rows'])
            data = buffer.getvalue()
        else:
            raise ValueError(f'sheet {entry["name"]!r} needs csv or rows')
        built.append(sheet_from_csv(
            entry['name'], data, borders=borders, autofilter=autofilter,
            columns=entry.get('columns'), formulas=entry.get('formulas'),
            encoding=entry.get('encoding', spec.get('encoding', 'auto')),
        ))
    return workbook_from_sheets(built)
