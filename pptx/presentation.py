"""In-memory presentation model backed by the reversible slide spec."""
import io
from pathlib import Path
from zipfile import ZipFile

from pptx.dml.color import MSO_COLOR_TYPE, RGBColor
from pptx.enum.dml import MSO_FILL_TYPE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Emu
from pptx_mapping import ANS, _inches_from_emu, _q, describe_slide, write_slide_xml
from pptx_render import _package_bytes

_NS = {'a': ANS, 'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}


class _Node:
    def __init__(self, element):
        self._element = element

    def get(self, name):
        return self._element.get(name)

    def xpath(self, expr):
        expr = expr.strip()
        if expr.startswith('.//'):
            tag = _clark(expr[3:])
            return [_Node(node) for node in self._element.findall('.//' + tag)]
        if expr.startswith('./'):
            expr = expr[2:]
        node = self._element
        for part in expr.split('/'):
            if node is None:
                return []
            node = node.find(_clark(part))
        return [] if node is None else [_Node(node)]


def _clark(prefixed):
    prefix, local = prefixed.split(':')
    return _q(prefix, local)


class ColorFormat:
    def __init__(self):
        self._rgb = None
        self.type = None

    @property
    def rgb(self):
        return self._rgb

    @rgb.setter
    def rgb(self, value):
        self._rgb = RGBColor(value[0], value[1], value[2])
        self.type = MSO_COLOR_TYPE.RGB


class FillFormat:
    def __init__(self, *, inherited=False):
        self.fore_color = ColorFormat()
        self.type = MSO_FILL_TYPE.BACKGROUND if inherited else None

    def solid(self):
        self.type = MSO_FILL_TYPE.SOLID


class _LineFill:
    def __init__(self, line):
        self._line = line

    def background(self):
        self._line.color._rgb = None
        self._line.color.type = None
        self._line._none = True


class LineFormat:
    def __init__(self):
        self.color = ColorFormat()
        self.fill = _LineFill(self)
        self._width = None
        self._none = False

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        self._width = Emu(int(value))
        self._none = False


class Font:
    def __init__(self):
        self.name = None
        self.bold = None
        self.italic = None
        self.color = ColorFormat()
        self._size = None

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, value):
        self._size = None if value is None else Emu(int(value))


class Run:
    def __init__(self):
        self.text = ''
        self.font = Font()


class Paragraph:
    def __init__(self):
        self.runs = []
        self.alignment = None

    def add_run(self):
        run = Run()
        self.runs.append(run)
        return run


class TextFrame:
    def __init__(self):
        self.paragraphs = [Paragraph()]
        self.word_wrap = None
        self.auto_size = None
        self.vertical_anchor = None
        self.margin_left = self.margin_right = None
        self.margin_top = self.margin_bottom = None

    def clear(self):
        self.paragraphs = [Paragraph()]

    def add_paragraph(self):
        paragraph = Paragraph()
        self.paragraphs.append(paragraph)
        return paragraph

    @property
    def text(self):
        return '\n'.join(''.join(run.text for run in paragraph.runs) for paragraph in self.paragraphs)


def _run_from_spec(spec):
    run = Run()
    run.text = spec.get('text') or ''
    if 'fontSize' in spec:
        run.font.size = Emu(int(round(float(spec['fontSize']) * 12700)))
    if 'bold' in spec:
        run.font.bold = spec['bold']
    if 'italic' in spec:
        run.font.italic = spec['italic']
    if 'color' in spec:
        run.font.color.rgb = RGBColor.from_string(spec['color'])
    if spec.get('fontFace'):
        run.font.name = spec['fontFace']
    return run


def _frame_from_paragraphs(paragraphs):
    frame = TextFrame()
    frame.paragraphs = []
    for spec in paragraphs or []:
        paragraph = Paragraph()
        paragraph.alignment = spec.get('align')
        paragraph.runs = [_run_from_spec(run) for run in spec.get('runs') or []]
        frame.paragraphs.append(paragraph)
    if not frame.paragraphs:
        frame.paragraphs = [Paragraph()]
    return frame


