"""📊 Slides and sheets: Markdown/Marp to PPTX, Mermaid, Open XML patterns and shapes, layout, mapping, replace, PptxGenJS images, UNO read-back and xlsx/csv."""

import base64
import csv
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from tests.fixture_pptx import generate, parse_blocks
from tests.fixture_pptx_layout import CASES, IDS, case_rule, make_source
from tests.test_uno_roundtrip import CLIENT, _assert_fixture_readback

ROOT = Path(__file__).resolve().parents[1]
import pptx_pipeline
import pptx_replace
from ironlib import mermaid_svg, xlsx_render, xlsx_spec
from ironlib.pptx_mapping import NOT_REVERSIBLE, canonical_spec, normalized_xml, public_slide, read_slide_xml, write_slide_xml, xml_round_trip
from ironlib.pptx_render import read_package_spec, render_bytes
from ironlib.pptx_spec import arrow_geometry, expand_connector, sample_deck_spec
from ironlib.pptx_xml import edit_shape, edit_shape_fills, set_slide_name
from ironlib.xlsx_ooxml import read_spec, write_package
from ironlib.xlsx_render import read_workbook, write_workbook
from ironlib.xlsx_spec import decode_csv_bytes, sheet_from_csv, workbook_from_sheets, workbook_from_spec
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Inches, Pt
from pptx_inspect import inspect
from pptx_layout import arrange
from pptx_replace import transform
from xlsx_csv import convert_paths, main, write_csv_workbook


# ═══ · markdown pptx ═════════════════════════════════════════════════════════════════════════════════════

def test_markdown_pptx_xml_edit_roundtrip(tmp_path):
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    original, edited = tmp_path / "original.pptx", tmp_path / "edited.pptx"
    manifest = generate(source, original)
    assert len(manifest["blocks"]) == 5
    prs = Presentation(original)
    shapes = list(prs.slides[0].shapes)
    assert [s.name for s in shapes] == [b["shape_name"] for b in manifest["blocks"]]
    assert [s.text for s in shapes] == [b["text"] for b in manifest["blocks"]]
    assert all(s.text_frame.paragraphs[0].runs[0].font.color.rgb == RGBColor(0, 0, 0) for s in shapes)

    result = transform(original, [{"operation": "text_color", "color": "#2244AA"}], destination=edited)
    assert result["change_count"] == 5
    changed = Presentation(edited).slides[0].shapes
    assert [s.text for s in changed] == [b["text"] for b in manifest["blocks"]]
    assert all(s.text_frame.paragraphs[0].runs[0].font.color.rgb == RGBColor(34, 68, 170) for s in changed)

    with zipfile.ZipFile(original) as before, zipfile.ZipFile(edited) as after:
        names = set(before.namelist())
        assert names == set(after.namelist())
        for name in names - {"ppt/slides/slide1.xml"}:
            assert before.read(name) == after.read(name), name
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        xml = ET.fromstring(after.read("ppt/slides/slide1.xml"))
        assert [t.text for t in xml.findall(".//a:t", ns)] == [b["text"] for b in manifest["blocks"]]


