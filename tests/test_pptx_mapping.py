"""JSON slide spec ↔ OOXML round trips for the supported subset."""
import json
from xml.etree import ElementTree as ET

import pytest

from pptx_mapping import NOT_REVERSIBLE, canonical_spec, normalized_xml, public_slide, read_slide_xml, write_slide_xml, xml_round_trip
from pptx_render import read_package_spec, render_bytes
from pptx_spec import arrow_geometry, expand_connector, sample_deck_spec


def _slide(**kwargs):
    slide = {'objects': kwargs.pop('objects')}
    slide.update(kwargs)
    return slide


def test_arrow_geometry_matches_the_shared_line_and_triangle_contract():
    side = arrow_geometry({'x': 0.5, 'y': 1, 'w': 2, 'h': 1}, {'x': 4, 'y': 1, 'w': 2, 'h': 1})
    assert (side['x1'], side['y1'], side['x2'], side['y2']) == (2.5, 1.5, 4, 1.5)
    assert side['midpoint'] == {'x': 3.25, 'y': 1.5}
    assert side['distance'] == 1.5
    assert side['rotate'] == 90
    assert side['line']['options']['flipH'] is False
    reverse = arrow_geometry({'x': 4, 'y': 1, 'w': 2, 'h': 1}, {'x': 0.5, 'y': 1, 'w': 2, 'h': 1})
    assert reverse['rotate'] == 270
    assert (reverse['x1'], reverse['x2']) == (4, 2.5)
    vertical = arrow_geometry({'x': 1, 'y': 0.5, 'w': 2, 'h': 1}, {'x': 1, 'y': 3.5, 'w': 2, 'h': 1})
    assert (vertical['x1'], vertical['y1'], vertical['x2'], vertical['y2']) == (2, 1.5, 2, 3.5)
    assert vertical['rotate'] == 180
    assert vertical['midpoint']['y'] == 2.5
    diagonal = arrow_geometry({'x': 0, 'y': 0, 'w': 2, 'h': 1}, {'x': 3, 'y': 3, 'w': 2, 'h': 1})
    assert (diagonal['x1'], diagonal['y1'], diagonal['x2'], diagonal['y2']) == (1.5, 1, 3.5, 3)
    assert diagonal['rotate'] == 135
    assert diagonal['midpoint'] == {'x': 2.5, 'y': 2}
    offset = arrow_geometry({'x': 0, 'y': 0, 'w': 2, 'h': 1}, {'x': 5, 'y': 0.5, 'w': 2, 'h': 1})
    assert (offset['x1'], offset['x2']) == (2, 5)


