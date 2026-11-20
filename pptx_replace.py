"""Conservative PPTX attribute replacement prototype. Python 3.11+."""
import io, json, os, tempfile, tomllib
from pathlib import Path
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError
from zipfile import ZipFile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt


def _rgb(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError("color must be #RRGGBB")
    try:
        return RGBColor.from_string(value[1:])
    except ValueError as exc:
        raise ValueError("color must be #RRGGBB") from exc


# Apply narrowly scoped native edits directly to existing OOXML. The compatibility
# Presentation writer does not preserve all connector and extension properties.
_NATIVE_OPS = {"text_frame_top", "shape_top", "arrow_color", "arrowhead_type"}
_ARROW_TYPES = {"triangle", "stealth", "diamond", "oval", "arrow"}
_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PRESENTATION = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _child(parent, ns, name):
    nodes = [n for n in parent.childNodes
             if n.nodeType == Node.ELEMENT_NODE and n.namespaceURI == ns and n.localName == name]
    if len(nodes) != 1:
        raise ValueError(f"expected exactly one native {name} element")
    return nodes[0]


def _named_shape(tree, name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("shape_name and reference_shape must be nonempty strings")
    nonvisual = {"sp": "nvSpPr", "cxnSp": "nvCxnSpPr"}
    matches = []
    for n in tree.childNodes:
        if n.namespaceURI != _PRESENTATION or n.localName not in nonvisual:
            continue
        props = _child(_child(n, _PRESENTATION, nonvisual[n.localName]), _PRESENTATION, "cNvPr")
        if props.getAttribute("name") == name:
            matches.append(n)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one top-level native shape named {name!r}")
    return matches[0]


def _native_attribute(tree, rule):
    shape = _named_shape(tree, rule["shape_name"])
    operation = rule["operation"]
    if operation in {"arrow_color", "arrowhead_type"}:
        if shape.localName != "cxnSp":
            raise ValueError(f"{operation} requires a native connector with a line-end arrow")
        line = _child(_child(shape, _PRESENTATION, "spPr"), _DRAWING, "ln")
        if operation == "arrowhead_type":
            end, kind = rule["end"], rule["type"]
            if end not in ("head", "tail") or not isinstance(kind, str) or kind not in _ARROW_TYPES:
                raise ValueError("arrowhead_type requires head/tail and a visible arrow type")
            marker = _child(line, _DRAWING, end + "End")
            if marker.getAttribute("type") not in _ARROW_TYPES:
                raise ValueError("arrowhead_type requires an existing visible marker on that end")
            return marker, "type", kind
        if not any(n.nodeType == Node.ELEMENT_NODE and n.namespaceURI == _DRAWING
                   and n.localName in {"headEnd", "tailEnd"} and n.getAttribute("type") in _ARROW_TYPES
                   for n in line.childNodes):
            raise ValueError("arrow_color requires an explicit line-end arrow")
        color = _child(_child(line, _DRAWING, "solidFill"), _DRAWING, "srgbClr")
        if not color.hasAttribute("val"):
            raise ValueError("arrow_color requires an explicit RGB line color")
        return color, "val", str(_rgb(rule["color"]))

    if shape.localName != "sp":
        raise ValueError(f"{operation} requires a top-level native shape")
    if operation == "text_frame_top":
        return _child(_child(shape, _PRESENTATION, "txBody"), _DRAWING, "bodyPr"), "anchor", "t"

    def offset(node):
        if node.localName != "sp":
            raise ValueError("shape_top requires a native shape reference")
        transform = _child(_child(node, _PRESENTATION, "spPr"), _DRAWING, "xfrm")
        if transform.getAttribute("rot") not in ("", "0"):
            raise ValueError("shape_top does not support rotated shapes")
        position = _child(transform, _DRAWING, "off")
        if not position.hasAttribute("y"):
            raise ValueError("shape_top requires an explicit vertical position")
        return position

    reference = offset(_named_shape(tree, rule["reference_shape"]))
    return offset(shape), "y", reference.getAttribute("y")


def _native_rules(source_bytes, rules):
    from ironlib.pptx_ooxml import ordered_slide_members
    changes, documents, touched = [], {}, set()
    with ZipFile(io.BytesIO(source_bytes)) as package:
        if len(package.namelist()) != len(set(package.namelist())):
            raise ValueError("duplicate ZIP members are unsupported")
        members = ordered_slide_members(package)
        for index, rule in enumerate(rules):
            operation = rule.get("operation")
            required = {"operation", "slide", "shape_name"} | {
                "shape_top": {"reference_shape"}, "arrow_color": {"color"},
                "arrowhead_type": {"end", "type"},
            }.get(operation, set())
            if not required <= rule.keys() <= required | {"expected"}:
                raise ValueError(f"{operation} requires {', '.join(sorted(required))}; only expected is optional")
            if "expected" in rule and not isinstance(rule["expected"], str):
                raise ValueError("expected must be the XML attribute's old value as a string")
            number = rule["slide"]
            if type(number) is not int or not 1 <= number <= len(members):
                raise ValueError("slide must be a valid 1-based slide number")
            member = members[number - 1]
            if member not in documents:
                try:
                    document = minidom.parseString(package.read(member))
                except ExpatError as exc:
                    raise ValueError("invalid native slide XML") from exc
                if document.doctype is not None:
                    raise ValueError("DOCTYPE is unsupported")
                documents[member] = document
            root = documents[member].documentElement
            tree = _child(_child(root, _PRESENTATION, "cSld"), _PRESENTATION, "spTree")
            element, attribute, target = _native_attribute(tree, rule)
            current = element.getAttribute(attribute)
            if "expected" in rule and current != rule["expected"]:
                raise ValueError(f"{operation}: expected old value does not match {attribute}")
            if (current.upper() if operation == "arrow_color" else current) != target:
                element.setAttribute(attribute, target)
                touched.add(member)
                changes.append({"rule": index, "slide": number, "shape_name": rule["shape_name"],
                                "operation": operation, "count": 1})
    return changes, {member: documents[member].toxml(encoding="utf-8") for member in touched}


def _save_native(source_bytes, destination, replacements):
    if not replacements:
        destination.write(source_bytes)
        return
    with ZipFile(io.BytesIO(source_bytes)) as incoming, ZipFile(destination, "w") as outgoing:
        outgoing.comment = incoming.comment
        for entry in incoming.infolist():
            data = replacements.get(entry.filename)
            outgoing.writestr(entry, incoming.read(entry) if data is None else data)


def _publish(destination, save):
    if destination is None:
        raise ValueError("destination is required unless dry-run")
    dst = Path(destination)
    # Complete privately, then publish exclusively without replacing other writers.
    with tempfile.TemporaryDirectory(prefix=".pptx-replace-", dir=dst.parent) as staging_dir:
        staged = Path(staging_dir) / "complete.pptx"
        with staged.open("xb") as output:
            save(output)
        os.link(staged, dst)


def transform(source, rules, *, dry_run=False, destination=None):
    if not isinstance(rules, list) or not rules:
        raise ValueError("at least one rule is required")
    if destination is not None and not dry_run:
        src, dst = Path(source), Path(destination)
        if src.resolve() == dst.resolve() or os.path.lexists(dst):
            raise ValueError("destination must be a new file distinct from source")
    if not all(isinstance(rule, dict) for rule in rules):
        raise ValueError("each rule must be a table")
    if any(rule.get("operation") in _NATIVE_OPS for rule in rules):
        if not all(rule.get("operation") in _NATIVE_OPS for rule in rules):
            raise ValueError("native shape operations cannot be mixed with legacy run operations")
        source_bytes = Path(source).read_bytes()
        changes, replacements = _native_rules(source_bytes, rules)
        if not dry_run:
            _publish(destination, lambda output: _save_native(source_bytes, output, replacements))
        return {"dry_run": dry_run, "changes": changes, "change_count": len(changes)}
    # Both modes apply every rule to this private in-memory presentation.
    # Dry-run skips publication only, so later rules see all earlier edits.
    presentation = Presentation(str(source))
    changes = []
    for index, rule in enumerate(rules):
        operation = rule.get("operation")
        if operation not in {"replace_text", "text_color", "slide_background", "font_size", "bold", "font_family"}:
            raise ValueError(f"unsupported operation: {operation!r}")
        slide_number = rule.get("slide")
        if slide_number is not None and (type(slide_number) is not int or not 1 <= slide_number <= len(presentation.slides)):
            raise ValueError("slide must be a valid 1-based slide number")
        if operation == "replace_text":
            old, new = rule.get("old"), rule.get("new")
            if not isinstance(old, str) or not old or not isinstance(new, str):
                raise ValueError("replace_text requires nonempty old and string new")
        elif operation in {"text_color", "slide_background"}:
            color = _rgb(rule.get("color"))
        elif operation == "font_size":
            size = rule.get("points")
            if type(size) not in (int, float) or not 1 <= size <= 400:
                raise ValueError("font_size requires numeric points between 1 and 400")
        elif operation == "font_family":
            family = rule.get("name")
            if not isinstance(family, str) or not family.strip():
                raise ValueError("font_family requires a nonempty name")
        elif operation == "bold":
            if type(rule.get("value")) is not bool:
                raise ValueError("bold requires a boolean value")
        for number, slide in enumerate(presentation.slides, 1):
            if slide_number is not None and number != slide_number:
                continue
            if operation == "slide_background":
                # Only explicit solid RGB backgrounds are supported.
                fill = slide.background.fill
                if fill.type is None:
                    raise ValueError("inherited slide background is unsupported")
                from pptx.enum.dml import MSO_FILL_TYPE
                from pptx.dml.color import MSO_COLOR_TYPE
                if fill.type != MSO_FILL_TYPE.SOLID or fill.fore_color.type != MSO_COLOR_TYPE.RGB:
                    raise ValueError("only explicit solid RGB slide backgrounds are supported")
                if fill.fore_color.rgb != color:
                    changes.append({"rule": index, "slide": number, "operation": operation})
                    fill.fore_color.rgb = color
                continue
            for shape_index, shape in enumerate(slide.shapes, 1):
                if not shape.has_text_frame:
                    continue
                for paragraph_index, paragraph in enumerate(shape.text_frame.paragraphs, 1):
                    for run_index, run in enumerate(paragraph.runs, 1):
                        if operation == "replace_text":
                            count = run.text.count(old)
                            if count:
                                changes.append({"rule": index, "slide": number, "shape": shape_index, "paragraph": paragraph_index, "run": run_index, "count": count})
                                run.text = run.text.replace(old, new)
                        elif operation == "font_family":
                            if run.font.name != family:
                                changes.append({"rule": index, "slide": number, "shape": shape_index, "paragraph": paragraph_index, "run": run_index, "count": 1})
                                run.font.name = family
                        elif operation == "font_size":
                            if run.font.size != Pt(size):
                                changes.append({"rule": index, "slide": number, "shape": shape_index, "paragraph": paragraph_index, "run": run_index, "count": 1})
                                run.font.size = Pt(size)
                        elif operation == "bold":
                            if run.font.bold is not rule["value"]:
                                changes.append({"rule": index, "slide": number, "shape": shape_index, "paragraph": paragraph_index, "run": run_index, "count": 1})
                                run.font.bold = rule["value"]
                        elif operation == "text_color":
                            from pptx.dml.color import MSO_COLOR_TYPE
                            if run.font.color.type != MSO_COLOR_TYPE.RGB:
                                raise ValueError("text_color requires explicit RGB run colors")
                            if run.font.color.rgb != color:
                                changes.append({"rule": index, "slide": number, "shape": shape_index, "paragraph": paragraph_index, "run": run_index, "count": 1})
                                run.font.color.rgb = color
    if not dry_run:
        _publish(destination, presentation.save)
    return {"dry_run": dry_run, "changes": changes, "change_count": sum(c.get("count", 1) for c in changes)}


def main(argv=None):
    from ironlib.ironmate_cli import ToolParser, guard
    parser = ToolParser(description=__doc__, tool="pptx_replace.py")
    parser.add_argument("source", type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"))
    parser.add_argument("--text-color")
    parser.add_argument("--background")
    parser.add_argument("--font-size", type=float)
    parser.add_argument("--font-family")
    parser.add_argument("--bold", choices=("true", "false"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_json_flag()
    args = parser.parse_args(argv)
    if not args.dry_run and args.output is None:
        parser.error("--output is required unless --dry-run")
    if args.rules and any((args.replace, args.text_color, args.background, args.font_size is not None, args.font_family is not None, args.bold is not None)):
        parser.error("--rules cannot be combined with inline operations")
    if args.rules:
        with args.rules.open("rb") as stream:
            config = tomllib.load(stream)
        rules = config.get("rules")
    else:
        rules = []
        if args.replace:
            rules.append({"operation": "replace_text", "old": args.replace[0], "new": args.replace[1]})
        if args.text_color:
            rules.append({"operation": "text_color", "color": args.text_color})
        if args.background:
            rules.append({"operation": "slide_background", "color": args.background})
        if args.font_family is not None:
            rules.append({"operation": "font_family", "name": args.font_family})
        if args.font_size is not None:
            rules.append({"operation": "font_size", "points": args.font_size})
        if args.bold is not None:
            rules.append({"operation": "bold", "value": args.bold == "true"})
        if not rules:
            parser.error("specify --rules or an inline operation")
    def work():
        result = transform(args.source, rules, dry_run=args.dry_run, destination=args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return guard("pptx_replace.py", work, json_mode=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