def test_markdown_cli_one_liner(tmp_path):
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    output = tmp_path / "fixture.pptx"
    script = Path(__file__).resolve().parent / "fixture_pptx.py"
    p = subprocess.run([sys.executable, str(script), str(source), "-o", str(output)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert output.is_file()
    assert "markdown:line-1:title" in p.stdout


@pytest.mark.parametrize("text", ["", "### Unsupported", "- list", "# ", "\n".join(["text"] * 9)])
def test_markdown_explicit_failures(text):
    with pytest.raises(ValueError):
        parse_blocks(text)


def test_markdown_output_collision(tmp_path):
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    output = tmp_path / "existing.pptx"
    output.write_bytes(b"unchanged")
    with pytest.raises(ValueError, match="new file"):
        generate(source, output)
    assert output.read_bytes() == b"unchanged"


# ═══ · marp input modes ══════════════════════════════════════════════════════════════════════════════════
# Input-mode tests without requiring Marp or a browser.

@pytest.mark.parametrize("mode", ["file", "text", "stdin"])
def test_input_modes_share_converter(monkeypatch, tmp_path, capsys, mode):
    captured = []
    def fake_convert(source, output, *, marp):
        content = Path(source).read_text(encoding="utf-8")
        captured.append(content)
        return {"source": str(source), "output": str(output), "slides": 1, "backend": "marp"}
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": []})
    output = tmp_path / "out.pptx"
    source = tmp_path / "sample.md"
    source.write_text("# Hello\n", encoding="utf-8")
    if mode == "file":
        args = [str(source), "-o", str(output)]
    elif mode == "text":
        args = ["--text", "# Hello\n", "-o", str(output)]
    else:
        monkeypatch.setattr(pptx_pipeline.sys, "stdin", io.StringIO("# Hello\n"))
        args = ["-", "-o", str(output)]
    pptx_pipeline.main(args)
    assert captured == ["# Hello\n"]
    result = json.loads(capsys.readouterr().out)
    assert result["conversion"]["slides"] == 1
    assert result["conversion"]["source"] == (str(source) if mode == "file" else mode if mode == "stdin" else "inline")


def test_empty_stdin_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(pptx_pipeline.sys, "stdin", io.StringIO(" \n"))
    with pytest.raises(SystemExit) as exc:
        pptx_pipeline.main(["-", "-o", str(tmp_path / "out.pptx")])
    assert exc.value.code == 2


from pptx_pipeline import read_markdown_input


def test_file_mode(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# テスト\n", encoding="utf-8")
    assert read_markdown_input(source=path) == ("# テスト\n", str(path))


def test_inline_mode():
    assert read_markdown_input(text="# Hello\n") == ("# Hello\n", "inline")


def test_stdin_mode():
    assert read_markdown_input(source="-", stdin=io.StringIO("# Input\n")) == (
        "# Input\n", "stdin")


@pytest.mark.parametrize("kwargs", [{}, {"source": "sample.md", "text": "# Both"}])
def test_invalid_mode_selection(kwargs):
    with pytest.raises(ValueError, match="exactly one"):
        read_markdown_input(**kwargs)


# ═══ · mermaid svg ═══════════════════════════════════════════════════════════════════════════════════════
# Mermaid SVG preprocessing: source retention, fail closed and pipeline handoff.

def test_mermaid_to_svg_preserves_source_and_uses_local_image(monkeypatch, tmp_path):
    source = "Before\n```mermaid\nflowchart LR\n A --> B\n```\nAfter\n"
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: "/fake/mmdc")
    def fake_run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text("<svg></svg>", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(mermaid_svg.subprocess, "run", fake_run)
    transformed, images = mermaid_svg.render_mermaid(source, tmp_path, mmdc="mmdc")
    assert len(images) == 1
    assert images[0].is_file()
    assert "```mermaid" not in transformed
    assert "![Diagram 1 h:480](./mermaid-" in transformed
    assert transformed.startswith("Before\n") and transformed.endswith("\nAfter\n")
    assert source == "Before\n```mermaid\nflowchart LR\n A --> B\n```\nAfter\n"


def test_missing_mmdc_fails_explicitly(monkeypatch, tmp_path):
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: None)
    with pytest.raises(RuntimeError, match="not installed"):
        mermaid_svg.render_mermaid("```mermaid\nA-->B\n```", tmp_path)


def test_pipeline_opt_in_uses_svg_and_preserves_original(monkeypatch, tmp_path):
    source = "```mermaid\nflowchart LR\n A --> B\n```\n"
    seen = {}
    def fake_render(raw, directory, *, mmdc, background="#FFFFFF", foreground=None):
        assert background == "#FFFFFF"
        assert raw == source
        return "# Diagram\n", [directory / "mermaid-1.svg"]
    def fake_convert(path, output, *, marp, allow_local_files=False):
        assert allow_local_files
        seen["prepared"] = Path(path).read_text(encoding="utf-8")
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "render_mermaid", fake_render)
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": []})
    result = pptx_pipeline.run(text=source, output=tmp_path / "out.pptx", mmdc="mmdc")
    assert seen["prepared"] == "# Diagram\n"
    assert result["conversion"]["mermaid_svg_count"] == 1


def test_mermaid_background_option_and_invalid_color(monkeypatch, tmp_path):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: "/fake/mmdc")
    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[command.index("-o") + 1]).write_text("<svg></svg>", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(mermaid_svg.subprocess, "run", fake_run)
    source = "```mermaid\nflowchart LR\n A --> B\n```"
    mermaid_svg.render_mermaid(source, tmp_path / "white")
    mermaid_svg.render_mermaid(source, tmp_path / "navy", background="#14213D")
    assert calls[0][-2:] == ["-b", "#FFFFFF"]
    assert calls[1][-2:] == ["-b", "#14213D"]
    with pytest.raises(ValueError, match="background"):
        mermaid_svg.render_mermaid(source, tmp_path / "bad", background="red")


def test_foreground_is_applied_before_svg_render_not_by_marp(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: "/fake/mmdc")
    observed = []
    def fake_run(command, **kwargs):
        assert "-c" not in command  # theme directive is not a config-file path
        source = Path(command[command.index("-i") + 1])
        observed.append(source.read_text(encoding="utf-8"))
        Path(command[command.index("-o") + 1]).write_text("<svg></svg>", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(mermaid_svg.subprocess, "run", fake_run)
    raw = "flowchart LR\n A --> B"
    original = "```mermaid\n" + raw + "\n```"
    transformed, images = mermaid_svg.render_mermaid(
        original, tmp_path, foreground="#FFFFFF", background="#14213D")
    assert "primaryTextColor" in observed[0]
    assert '"#FFFFFF"' in observed[0]
    assert "lineColor" in observed[0]
    assert "primaryColor" in observed[0]
    assert "#243552" in observed[0]
    assert raw in observed[0]
    assert images[0].exists()
    assert "primaryTextColor" not in transformed


# ═══ · openxml patterns ══════════════════════════════════════════════════════════════════════════════════
# Contract tests for tri-state editability master registry.

REGISTRY = Path(__file__).parent / "fixtures/openxml/editability_patterns.toml"


def test_registry_has_unique_ids_and_fail_closed_default():
    with REGISTRY.open("rb") as stream:
        data = tomllib.load(stream)
    assert data["schema_version"] == 1
    assert data["default_status"] == "unknown"
    patterns = data["patterns"]
    assert len(patterns) >= 3
    assert len({p["id"] for p in patterns}) == len(patterns)
    assert all(p["status"] in {"editable", "unsupported", "unknown"} for p in patterns)
    assert all(p["operation"] and p["condition"] for p in patterns)
    assert all(p.get("evidence") for p in patterns if p["status"] == "editable")


def test_registry_does_not_claim_marp_image_text_is_editable():
    with REGISTRY.open("rb") as stream:
        patterns = tomllib.load(stream)["patterns"]
    image = next(p for p in patterns if p["id"] == "rasterized-slide-text")
    assert image["status"] == "unsupported"
    assert image["alternative"] == "regenerate_from_markdown"


# ═══ · pptx attribute matrix ═════════════════════════════════════════════════════════════════════════════
# Attribute insertion and narrow Open XML mutation experiments.

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def make_input(path):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    shape.text_frame.paragraphs[0].add_run().text = "Test"
    presentation.save(path)


def properties(path):
    with ZipFile(path) as archive:
        xml = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    return xml.find(".//a:rPr", NS)


@pytest.mark.parametrize("operation,rule,expected", [
    ("bold", {"value": True}, {"b": "1"}),
    ("bold", {"value": False}, {"b": "0"}),
    ("font_size", {"points": 18}, {"sz": "1800"}),
    ("text_color", {"color": "#123456"}, {"rgb": "123456"}),
])
def test_absent_attribute_insertion(tmp_path, operation, rule, expected):
    source, output = tmp_path / "source.pptx", tmp_path / "output.pptx"
    make_input(source)
    before = properties(source)
    assert before is None or not any(key in before.attrib for key in ("b", "sz"))
    if operation == "text_color":
        # Current CLI deliberately rejects inherited/theme color; record unsupported.
        with pytest.raises(ValueError, match="explicit RGB"):
            transform(source, [{"operation": operation, **rule}], destination=output)
        assert not output.exists()
        return
    assert transform(source, [{"operation": operation, **rule}], destination=output)["change_count"] == 1
    after = properties(output)
    assert after is not None
    for key, value in expected.items():
        assert after.attrib[key] == value
    assert Presentation(output).slides[0].shapes[0].text == "Test"


def test_sequential_style_edits_and_dry_run(tmp_path):
    source, output = tmp_path / "source.pptx", tmp_path / "styled.pptx"
    make_input(source)
    rules = [
        {"operation": "font_size", "points": 18},
        {"operation": "bold", "value": True},
        {"operation": "bold", "value": False},
    ]
    preview = transform(source, rules, dry_run=True)
    actual = transform(source, rules, destination=output)
    assert preview["change_count"] == actual["change_count"] == 3
    run = Presentation(output).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.size == Pt(18)
    assert run.font.bold is False
    assert properties(output).attrib["b"] == "0"


def test_xml_fallback_inserts_explicit_rgb_without_changing_other_members(tmp_path):
    """Experimental XML-only fixture, not a production CLI mutation."""
    source, output = tmp_path / "source.pptx", tmp_path / "xml-color.pptx"
    make_input(source)
    uri = NS["a"]
    with ZipFile(source) as archive:
        names = archive.namelist()
        members = {name: archive.read(name) for name in names}
    root = ET.fromstring(members["ppt/slides/slide1.xml"])
    run = root.find(".//a:r", NS)
    assert run is not None
    rpr = run.find("a:rPr", NS)
    if rpr is None:
        rpr = ET.Element(f"{{{uri}}}rPr")
        run.insert(0, rpr)
    fill = ET.SubElement(rpr, f"{{{uri}}}solidFill")
    ET.SubElement(fill, f"{{{uri}}}srgbClr", {"val": "123456"})
    members["ppt/slides/slide1.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with ZipFile(output, "x") as archive:
        for name in names:
            archive.writestr(name, members[name])
    with ZipFile(source) as before, ZipFile(output) as after:
        assert set(before.namelist()) == set(after.namelist())
        assert all(before.read(name) == after.read(name) for name in names if name != "ppt/slides/slide1.xml")
    run = Presentation(output).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.color.rgb == RGBColor(18, 52, 86)
    assert run.text == "Test"


# ═══ · pptx diagram shapes ═══════════════════════════════════════════════════════════════════════════════
# Test-only prototype: background line and separate angular arrowheads.

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


def test_multiple_horizontal_boxes_have_independent_midpoint_heads(tmp_path):
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    boxes = []
    for x in (1, 4, 7):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(1), Inches(1), Inches(1))
        boxes.append(shape)
    for first, second in zip(boxes, boxes[1:]):
        center_y = first.top + first.height // 2
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, first.left, center_y,
            second.left + second.width, center_y)
        midpoint = (first.left + first.width + second.left) // 2
        head = slide.shapes.add_shape(
            MSO_SHAPE.RIGHT_TRIANGLE, midpoint - Inches(0.15),
            center_y - Inches(0.15), Inches(0.3), Inches(0.3))
        assert head.left + head.width // 2 == midpoint
        assert line.left == first.left
        assert line.left + line.width == second.left + second.width
    path = tmp_path / "horizontal.pptx"
    p.save(path)
    assert len(Presentation(path).slides[0].shapes) == 7


def test_vertical_boxes_use_full_height_line_and_midpoint_head(tmp_path):
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    upper = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(3), Inches(1), Inches(2), Inches(1))
    lower = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(3), Inches(4), Inches(2), Inches(1))
    center_x = upper.left + upper.width // 2
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, center_x, upper.top,
        center_x, lower.top + lower.height)
    midpoint = (upper.top + upper.height + lower.top) // 2
    head = slide.shapes.add_shape(
        MSO_SHAPE.DOWN_ARROW, center_x - Inches(0.15),
        midpoint - Inches(0.15), Inches(0.3), Inches(0.3))
    assert head.top + head.height // 2 == midpoint
    assert line.top == upper.top
    assert line.top + line.height == lower.top + lower.height
    path = tmp_path / "vertical.pptx"
    p.save(path)
    assert len(Presentation(path).slides[0].shapes) == 4


def edge_center(shape, edge):
    if edge == "left":
        return shape.left, shape.top + shape.height // 2
    if edge == "right":
        return shape.left + shape.width, shape.top + shape.height // 2
    if edge == "top":
        return shape.left + shape.width // 2, shape.top
    if edge == "bottom":
        return shape.left + shape.width // 2, shape.top + shape.height
    raise ValueError("edge must be left/right/top/bottom")


