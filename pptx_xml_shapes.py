"""Narrow native-shape Open XML mutation; no raster/SVG internals are modified."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from pptx import Presentation
from pptx.util import Emu

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def edit_shape(source, destination, *, slide=1, shape_name, fill_rgb=None, line_rgb=None,
               left=None, top=None, width=None, height=None):
    if not isinstance(shape_name, str) or not shape_name.strip():
        raise ValueError("shape_name is required")
    if type(slide) is not int or slide < 1:
        raise ValueError("invalid slide")
    if all(value is None for value in (fill_rgb, line_rgb, left, top, width, height)):
        raise ValueError("no changes requested")
    for color in (fill_rgb, line_rgb):
        if color is not None and (not isinstance(color, str) or len(color) != 7
                                  or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:])):
            raise ValueError("colors must be #RRGGBB")
    for key, value in (("left", left), ("top", top), ("width", width), ("height", height)):
        if value is not None and (type(value) not in (int, Emu) or (key in ("width", "height") and value <= 0)):
            raise ValueError("geometry must be integer EMUs with positive size")
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("destination must be new and distinct")
    member = f"ppt/slides/slide{slide}.xml"
    with ZipFile(source) as package:
        entries = package.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or member not in names:
            raise ValueError("invalid or missing slide XML")
        root = ET.fromstring(package.read(member))
        matches = [node for node in root.findall(".//" + P + "sp")
                   if (node.find(P + "nvSpPr/" + P + "cNvPr") is not None
                       and node.find(P + "nvSpPr/" + P + "cNvPr").get("name") == shape_name)]
        if len(matches) != 1:
            raise ValueError("expected exactly one named native shape")
        shape = matches[0]
        props = shape.find(P + "spPr")
        if props is None:
            raise ValueError("shape properties missing")
        if fill_rgb is not None:
            fill = props.find(A + "solidFill")
            if fill is None or len(fill) != 1 or fill[0].tag != A + "srgbClr":
                raise ValueError("explicit RGB shape fill required")
            fill[0].set("val", fill_rgb[1:].upper())
        if line_rgb is not None:
            line = props.find(A + "ln")
            fill = line.find(A + "solidFill") if line is not None else None
            if fill is None or len(fill) != 1 or fill[0].tag != A + "srgbClr":
                raise ValueError("explicit RGB shape line required")
            fill[0].set("val", line_rgb[1:].upper())
        if any(value is not None for value in (left, top, width, height)):
            xfrm = props.find(A + "xfrm")
            if xfrm is None or xfrm.find(A + "off") is None or xfrm.find(A + "ext") is None:
                raise ValueError("explicit shape geometry required")
            off, ext = xfrm.find(A + "off"), xfrm.find(A + "ext")
            for node, key, value in ((off, "x", left), (off, "y", top),
                                     (ext, "cx", width), (ext, "cy", height)):
                if value is not None:
                    node.set(key, str(value))
        replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        try:
            with ZipFile(destination, "x") as changed:
                for entry in entries:
                    changed.writestr(entry, replacement if entry.filename == member
                                     else package.read(entry.filename))
            Presentation(destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return {"output": str(destination), "shape_name": shape_name, "slide": slide}