def _paragraphs_from_frame(frame):
    paragraphs = []
    for paragraph in frame.paragraphs:
        if not paragraph.runs:
            continue
        spec = {'runs': []}
        if paragraph.alignment:
            spec['align'] = paragraph.alignment
        for run in paragraph.runs:
            item = {'text': run.text}
            if run.font.size is not None:
                points = run.font.size / 12700
                item['fontSize'] = int(points) if points == int(points) else points
            if run.font.bold is not None:
                item['bold'] = run.font.bold
            if run.font.italic is not None:
                item['italic'] = run.font.italic
            if run.font.color.type == MSO_COLOR_TYPE.RGB:
                item['color'] = str(run.font.color.rgb)
            if run.font.name:
                item['fontFace'] = run.font.name
            spec['runs'].append(item)
        if spec['runs']:
            paragraphs.append(spec)
    return paragraphs or None


def _options_from_frame(frame, options):
    if frame.word_wrap is True:
        options['wrap'] = 'square'
    elif frame.word_wrap is False:
        options['wrap'] = 'none'
    if frame.vertical_anchor:
        options['valign'] = frame.vertical_anchor
    for key, value in (('marginLeft', frame.margin_left), ('marginRight', frame.margin_right),
                       ('marginTop', frame.margin_top), ('marginBottom', frame.margin_bottom)):
        if value is not None:
            options[key] = _inches_from_emu(value)


class _BaseShape:
    def __init__(self, slide, shape_id, name):
        self._slide = slide
        self.shape_id = shape_id
        self.name = name
        self._x = self._y = self._w = self._h = 0
        self._rotation = 0.0
        self.has_text_frame = False
        self.shape_type = 1

    def _touch(self):
        if self._slide is not None:
            self._slide._dirty = True

    @property
    def left(self):
        return Emu(self._x)

    @left.setter
    def left(self, value):
        self._x = int(value)
        self._touch()

    @property
    def top(self):
        return Emu(self._y)

    @top.setter
    def top(self, value):
        self._y = int(value)
        self._touch()

    @property
    def width(self):
        return Emu(self._w)

    @width.setter
    def width(self, value):
        self._w = int(value)
        self._touch()

    @property
    def height(self):
        return Emu(self._h)

    @height.setter
    def height(self, value):
        self._h = int(value)
        self._touch()

    @property
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = float(value)
        self._touch()

    def _box(self):
        options = {
            'x': _inches_from_emu(self._x), 'y': _inches_from_emu(self._y),
            'w': _inches_from_emu(self._w), 'h': _inches_from_emu(self._h),
        }
        if self._rotation % 360:
            options['rotate'] = self._rotation
        return options


class Shape(_BaseShape):
    def __init__(self, slide, shape_id, name, prst, *, text_box=False):
        super().__init__(slide, shape_id, name)
        self._prst = prst
        self._text_box = text_box
        self.fill = FillFormat()
        self.line = LineFormat()
        self.text_frame = TextFrame()
        self.has_text_frame = True
        self.shape_type = 17 if text_box else 1

    @property
    def text(self):
        return self.text_frame.text

    @text.setter
    def text(self, value):
        self.text_frame.clear()
        lines = str(value).split('\n')
        for index, line in enumerate(lines):
            paragraph = self.text_frame.paragraphs[0] if index == 0 else self.text_frame.add_paragraph()
            paragraph.add_run().text = line
        self._touch()

    def to_spec(self):
        options = self._box()
        if self.fill.type == MSO_FILL_TYPE.SOLID and self.fill.fore_color.type == MSO_COLOR_TYPE.RGB:
            options['fill'] = {'color': str(self.fill.fore_color.rgb)}
        if self.line.color.type == MSO_COLOR_TYPE.RGB and not self.line._none:
            line = {'color': str(self.line.color.rgb)}
            if self.line.width is not None:
                points = self.line.width / 12700
                line['width'] = int(points) if points == int(points) else points
            options['line'] = line
        _options_from_frame(self.text_frame, options)
        if self._text_box or self._prst == 'rect' and self.shape_type == 17:
            spec = {'op': 'text', 'name': self.name, 'options': options}
        elif self._prst == 'line':
            spec = {'op': 'line', 'name': self.name, 'options': options}
        else:
            spec = {'op': 'shape', 'name': self.name, 'shape': self._prst, 'options': options}
        paragraphs = _paragraphs_from_frame(self.text_frame)
        if paragraphs and spec['op'] != 'line':
            spec['paragraphs'] = paragraphs
        return spec