def test_diagonal_edge_selection_and_rotation(tmp_path):
    import math

    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    a = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    c = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(6), Inches(4), Inches(2), Inches(1))
    for start_edge in ("left", "top", "bottom", "right"):
        start = edge_center(c, start_edge)
        end = edge_center(a, "bottom")
        dx, dy = end[0] - start[0], end[1] - start[1]
        angle = math.degrees(math.atan2(dy, dx))
        assert math.isfinite(angle)
        line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *start, *end)
        mid_x, mid_y = (start[0] + end[0]) // 2, (start[1] + end[1]) // 2
        head = slide.shapes.add_shape(
            MSO_SHAPE.RIGHT_TRIANGLE, mid_x - Inches(0.15),
            mid_y - Inches(0.15), Inches(0.3), Inches(0.3))
        head.rotation = angle
        assert abs((head.rotation - angle + 180) % 360 - 180) < 0.01
        assert line is not None
    with pytest.raises(ValueError, match="edge"):
        edge_center(c, "diagonal")
    path = tmp_path / "diagonal.pptx"
    p.save(path)
    assert len(Presentation(path).slides[0].shapes) == 10


# ═══ · pptx edge geometry ════════════════════════════════════════════════════════════════════════════════
# Geometry-only contracts for explicit edge-to-edge connections.
#
# These tests deliberately separate mathematical orientation from PPTX shape
# rotation, which must be calibrated using rendered output.

EDGES = ("left", "right", "top", "bottom")


def direction(source, source_edge, target, target_edge):
    sx, sy = edge_center(source, source_edge)
    tx, ty = edge_center(target, target_edge)
    dx, dy = tx - sx, ty - sy
    if dx == 0 and dy == 0:
        raise ValueError("coincident anchors")
    return (sx, sy), (tx, ty), math.degrees(math.atan2(dy, dx))


def head_vertices(center, angle, length, half_width):
    """Return tip, left base, right base in slide coordinate space."""
    theta = math.radians(angle)
    ux, uy = math.cos(theta), math.sin(theta)
    nx, ny = -uy, ux
    cx, cy = center
    tip = (cx + ux * length / 2, cy + uy * length / 2)
    base = (cx - ux * length / 2, cy - uy * length / 2)
    return tip, (base[0] + nx * half_width, base[1] + ny * half_width), (
        base[0] - nx * half_width, base[1] - ny * half_width)


@pytest.mark.parametrize("start_edge", EDGES)
@pytest.mark.parametrize("end_edge", EDGES)
@pytest.mark.parametrize("reverse", (False, True))
def test_all_edge_pairs_and_reverse(start_edge, end_edge, reverse):
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    a = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    b = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6), Inches(4), Inches(2), Inches(1))
    source, target = (b, a) if reverse else (a, b)
    start, end, angle = direction(source, start_edge, target, end_edge)
    center = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    tip, left, right = head_vertices(center, angle, Inches(0.4), Inches(0.15))
    ux, uy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    assert math.isclose((tip[0] - center[0]) * ux + (tip[1] - center[1]) * uy,
                        Inches(0.2), abs_tol=1)
    assert math.isclose((left[0] + right[0]) / 2, center[0] - ux * Inches(0.2), abs_tol=1)
    assert math.isclose((left[1] + right[1]) / 2, center[1] - uy * Inches(0.2), abs_tol=1)
    assert math.isclose(math.hypot(left[0] - center[0], left[1] - center[1]),
                        math.hypot(right[0] - center[0], right[1] - center[1]), abs_tol=1)


def test_coincident_anchor_rejected():
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    with pytest.raises(ValueError, match="coincident"):
        direction(shape, "left", shape, "left")


# ═══ · pptx inspect ══════════════════════════════════════════════════════════════════════════════════════
# Regression tests for conservative editability decisions.

def test_native_text_is_editable(tmp_path):
    path = tmp_path / "native.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text = "Hello"
    prs.save(path)
    result = inspect(path)["slides"][0]
    assert result["status"] == "editable"
    assert result["editable_runs"] == 1


def test_no_text_is_unsupported(tmp_path):
    path = tmp_path / "empty.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(path)
    result = inspect(path)["slides"][0]
    assert result["status"] == "unsupported"
    assert result["editable_runs"] == 0


# ═══ · pptx layout ═══════════════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def deck(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i in range(4):
        s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(.1), Inches(.1), Inches(1 + i * .1), Inches(.5))
        s.text = f'Card {i}'
    path = tmp_path / 'source.pptx'
    prs.save(path)
    return path

def rule():
    return dict(pattern='grid', slide=1, shape_ids=[2,3,4,5], columns=2, x=1, y=1, gap_x=.2, gap_y=.3)

def test_geometry_preservation_and_preview(deck, tmp_path):
    out = tmp_path / 'out.pptx'
    before = deck.read_bytes()
    preview = arrange(deck, [rule()], dry_run=True)
    assert preview['changes'] == arrange(deck, [rule()], destination=out)['changes']
    assert deck.read_bytes() == before
    shapes = Presentation(out).slides[0].shapes
    assert [(s.left, s.top) for s in shapes] == [(Inches(1), Inches(1)), (Inches(2.5), Inches(1)), (Inches(1), Inches(1.8)), (Inches(2.5), Inches(1.8))]
    assert [(s.text,s.width,s.height) for s in shapes] == [(s.text,s.width,s.height) for s in Presentation(deck).slides[0].shapes]
    with ZipFile(deck) as a, ZipFile(out) as b:
        assert a.namelist() == b.namelist()
        assert all(a.read(n) == b.read(n) for n in a.namelist() if n != 'ppt/slides/slide1.xml')
    assert arrange(out, [rule()], dry_run=True)['change_count'] == 0

@pytest.mark.parametrize('patch', [dict(gap_x=float('nan')),dict(gap_y=-1),dict(shape_ids=[2,2]),dict(shape_ids=[99]),dict(columns=0),dict(x=99),dict(pattern='bad')])
def test_invalid_does_not_publish(deck,tmp_path,patch):
    config = rule()
    config.update(patch)
    out = tmp_path / 'bad.pptx'
    with pytest.raises(ValueError):
        arrange(deck,[config],destination=out)
    assert not out.exists()

@pytest.mark.parametrize('mode',['row','column'])
def test_sequential_preview(deck,tmp_path,mode):
    second = rule()
    second['pattern'] = mode
    out = tmp_path / 'out.pptx'
    assert arrange(deck,[rule(),second],dry_run=True)['changes'] == arrange(deck,[rule(),second],destination=out)['changes']

def test_no_overwrite(deck):
    before = deck.read_bytes()
    with pytest.raises(ValueError):
        arrange(deck,[rule()],destination=deck)
    assert deck.read_bytes() == before

def test_connected_and_rotated_shapes_rejected(deck,tmp_path):
    from pptx.enum.shapes import MSO_CONNECTOR
    prs = Presentation(deck)
    slide = prs.slides[0]
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,0,0,100,100)
    connector.begin_connect(slide.shapes[0],0)
    connected = tmp_path / 'connected.pptx'
    prs.save(connected)
    with pytest.raises(ValueError,match='routing'):
        arrange(connected,[rule()],dry_run=True)
    prs = Presentation(deck)
    prs.slides[0].shapes[0].rotation = 20
    rotated = tmp_path / 'rotated.pptx'
    prs.save(rotated)
    with pytest.raises(ValueError,match='unrotated'):
        arrange(rotated,[rule()],dry_run=True)


