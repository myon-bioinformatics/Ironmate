"""CSV encoding and xlsx Open XML checks. No spreadsheet app."""
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from xlsx_csv import convert_paths, main, write_csv_workbook
from xlsx_ooxml import read_spec
from xlsx_render import read_workbook, write_workbook
from xlsx_spec import decode_csv_bytes, sheet_from_csv, workbook_from_sheets, workbook_from_spec

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _book():
    text = '名前,金額,税込\n"東京,本店",1200,=B2*1.1\n'
    columns = [{}, {'numFmt': '#,##0', 'align': 'right'}, {'numFmt': '0.000', 'align': 'left'}]
    sales = sheet_from_csv('売上', text.encode('cp932'), borders=True, autofilter=True, columns=columns)
    notes = sheet_from_csv('メモ', '区分,内容\nA,\n'.encode('utf-8'), borders=True, autofilter=True,
                           columns=[{'align': 'center'}, {'clear': True}])
    return workbook_from_sheets([sales, notes])


def test_encoding_detection_covers_utf8_bom_shift_jis_and_cp932():
    text = '名前,値\n東京,1\n'
    assert decode_csv_bytes(text.encode('utf-8')) == (text, 'utf-8')
    assert decode_csv_bytes(b'\xef\xbb\xbf' + text.encode('utf-8')) == (text, 'utf-8-sig')
    assert decode_csv_bytes(text.encode('shift_jis')) == (text, 'shift_jis')
    special = '髙島,①\n'
    assert decode_csv_bytes(special.encode('cp932')) == (special, 'cp932')
    # 0x8160 is the Windows fullwidth tilde when the two codecs disagree.
    assert decode_csv_bytes(b'\x81\x60') == ('～', 'cp932')
    with pytest.raises(ValueError, match='Shift_JIS'):
        decode_csv_bytes(b'\x81')


def test_numbers_formulas_borders_and_clear_cells():
    sheet = sheet_from_csv(
        'S', 'code,n\n001,=A1\n', borders=True, columns=[{'clear': True}, {'numFmt': '0', 'align': 'right'}],
    )
    code, formula = sheet['rows'][1]
    assert code == {'v': '001'}
    assert formula['f'] == 'A1'
    assert formula['z'] == '0' and formula['align'] == 'right' and formula['border'] == 'thin'
    assert 'border' not in code


def test_rejected_features_and_sheet_names():
    with pytest.raises(ValueError, match='merge'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']], 'merges': ['A1:B1']}]}, '.')
    with pytest.raises(ValueError, match='image'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']], 'images': ['a.png']}]}, '.')
    with pytest.raises(ValueError, match='conditional'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']]}], 'conditionalFormatting': []}, '.')
    with pytest.raises(ValueError, match='Excel rejects'):
        sheet_from_csv('bad:name', 'a\n')


@pytest.mark.parametrize('engine', ['exceljs', 'sheetjs'])
def test_workbook_xml_round_trip(engine):
    spec = _book()
    payload = write_workbook(spec, engine)
    assert read_spec(payload) == spec
    with ZipFile(BytesIO(payload)) as archive:
        workbook = archive.read('xl/workbook.xml')
        styles = archive.read('xl/styles.xml')
        sheets = [name for name in archive.namelist() if name.startswith('xl/worksheets/sheet')]
    assert '売上' in workbook.decode('utf-8') and 'メモ' in workbook.decode('utf-8')
    root = ET.fromstring(archive_sheet(payload, 0))
    formula = root.find('.//m:f', NS)
    assert formula is not None and formula.text == 'B2*1.1'
    assert root.find('m:autoFilter', NS).get('ref') == 'A1:C2'
    bordered = [cell for cell in root.findall('.//m:c', NS) if cell.get('s') not in (None, '0')]
    assert bordered
    style_root = ET.fromstring(styles)
    thin = [item for item in style_root.findall('.//m:border', NS) if item.find('m:left', NS).get('style') == 'thin']
    assert len(thin) == 1
    assert thin[0].find('m:left/m:color', NS).get('rgb') == 'FF000000'
    assert style_root.find('.//m:numFmt[@formatCode="0.000"]', NS) is not None
    assert style_root.find('.//m:alignment[@horizontal="right"]', NS) is not None
    assert len(sheets) == 2


def archive_sheet(payload, index):
    with ZipFile(BytesIO(payload)) as archive:
        return archive.read(f'xl/worksheets/sheet{index + 1}.xml')


def test_engines_read_each_others_packages():
    spec = _book()
    from_excel = write_workbook(spec, 'exceljs')
    from_sheet = write_workbook(spec, 'sheetjs')
    assert _data(read_workbook(from_excel, 'sheetjs')) == _data(spec)
    excel_view = read_workbook(from_sheet, 'exceljs')
    assert excel_view == spec


def _data(spec):
    """Fields SheetJS community returns: values, formulas, number formats, autofilter."""
    sheets = []
    for sheet in spec['sheets']:
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
                line.append(item or None)
            rows.append(line)
        item = {'name': sheet['name'], 'rows': rows}
        if sheet.get('autofilter'):
            item['autofilter'] = sheet['autofilter']
        sheets.append(item)
    return {'sheets': sheets}


def test_cli_writes_shift_jis_csv(tmp_path):
    source = tmp_path / 'costs.csv'
    source.write_bytes('名前,金額\n東京,12\n'.encode('shift_jis'))
    output = tmp_path / 'book.xlsx'
    main(['--border', '--autofilter', '-o', str(output), f'売上={source}'])
    spec = read_spec(output.read_bytes())
    assert spec['sheets'][0]['name'] == '売上'
    assert spec['sheets'][0]['rows'][1][0]['v'] == '東京'
    assert spec['sheets'][0]['rows'][1][1]['v'] == 12
    assert spec['sheets'][0]['autofilter'] == 'A1:B2'
    assert spec['sheets'][0]['rows'][0][0]['border'] == 'thin'
    output.write_bytes(b'exists')
    with pytest.raises(ValueError, match='new file'):
        write_csv_workbook(output, spec)


def test_spec_file_resolves_csv_encoding(tmp_path):
    csv_path = tmp_path / 'notes.csv'
    csv_path.write_bytes('項目\n髙島\n'.encode('cp932'))
    spec_path = tmp_path / 'book.json'
    spec_path.write_text(json.dumps({
        'borders': True,
        'sheets': [{'name': 'メモ', 'csv': 'notes.csv', 'columns': [{'align': 'left'}]}],
    }), encoding='utf-8')
    output = tmp_path / 'out.xlsx'
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / 'xlsx_csv.py'),
         '--spec', str(spec_path), '-o', str(output)],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert read_spec(output.read_bytes())['sheets'][0]['rows'][1][0]['v'] == '髙島'


def test_convert_paths_reports_detected_encoding(tmp_path):
    path = tmp_path / 'a.csv'
    path.write_bytes(b'\xef\xbb\xbf' + 'a\n1\n'.encode('utf-8'))
    _spec, report = convert_paths([('A', path)], autofilter=True)
    assert report == [{'name': 'A', 'encoding': 'utf-8-sig', 'rows': 2, 'columns': 1}]