class Connector(_BaseShape):
    def __init__(self, slide, shape_id, name, x1, y1, x2, y2):
        super().__init__(slide, shape_id, name)
        self._x1, self._y1, self._x2, self._y2 = int(x1), int(y1), int(x2), int(y2)
        self._sync_box()
        self.line = LineFormat()
        self.has_text_frame = False
        self.shape_type = 9
        self._start = None
        self._end = None

    def _sync_box(self):
        self._x, self._y = min(self._x1, self._x2), min(self._y1, self._y2)
        self._w, self._h = abs(self._x2 - self._x1), abs(self._y2 - self._y1)

    def begin_connect(self, shape, index):
        self._start = {'id': int(shape.shape_id), 'idx': int(index)}
        self._touch()

    def end_connect(self, shape, index):
        self._end = {'id': int(shape.shape_id), 'idx': int(index)}
        self._touch()

    def to_spec(self):
        from pptx_spec import line_box
        x1, y1 = _inches_from_emu(self._x1), _inches_from_emu(self._y1)
        x2, y2 = _inches_from_emu(self._x2), _inches_from_emu(self._y2)
        color = str(self.line.color.rgb) if self.line.color.type == MSO_COLOR_TYPE.RGB else '000000'
        width = 1 if self.line.width is None else self.line.width / 12700
        options = line_box(x1, y1, x2, y2, color=color, width=width)
        for key in ('flipH', 'flipV'):
            if options.get(key) is False:
                options.pop(key, None)
        spec = {'op': 'connector', 'name': self.name, 'options': options}
        if self._start:
            spec['start'] = self._start
        if self._end:
            spec['end'] = self._end
        return spec


class Cell:
    def __init__(self, fill=None, paragraphs=None):
        self.fill = FillFormat()
        if fill:
            self.fill.solid()
            self.fill.fore_color.rgb = RGBColor.from_string(fill)
        self.text_frame = _frame_from_paragraphs(paragraphs)
        self.text_frame.word_wrap = True
        self.text_frame.vertical_anchor = MSO_ANCHOR.TOP

    @property
    def text(self):
        return self.text_frame.text

    @text.setter
    def text(self, value):
        self.text_frame.clear()
        for index, line in enumerate(str(value).split('\n')):
            paragraph = self.text_frame.paragraphs[0] if index == 0 else self.text_frame.add_paragraph()
            paragraph.add_run().text = line

    @property
    def _tc(self):
        from pptx_mapping import write_slide_xml
        payload = write_slide_xml({'objects': [self._owner_spec()]})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(payload)
        return _Node(root.find('.//' + _q('a', 'tc')))

    def _owner_spec(self):
        return getattr(self, '_table_spec', {'op': 'table', 'name': 'cell', 'rows': [{'h': 0.5, 'cells': [self.to_spec()]}],
                                              'options': {'x': 0, 'y': 0, 'w': 1, 'h': 0.5, 'colW': [1], 'border': {'color': 'B3B3B3', 'pt': 0.5}}})

    def to_spec(self):
        spec = {}
        if self.fill.type == MSO_FILL_TYPE.SOLID and self.fill.fore_color.type == MSO_COLOR_TYPE.RGB:
            spec['fill'] = str(self.fill.fore_color.rgb)
        paragraphs = _paragraphs_from_frame(self.text_frame)
        if paragraphs:
            spec['paragraphs'] = paragraphs
        return spec


class Table:
    def __init__(self, cells):
        self._cells = cells

    def cell(self, row, column):
        return self._cells[row][column]