@pytest.mark.parametrize('case', CASES, ids=[case[0] for case in CASES])
def test_unequal_sizes_literal_coordinates_and_preservation(tmp_path, case):
    source, output = tmp_path / 'source.pptx', tmp_path / 'output.pptx'
    make_source(source)
    original_bytes = source.read_bytes()
    config = case_rule(case)
    preview = arrange(source, [config], dry_run=True)
    rules = tmp_path / 'rules.toml'
    rules.write_text('[[rules]]\n' + '\n'.join(
        f'{key} = {json.dumps(value)}' for key, value in config.items()) + '\n', encoding='utf-8')
    process = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'pptx_layout.py'),
                              str(source), '--rules', str(rules), '--output', str(output)],
                             capture_output=True, text=True, check=True)
    applied = json.loads(process.stdout)
    assert preview['changes'] == applied['changes']
    assert applied['change_count'] == 5
    assert source.read_bytes() == original_bytes
    before = Presentation(source).slides[0].shapes
    after = Presentation(output).slides[0].shapes
    by_id = {s.shape_id: s for s in after}
    # Explicit independent expectations, not calculated from preview or apply.
    assert [(by_id[i].left, by_id[i].top) for i in IDS] == [
        (round(x * 914400), round(y * 914400)) for x, y in case[4]]
    assert [(s.shape_id, s.name, s.text, s.width, s.height) for s in before] == [
        (s.shape_id, s.name, s.text, s.width, s.height) for s in after]
    assert (before[-1].left, before[-1].top) == (after[-1].left, after[-1].top)
    # Positive-area overlap is forbidden; touching edges for zero gap is valid.
    targets = [by_id[i] for i in IDS]
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            assert (a.left + a.width <= b.left or b.left + b.width <= a.left
                    or a.top + a.height <= b.top or b.top + b.height <= a.top)
    # Normalizing only selected offsets must leave the complete XML unchanged:
    # covers runs/styles, shape geometry, ordering and unselected shapes.
    ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
          'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with ZipFile(source) as old, ZipFile(output) as new:
        assert old.namelist() == new.namelist()
        for name in old.namelist():
            if name != 'ppt/slides/slide1.xml':
                assert old.read(name) == new.read(name)
                continue
            roots = [ET.fromstring(z.read(name)) for z in (old, new)]
            for root in roots:
                for shape in root.findall('p:cSld/p:spTree/p:sp', ns):
                    if int(shape.find('p:nvSpPr/p:cNvPr', ns).get('id')) in IDS:
                        off = shape.find('p:spPr/a:xfrm/a:off', ns)
                        off.set('x', '0')
                        off.set('y', '0')
            assert ET.canonicalize(ET.tostring(roots[0], encoding='unicode')) == ET.canonicalize(ET.tostring(roots[1], encoding='unicode'))
    assert arrange(output, [config], dry_run=True)['change_count'] == 0


# ═══ · pptx mapping ══════════════════════════════════════════════════════════════════════════════════════
# JSON slide spec ↔ OOXML round trips for the supported subset.

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


def _sp_tree_names(payload):
    presentation = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
    root = ET.fromstring(payload)
    tree = root.find(f'.//{presentation}spTree')
    names = []
    for child in list(tree):
        if child.tag in (f'{presentation}nvGrpSpPr', f'{presentation}grpSpPr'):
            continue
        names.append(child.find(f'.//{presentation}cNvPr').get('name'))
    return names


def test_one_deck_json_and_object_array_order_is_z_order():
    line = {'op': 'line', 'name': 'back-line', 'options': {
        'x': 0, 'y': 0, 'w': 1, 'h': 0, 'line': {'color': '000000', 'width': 1}}}
    box = {'op': 'shape', 'name': 'box', 'shape': 'rect', 'options': {
        'x': 0.2, 'y': 0.2, 'w': 1, 'h': 1, 'fill': {'color': 'FFFFFF'}}}
    head = {'op': 'shape', 'name': 'head', 'shape': 'triangle', 'options': {
        'x': 0.4, 'y': 0.4, 'w': 0.2, 'h': 0.2, 'fill': {'color': '000000'}}}
    deck = {'width': 10, 'height': 7.5, 'slides': [{
        'behind': [line], 'objects': [box], 'inFront': [head],
    }]}
    spec = canonical_spec(deck)
    assert set(spec) == {'width', 'height', 'slides'}
    slide = spec['slides'][0]
    assert set(slide) == {'objects'}
    assert [obj['name'] for obj in slide['objects']] == ['back-line', 'box', 'head']
    assert _sp_tree_names(write_slide_xml(deck['slides'][0])) == ['back-line', 'box', 'head']
    assert [obj['name'] for obj in xml_round_trip(slide)['objects']] == ['back-line', 'box', 'head']
    with pytest.raises(ValueError, match='list of slide documents'):
        canonical_spec([deck['slides'][0]])
    with pytest.raises(ValueError, match='objects array'):
        canonical_spec({'slides': [{'back': [line], 'items': [box], 'front': [head]}]})


def test_not_reversible_is_explicit():
    assert 'theme' in NOT_REVERSIBLE
    assert 'built-in connectors' in NOT_REVERSIBLE
    assert 'authoring connector kind' in NOT_REVERSIBLE
    assert 'xlsx' in NOT_REVERSIBLE
    assert 'shape ids' in NOT_REVERSIBLE
    # The sample deck is inside the subset, including the line-plus-triangle arrows.
    xml_round_trip(canonical_spec(sample_deck_spec())['slides'][0])
    xml_round_trip(canonical_spec(sample_deck_spec())['slides'][1])


# ═══ · pptx plain style ══════════════════════════════════════════════════════════════════════════════════
# PPTX-first styling contracts and explicit Open XML fallback boundaries.

def sample(path, *, explicit_background=True, explicit_text=True):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if explicit_background:
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(25, 50, 75)
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    run = shape.text_frame.paragraphs[0].add_run()
    run.text = "Heading"
    if explicit_text:
        run.font.color.rgb = RGBColor(200, 100, 50)
    prs.save(path)


def test_plain_style_batch_is_repeatable_and_preserves_other_parts(tmp_path):
    original = tmp_path / "original.pptx"
    first = tmp_path / "first.pptx"
    second = tmp_path / "second.pptx"
    sample(original)
    rules = [
        {"operation": "slide_background", "color": "#FFFFFF"},
        {"operation": "text_color", "color": "#000000"},
        {"operation": "font_family", "name": "Meiryo"},
        {"operation": "font_size", "points": 20},
        {"operation": "bold", "value": True},
    ]
    assert transform(original, rules, dry_run=True)["change_count"] == 5
    assert transform(original, rules, destination=first)["change_count"] == 5
    assert transform(first, rules, dry_run=True)["change_count"] == 0
    assert transform(first, rules, destination=second)["change_count"] == 0
    prs = Presentation(second)
    slide = prs.slides[0]
    run = slide.shapes[0].text_frame.paragraphs[0].runs[0]
    assert slide.background.fill.fore_color.rgb == RGBColor(255, 255, 255)
    assert run.text == "Heading"
    assert run.font.color.rgb == RGBColor(0, 0, 0)
    assert run.font.name == "Meiryo"
    assert run.font.size.pt == 20
    assert run.font.bold is True
    with ZipFile(original) as before, ZipFile(first) as after:
        names = set(before.namelist())
        assert names == set(after.namelist())
        assert all(before.read(name) == after.read(name)
                   for name in names if name != "ppt/slides/slide1.xml")
        xml = ET.fromstring(after.read("ppt/slides/slide1.xml"))
        assert xml.find(".//a:rPr/a:solidFill/a:srgbClr", NS).attrib["val"] == "000000"


@pytest.mark.parametrize("explicit_background,explicit_text,operation,expected", [
    (False, True, "slide_background", "only explicit solid RGB slide backgrounds"),
    (True, False, "text_color", "explicit RGB"),
])
def test_unverified_inherited_styles_fail_closed(tmp_path, explicit_background,
                                                   explicit_text, operation, expected):
    source = tmp_path / "source.pptx"
    target = tmp_path / "target.pptx"
    sample(source, explicit_background=explicit_background, explicit_text=explicit_text)
    rule = {"operation": operation, "color": "#FFFFFF" if operation == "slide_background" else "#000000"}
    with pytest.raises(ValueError, match=expected):
        transform(source, [rule], destination=target)
    assert not target.exists()
    assert Presentation(source).slides[0].shapes[0].text == "Heading"


# ═══ · pptx replace ══════════════════════════════════════════════════════════════════════════════════════

def fixture(tmp_path):
    path = tmp_path / "source.pptx"
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    run = shape.text_frame.paragraphs[0].add_run()
    run.text = "Draft title"
    run.font.color.rgb = RGBColor(255, 0, 0)
    run.font.bold = True
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor(255, 255, 255)
    p.save(path)
    return path


