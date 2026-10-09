"""One-command Markdown -> Marp PPTX -> Open XML inspection.

No promise of Mermaid rendering unless a configured Marp renderer supports it.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

from marp_pptx import convert
from pptx_inspect import inspect


def run(*, source=None, text=None, output, marp="marp"):
    output = Path(output)
    if (source is None) == (text is None):
        raise ValueError("provide exactly one Markdown source")
    if text is not None:
        if not text.strip():
            raise ValueError("Markdown must not be empty")
        with tempfile.TemporaryDirectory(prefix="ironmate-md-") as directory:
            input_path = Path(directory) / "input.md"
            input_path.write_text(text, encoding="utf-8")
            conversion = convert(input_path, output, marp=marp)
    else:
        conversion = convert(source, output, marp=marp)
    report = inspect(output)
    return {"conversion": conversion, "inspection": report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("source", nargs="?", help="Markdown file or '-' for stdin")
    source.add_argument("--text", help="Markdown source inline")
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--marp", default="marp")
    args = parser.parse_args(argv)
    inline = args.text if args.text is not None else sys.stdin.read() if args.source == "-" else None
    result = run(source=None if inline is not None else args.source,
                 text=inline, output=args.output, marp=args.marp)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