class TableShape(_BaseShape):
    def __init__(self, slide, shape_id, name, options, rows):
        super().__init__(slide, shape_id, name)
        self._x = int(round(float(options['x']) * 914400))
        self._y = int(round(float(options['y']) * 914400))
        self._w = int(round(float(options['w']) * 914400))
        self._h = int(round(float(options['h']) * 914400))
        self._options = options
        self.has_text_frame = False
        self.shape_type = 19
        self.table = Table([[Cell(cell.get('fill'), cell.get('paragraphs')) for cell in row['cells']] for row in rows])
        self._row_heights = [row['h'] for row in rows]

    def to_spec(self):
        rows = []
        for height, row in zip(self._row_heights, self.table._cells):
            rows.append({'h': height, 'cells': [cell.to_spec() for cell in row]})
        options = dict(self._options)
        options.update(self._box())
        return {'op': 'table', 'name': self.name, 'rows': rows, 'options': options}


class Picture(_BaseShape):
    def __init__(self, slide, shape_id, name):
        super().__init__(slide, shape_id, name or '')
        self.shape_type = 13
        self.has_text_frame = False


class Shapes(list):
    def __init__(self, slide):
        super().__init__()
        self._slide = slide

    def _id(self):
        return self._slide._next_id()

    def add_shape(self, prst, left, top, width, height):
        shape = Shape(self._slide, self._id(), self._slide._auto_name(prst), prst)
        shape._x, shape._y, shape._w, shape._h = int(left), int(top), int(width), int(height)
        self.append(shape)
        self._slide._dirty = True
        return shape

    def add_textbox(self, left, top, width, height):
        shape = Shape(self._slide, self._id(), self._slide._auto_name('textbox'), 'rect', text_box=True)
        shape._x, shape._y, shape._w, shape._h = int(left), int(top), int(width), int(height)
        self.append(shape)
        self._slide._dirty = True
        return shape

    def add_connector(self, kind, x1, y1, x2, y2):
        if kind != MSO_CONNECTOR.STRAIGHT:
            raise ValueError('only straight connectors are supported')
        shape = Connector(self._slide, self._id(), self._slide._auto_name('connector'), x1, y1, x2, y2)
        self.append(shape)
        self._slide._dirty = True
        return shape

    def add_table(self, rows, cols, left, top, width, height):
        options = {
            'x': _inches_from_emu(left), 'y': _inches_from_emu(top),
            'w': _inches_from_emu(width), 'h': _inches_from_emu(height),
            'colW': [_inches_from_emu(int(width) / cols)] * cols,
        }
        row_h = _inches_from_emu(int(height) / rows)
        body = [{'h': row_h, 'cells': [{} for _ in range(cols)]} for _ in range(rows)]
        shape = TableShape(self._slide, self._id(), self._slide._auto_name('table'), options, body)
        self.append(shape)
        self._slide._dirty = True
        return shape


class Slide:
    def __init__(self, owner, creation_index):
        self._owner = owner
        self.creation_index = creation_index
        self.shapes = Shapes(self)
        self.background = type('Background', (), {})()
        self.background.fill = FillFormat(inherited=True)
        self._dirty = False
        self._next = 2
        self._counters = {}
        self._member = f'ppt/slides/slide{creation_index + 1}.xml'
        self._raw = None
        self._reversible = True
        self.part = type('Part', (), {'partname': '/' + self._member})()

    def _next_id(self):
        value = self._next
        self._next += 1
        return value

    def _auto_name(self, kind):
        self._counters[kind] = self._counters.get(kind, 0) + 1
        label = {'rect': 'Rectangle', 'roundRect': 'Rounded Rectangle', 'textbox': 'TextBox',
                 'connector': 'Straight Connector', 'table': 'Table', 'rtTriangle': 'Right Triangle',
                 'chevron': 'Chevron', 'downArrow': 'Down Arrow', 'triangle': 'Triangle'}.get(kind, 'Shape')
        return f'{label} {self._counters[kind]}'

    def to_xml(self):
        if not self._reversible:
            if self._dirty:
                raise ValueError('this slide is outside the reversible subset and cannot be rewritten')
            return self._raw
        slide = {'objects': [shape.to_spec() for shape in self.shapes]}
        fill = self.background.fill
        if fill.type == MSO_FILL_TYPE.SOLID and fill.fore_color.type == MSO_COLOR_TYPE.RGB:
            slide['background'] = {'color': str(fill.fore_color.rgb)}
        ids = [shape.shape_id for shape in self.shapes]
        return write_slide_xml(slide, ids or None)


