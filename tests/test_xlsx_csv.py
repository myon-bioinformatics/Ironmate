"""CSV encoding and xlsx Open XML checks. No spreadsheet app."""
import csv, io, json, shutil, subprocess, sys
from io import BytesIO; from pathlib import Path; from xml.etree import ElementTree as ET; from zipfile import ZipFile

import pytest

from xlsx_csv import convert_paths, main, write_csv_workbook
from xlsx_ooxml import read_spec, write_package
import xlsx_render
from xlsx_render import read_workbook, write_workbook
import xlsx_spec
from xlsx_spec import decode_csv_bytes, sheet_from_csv, workbook_from_sheets, workbook_from_spec

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _book():
    text = '名前,金額,税込\n"東京,本店",1200,=B2*1.1\n予備,15,2.5\n'
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
    # These bytes decode differently in Shift_JIS and CP932. Windows Excel uses CP932.
    assert decode_csv_bytes(b'\x81\x60') == ('～', 'cp932')
    assert decode_csv_bytes(b'\x81\x61') == ('∥', 'cp932')
    assert decode_csv_bytes(b'\x81\x7c') == ('－', 'cp932')
    assert decode_csv_bytes(b'\x81\x91') == ('￠', 'cp932')
    assert decode_csv_bytes(b'\x81\x92') == ('￡', 'cp932')
    assert decode_csv_bytes(b'\x81\xca') == ('￢', 'cp932')
    # The same character stored as UTF-8, with or without a BOM, stays UTF-8.
    assert decode_csv_bytes('～'.encode('utf-8')) == ('～', 'utf-8')
    assert decode_csv_bytes(b'\xef\xbb\xbf' + '～'.encode('utf-8')) == ('～', 'utf-8-sig')
    # Halfwidth katakana is a single Shift_JIS byte and is not valid UTF-8.
    assert decode_csv_bytes('ｱ'.encode('shift_jis')) == ('ｱ', 'shift_jis')
    with pytest.raises(ValueError, match='Shift_JIS'):
        decode_csv_bytes(b'\x81')
    with pytest.raises(ValueError, match='UTF-8 with BOM'):
        decode_csv_bytes(b'\xef\xbb\xbf\xff')


def test_numbers_formulas_borders_and_clear_cells():
    sheet = sheet_from_csv(
        'S', 'code,n,whole\n001,=A1,1.0\n', borders=True,
        columns=[{'clear': True}, {'numFmt': '0', 'align': 'right'}, {}],
    )
    code, formula, whole = sheet['rows'][1]
    assert code == {'v': '001'}
    assert formula == {'f': 'A1', 'z': '0', 'align': 'right', 'border': 'thin'}
    assert 'border' not in code
    assert whole == {'v': 1, 'border': 'thin'}
    assert type(whole['v']) is int
    kept = sheet_from_csv('S', 'n\n2.5\n')
    assert kept['rows'][1][0]['v'] == 2.5 and type(kept['rows'][1][0]['v']) is float


def _csv_cell(formula):
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\n').writerows([['h'], [formula]])
    return sheet_from_csv('S', buffer.getvalue())['rows'][1][0]


@pytest.mark.parametrize('raw', [
    '=IMAGE(A2)', '=image(A2)', '=Image ( A2 )', '= IMAGE( A2 )',
    '=SUM(IMAGE(A2))', '=SUM( 1, image ( A2 ) )',
    '=IF(A1,IMAGE(A2),ROUND(B1,0))', '=_xlfn.IMAGE(A2)',
    '=HYPERLINK(A2,"x")', '=WEBSERVICE(A2)', '=FILTERXML(A2,"//a")',
    '=RTD(A2,B2,C2)', '=CALL(A2)', '=REGISTER.ID(A2,B2)', '=EXEC(A2)',
    '=INDIRECT(A2)', '=SUM(indirect ( A2 ))', '=FUTUREFUNCTION(A2)',
    "=cmd|'/c calc'!A0", "='https://evil.example/book.xlsx'!A1",
    "='C:\\evil.xlsx'!A1", "='\\\\server\\book.xlsx'!A1", "='[book.xlsx]S'!A1",
    '=[book.xlsx]S!A1', '=Sheet1:Sheet3!A1', '=named_formula',
    '=A0', '=XFE1', '=A1048577', '=SUM(A1;A2)', '=SUM(A1)IMAGE(A2)',
    '=SUM(A1', '=A1 A2', '=1+', '=()', '=SUM(,A1)', '=SUM(A1,)',
    '="unterminated', "='IMAGE'(A2)", '=A1#', '=@SUM(A1)', '=1\t+2',
])
@pytest.mark.parametrize('source', ['csv', 'explicit'])
def test_formula_policy_rejects_external_calls_and_unsupported_syntax(raw, source):
    # The URL lives in A2, never in the formula itself. No lexical URL test
    # can catch IMAGE(A2). Exercise real workbook input for both entry points.
    spec = {'sheets': [{'name': 'S', 'rows': [
        ['url', 'result'], ['https://example.invalid/pixel.png', raw if source == 'csv' else ''],
    ]}]}
    if source == 'explicit':
        spec['sheets'][0]['formulas'] = [{'cell': 'B2', 'formula': raw}]
    with pytest.raises(ValueError, match='formula is outside'):
        workbook_from_spec(spec, '.')