def test_dry_run_and_preservation(tmp_path):
    src = fixture(tmp_path)
    dst = tmp_path / "output.pptx"
    rules = [{"operation": "replace_text", "old": "Draft", "new": "Final"}, {"operation": "text_color", "color": "#000000"}]
    preview = transform(src, rules, dry_run=True)
    assert preview["change_count"] == 2
    assert not dst.exists()
    result = transform(src, rules, destination=dst)
    assert result["change_count"] == 2
    original = Presentation(src).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    updated = Presentation(dst).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert original.text == "Draft title"
    assert updated.text == "Final title"
    assert updated.font.bold is True
    assert updated.font.color.rgb == RGBColor(0, 0, 0)


def test_background_and_no_overwrite(tmp_path):
    src = fixture(tmp_path)
    dst = tmp_path / "out.pptx"
    assert transform(src, [{"operation": "slide_background", "color": "#112233"}], destination=dst)["change_count"] == 1
    assert Presentation(dst).slides[0].background.fill.fore_color.rgb == RGBColor(17, 34, 51)
    with pytest.raises(ValueError, match="new file"):
        transform(src, [{"operation": "replace_text", "old": "none", "new": "x"}], destination=dst)


def test_unsupported_and_zero_match(tmp_path):
    src = fixture(tmp_path)
    assert transform(src, [{"operation": "replace_text", "old": "missing", "new": "x"}], dry_run=True)["change_count"] == 0
    with pytest.raises(ValueError, match="unsupported operation"):
        transform(src, [{"operation": "arrow", "color": "#000000"}], dry_run=True)


def test_cli_one_liner_and_explicit_failure_evidence(tmp_path):
    """An intentionally failing child suite must yield a nonzero exit and JUnit failure."""
    import subprocess
    import sys
    import xml.etree.ElementTree as ET

    src = fixture(tmp_path)
    output = tmp_path / "cli-output.pptx"
    cli = Path(__file__).resolve().parents[1] / "pptx_replace.py"
    command = [sys.executable, str(cli), str(src), "--replace", "Draft", "Final", "--output", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert Presentation(output).slides[0].shapes[0].text_frame.paragraphs[0].runs[0].text == "Final title"

    child = tmp_path / "test_intentional_failure.py"
    child.write_text(
        "def test_expected_failure():\\n    assert 1 == 2, 'intentional pptx CI failure probe'\\n".replace("\\n", "\n"),
        encoding="utf-8",
    )
    junit = tmp_path / "intentional-failure.xml"
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(child), f"--junitxml={junit}"],
        capture_output=True, text=True, check=False, cwd=tmp_path,
    )
    assert probe.returncode == 1, probe.stdout + probe.stderr
    root = ET.parse(junit).getroot()
    failures = root.findall(".//testcase/failure")
    assert len(failures) == 1
    assert "intentional pptx CI failure probe" in (failures[0].text or "")


def test_output_collision_is_rejected_before_reading_input(tmp_path):
    existing = tmp_path / "existing.pptx"
    existing.write_bytes(b"preserve me")
    with pytest.raises(ValueError, match="new file"):
        transform(tmp_path / "missing.pptx", [{"operation": "replace_text", "old": "x", "new": "y"}], destination=existing)
    assert existing.read_bytes() == b"preserve me"


def test_slide_xml_preserves_unrelated_shape_and_text(tmp_path):
    import zipfile
    import xml.etree.ElementTree as ET

    src = fixture(tmp_path)
    dst = tmp_path / "changed.pptx"
    transform(src, [{"operation": "replace_text", "old": "Draft", "new": "Final"}], destination=dst)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    def slide_xml(path):
        with zipfile.ZipFile(path) as archive:
            return ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    before, after = slide_xml(src), slide_xml(dst)
    assert [node.text for node in before.findall(".//a:t", ns)] == ["Draft title"]
    assert [node.text for node in after.findall(".//a:t", ns)] == ["Final title"]
    # Normalized XML trees must agree after restoring only the intended text change.
    after.find(".//a:t", ns).text = "Draft title"
    assert ET.tostring(before) == ET.tostring(after)


def test_font_size_bold_and_rgb_xml_roundtrip(tmp_path):
    import zipfile
    import xml.etree.ElementTree as ET

    src = fixture(tmp_path)
    dst = tmp_path / "styled.pptx"
    rules = [
        {"operation": "font_size", "points": 24},
        {"operation": "bold", "value": False},
        {"operation": "text_color", "color": "#112233"},
    ]
    assert transform(src, rules, dry_run=True)["change_count"] == 3
    assert transform(src, rules, destination=dst)["change_count"] == 3
    run = Presentation(dst).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.size.pt == 24
    assert run.font.bold is False
    assert run.font.color.rgb == RGBColor(17, 34, 51)
    with zipfile.ZipFile(dst) as z:
        root = ET.fromstring(z.read("ppt/slides/slide1.xml"))
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    properties = root.find(".//a:rPr", ns)
    assert properties is not None
    assert properties.attrib["sz"] == "2400"
    assert properties.attrib["b"] == "0"
    assert properties.find(".//a:srgbClr", ns).attrib["val"].upper() == "112233"


@pytest.mark.parametrize("rule", [
    {"operation": "font_size", "points": 0},
    {"operation": "font_size", "points": "12"},
    {"operation": "font_size", "points": True},
    {"operation": "bold", "value": "true"},
])
def test_style_rule_rejects_invalid_types(tmp_path, rule):
    src = fixture(tmp_path)
    with pytest.raises(ValueError):
        transform(src, [rule], dry_run=True)


def test_batch_font_family_override(tmp_path):
    src = fixture(tmp_path)
    dst = tmp_path / "font.pptx"
    rules = [{"operation": "font_family", "name": "Yu Gothic"}]
    assert transform(src, rules, dry_run=True)["change_count"] == 1
    assert transform(src, rules, destination=dst)["change_count"] == 1
    run = Presentation(dst).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Yu Gothic"
    import zipfile
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(dst) as archive:
        root = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    latin = root.find(".//a:rPr/a:latin", ns)
    assert latin is not None and latin.attrib["typeface"] == "Yu Gothic"


def test_font_family_rejects_empty(tmp_path):
    src = fixture(tmp_path)
    with pytest.raises(ValueError, match="nonempty"):
        transform(src, [{"operation": "font_family", "name": ""}], dry_run=True)


@pytest.mark.parametrize("target_exists", [True, False], ids=["symlink", "dangling-symlink"])
def test_output_symlink_is_rejected_before_reading_source(tmp_path, target_exists):
    target = tmp_path / "link-target.pptx"
    if target_exists:
        target.write_bytes(b"do not touch")
    destination = tmp_path / "output.pptx"
    try:
        destination.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    rules = [{"operation": "replace_text", "old": "Draft", "new": "Final"}]
    with pytest.raises(ValueError, match="new file"):
        transform(tmp_path / "missing-source.pptx", rules, destination=destination)
    assert destination.is_symlink()
    assert os.readlink(destination) == str(target)
    if target_exists:
        assert target.read_bytes() == b"do not touch"
    else:
        assert not target.exists()


@pytest.mark.parametrize("intruder", ["file", "symlink", "dangling-symlink"])
def test_competing_destination_creation_is_not_removed(tmp_path, monkeypatch, intruder):
    src = fixture(tmp_path)
    source_bytes = src.read_bytes()
    destination = tmp_path / "output.pptx"
    target = tmp_path / "other.pptx"
    if intruder == "symlink":
        target.write_bytes(b"another process")
    real_link = os.link

    def race_before_publish(staged, output, *args, **kwargs):
        assert Path(staged).is_file()  # A complete staged PPTX already exists.
        if intruder == "file":
            Path(output).write_bytes(b"another process")
        else:
            try:
                Path(output).symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                pytest.skip(f"symlink creation unavailable: {exc}")
        return real_link(staged, output, *args, **kwargs)

    monkeypatch.setattr(pptx_replace.os, "link", race_before_publish)
    with pytest.raises(FileExistsError):
        transform(src, [{"operation": "replace_text", "old": "Draft", "new": "Final"}], destination=destination)
    assert src.read_bytes() == source_bytes
    assert os.path.lexists(destination)
    if intruder == "file":
        assert destination.read_bytes() == b"another process"
    else:
        assert destination.is_symlink()
        assert os.readlink(destination) == str(target)
        if intruder == "symlink":
            assert target.read_bytes() == b"another process"
        else:
            assert not target.exists()
    assert not list(tmp_path.glob(".pptx-replace-*"))


