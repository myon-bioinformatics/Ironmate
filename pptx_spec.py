"""Ironmate slide-spec helpers: arrow geometry and native pattern objects.

Arrow geometry matches the web-ui JSON connector helper: a straight line plus a
separate triangle, never a built-in connector or line arrow. Pattern objects use
the same coordinates as the previous python-pptx enrich path.
"""
import math

from pptx_mapping import canon_color, emu_inches

_EMU = 914400


def _round(value):
    return round(float(value), 6)


def _positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be a positive number')
    return float(value)


def _color(value, label):
    try:
        return canon_color(value)
    except ValueError as exc:
        raise ValueError(f'{label} must be #RRGGBB or RRGGBB') from exc


def line_box(x1, y1, x2, y2, *, color, width):
    """Straight line as a non-negative box plus flip, with no arrow styling."""
    main_diagonal = (x1 <= x2 and y1 <= y2) or (x1 >= x2 and y1 >= y2)
    return {
        'x': _round(min(x1, x2)),
        'y': _round(min(y1, y2)),
        'w': _round(abs(x2 - x1)),
        'h': _round(abs(y2 - y1)),
        'flipH': not main_diagonal,
        'flipV': False,
        'line': {'color': color, 'width': width},
    }


def _center(box):
    return (box['x'] + box['w'] / 2.0, box['y'] + box['h'] / 2.0)


def _boundary_toward(box, toward):
    """Point where the ray from this box's center toward another point exits the box."""
    center_x, center_y = _center(box)
    delta_x = toward[0] - center_x
    delta_y = toward[1] - center_y
    if delta_x == 0 and delta_y == 0:
        raise ValueError('connector objects share a center')
    scale_x = (box['w'] / 2.0) / abs(delta_x) if delta_x else math.inf
    scale_y = (box['h'] / 2.0) / abs(delta_y) if delta_y else math.inf
    return (center_x + delta_x * min(scale_x, scale_y), center_y + delta_y * min(scale_x, scale_y))


def _box(box, label):
    if not isinstance(box, dict):
        raise ValueError(f'connector {label} must be a positioned object')
    for key in ('x', 'y', 'w', 'h'):
        if key not in box:
            raise ValueError(f'connector {label} needs x, y, w, and h')
    return {key: float(box[key]) for key in ('x', 'y', 'w', 'h')}


def arrow_geometry(source, target, *, mode='edge', color='363636', width=1.25, head=0.18):
    """Line plus triangle arrowhead between two positioned boxes, in inches.

    ``mode="edge"`` joins the box edges crossed by the center-to-center ray.
    ``mode="center"`` joins the centers. The triangle is centered on the midpoint
    and rotated so its tip follows the line. This is not a connector shape.
    """
    if mode not in ('edge', 'center'):
        raise ValueError('connector mode must be edge or center')
    source_box, target_box = _box(source, 'source'), _box(target, 'target')
    source_center, target_center = _center(source_box), _center(target_box)
    if mode == 'center':
        x1, y1 = source_center
        x2, y2 = target_center
    else:
        x1, y1 = _boundary_toward(source_box, target_center)
        x2, y2 = _boundary_toward(target_box, source_center)
    if math.hypot(x2 - x1, y2 - y1) == 0:
        raise ValueError('connector length must be positive')
    ink, stroke, head_size = _color(color, 'connector color'), _positive(width, 'connector width'), _positive(head, 'connector head')
    rotate = round((math.degrees(math.atan2(y2 - y1, x2 - x1)) + 90.0) % 360.0, 4)
    midpoint = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return {
        'mode': mode,
        'x1': _round(x1), 'y1': _round(y1), 'x2': _round(x2), 'y2': _round(y2),
        'midpoint': {'x': _round(midpoint[0]), 'y': _round(midpoint[1])},
        'distance': _round(math.hypot(x2 - x1, y2 - y1)),
        'rotate': rotate,
        'line': {'op': 'line', 'options': line_box(x1, y1, x2, y2, color=ink, width=stroke)},
        'head': {'op': 'shape', 'shape': 'triangle', 'options': {
            'x': _round(midpoint[0] - head_size / 2.0),
            'y': _round(midpoint[1] - head_size / 2.0),
            'w': _round(head_size), 'h': _round(head_size), 'rotate': rotate,
            'fill': {'color': ink}, 'line': {'color': ink, 'width': stroke},
        }},
    }


