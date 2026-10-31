"""Convert one or more CSV files into an xlsx workbook.

Usage:
  python xlsx_csv.py -o book.xlsx --border --autofilter 売上=costs.csv メモ=notes.csv
  python xlsx_csv.py --spec book.json -o book.xlsx
"""
import json
import os
from pathlib import Path

from xlsx_render import write_workbook
from xlsx_spec import sheet_from_csv, workbook_from_sheets, workbook_from_spec


def convert_paths(sheets, *, borders=False, autofilter=False, encoding='auto'):
    """``sheets`` is a list of ``(name, path)``."""
    built = []
    report = []
    for name, path in sheets:
        path = Path(path)
        data = path.read_bytes()
        sheet = sheet_from_csv(name, data, borders=borders, autofilter=autofilter, encoding=encoding)
        report.append({
            'name': sheet['name'], 'encoding': sheet['encoding'],
            'rows': len(sheet['rows']), 'columns': len(sheet['rows'][0]),
        })
        built.append(sheet)
    return workbook_from_sheets(built), report


def write_csv_workbook(path, spec):
    path = Path(path)
    if path.suffix.lower() != '.xlsx':
        raise ValueError('output must be a .xlsx file')
    if os.path.lexists(path):
        raise ValueError('output must be a new file')
    path.write_bytes(write_workbook(spec))
    return path


def _sheet_arg(value):
    name, separator, filename = value.partition('=')
    if not separator:
        path = Path(value)
        return path.stem, path
    return name, Path(filename)


def main(argv=None):
    from ironmate_cli import ToolParser, guard
    parser = ToolParser(description='Convert CSV files into an xlsx workbook.', tool='xlsx_csv.py')
    parser.add_argument('sheets', nargs='*', type=_sheet_arg, help='SheetName=file.csv, or a csv path')
    parser.add_argument('-o', '--output', type=Path, required=True)
    parser.add_argument('--spec', type=Path, help='JSON workbook spec; csv paths are relative to the spec file')
    parser.add_argument('--border', action='store_true', help='draw a thin grid border on every cell')
    parser.add_argument('--autofilter', action='store_true', help='turn on autofilter for the used range')
    parser.add_argument('--encoding', default='auto', choices=('auto', 'utf-8', 'utf-8-sig', 'shift_jis', 'cp932'))
    parser.add_json_flag()
    args = parser.parse_args(argv)
    if (args.spec is None) == (not args.sheets):
        parser.error('provide CSV sheets or --spec')

    def work():
        if args.spec is not None:
            spec_data = json.loads(args.spec.read_text(encoding='utf-8'))
            spec = workbook_from_spec(spec_data, args.spec.parent)
            report = [{'name': sheet['name'], 'rows': len(sheet['rows']), 'columns': len(sheet['rows'][0])} for sheet in spec['sheets']]
        else:
            spec, report = convert_paths(args.sheets, borders=args.border, autofilter=args.autofilter, encoding=args.encoding)
        write_csv_workbook(args.output, spec)
        print(json.dumps({'output': str(args.output), 'sheets': report}, ensure_ascii=False))
        return 0

    return guard('xlsx_csv.py', work, json_mode=args.json, extra=(RuntimeError,))


if __name__ == '__main__':
    raise SystemExit(main())