@pytest.mark.parametrize("concurrent_creation", [False, True])
def test_partial_save_failure_never_publishes_or_deletes_output(
    tmp_path, monkeypatch, concurrent_creation
):
    src = fixture(tmp_path)
    source_bytes = src.read_bytes()
    destination = tmp_path / "output.pptx"
    presentation_type = type(Presentation(src))

    def interrupted_save(self, output):
        output.write(b"incomplete archive")
        if concurrent_creation:
            destination.write_bytes(b"competing writer")
        raise OSError("injected PPTX write failure")

    monkeypatch.setattr(presentation_type, "save", interrupted_save)
    with pytest.raises(OSError, match="injected PPTX write failure"):
        transform(src, [{"operation": "replace_text", "old": "Draft", "new": "Final"}], destination=destination)
    assert src.read_bytes() == source_bytes
    if concurrent_creation:
        assert destination.read_bytes() == b"competing writer"
    else:
        assert not os.path.lexists(destination)
    assert not list(tmp_path.glob(".pptx-replace-*"))


def test_successful_publish_removes_staging_directory(tmp_path):
    src = fixture(tmp_path)
    destination = tmp_path / "output.pptx"
    transform(src, [{"operation": "replace_text", "old": "Draft", "new": "Final"}], destination=destination)
    assert Presentation(destination).slides[0].shapes[0].text == "Final title"
    assert not list(tmp_path.glob(".pptx-replace-*"))


# ═══ · pptx replace sequential ═══════════════════════════════════════════════════════════════════════════
# Dry-run must predict cascading edits, including their exact locations.

def make_source_pptx_replace_sequential(tmp_path):
    source = tmp_path / "source.pptx"
    presentation = Presentation()
    for _ in range(2):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(255, 255, 255)
        shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        for text in ("Draft Draft", " unchanged"):
            run = shape.text_frame.paragraphs[0].add_run()
            run.text = text
            run.font.color.rgb = RGBColor(255, 0, 0)
            run.font.name = "Arial"
            run.font.size = Pt(12)
            run.font.bold = False
    presentation.save(source)
    return source


def test_chained_text_reports_exact_matches_and_locations(tmp_path):
    source = make_source_pptx_replace_sequential(tmp_path)
    before = source.read_bytes()
    output = tmp_path / "output.pptx"
    rules = [
        {"operation": "replace_text", "old": "Draft", "new": "Final", "slide": 1},
        {"operation": "replace_text", "old": "Final", "new": "Approved"},
        {"operation": "replace_text", "old": "Draft", "new": "Archived"},
    ]
    expected = [
        {"rule": rule, "slide": slide, "shape": 1, "paragraph": 1, "run": 1, "count": 2}
        for rule, slide in ((0, 1), (1, 1), (2, 2))
    ]
    preview = pptx_replace.transform(source, rules, dry_run=True, destination=output)
    assert source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source}
    actual = pptx_replace.transform(source, rules, destination=output)
    assert preview == {**actual, "dry_run": True}
    assert preview["changes"] == expected
    assert preview["change_count"] == 6
    result = Presentation(output)
    assert result.slides[0].shapes[0].text == "Approved Approved unchanged"
    assert result.slides[1].shapes[0].text == "Archived Archived unchanged"
    assert source.read_bytes() == before


@pytest.mark.parametrize("operation,values", [
    ("text_color", [{"color": "#112233"}, {"color": "#FF0000"}]),
    ("font_family", [{"name": "Meiryo"}, {"name": "Arial"}]),
    ("font_size", [{"points": 18}, {"points": 12}]),
    ("bold", [{"value": True}, {"value": False}]),
    ("slide_background", [{"color": "#112233"}, {"color": "#FFFFFF"}]),
])
def test_style_repeat_and_restore_use_previous_rule_state(tmp_path, operation, values):
    source = make_source_pptx_replace_sequential(tmp_path)
    output = tmp_path / "output.pptx"
    # Repeating the first update is a no-op; restoring the original is an edit.
    rules = [{"operation": operation, "slide": 1, **value}
             for value in (values[0], values[0], values[1])]
    preview = pptx_replace.transform(source, rules, dry_run=True)
    actual = pptx_replace.transform(source, rules, destination=output)
    assert preview == {**actual, "dry_run": True}
    if operation == "slide_background":
        expected = [{"rule": rule, "slide": 1, "operation": operation} for rule in (0, 2)]
    else:
        expected = [{"rule": rule, "slide": 1, "shape": 1, "paragraph": 1,
                     "run": run, "count": 1} for rule in (0, 2) for run in (1, 2)]
    assert preview["changes"] == expected
    assert preview["change_count"] == len(expected)
    result = Presentation(output)
    for slide in result.slides:
        assert slide.background.fill.fore_color.rgb == RGBColor(255, 255, 255)
        for run in slide.shapes[0].text_frame.paragraphs[0].runs:
            assert run.font.color.rgb == RGBColor(255, 0, 0)
            assert run.font.name == "Arial"
            assert run.font.size == Pt(12)
            assert run.font.bold is False


def test_cli_mixed_rules_and_no_dry_run_writes(tmp_path, capsys, monkeypatch):
    source = make_source_pptx_replace_sequential(tmp_path)
    before = source.read_bytes()
    output = tmp_path / "output.pptx"
    rules = tmp_path / "rules.toml"
    rules.write_text('''
[[rules]]
operation = "replace_text"
old = "Draft"
new = "Final"
[[rules]]
operation = "text_color"
color = "#000000"
[[rules]]
operation = "font_family"
name = "Meiryo"
[[rules]]
operation = "slide_background"
color = "#112233"
[[rules]]
operation = "font_size"
points = 18
[[rules]]
operation = "bold"
value = true
[[rules]]
operation = "replace_text"
old = "Final"
new = "Approved"
''', encoding="utf-8")
    arguments = [str(source), "--rules", str(rules), "--output", str(output)]
    presentation_type = type(Presentation(source))

    def no_save(*args, **kwargs):
        pytest.fail("dry-run must never call save")

    with monkeypatch.context() as patch:
        patch.setattr(presentation_type, "save", no_save)
        pptx_replace.main([*arguments, "--dry-run"])
        preview = json.loads(capsys.readouterr().out)
        # Even an output aliasing the source must leave the original untouched.
        pptx_replace.main([str(source), "--rules", str(rules), "--output", str(source), "--dry-run"])
        assert json.loads(capsys.readouterr().out) == preview
    assert source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source, rules}
    pptx_replace.main(arguments)
    actual = json.loads(capsys.readouterr().out)
    assert preview == {**actual, "dry_run": True}
    assert preview["change_count"] == 26
    for slide in Presentation(output).slides:
        assert slide.shapes[0].text == "Approved Approved unchanged"
        assert slide.background.fill.fore_color.rgb == RGBColor(17, 34, 51)
        for run in slide.shapes[0].text_frame.paragraphs[0].runs:
            assert run.font.color.rgb == RGBColor(0, 0, 0)
            assert run.font.name == "Meiryo"
            assert run.font.size == Pt(18)
            assert run.font.bold is True
    assert source.read_bytes() == before


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("rule,message", [
    ({"operation": "arrow"}, "unsupported operation"),
    ({"operation": "replace_text", "old": "", "new": "x"}, "nonempty old"),
    ({"operation": "text_color", "color": "red"}, "#RRGGBB"),
    ({"operation": "slide_background", "color": "#GGGGGG"}, "#RRGGBB"),
    ({"operation": "font_family", "name": " "}, "nonempty name"),
    ({"operation": "font_size", "points": True}, "numeric points"),
    ({"operation": "bold", "value": "true"}, "boolean value"),
    ({"operation": "bold", "value": True, "slide": 3}, "slide must be"),
])
def test_invalid_later_rule_fails_without_writes(tmp_path, dry_run, rule, message):
    source = make_source_pptx_replace_sequential(tmp_path)
    before = source.read_bytes()
    with pytest.raises(ValueError, match=message):
        pptx_replace.transform(source, [
            {"operation": "replace_text", "old": "Draft", "new": "Final"}, rule,
        ], dry_run=dry_run, destination=tmp_path / "output.pptx")
    assert source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source}


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("operation", ["text_color", "slide_background"])
def test_inherited_colors_still_fail_after_prior_edit(tmp_path, dry_run, operation):
    source = tmp_path / "source.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = "Draft"
    presentation.save(source)
    before = source.read_bytes()
    with pytest.raises(ValueError, match="explicit RGB|explicit solid RGB|inherited slide background"):
        pptx_replace.transform(source, [
            {"operation": "replace_text", "old": "Draft", "new": "Final"},
            {"operation": operation, "color": "#112233"},
        ], dry_run=dry_run, destination=tmp_path / "output.pptx")
    assert source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source}


