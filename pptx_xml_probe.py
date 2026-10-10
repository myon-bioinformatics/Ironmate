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