class _SlideRef:
    def __init__(self, slide):
        self.slide = slide


class Slides:
    def __init__(self, owner):
        self._owner = owner
        self._created = []
        self._sldIdLst = []

    def __len__(self):
        return len(self._sldIdLst)

    def __getitem__(self, index):
        return self._sldIdLst[index].slide

    def add_slide(self, layout):
        if layout != 6 and not isinstance(layout, int):
            raise ValueError('only a blank slide layout is supported')
        slide = Slide(self._owner, len(self._created))
        self._created.append(slide)
        self._sldIdLst.append(_SlideRef(slide))
        return slide


class SlideLayouts:
    def __getitem__(self, index):
        if type(index) is not int or not 0 <= index <= 10:
            raise IndexError('slide layout index out of range')
        return index


class Presentation:
    def __init__(self, source=None):
        self.slide_width = 9144000
        self.slide_height = 6858000
        self.slides = Slides(self)
        self.slide_layouts = SlideLayouts()
        self._source = None
        self._source_bytes = None
        if source is not None:
            self._load(source)

    def _load(self, source):
        from pptx_ooxml import ordered_slide_members, slide_size
        if hasattr(source, 'read'):
            data = source.read()
        else:
            self._source = Path(source)
            data = self._source.read_bytes()
        self._source_bytes = data
        with ZipFile(io.BytesIO(data)) as archive:
            self.slide_width, self.slide_height = slide_size(archive)
            members = ordered_slide_members(archive)
            payloads = {member: archive.read(member) for member in members}
        order = sorted(payloads, key=lambda member: int(Path(member).stem.replace('slide', '')))
        for index, member in enumerate(order):
            described = describe_slide(payloads[member])
            slide = Slide(self, index)
            slide._member = member
            slide.part.partname = '/' + member
            slide._raw = payloads[member]
            ops = {item['op'] for item in described['drawables']}
            slide._reversible = not (ops & {'opaque', 'picture'})
            self._populate(slide, described)
            slide._dirty = False
            self.slides._created.append(slide)
        by_member = {slide._member: slide for slide in self.slides._created}
        for member in members:
            self.slides._sldIdLst.append(_SlideRef(by_member[member]))
        self._loaded_display = [slide.creation_index for slide in self.slides]

    def _populate(self, slide, described):
        if described.get('background'):
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = RGBColor.from_string(described['background']['color'])
        highest = 1
        for item in described['drawables']:
            shape = _shape_from_drawable(slide, item)
            if shape is not None:
                slide.shapes.append(shape)
                if shape.shape_id:
                    highest = max(highest, shape.shape_id)
        slide._next = highest + 1

    def save(self, target):
        if self._source_bytes is None:
            payloads, backgrounds, display = [], [], []
            created = {slide: index for index, slide in enumerate(self.slides._created)}
            for ref in self.slides._sldIdLst:
                display.append(created[ref.slide])
            for slide in self.slides._created:
                payloads.append(slide.to_xml())
                fill = slide.background.fill
                backgrounds.append({'background': {'color': str(fill.fore_color.rgb)}} if fill.type == MSO_FILL_TYPE.SOLID and fill.fore_color.rgb else {})
            if not payloads:
                raise ValueError('presentation has no slides')
            shell = {'width': self.slide_width / 914400, 'height': self.slide_height / 914400, 'slides': backgrounds}
            data = _package_bytes(shell, payloads, display=display)
        else:
            data = self._save_loaded()
        if hasattr(target, 'write'):
            target.write(data)
        else:
            Path(target).write_bytes(data)

    def _save_loaded(self):
        from pptx_mapping import normalized_xml
        from pptx_ooxml import reorder_sld_id_lst, set_sld_sz, slide_size
        replacements = {}
        with ZipFile(io.BytesIO(self._source_bytes)) as original:
            width, height = slide_size(original)
            display = [slide.creation_index for slide in self.slides]
            presentation = original.read('ppt/presentation.xml')
            if (width, height) != (self.slide_width, self.slide_height) or display != self._loaded_display:
                presentation = set_sld_sz(presentation, self.slide_width, self.slide_height)
                inverse = [0] * len(self._loaded_display)
                for position, creation in enumerate(self._loaded_display):
                    inverse[creation] = position
                presentation = reorder_sld_id_lst(presentation, inverse)
                presentation = reorder_sld_id_lst(presentation, display)
                replacements['ppt/presentation.xml'] = presentation
            for slide in self.slides._created:
                if not slide._reversible:
                    continue
                payload = slide.to_xml()
                if normalized_xml(payload) != normalized_xml(slide._raw):
                    replacements[slide._member] = payload
            buffer = io.BytesIO()
            with ZipFile(buffer, 'w') as output:
                output.comment = original.comment
                for entry in original.infolist():
                    output.writestr(entry, replacements.get(entry.filename, original.read(entry.filename)))
        return buffer.getvalue()