@pytest.mark.parametrize('raw', [
    '=B2*1.1', '=SUM(A1:A2)', '=sum ( $A$1:A2 )',
    '=ROUND(AVERAGE(A1:A2),2)', '=IF(A1>0,SUM(B1:B2),0)',
    '=IF(A1="IMAGE(A2)",SUM(B1:B2),0)',
    '=IF(A1="a""IMAGE(A2)",1,0)', '=SUM(1,2,3)',
    '=-(A1+2)^2/100%', '=TRUE', '=AND(TRUE,NOT(FALSE))',
    '=CONCAT("https://example.invalid/",A1)', '=1.2E-3+2E3',
    "='売上 メモ'!$A$1+'O''Brien'!B2", '=Sheet2!A1:A2',
    '=IFERROR(ROUND(B2*1.1,0),0)',
])
@pytest.mark.parametrize('source', ['csv', 'explicit'])
def test_safe_formulas_remain_formulas(raw, source):
    if source == 'csv':
        cell = _csv_cell(raw)
    else:
        sheet = sheet_from_csv('S', 'h\n1\n', formulas=[{'cell': 'A2', 'formula': raw}])
        cell = sheet['rows'][1][0]
    assert cell == {'f': raw[1:]}


@pytest.mark.parametrize('engine', ['min', 'exceljs'])
@pytest.mark.parametrize('raw', ['IMAGE(A2)', 'SUM(IMAGE(A2))', 'WEBSERVICE(A2)',
                                 'INDIRECT(A2)', 'FUTUREFUNCTION(A2)', '', None])
def test_canonical_spec_cannot_bypass_formula_policy(engine, raw, monkeypatch):
    spec = {'sheets': [{'name': 'S', 'rows': [[{'v': 'https://example.invalid/pixel.png'}, {'f': raw}]]}]}
    def unexpected_writer(*args):
        pytest.fail('rejected formula reached the Node writer')
    monkeypatch.setattr('xlsx_render._run', unexpected_writer)
    with pytest.raises(ValueError, match='formula is outside'):
        write_workbook(spec, engine)


@pytest.mark.parametrize('engine', ['min', 'exceljs'])
@pytest.mark.parametrize('source', ['csv', 'explicit'])
def test_url_cells_and_safe_formulas_write_without_external_relationships(engine, source):
    entry = {'name': 'S', 'rows': [
        ['url', 'result'], ['https://example.invalid/pixel.png', '=SUM(1,2)' if source == 'csv' else ''],
    ]}
    if source == 'explicit':
        entry['formulas'] = [{'cell': 'B2', 'formula': 'SUM(1,2)'}]
    spec = workbook_from_spec({'sheets': [entry]}, '.')
    payload = write_workbook(spec, engine)
    assert read_spec(payload) == spec
    root = ET.fromstring(archive_sheet(payload, 0))
    assert [node.text for node in root.findall('.//m:f', NS)] == ['SUM(1,2)']
    assert spec['sheets'][0]['rows'][1][0] == {'v': 'https://example.invalid/pixel.png'}
    with ZipFile(BytesIO(payload)) as archive:
        assert not any(name.startswith(('xl/media/', 'xl/externalLinks/')) for name in archive.namelist())
        for name in archive.namelist():
            if name.endswith('.rels'):
                assert all(rel.get('TargetMode') != 'External' for rel in ET.fromstring(archive.read(name)))


@pytest.mark.parametrize('engine', ['min', 'exceljs'])
def test_sheet_qualifiers_must_resolve_inside_the_written_workbook(engine):
    spec = workbook_from_spec({'sheets': [
        {'name': 'S', 'rows': [["='売上 メモ'!A1+other!A1"]]},
        {'name': '売上 メモ', 'rows': [[2]]},
        {'name': 'Other', 'rows': [[3]]},
    ]}, '.')
    assert read_spec(write_workbook(spec, engine)) == spec
    for raw in ("'missing.xlsx'!A1", 'MissingSheet!A1'):
        spec['sheets'][0]['rows'][0][0] = {'f': raw}
        with pytest.raises(ValueError, match='formula is outside'):
            write_workbook(spec, engine)