# ═══ · pptx xml batch ════════════════════════════════════════════════════════════════════════════════════
# Multi-slide Open XML mapping, selective changes, and atomic rejection.

def make_deck(path, *, reordered=False):
    presentation = Presentation()
    for i in range(3):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1),
                                       Inches(3), Inches(1))
        shape.name = "Shared"
        shape.text = f"Slide {i + 1}"
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(10, 20, 30)
    if reordered:
        ids = presentation.slides._sldIdLst
        first = ids[0]
        ids.remove(first)
        ids.append(first)
    presentation.save(path)


def rgb(deck, index):
    return Presentation(deck).slides[index].shapes[0].fill.fore_color.rgb


def test_selective_and_all_slide_recolor(tmp_path):
    source, selective, all_slides = (tmp_path / n for n in ("original.pptx", "selective.pptx", "all.pptx"))
    make_deck(source)
    report = edit_shape_fills(source, selective, [
        {"slide": 2, "shape_name": "Shared", "fill_rgb": "#AABBCC"}])
    assert report["changed_slides"] == [2]
    assert [rgb(selective, i) for i in range(3)] == [
        RGBColor(10, 20, 30), RGBColor(170, 187, 204), RGBColor(10, 20, 30)]
    rules = [{"slide": i, "shape_name": "Shared", "fill_rgb": "#FFFFFF"} for i in range(1, 4)]
    result = edit_shape_fills(selective, all_slides, rules)
    assert result["changed_slides"] == [1, 2, 3]
    assert all(rgb(all_slides, i) == RGBColor(255, 255, 255) for i in range(3))
    with ZipFile(source) as old, ZipFile(selective) as new:
        assert old.namelist() == new.namelist()
        assert [name for name in old.namelist() if old.read(name) != new.read(name)] == [
            "ppt/slides/slide2.xml"]


def test_reordered_slide_uses_display_order_not_xml_suffix(tmp_path):
    source, output = tmp_path / "reordered.pptx", tmp_path / "edited.pptx"
    make_deck(source, reordered=True)
    assert [s.shapes[0].text for s in Presentation(source).slides] == [
        "Slide 2", "Slide 3", "Slide 1"]
    report = edit_shape_fills(source, output, [
        {"slide": 1, "shape_name": "Shared", "fill_rgb": "#ABCDEF"}])
    # Raw presentation.xml.rels maps the first displayed slide to slide2.xml.
    # python-pptx partname can be re-normalized and is not a stored ZIP locator.
    assert report["changed_members"] == ["ppt/slides/slide2.xml"]
    assert rgb(output, 0) == RGBColor(171, 205, 239)
    assert rgb(output, 1) == RGBColor(10, 20, 30)


@pytest.mark.parametrize("rules", [
    [{"slide": 4, "shape_name": "Shared", "fill_rgb": "#FFFFFF"}],
    [{"slide": 1, "shape_name": "Missing", "fill_rgb": "#FFFFFF"}],
    [{"slide": 1, "shape_name": "Shared", "fill_rgb": "white"}],
    [{"slide": 1, "shape_name": "Shared", "fill_rgb": "#FFFFFF"},
     {"slide": 1, "shape_name": "Shared", "fill_rgb": "#000000"}],
    [{"slide": 1, "shape_name": "Shared", "fill_rgb": "#FFFFFF"},
     {"slide": 3, "shape_name": "Missing", "fill_rgb": "#000000"}],
])
def test_invalid_batch_writes_nothing(tmp_path, rules):
    source, output = tmp_path / "source.pptx", tmp_path / "edited.pptx"
    make_deck(source)
    with pytest.raises(ValueError):
        edit_shape_fills(source, output, rules)
    assert not output.exists()
    assert all(rgb(source, i) == RGBColor(10, 20, 30) for i in range(3))


# ═══ · pptx xml probe ════════════════════════════════════════════════════════════════════════════════════
# Open XML metadata mutation must preserve unrelated ZIP parts and reopen.

def test_slide_name_xml_edit_roundtrip(tmp_path):
    source = tmp_path / "original.pptx"
    destination = tmp_path / "edited.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(source)
    result = set_slide_name(source, destination, name="UML diagram")
    assert result["member"] == "ppt/slides/slide1.xml"
    with ZipFile(source) as before, ZipFile(destination) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != "ppt/slides/slide1.xml":
                assert before.read(name) == after.read(name)
        root = ET.fromstring(after.read("ppt/slides/slide1.xml"))
        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
        assert root.find("p:cSld", ns).get("name") == "UML diagram"
    assert len(Presentation(destination).slides) == 1


def test_xml_edit_rejects_overwrite(tmp_path):
    source = tmp_path / "original.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(source)
    with pytest.raises(ValueError, match="new file"):
        set_slide_name(source, source)


def test_xml_native_run_style_roundtrip(tmp_path):
    from pptx.dml.color import RGBColor
    from pptx.util import Inches
    from ironlib.pptx_xml import set_run_style
    src, dst = tmp_path / "source.pptx", tmp_path / "style.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "Editable"
    run.font.color.rgb = RGBColor(100, 100, 100)
    prs.save(src)
    report = set_run_style(src, dst, rgb="#112233", points=24, bold=True)
    assert report["runs"] == 1
    actual = Presentation(dst).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert actual.font.color.rgb == RGBColor(17, 34, 51)
    assert actual.font.size.pt == 24
    assert actual.font.bold is True
    assert actual.text == "Editable"
    with ZipFile(src) as before, ZipFile(dst) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist()
                   if name != "ppt/slides/slide1.xml")


def test_xml_style_rejects_inherited_rgb_without_output(tmp_path):
    from pptx.util import Inches
    from ironlib.pptx_xml import set_run_style
    src, dst = tmp_path / "source.pptx", tmp_path / "style.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = "Inherited"
    prs.save(src)
    with pytest.raises(ValueError, match="explicit RGB"):
        set_run_style(src, dst, rgb="#000000")
    assert not dst.exists()


@pytest.mark.parametrize("kwargs", [
    {"rgb": "#xyzxyz"}, {"points": 0}, {"bold": "true"}, {}
])
def test_xml_style_invalid_rules_fail_closed(tmp_path, kwargs):
    from ironlib.pptx_xml import set_run_style
    with pytest.raises(ValueError):
        set_run_style(tmp_path / "missing.pptx", tmp_path / "out.pptx", **kwargs)


# ═══ · pptx xml shapes ═══════════════════════════════════════════════════════════════════════════════════
# Open XML shape mutation preserves other package members and rejects ambiguity.

def sample_pptx_xml_shapes(path, *, explicit=True):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    shape.name = "Target"
    if explicit:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(20, 30, 40)
        shape.line.color.rgb = RGBColor(50, 60, 70)
    prs.save(path)


def test_shape_fill_line_and_geometry_roundtrip(tmp_path):
    src, dst = tmp_path / "source.pptx", tmp_path / "edited.pptx"
    sample_pptx_xml_shapes(src)
    edit_shape(src, dst, shape_name="Target", fill_rgb="#112233",
               line_rgb="#445566", left=Inches(2), top=Inches(3),
               width=Inches(4), height=Inches(2))
    shape = Presentation(dst).slides[0].shapes[0]
    assert shape.fill.fore_color.rgb == RGBColor(17, 34, 51)
    assert shape.line.color.rgb == RGBColor(68, 85, 102)
    assert (shape.left, shape.top, shape.width, shape.height) == (
        Inches(2), Inches(3), Inches(4), Inches(2))
    with ZipFile(src) as before, ZipFile(dst) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist()
                   if name != "ppt/slides/slide1.xml")


def test_missing_explicit_style_fails_closed(tmp_path):
    src, dst = tmp_path / "source.pptx", tmp_path / "edited.pptx"
    sample_pptx_xml_shapes(src, explicit=False)
    with pytest.raises(ValueError, match="explicit RGB"):
        edit_shape(src, dst, shape_name="Target", fill_rgb="#FFFFFF")
    assert not dst.exists()


