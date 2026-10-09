"""Test-only prototype: background line and separate angular arrowheads."""
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt


def add_diagram(slide, *, chevron=False):
    # Geometry in inches: full line extends behind both boxes.
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(0.5), Inches(1.4), Inches(9.5), Inches(1.4))
    line.line.color.rgb = RGBColor(0, 0, 0)
    line.line.width = Pt(2)
    boxes = []
    for x, text in ((0.5, "A"), (7.5, "B")):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(0.9), Inches(2), Inches(1))
        shape.text = text
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(255, 255, 255)
        boxes.append(shape)
    head = slide.shapes.add_shape(
        MSO_SHAPE.CHEVRON if chevron else MSO_SHAPE.RIGHT_TRIANGLE,
        Inches(4.75), Inches(1.22), Inches(0.35), Inches(0.36))
    head.fill.solid()
    head.fill.fore_color.rgb = RGBColor(0, 0, 0)
    head.line.fill.background()
    return line, boxes, head


def test_diagram_arrowhead_variants(tmp_path):
    for chevron in (False, True):
        p = Presentation()
        slide = p.slides.add_slide(p.slide_layouts[6])
        line, boxes, head = add_diagram(slide, chevron=chevron)
        assert slide.shapes[0] == line
        assert slide.shapes[-1] == head
        assert line.left == boxes[0].left
        assert line.left + line.width == boxes[1].left + boxes[1].width
        assert boxes[0].left + boxes[0].width < head.left < boxes[1].left
        path = tmp_path / ("chevron.pptx" if chevron else "triangle.pptx")
        p.save(path)
        assert len(Presentation(path).slides[0].shapes) == 4
