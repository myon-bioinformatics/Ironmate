"""Structural fixtures for exact native PPTX edits, independent of rendering."""
from xml.dom import minidom
from zipfile import ZipFile

import pytest

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches
from pptx_replace import transform

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
MEMBER = "ppt/slides/slide1.xml"


def first(node, ns, name):
    return node.getElementsByTagNameNS(ns, name)[0]


@pytest.fixture
def deck(tmp_path):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    source_box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(2), Inches(1))
    source_box.name = "Target box"
    source_box.text = "文字・text"
    source_box.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    reference = slide.shapes.add_textbox(Inches(5), Inches(2), Inches(2), Inches(1))
    reference.name = "Reference box"
    reference.text = "do not modify"
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(6), Inches(4), Inches(2), Inches(2))
    connector.name = "Existing arrow"
    connector.line.color.rgb = RGBColor(0x20, 0x40, 0x60)
    connector.begin_connect(reference, 0)
    connector.end_connect(source_box, 2)
    other = presentation.slides.add_slide(presentation.slide_layouts[6])
    other.shapes.add_textbox(Inches(0), Inches(0), Inches(1), Inches(1)).text = "second slide"
    initial = tmp_path / "initial.pptx"
    presentation.save(initial)
    source = tmp_path / "source.pptx"
    with ZipFile(initial) as old, ZipFile(source, "w") as new:
        xml = minidom.parseString(old.read(MEMBER))
        native = first(xml, P, "cxnSp")
        line = first(native, A, "ln")
        marker = xml.createElementNS(A, "a:headEnd")
        for key, value in (("type", "triangle"), ("w", "lg"), ("len", "sm")):
            marker.setAttribute(key, value)
        line.appendChild(marker)
        for entry in old.infolist():
            new.writestr(entry, xml.toxml(encoding="UTF-8") if entry.filename == MEMBER else old.read(entry))
    return source


def test_native_rules_change_only_selected_attributes(deck, tmp_path):
    rules = [
        dict(operation="text_frame_top", slide=1, shape_name="Target box", expected="ctr"),
        dict(operation="shape_top", slide=1, shape_name="Target box", reference_shape="Reference box"),
        dict(operation="arrow_color", slide=1, shape_name="Existing arrow", color="#000000", expected="204060"),
        dict(operation="arrowhead_type", slide=1, shape_name="Existing arrow", end="head", type="stealth"),
    ]
    output = tmp_path / "output.pptx"
    source_bytes = deck.read_bytes()
    preview = transform(deck, rules, dry_run=True, destination=output)
    assert not output.exists()
    actual = transform(deck, rules, destination=output)
    assert actual["changes"] == preview["changes"]
    assert actual["change_count"] == 4
    assert source_bytes == deck.read_bytes()
    with ZipFile(deck) as before, ZipFile(output) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != MEMBER:
                assert before.read(name) == after.read(name), name
        expected = minidom.parseString(before.read(MEMBER))
        target = first(expected, P, "sp")
        first(target, A, "bodyPr").setAttribute("anchor", "t")
        first(target, A, "off").setAttribute("y", str(int(Inches(2))))
        connector = first(expected, P, "cxnSp")
        first(connector, A, "srgbClr").setAttribute("val", "000000")
        first(connector, A, "headEnd").setAttribute("type", "stealth")
        # Entire remaining XML, including attachments, orientation and transforms, is unchanged.
        assert minidom.parseString(after.read(MEMBER)).toxml() == expected.toxml()
    result = Presentation(output)
    assert len(result.slides) == 2
    assert result.slides[0].shapes[0].text == "文字・text"
    assert result.slides[0].shapes[0].top == Inches(2)
    assert result.slides[0].shapes[0].text_frame.vertical_anchor == MSO_ANCHOR.TOP
    repeat = tmp_path / "repeat.pptx"
    assert transform(output, [{k: v for k, v in rule.items() if k != "expected"} for rule in rules],
                     destination=repeat)["change_count"] == 0
    assert output.read_bytes() == repeat.read_bytes()


@pytest.mark.parametrize(("rule", "message"), [
    (dict(operation="text_frame_top", slide=1, shape_name="missing"), "exactly one"),
    (dict(operation="text_frame_top", slide=1, shape_name="Target box", expected="b"), "expected old value"),
    (dict(operation="arrow_color", slide=1, shape_name="Target box", color="#000000"), "native connector"),
    (dict(operation="arrowhead_type", slide=1, shape_name="Existing arrow", end="tail", type="diamond"), "tailEnd"),
    (dict(operation="arrowhead_type", slide=1, shape_name="Existing arrow", end="head", type="none"), "visible arrow"),
])
def test_unsupported_native_target_fails_without_publication(deck, tmp_path, rule, message):
    output = tmp_path / "not-created.pptx"
    valid = dict(operation="text_frame_top", slide=1, shape_name="Target box")
    with pytest.raises(ValueError, match=message):
        transform(deck, [valid, rule], destination=output)
    assert not output.exists()


def test_native_rules_cli_uses_toml_and_dry_run(deck, tmp_path, capsys):
    import json
    from pptx_replace import main

    rules = tmp_path / "rules.toml"
    rules.write_text('[[rules]]\noperation = "text_frame_top"\nslide = 1\nshape_name = "Target box"\n',
                     encoding="utf-8")
    output = tmp_path / "cli.pptx"
    main([str(deck), "--rules", str(rules), "--dry-run", "--output", str(output)])
    assert json.loads(capsys.readouterr().out)["change_count"] == 1
    assert not output.exists()
    main([str(deck), "--rules", str(rules), "--output", str(output)])
    assert json.loads(capsys.readouterr().out)["change_count"] == 1
    assert Presentation(output).slides[0].shapes[0].text_frame.vertical_anchor == MSO_ANCHOR.TOP
