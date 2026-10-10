"""Narrow Open XML slide-name mutation, preserving every other package member."""
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pptx import Presentation

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def set_slide_name(source, destination, *, slide=1, name="Diagram"):
    """Edit p:cSld/@name in a new PPTX; never rewrite the source."""
    source, destination = Path(source), Path(destination)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be nonempty")
    if type(slide) is not int or slide < 1:
        raise ValueError("slide must be a positive integer")
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("destination must be a new file")
    member = f"ppt/slides/slide{slide}.xml"
    with ZipFile(source) as original:
        names = original.namelist()
        if member not in names:
            raise ValueError("slide XML member not found")
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members are unsupported")
        root = ET.fromstring(original.read(member))
        csld = root.find(P + "cSld")
        if csld is None:
            raise ValueError("p:cSld missing")
        csld.set("name", name)
        replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        try:
            with ZipFile(destination, "x") as changed:
                for entry in original.infolist():
                    changed.writestr(entry, replacement if entry.filename == member
                                     else original.read(entry.filename))
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    Presentation(destination)
    return {"source": str(source), "output": str(destination), "member": member, "name": name}



A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def set_run_style(source, destination, *, slide=1, rgb=None, points=None, bold=None):
    """Experimental native a:rPr edit; reject inherited colors and image text."""
    if rgb is None and points is None and bold is None:
        raise ValueError("at least one style attribute required")
    if rgb is not None:
        if not isinstance(rgb, str) or len(rgb) != 7 or rgb[0] != "#" or not all(
                char in "0123456789abcdefABCDEF" for char in rgb[1:]):
            raise ValueError("rgb must be #RRGGBB")
    if points is not None and (type(points) not in (int, float) or not 1 <= points <= 400):
        raise ValueError("points must be between 1 and 400")
    if bold is not None and type(bold) is not bool:
        raise ValueError("bold must be boolean")
    if type(slide) is not int or slide < 1:
        raise ValueError("slide must be positive")
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("destination must be a new file")
    member = f"ppt/slides/slide{slide}.xml"
    with ZipFile(source) as original:
        names = original.namelist()
        if member not in names or len(names) != len(set(names)):
            raise ValueError("missing or duplicate slide XML member")
        root = ET.fromstring(original.read(member))
        runs = root.findall(".//" + A + "r")
        if not runs:
            raise ValueError("no editable native text runs")
        # Prevalidate every run before modifying any XML or writing output.
        if rgb is not None:
            for run in runs:
                props = run.find(A + "rPr")
                fill = props.find(A + "solidFill") if props is not None else None
                if fill is None or len(fill) != 1 or fill[0].tag != A + "srgbClr":
                    raise ValueError("explicit RGB run color required")
        for run in runs:
            props = run.find(A + "rPr")
            if props is None:
                props = ET.Element(A + "rPr")
                run.insert(0, props)
            if points is not None:
                props.set("sz", str(round(points * 100)))
            if bold is not None:
                props.set("b", "1" if bold else "0")
            if rgb is not None:
                props.find(A + "solidFill")[0].set("val", rgb[1:].upper())
        replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        try:
            with ZipFile(destination, "x") as changed:
                for entry in original.infolist():
                    changed.writestr(entry, replacement if entry.filename == member
                                     else original.read(entry.filename))
            Presentation(destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return {"output": str(destination), "member": member, "runs": len(runs)}