@pytest.mark.parametrize("kwargs", [
    {"shape_name": "Missing", "fill_rgb": "#112233"},
    {"shape_name": "Target", "width": 0},
    {"shape_name": "Target", "line_rgb": "red"},
    {"shape_name": "Target"},
])
def test_invalid_shape_rules_are_rejected(tmp_path, kwargs):
    src, dst = tmp_path / "source.pptx", tmp_path / "edited.pptx"
    sample_pptx_xml_shapes(src)
    with pytest.raises(ValueError):
        edit_shape(src, dst, **kwargs)
    assert not dst.exists()


# ═══ · pptxgenjs image ═══════════════════════════════════════════════════════════════════════════════════
# PptxGenJS image embedding (exercises the pinned image-size override).

# 1x1 PNG
_MIN_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD0lEQVQImWNgYGBgAAAABQABDavlc2QAAAABJRU5ErkJggg=='
)

_NODE_SCRIPT = """
const PptxGenJS = require('pptxgenjs');
(async () => {
  const pptx = new PptxGenJS();
  const slide = pptx.addSlide();
  slide.addImage({ path: process.argv[1], x: 1, y: 1, w: 2, h: 2 });
  await pptx.writeFile({ fileName: process.argv[2] });
})();
"""


def test_pptxgenjs_embeds_image_with_overridden_image_size(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node.js required for pptxgenjs image-size check')
    if not (ROOT / 'node_modules' / 'pptxgenjs' / 'package.json').is_file():
        pytest.skip('pinned pptxgenjs is not installed; run npm ci from the repository root')
    image = tmp_path / 'dot.png'
    image.write_bytes(_MIN_PNG)
    deck = tmp_path / 'deck.pptx'
    run = subprocess.run(
        ['node', '-e', _NODE_SCRIPT, str(image), str(deck)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    assert deck.is_file() and deck.stat().st_size > 0
    with zipfile.ZipFile(deck) as archive:
        media = [name for name in archive.namelist() if name.startswith('ppt/media/') and not name.endswith('/')]
    assert media, 'expected at least one embedded media part'


# ═══ · uno readback ══════════════════════════════════════════════════════════════════════════════════════
# Offline UNO readback contracts; no LibreOffice process or package install.

__all__ = []


def _readback():
    return {'pages': 1, 'shapes': [
        {'text': 'Box 1', 'origin': [25400, 20320]},
        {'text': 'Box 2', 'origin': [25781, 20574]},
        {'text': 'Box 3', 'origin': [26162, 20828]},
        {'text': 'Box 4', 'origin': [26543, 21082]},
        {'text': 'Box 5', 'origin': [26924, 21336]},
        {'text': 'Synthetic layout fixture: unchanged label', 'origin': [1905, 381]},
    ]}


def test_readback_accepts_expected_shapes_in_any_order():
    seen = _readback()
    seen['shapes'].reverse()
    _assert_fixture_readback(seen)


@pytest.mark.parametrize('text', ['Box 1', 'Unexpected label', ''])
def test_readback_rejects_extra_shapes_including_duplicates_and_unlabelled(text):
    seen = _readback()
    seen['shapes'].append({'text': text, 'origin': [25400, 20320]})
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_readback_rejects_duplicate_replacing_an_expected_shape():
    seen = _readback()
    seen['shapes'][1] = dict(seen['shapes'][0])
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


@pytest.mark.parametrize('index', [0, 5])
def test_readback_rejects_missing_box_or_label(index):
    seen = _readback()
    seen['shapes'].pop(index)
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_readback_rejects_wrong_page_count():
    seen = _readback()
    seen['pages'] = 2
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


@pytest.mark.parametrize('axis', [0, 1])
def test_readback_position_tolerance_still_fails_outside_boundary(axis):
    seen = _readback()
    seen['shapes'][0]['origin'][axis] += 5
    _assert_fixture_readback(seen)
    seen['shapes'][0]['origin'][axis] += 1
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_client_preserves_every_shape_record(monkeypatch, capsys):
    records = [
        {'text': 'Box 1', 'origin': [1, 2]},
        {'text': 'Box 1', 'origin': [3, 4]},
        {'text': '', 'origin': [5, 6]},
    ]
    shapes = [SimpleNamespace(String=s['text'],
                              Position=SimpleNamespace(X=s['origin'][0], Y=s['origin'][1]))
              for s in records]
    page = SimpleNamespace(Count=len(shapes), getByIndex=shapes.__getitem__)
    closed = []
    doc = SimpleNamespace(DrawPages=SimpleNamespace(Count=1, getByIndex=lambda _: page),
                          close=lambda value: closed.append(value))
    desktop = SimpleNamespace(loadComponentFromURL=lambda *args: doc, terminate=lambda: None)
    remote = SimpleNamespace(ServiceManager=SimpleNamespace(createInstanceWithContext=lambda *args: desktop))
    resolver = SimpleNamespace(resolve=lambda _: remote)
    context = SimpleNamespace(ServiceManager=SimpleNamespace(createInstanceWithContext=lambda *args: resolver))
    monkeypatch.setitem(sys.modules, 'uno', SimpleNamespace(getComponentContext=lambda: context,
                                                           systemPathToFileUrl=lambda path: path))
    monkeypatch.setitem(sys.modules, 'com.sun.star.beans', SimpleNamespace(PropertyValue=SimpleNamespace))
    monkeypatch.setattr(sys, 'argv', ['-c', '/synthetic/source.pptx', '12345'])
    exec(compile(CLIENT, '<fake UNO client>', 'exec'), {})
    assert json.loads(capsys.readouterr().out) == {'pages': 1, 'shapes': records}
    assert closed == [True]


# ═══ · xlsx csv ══════════════════════════════════════════════════════════════════════════════════════════
# CSV encoding and xlsx Open XML checks. No spreadsheet app.

XLSX_CSV_NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


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
    monkeypatch.setattr('ironlib.xlsx_render._run', unexpected_writer)
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
    assert [node.text for node in root.findall('.//m:f', XLSX_CSV_NS)] == ['SUM(1,2)']
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
    assert root.find('.//m:f', XLSX_CSV_NS).text == 'B2*1.1'
    assert read_spec(payload)['sheets'][0]['rows'][1][2]['f'] == 'B2*1.1'
    assert root.find('m:autoFilter', XLSX_CSV_NS).get('ref') == 'A1:C3'
    bordered = [cell for cell in root.findall('.//m:c', XLSX_CSV_NS) if cell.get('s') not in (None, '0')]
    assert bordered
    style_root = ET.fromstring(styles)
    thin = [item for item in style_root.findall('.//m:border', XLSX_CSV_NS) if item.find('m:left', XLSX_CSV_NS).get('style') == 'thin']
    assert len(thin) == 1
    assert thin[0].find('m:left/m:color', XLSX_CSV_NS).get('rgb') == 'FF000000'
    assert style_root.find('.//m:numFmt[@formatCode="0.000"]', XLSX_CSV_NS) is not None
    assert style_root.find('.//m:alignment[@horizontal="right"]', XLSX_CSV_NS) is not None
    assert len(sheets) == 2
    xfs = style_root.findall('m:cellXfs/m:xf', XLSX_CSV_NS)
    assert xfs
    assert int(style_root.find('m:cellXfs', XLSX_CSV_NS).get('count')) == len(xfs)
    for cell in root.findall('.//m:c', XLSX_CSV_NS):
        assert 0 <= int(cell.get('s')) < len(xfs)


def test_empty_cells_keep_grid_borders():
    sheet = sheet_from_csv('S', 'a,b,\n1,2,\n', borders=True, autofilter=True)
    spec = workbook_from_sheets([sheet])
    for name in ('min', 'exceljs'):
        payload = write_workbook(spec, name)
        assert read_spec(payload) == spec
        root = ET.fromstring(archive_sheet(payload, 0))
        empty = root.find('m:sheetData/m:row[@r="1"]/m:c[@r="C1"]', XLSX_CSV_NS)
        assert empty is not None and empty.find('m:v', XLSX_CSV_NS) is None
        with ZipFile(BytesIO(payload)) as archive:
            styles = ET.fromstring(archive.read('xl/styles.xml'))
        xf = styles.findall('m:cellXfs/m:xf', XLSX_CSV_NS)[int(empty.get('s'))]
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
            texts = ET.fromstring(archive.read(sheet_name)).findall('.//m:is/m:t', XLSX_CSV_NS)
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
