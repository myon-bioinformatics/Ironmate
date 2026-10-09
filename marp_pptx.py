"""Optional Marp CLI adapter: Markdown -> PPTX, no Node dependency at import time."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from pptx import Presentation


def convert(source, output, *, marp="marp"):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--marp", default="marp", help="Path/name of installed pinned Marp CLI")
    args = parser.parse_args(argv)
    print(json.dumps(convert(args.source, args.output, marp=args.marp), ensure_ascii=False))


if __name__ == "__main__":
    main()
