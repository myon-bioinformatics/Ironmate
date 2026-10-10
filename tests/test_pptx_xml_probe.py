"""Open XML metadata mutation must preserve unrelated ZIP parts and reopen."""
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from pptx import Presentation
from pptx_xml_probe import set_slide_name
import pytest


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

