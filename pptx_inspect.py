"""Inspect generated PPTX text editability without assuming raster content is editable."""
import json
import sys
from io import BytesIO
from pathlib import Path; from xml.etree import ElementTree as ET; from zipfile import ZipFile

from ironlib.pptx_ooxml import ordered_slide_members

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
    """Inspect a path or an in-memory PPTX byte sequence."""
    if isinstance(path, (bytes, bytearray, memoryview)):
        package_input = BytesIO(path)
        source = "<memory>"
    else:
        package_input = Path(path)
        source = str(package_input)
    slides = []
    with ZipFile(package_input) as package:
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
    return {"source": source, "slides": slides}


def main(argv=None):
    from ironlib.ironmate_cli import ToolParser, guard
    parser = ToolParser(description=__doc__, tool="pptx_inspect.py")
    parser.add_argument("source", help="PPTX path or - for raw PPTX bytes on stdin")
    parser.add_argument("-o", "--output", type=Path,help="new file for the JSON report (default: stdout)")
    parser.add_json_flag()
    args = parser.parse_args(argv)

    def work():
        source = sys.stdin.buffer.read() if args.source == "-" else args.source
        report = json.dumps(inspect(source), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(report)
        else:
            print(report, end="")
        return 0

    return guard("pptx_inspect.py", work, json_mode=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
