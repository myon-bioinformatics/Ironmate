"""Test-only fixture: generate a small editable PPTX from limited Markdown.

Python 3.11+; requires python-pptx. This is only a test helper, not a
general-purpose Markdown or Marp parser.
"""
import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt


def parse_blocks(text):
    blocks = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith("# "):
            kind, value = "title", line[2:].strip()
        elif line.startswith("## "):
            kind, value = "heading", line[3:].strip()
        elif line.startswith("#"):
            raise ValueError(f"unsupported Markdown heading at line {line_number}")
        elif line.lstrip().startswith(("- ", "* ", ">", "`", "|")):
            raise ValueError(f"unsupported Markdown construct at line {line_number}")
        else:
            kind, value = "body", line.strip()
        if not value:
            raise ValueError(f"empty block at line {line_number}")
        blocks.append({"id": f"line-{line_number}", "kind": kind, "text": value})
    if not blocks:
        raise ValueError("Markdown input is empty")
    if len(blocks) > 8:
        raise ValueError("fixture supports at most eight nonempty blocks")
    return blocks


def generate(source, output):
    src, dst = Path(source), Path(output)
    if src.resolve() == dst.resolve() or dst.exists():
        raise ValueError("output must be a new file distinct from input")
    blocks = parse_blocks(src.read_text(encoding="utf-8"))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    manifest = []
    for index, block in enumerate(blocks):
        shape = slide.shapes.add_textbox(Inches(0.7), Inches(0.45 + index * 0.8), Inches(11.5), Inches(0.65))
        shape.name = f"markdown:{block['id']}:{block['kind']}"
        run = shape.text_frame.paragraphs[0].add_run()
        run.text = block["text"]
        run.font.size = Pt(28 if block["kind"] == "title" else 21 if block["kind"] == "heading" else 16)
        run.font.color.rgb = RGBColor(0, 0, 0)
        manifest.append({**block, "shape_name": shape.name})
    try:
        with dst.open("xb") as stream:
            prs.save(stream)
    except Exception:
        # Only remove the file if this process successfully created it.
        # The caller must not concurrently reuse the output path.
        if dst.exists():
            dst.unlink()
        raise
    return {"output": str(dst), "blocks": manifest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(generate(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