def expand_connector(item, lookup):
    """Turn one authoring connector into a line object and a triangle object."""
    if item.get('op') != 'connector' and item.get('kind') != 'connector':
        raise ValueError('expected a connector object')
    for key in ('beginArrowType', 'endArrowType', 'lineHead', 'lineTail'):
        if key in item:
            raise ValueError(f'built-in arrow styling is not reversible: {key}')
    source, target = lookup(item['from']), lookup(item['to'])
    geom = arrow_geometry(source, target, mode=item.get('mode', 'edge'), color=item.get('color', '363636'),
                          width=item.get('width', 1.25), head=item.get('head', 0.18))
    line, head = geom['line'], geom['head']
    if item.get('name'):
        line['name'] = item['name'] + '-line'
        head['name'] = item['name'] + '-head'
    return geom['mode'], line, head


def _paragraphs(text, *, bold=False, color='000000', font_size=14, font_face='Meiryo'):
    paragraphs = []
    for line in str(text).split('\n'):
        paragraphs.append({'runs': [{
            'text': line, 'bold': bold, 'color': color, 'fontSize': font_size, 'fontFace': font_face,
        }]})
    return paragraphs


def _textbox(name, rect, text, points, *, bold=False, color='000000'):
    x, y, w, h = rect
    return {
        'op': 'text', 'name': name,
        'options': {
            'x': x, 'y': y, 'w': w, 'h': h, 'valign': 'top', 'wrap': 'square',
            'marginLeft': 0.08, 'marginRight': 0.08, 'marginTop': 0.04, 'marginBottom': 0.04,
        },
        'paragraphs': _paragraphs(text, bold=bold, color=color, font_size=points),
    }


def _shape(name, prst, rect, *, fill='FFFFFF', line='000000', width=1, paragraphs=None):
    x, y, w, h = rect
    obj = {
        'op': 'shape', 'name': name, 'shape': prst,
        'options': {
            'x': x, 'y': y, 'w': w, 'h': h,
            'fill': {'color': fill},
            'line': {'color': line, 'width': width},
        },
    }
    if paragraphs:
        obj['paragraphs'] = paragraphs
        obj['options'].update(valign='top', wrap='square', marginLeft=0.08, marginRight=0.08, marginTop=0.04, marginBottom=0.04)
    return obj


def _arrow_pair(name, source, target, color):
    geom = arrow_geometry(source, target, mode='edge', color=color, width=1.5, head=0.18)
    line, head = geom['line'], geom['head']
    line['name'] = name + '-arrow-line'
    head['name'] = name + '-arrow-head'
    # False flips are not XML attributes; keep the geometry helper's full dict
    # on the geometry result, but store the reversible options here.
    for key in ('flipH', 'flipV'):
        if line['options'].get(key) is False:
            line['options'].pop(key)
    return line, head


def _number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    return value


def _text(value):
    if not isinstance(value, str):
        raise ValueError('text values must be strings')
    return value


def _hex(value):
    if not isinstance(value, str) or len(value) != 7 or not value.startswith('#'):
        raise ValueError('colors must be #RRGGBB')
    return canon_color(value)