def test_json_xml_json_and_normalized_xml_round_trip():
    slide = _slide(
        background={'color': '#ffffff'},
        objects=[
            {'op': 'shape', 'name': 'box', 'shape': 'roundRect', 'options': {
                'x': 0.5, 'y': 1, 'w': 2, 'h': 1, 'fill': {'color': '112233'},
                'line': {'color': '#abcdef', 'width': 1.5, 'dashType': 'solid'},
            }, 'paragraphs': [{'align': 'center', 'runs': [
                {'text': ' Box ', 'bold': False, 'italic': True, 'fontSize': 14, 'fontFace': 'Meiryo', 'color': '000000'},
                {'text': '2', 'bold': True, 'fontSize': 14},
            ]}]},
            {'op': 'text', 'name': 'title', 'options': {
                'x': 0.54, 'y': 1.04, 'w': 1.9, 'h': 0.4, 'valign': 'top', 'wrap': 'square',
                'marginLeft': 0.08, 'marginTop': 0.04,
            }, 'paragraphs': [{'runs': [{'text': 'Hello', 'bold': True, 'fontSize': 14, 'color': '000000'}]}]},
            {'op': 'line', 'name': 'arrow-line', 'options': {
                'x': 2.5, 'y': 1.5, 'w': 1.5, 'h': 0, 'flipH': False, 'flipV': False,
                'line': {'color': '000000', 'width': 1.5},
            }},
            {'op': 'shape', 'name': 'arrow-head', 'shape': 'triangle', 'options': {
                'x': 3.16, 'y': 1.41, 'w': 0.18, 'h': 0.18, 'rotate': 90,
                'fill': {'color': '000000'}, 'line': {'color': '000000', 'width': 1.5},
            }},
            {'op': 'table', 'name': 't', 'rows': [
                {'h': 0.5, 'cells': [
                    {'text': 'A', 'fill': '#222222', 'color': 'FFFFFF', 'bold': True, 'fontSize': 14},
                    {'text': 'B', 'fill': '222222', 'color': 'FFFFFF', 'bold': True, 'fontSize': 14},
                ]},
                {'h': 0.5, 'cells': [
                    {'text': 'b', 'fill': 'FFFFFF', 'bold': False},
                    {'text': 'c', 'fill': 'F2F2F2'},
                ]},
            ], 'options': {'x': 0.5, 'y': 2, 'w': 4, 'h': 1, 'colW': [2, 2], 'border': {'color': 'B3B3B3', 'pt': 0.5}}},
        ],
    )
    spec = xml_round_trip(slide)
    again = public_slide(read_slide_xml(write_slide_xml(spec)))
    assert again == spec
    assert normalized_xml(write_slide_xml(spec)) == normalized_xml(write_slide_xml(again))
    # Derived ids are not part of the spec, and they follow z-order.
    assert read_slide_xml(write_slide_xml(spec))['ids'] == [2, 3, 4, 5, 6]
    root = ET.fromstring(write_slide_xml(spec))
    box = root.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr[@name="box"]/../../{http://schemas.openxmlformats.org/presentationml/2006/main}spPr/{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm/{http://schemas.openxmlformats.org/drawingml/2006/main}off')
    assert box.get('x') == str(round(0.5 * 914400))
    assert 'tailEnd' not in write_slide_xml(spec).decode()
    assert 'endArrowType' not in json.dumps(spec)


def test_connector_authoring_expands_and_only_the_shapes_round_trip():
    objects = {
        'a': {'x': 0.5, 'y': 1, 'w': 2, 'h': 1},
        'b': {'x': 4, 'y': 1, 'w': 2, 'h': 1},
    }
    with pytest.raises(ValueError, match='connector'):
        canonical_spec(_slide(objects=[{'op': 'connector', 'from': 'a', 'to': 'b'}]))
    mode, line, head = expand_connector({'op': 'connector', 'from': 'a', 'to': 'b', 'mode': 'edge', 'name': 'link'}, objects.get)
    assert mode == 'edge'
    assert line['op'] == 'line' and head['shape'] == 'triangle'
    expanded = _slide(objects=[
        {'op': 'shape', 'name': 'a', 'shape': 'rect', 'options': {**objects['a'], 'fill': {'color': 'FFFFFF'}}},
        {'op': 'shape', 'name': 'b', 'shape': 'rect', 'options': {**objects['b'], 'fill': {'color': 'FFFFFF'}}},
        line, head,
    ])
    assert xml_round_trip(expanded)['objects'][2]['op'] == 'line'
    assert xml_round_trip(expanded)['objects'][3]['shape'] == 'triangle'


def test_builtin_arrow_styling_is_rejected():
    with pytest.raises(ValueError, match='endArrowType'):
        write_slide_xml(_slide(objects=[{'op': 'line', 'options': {
            'x': 0, 'y': 0, 'w': 1, 'h': 0, 'line': {'color': '000000', 'width': 1, 'endArrowType': 'triangle'},
        }}]))


def test_package_round_trip_uses_the_pptxgenjs_shell(tmp_path):
    spec = canonical_spec({'width': 10, 'height': 7.5, 'slides': [
        _slide(background={'color': 'FFFFFF'}, objects=[
            {'op': 'text', 'name': 'title', 'options': {'x': 1, 'y': 1, 'w': 4, 'h': 0.5, 'valign': 'top'},
             'paragraphs': [{'runs': [{'text': 'Round trip', 'fontSize': 18, 'bold': True, 'color': '112233'}]}]},
        ]),
    ]})
    path = tmp_path / 'deck.pptx'
    path.write_bytes(render_bytes(spec))
    assert canonical_spec(read_package_spec(path)) == spec


def test_not_reversible_is_explicit():
    assert 'theme' in NOT_REVERSIBLE
    assert 'built-in connectors' in NOT_REVERSIBLE
    assert 'authoring connector kind' in NOT_REVERSIBLE
    assert 'xlsx' in NOT_REVERSIBLE
    assert 'shape ids' in NOT_REVERSIBLE
    # The sample deck is inside the subset, including the line-plus-triangle arrows.
    xml_round_trip(canonical_spec(sample_deck_spec())['slides'][0])
    xml_round_trip(canonical_spec(sample_deck_spec())['slides'][1])
