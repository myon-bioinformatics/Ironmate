"""Inspect generated PPTX text editability without assuming raster content is editable."""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from pptx_ooxml import ordered_slide_members

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def _editable_runs(root):
    """Count a:r under top-level p:sp and p:cxnSp text bodies, not tables."""
    tree = root.find(f"{P}cSld/{P}spTree")
    if tree is None:
        return 0
    total = 0
    for child in list(tree):
        if child.tag not in (P + "sp", P + "cxnSp"):
            continue
        body = child.find(P + "txBody")
        if body is not None:
            total += len(body.findall(".//" + A + "r"))
    return total


def inspect(path):
    path = Path(path)
    slides = []
    with ZipFile(path) as package:
        for number, member in enumerate(ordered_slide_members(package), 1):
            root = ET.fromstring(package.read(member))
            runs = _editable_runs(root)
            pictures = len(root.findall(f".//{P}pic"))
            texts = [node.text or "" for node in root.findall(f".//{A}t")]
            # A slide may mix raster and native text. One run does not make
            # the whole slide editable, and a picture does not make it empty.
            status = "editable" if runs and not pictures else "unknown" if runs else "unsupported"
            slides.append({"slide": number, "status": status, "editable_runs": runs,
                           "pictures": pictures, "text_nodes": len(texts)})
    return {"source": str(path), "slides": slides}


def main(argv=None):
    from ironmate_cli import ToolParser, guard
    parser = ToolParser(description=__doc__, tool="pptx_inspect.py")
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_json_flag()
    args = parser.parse_args(argv)

    def work():
        report = json.dumps(inspect(args.source), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(report)
        else:
            print(report, end="")
        return 0

    return guard("pptx_inspect.py", work, json_mode=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