def test_formula_nesting_limit_is_a_validation_error():
    with pytest.raises(ValueError, match='formula is outside'):
        _csv_cell('=' + 'SUM(' * 66 + 'A1' + ')' * 66)


def test_rejected_features_and_sheet_names():
    with pytest.raises(ValueError, match='merge'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']], 'merges': ['A1:B1']}]}, '.')
    with pytest.raises(ValueError, match='image'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']], 'images': ['a.png']}]}, '.')
    with pytest.raises(ValueError, match='conditional'):
        workbook_from_spec({'sheets': [{'name': 'S', 'rows': [['a']]}], 'conditionalFormatting': []}, '.')
    with pytest.raises(ValueError, match='Excel rejects'):
        sheet_from_csv('bad:name', 'a\n')


@pytest.mark.parametrize('engine', ['min', 'exceljs'])
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
    assert root.find('.//m:f', NS).text == 'B2*1.1'
    assert read_spec(payload)['sheets'][0]['rows'][1][2]['f'] == 'B2*1.1'
    assert root.find('m:autoFilter', NS).get('ref') == 'A1:C3'
    bordered = [cell for cell in root.findall('.//m:c', NS) if cell.get('s') not in (None, '0')]
    assert bordered
    style_root = ET.fromstring(styles)
    thin = [item for item in style_root.findall('.//m:border', NS) if item.find('m:left', NS).get('style') == 'thin']
    assert len(thin) == 1
    assert thin[0].find('m:left/m:color', NS).get('rgb') == 'FF000000'
    assert style_root.find('.//m:numFmt[@formatCode="0.000"]', NS) is not None
    assert style_root.find('.//m:alignment[@horizontal="right"]', NS) is not None
    assert len(sheets) == 2
    xfs = style_root.findall('m:cellXfs/m:xf', NS)
    assert xfs
    assert int(style_root.find('m:cellXfs', NS).get('count')) == len(xfs)
    for cell in root.findall('.//m:c', NS):
        assert 0 <= int(cell.get('s')) < len(xfs)


def test_empty_cells_keep_grid_borders():
    sheet = sheet_from_csv('S', 'a,b,\n1,2,\n', borders=True, autofilter=True)
    spec = workbook_from_sheets([sheet])
    for name in ('min', 'exceljs'):
        payload = write_workbook(spec, name)
        assert read_spec(payload) == spec
        root = ET.fromstring(archive_sheet(payload, 0))
        empty = root.find('m:sheetData/m:row[@r="1"]/m:c[@r="C1"]', NS)
        assert empty is not None and empty.find('m:v', NS) is None
        with ZipFile(BytesIO(payload)) as archive:
            styles = ET.fromstring(archive.read('xl/styles.xml'))
        xf = styles.findall('m:cellXfs/m:xf', NS)[int(empty.get('s'))]
        assert xf.get('borderId') == '1'
        assert xf.get('applyBorder') == '1'
        # The independent reader sees the empty bordered cell as part of the grid.
        assert read_workbook(payload, 'exceljs') == spec


def archive_sheet(payload, index):
    with ZipFile(BytesIO(payload)) as archive:
        return archive.read(f'xl/worksheets/sheet{index + 1}.xml')


@pytest.mark.parametrize('engine', ['min', 'exceljs'])
def test_exceljs_reads_the_package_each_writer_wrote(engine):
    # ExcelJS is the independent oracle: it must read the full spec back, including
    # borders and alignment, from the package the min writer produced.
    spec = _book()
    assert read_workbook(write_workbook(spec, engine), 'exceljs') == spec


# Text that exercises escaping, whitespace, line breaks, Unicode, and characters XML 1.0 cannot hold.
_TRICKY_TEXT = [
    'a&b <c> "q" \'s\'', '  lead and trail  ', 'a    b', 'l1\nl2', 'l1\r\nl2', 'x\ry', 'a\tb',
    'emoji 😀 𠮷', '売上 メモ ｱｲｳ', '<![CDATA[x]]>', ']]>', '&amp;', '001', '1e3',
    'a\x01b', 'a\x0bb', 'a\x00b', 'a\x7fb', 'a\x85b', 'a b', '퟿�', 'x' * 40000,
]


def test_min_and_exceljs_write_the_same_workbook_content():
    rows = [[{'v': text}] for text in _TRICKY_TEXT]
    rows += [[{'v': number}, {'f': 'A1+1'}] for number in (0, 1, -7, 1200, 2.5, -0.125, 1e-7, 12345678901234, 1e21)]
    spec = {'sheets': [{'name': 'S', 'rows': [row + [None] * (2 - len(row)) for row in rows]},
                       {'name': '売上 メモ', 'rows': [[{'v': 1}]]},
                       {'name': 'R&D <x> "q"', 'rows': [[{'v': 2}]]}]}
    from_min = write_workbook(spec, 'min')
    from_exceljs = write_workbook(spec, 'exceljs')
    assert read_spec(from_min) == read_spec(from_exceljs)
    # The independent reader agrees on both packages, not only the stdlib reader.
    assert read_workbook(from_min, 'exceljs') == read_workbook(from_exceljs, 'exceljs')


def test_both_writers_leave_underscore_x_sequences_unescaped():
    # Known gap, unchanged by the min writer: OOXML reads _xHHHH_ as an escaped character and
    # expects a literal one as _x005F_xHHHH_. ExcelJS never escaped it, and its own reader
    # decodes it, so this text is not compared through the ExcelJS reader.
    spec = {'sheets': [{'name': 'S', 'rows': [[{'v': '_x0041_ and _x005F_'}]]}]}
    assert read_spec(write_workbook(spec, 'min')) == spec == read_spec(write_workbook(spec, 'exceljs'))


def test_min_writer_text_rules():
    # CR and CRLF become LF; control characters, DEL and U+FFFE/U+FFFF are dropped, as ExcelJS does.
    text = 'a\r\nb\rc\x01\x7f￾￿d\t&<>"'
    spec = {'sheets': [{'name': 'S', 'rows': [[{'v': text}]]}]}
    assert read_spec(write_workbook(spec, 'min'))['sheets'][0]['rows'][0][0] == {'v': 'a\nb\ncd\t&<>"'}


def test_min_writer_package_is_a_small_deterministic_zip():
    # Inspect the bytes write_package produced: write_workbook() re-zips them afterwards.
    spec = _book()
    first = write_package(spec)
    assert write_package(spec) == first
    assert write_workbook(spec, 'min') == write_workbook(spec, 'min')
    with ZipFile(BytesIO(first)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert names[0] == '[Content_Types].xml'
        assert sorted(names) == sorted([
            '[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml', 'xl/_rels/workbook.xml.rels',
            'xl/styles.xml', 'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml'])
        for name in names:
            ET.fromstring(archive.read(name))
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        # Excel trims leading and trailing spaces in <t> unless xml:space="preserve" is set.
        xml_space = '{http://www.w3.org/XML/1998/namespace}space'
        for sheet_name in ('xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml'):
            texts = ET.fromstring(archive.read(sheet_name)).findall('.//m:is/m:t', NS)
            assert texts and all(text.get(xml_space) == 'preserve' for text in texts)


def test_min_writer_rejects_what_it_cannot_write():
    for bad in (True, False, float('nan'), float('inf'), b'x', [1]):
        with pytest.raises(ValueError, match='unsupported value|not a finite number'):
            write_package({'sheets': [{'name': 'S', 'rows': [[{'v': bad}]]}]})
    with pytest.raises(ValueError, match='at least one sheet'):
        write_package({'sheets': []})
    # Cells without a value or formula are omitted, not written as empty strings.
    xml = ZipFile(BytesIO(write_package({'sheets': [{'name': 'S', 'rows': [[None, {'z': '0'}, {'f': ''}, {'v': 1}]]}]}))
                  ).read('xl/worksheets/sheet1.xml').decode('utf-8')
    assert xml.count('<c ') == 1 and 'r="D1"' in xml


def test_min_writer_needs_neither_node_nor_npm_packages(tmp_path, monkeypatch):
    # Writing is Python only: no Node.js on PATH, no node_modules (npm ci --omit=dev has no ExcelJS).
    (tmp_path / 'scripts').mkdir()
    for name in ('xlsx_io.mjs', 'xlsx_allowlist.json'):
        shutil.copy(Path(xlsx_render.ROOT) / 'scripts' / name, tmp_path / 'scripts' / name)
    monkeypatch.setattr(xlsx_render, 'ROOT', tmp_path)
    monkeypatch.setattr(xlsx_render.shutil, 'which', lambda *_args, **_kwargs: None)

    def unexpected_node(*_args, **_kwargs):
        pytest.fail('the min writer started a Node process')
    monkeypatch.setattr(xlsx_render.subprocess, 'run', unexpected_node)
    spec = _book()
    assert read_spec(write_workbook(spec)) == spec
    with pytest.raises(RuntimeError, match='exceljs is not installed'):
        write_workbook(spec, 'exceljs')


def test_unknown_engines_are_rejected():
    spec = _book()
    with pytest.raises(ValueError, match='engine must be min or exceljs'):
        write_workbook(spec, 'sheetjs')
    with pytest.raises(ValueError, match='only exceljs reads'):
        read_workbook(b'', 'min')


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