def pattern_objects(spec, *, index, slide_count, slide_width, slide_height):
    """Validate one enrich pattern and return reversible objects, in z-order."""
    if not isinstance(spec, dict):
        raise ValueError('pattern must be a mapping')
    mode, number = spec.get('pattern'), spec.get('slide')
    if mode not in ('cards', 'regions', 'agenda', 'flow', 'table'):
        raise ValueError('unknown pattern')
    if type(number) is not int or not 1 <= number <= slide_count:
        raise ValueError('slide must be a valid 1-based slide number')
    rect = [_number(spec.get(k), k, positive=k in ('width', 'height')) for k in ('x', 'y', 'width', 'height')]
    x, y, w, h = rect
    if round((x + w) * _EMU) > slide_width or round((y + h) * _EMU) > slide_height:
        raise ValueError('pattern extends beyond slide bounds')
    gap = _number(spec.get('gap', .2), 'gap')
    points = _number(spec.get('font_size', 14), 'font_size', positive=True)
    if not 6 <= points <= 72:
        raise ValueError('font_size must be between 6 and 72')
    accent = _hex(spec.get('accent', '#000000'))
    prefix = f'enrich-{index + 1}-{mode}'
    if mode == 'table':
        return _table_objects(spec, prefix, rect, points)
    items = spec.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 24:
        raise ValueError('items must contain 1..24 mappings')
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('item must be a mapping')
        _text(item.get('title', ''))
        _text(item.get('body', ''))
        _text(item.get('label', ''))
    n = len(items)
    columns = spec.get('columns', n)
    if mode in ('regions', 'flow'):
        columns = n
    elif mode == 'agenda':
        columns = 1
    if type(columns) is not int or not 1 <= columns <= n:
        raise ValueError('columns must be between 1 and item count')
    row_count = (n + columns - 1) // columns
    cw, ch = (w - gap * (columns - 1)) / columns, (h - gap * (row_count - 1)) / row_count
    if cw < .7 or ch < .7:
        raise ValueError('cells must be at least 0.7 inches wide and high')
    if mode == 'flow' and n > 1 and gap < .15:
        raise ValueError('flow gap must be at least 0.15 inches')
    boxes, objects = [], []
    for i, item in enumerate(items):
        cx, cy = x + (i % columns) * (cw + gap), y + (i // columns) * (ch + gap)
        name = f'{prefix}-{i + 1}'
        boxes.append({'x': cx, 'y': cy, 'w': cw, 'h': ch, 'name': name, 'item': item})
        kind = 'roundRect' if mode in ('regions', 'agenda') else 'rect'
        objects.append(_shape(name + '-box', kind, (cx, cy, cw, ch), line=accent))
        if mode == 'agenda':
            label = '  ' + item['label'] if item.get('label') else ''
            objects.append(_textbox(name + '-text', (cx + .05, cy + .03, cw - .1, ch - .06),
                                    item.get('title', '') + '\n' + item.get('body', '') + label, points))
            continue
        header = min(.45, ch * .3)
        if mode == 'regions':
            objects.append(_shape(
                name + '-label', 'roundRect', (cx + .05, cy + .03, cw - .1, header),
                fill=accent, line=accent,
                paragraphs=_paragraphs(item.get('title', ''), bold=True, color='FFFFFF', font_size=points),
            ))
        else:
            objects.append(_shape(name + '-bar', 'rect', (cx, cy, cw, .035), fill=accent, line=accent))
            objects.append(_textbox(name + '-title', (cx + .04, cy + .04, cw - .08, header), item.get('title', ''), points, bold=True))
        objects.append(_textbox(name + '-body', (cx + .04, cy + header + .07, cw - .08, ch - header - .1), item.get('body', ''), points))
    if mode == 'flow' and n > 1:
        lines, heads = [], []
        for left, right in zip(boxes, boxes[1:]):
            line, head = _arrow_pair(left['name'], left, right, accent)
            lines.append(line)
            heads.append(head)
        objects.extend(lines)
        objects.extend(heads)
    return objects


def _table_objects(spec, prefix, rect, points):
    import csv
    from pathlib import Path

    if 'csv' in spec and 'rows' in spec:
        raise ValueError('use either csv or rows, not both')
    if 'csv' in spec:
        with Path(_text(spec['csv'])).open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
    else:
        rows = spec.get('rows')
    header_fill = _hex(spec.get('header_fill', '#222222'))
    header_text = _hex(spec.get('header_text', '#FFFFFF'))
    row_fills = spec.get('row_fills', ['#FFFFFF', '#F2F2F2'])
    border = _hex(spec.get('border_color', '#B3B3B3'))
    if not isinstance(row_fills, list) or not row_fills:
        raise ValueError('row_fills must be a nonempty list of colors')
    row_fills = [_hex(value) for value in row_fills]
    if (not isinstance(rows, list) or not 2 <= len(rows) <= 30 or not isinstance(rows[0], list)
            or not 1 <= len(rows[0]) <= 12 or any(not isinstance(row, list) or len(row) != len(rows[0]) for row in rows)):
        raise ValueError('table requires 2..30 rectangular rows with 1..12 columns')
    for row in rows:
        for value in row:
            _text(value)
    x, y, w, h = rect
    col_w = w / len(rows[0])
    row_h = h / len(rows)
    body = []
    for ri, row in enumerate(rows):
        cells = []
        for value in row:
            cells.append({
                'fill': header_fill if ri == 0 else row_fills[(ri - 1) % len(row_fills)],
                'paragraphs': _paragraphs(value, bold=ri == 0, color=header_text if ri == 0 else '000000', font_size=points),
            })
        body.append({'h': row_h, 'cells': cells})
    return [{
        'op': 'table', 'name': prefix, 'rows': body,
        'options': {
            'x': x, 'y': y, 'w': w, 'h': h,
            'colW': [col_w] * len(rows[0]),
            'border': {'color': border, 'pt': 0.5},
        },
    }]


def sample_deck_spec():
    """Two-slide native deck: a flow row, then three boxes with edge arrows."""
    flow = {
        'pattern': 'flow', 'slide': 1, 'x': 0.5, 'y': 1.5, 'width': 9, 'height': 2.4,
        'gap': 0.55, 'accent': '#1F4E79', 'font_size': 14,
        'items': [
            {'title': 'Receive', 'body': 'Validate input.'},
            {'title': 'Transform', 'body': 'Apply explicit rules.'},
            {'title': 'Publish', 'body': 'Write a new file.'},
        ],
    }
    slide1 = [{'op': 'text', 'name': 'title', 'options': {'x': 0.5, 'y': 0.4, 'w': 9, 'h': 0.6, 'valign': 'top', 'wrap': 'square'},
               'paragraphs': [{'runs': [{'text': 'Flow: edge to edge', 'bold': True, 'fontSize': 28, 'fontFace': 'Meiryo', 'color': '1F4E79'}]}]}]
    slide1.extend(pattern_objects(flow, index=0, slide_count=1, slide_width=10 * _EMU, slide_height=int(7.5 * _EMU)))
    boxes = {
        'A': {'x': 0.6, 'y': 1.6, 'w': 2.6, 'h': 1.3},
        'B': {'x': 6.6, 'y': 1.6, 'w': 2.6, 'h': 1.3},
        'C': {'x': 3.6, 'y': 4.4, 'w': 2.6, 'h': 1.3},
    }
    slide2 = [{'op': 'text', 'name': 'title', 'options': {'x': 0.5, 'y': 0.35, 'w': 9, 'h': 0.5, 'valign': 'top'},
               'paragraphs': [{'runs': [{'text': 'Three objects: edge arrows', 'bold': True, 'fontSize': 24, 'fontFace': 'Meiryo', 'color': '1F4E79'}]}]}]
    for name, box in boxes.items():
        slide2.append(_shape('node-' + name, 'roundRect', (box['x'], box['y'], box['w'], box['h']), line='1F4E79',
                             paragraphs=_paragraphs(name, bold=True, font_size=20, color='1F4E79')))
    for source, target in (('A', 'B'), ('A', 'C'), ('B', 'C')):
        line, head = _arrow_pair(f'link-{source}-{target}', boxes[source], boxes[target], '1F4E79')
        slide2.extend((line, head))
    # Draw center-mode as a back line under a separate pair so the gap reads as the arrow.
    back_a = {'x': 0.6, 'y': 6.3, 'w': 1.6, 'h': 0.7}
    back_b = {'x': 3.2, 'y': 6.3, 'w': 1.6, 'h': 0.7}
    center = arrow_geometry(back_a, back_b, mode='center', color='1F4E79', width=1.5, head=0.18)
    center['line']['name'] = 'center-arrow-line'
    center['head']['name'] = 'center-arrow-head'
    for key in ('flipH', 'flipV'):
        if center['line']['options'].get(key) is False:
            center['line']['options'].pop(key)
    slide2.extend((center['line'], _shape('center-a', 'rect', (back_a['x'], back_a['y'], back_a['w'], back_a['h']), fill='E8EEF4', line='1F4E79',
                                          paragraphs=_paragraphs('A', bold=True, font_size=14, color='1F4E79')),
                   _shape('center-b', 'rect', (back_b['x'], back_b['y'], back_b['w'], back_b['h']), fill='E8EEF4', line='1F4E79',
                          paragraphs=_paragraphs('B', bold=True, font_size=14, color='1F4E79')),
                   center['head']))
    return {
        'width': 10, 'height': 7.5,
        'slides': [
            {'background': {'color': 'FFFFFF'}, 'objects': slide1},
            {'background': {'color': 'FFFFFF'}, 'objects': slide2},
        ],
    }