def _shape_from_drawable(slide, item):
    op = item.get('op')
    shape_id = item.get('id') or slide._next_id()
    if op == 'picture':
        return Picture(slide, shape_id, item.get('name'))
    if op == 'opaque':
        shape = Shape(slide, shape_id, item.get('name') or '', 'rect', text_box=True)
        if item.get('text'):
            shape.text = item['text']
            slide._dirty = False
        shape.has_text_frame = bool(item.get('text'))
        return shape
    if op == 'table':
        return TableShape(slide, shape_id, item.get('name') or '', item.get('options') or {}, item.get('rows') or [])
    if op == 'connector':
        options = item.get('options') or {}
        # Endpoints are recovered only as the line box; connections are kept.
        x = int(round(float(options.get('x', 0)) * 914400))
        y = int(round(float(options.get('y', 0)) * 914400))
        w = int(round(float(options.get('w', 0)) * 914400))
        h = int(round(float(options.get('h', 0)) * 914400))
        connector = Connector(slide, shape_id, item.get('name') or '', x, y, x + w, y + h)
        connector._start = item.get('start')
        connector._end = item.get('end')
        if options.get('line'):
            connector.line.color.rgb = RGBColor.from_string(options['line']['color'])
            if 'width' in options['line']:
                connector.line.width = Emu(int(round(float(options['line']['width']) * 12700)))
        return connector
    if op in ('shape', 'text', 'line'):
        text_box = op == 'text'
        prst = 'line' if op == 'line' else ('rect' if text_box else item.get('shape') or 'rect')
        shape = Shape(slide, shape_id, item.get('name') or '', prst, text_box=text_box)
        options = item.get('options') or {}
        shape._x = int(round(float(options.get('x', 0)) * 914400))
        shape._y = int(round(float(options.get('y', 0)) * 914400))
        shape._w = int(round(float(options.get('w', 0)) * 914400))
        shape._h = int(round(float(options.get('h', 0)) * 914400))
        if 'rotate' in options:
            shape._rotation = float(options['rotate'])
        if options.get('fill'):
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(options['fill']['color'])
        if options.get('line'):
            shape.line.color.rgb = RGBColor.from_string(options['line']['color'])
            if 'width' in options['line']:
                shape.line.width = Emu(int(round(float(options['line']['width']) * 12700)))
        if item.get('paragraphs'):
            shape.text_frame = _frame_from_paragraphs(item['paragraphs'])
        if options.get('wrap') == 'square':
            shape.text_frame.word_wrap = True
        elif options.get('wrap') == 'none':
            shape.text_frame.word_wrap = False
        if options.get('valign'):
            shape.text_frame.vertical_anchor = options['valign']
        for attr, key in (('margin_left', 'marginLeft'), ('margin_right', 'marginRight'),
                          ('margin_top', 'marginTop'), ('margin_bottom', 'marginBottom')):
            if key in options:
                setattr(shape.text_frame, attr, Emu(int(round(float(options[key]) * 914400))))
        return shape
    return None
