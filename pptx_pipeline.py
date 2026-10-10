"""One-command Markdown -> Marp PPTX -> Open XML inspection.

No promise of Mermaid rendering unless a configured Marp renderer supports it.
"""
import json
from pathlib import Path
import sys
import tempfile

from vendor.cli_args import Argument, make_parser
import shutil
import subprocess
from pptx import Presentation
from mermaid_svg import render_mermaid
from pptx_inspect import inspect


def convert(source, output, *, marp="marp", allow_local_files=False):
    source, output = Path(source), Path(output)
    if source.suffix.lower() != ".md":
        raise ValueError("input must be a .md file")
    if output.suffix.lower() != ".pptx":
        raise ValueError("output must be a .pptx file")
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("output must be a new file distinct from input")
    executable = shutil.which(marp)
    if executable is None:
        raise RuntimeError("Marp CLI not installed; install and pin @marp-team/marp-cli separately")
    command = [executable, str(source), "--pptx", "--output", str(output)]
    if allow_local_files:
        command.append("--allow-local-files")
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Marp conversion failed (exit {result.returncode}): {result.stderr.strip()}")
    if not output.is_file():
        raise RuntimeError("Marp returned success but produced no PPTX")
    try:
        slides = len(Presentation(output).slides)
    except Exception as exc:
        raise RuntimeError("Marp output is not a readable PPTX") from exc
    return {"source": str(source), "output": str(output), "slides": slides, "backend": "marp"}


def read_markdown_input(*, source=None, text=None, stdin=None):
    """Resolve Markdown from file, inline text, or stdin without altering CLI semantics."""
    if (source is None) == (text is None):
        raise ValueError("provide exactly one Markdown source")
    if text is not None:
        return text, "inline"
    if source == "-":
        return (sys.stdin if stdin is None else stdin).read(), "stdin"
    return Path(source).read_text(encoding="utf-8"), str(source)



def run(*, source=None, text=None, output, marp="marp", mmdc=None, background="#FFFFFF", svg_foreground=None):
    output = Path(output)
    if (source is None) == (text is None):
        raise ValueError("provide exactly one Markdown source")
    if mmdc is not None:
        raw, _ = read_markdown_input(source=source, text=text)
        if not raw.strip():
            raise ValueError("Markdown must not be empty")
        with tempfile.TemporaryDirectory(prefix="ironmate-svg-") as directory:
            working = Path(directory)
            prepared, images = render_mermaid(raw, working, mmdc=mmdc, background=background, foreground=svg_foreground)
            input_path = working / "input.md"
            input_path.write_text(prepared, encoding="utf-8")
            conversion = convert(input_path, output, marp=marp, allow_local_files=True)
            conversion["mermaid_svg_count"] = len(images)
    elif text is not None:
        if not text.strip():
            raise ValueError("Markdown must not be empty")
        with tempfile.TemporaryDirectory(prefix="ironmate-md-") as directory:
            input_path = Path(directory) / "input.md"
            input_path.write_text(text, encoding="utf-8")
            conversion = convert(input_path, output, marp=marp)
            conversion["source"] = "inline"
    else:
        conversion = convert(source, output, marp=marp)
    report = inspect(output)
    return {"conversion": conversion, "inspection": report}


def main(argv=None):
    """Single supported Markdown-to-PPTX CLI, with optional SVG preprocessing."""
    parser = make_parser([
        Argument(("source",), {"nargs": "?", "help": "Markdown file path or - for stdin"}),
        Argument(("--text",), {"help": "Inline Markdown source"}),
        Argument(("-o", "--output"), {"type": Path, "required": True}),
        Argument(("--marp",), {"default": "marp"}),
        Argument(("--mmdc",), {"help": "Optional Mermaid SVG pre-renderer"}),
        Argument(("--background",), {"default": "#FFFFFF"}),
        Argument(("--svg-foreground",), {}),
    ], description=__doc__)
    args = parser.parse_args(argv)
    if (args.source is None) == (args.text is None):
        parser.error("provide exactly one of source or --text")
    inline = args.text if args.text is not None else sys.stdin.read() if args.source == "-" else None
    if inline is not None and not inline.strip():
        parser.error("Markdown content must not be empty")
    result = run(source=None if inline is not None else args.source, text=inline,
                 output=args.output, marp=args.marp, mmdc=args.mmdc,
                 background=args.background, svg_foreground=args.svg_foreground)
    if args.source == "-":
        result["conversion"]["source"] = "stdin"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
