"""Render fenced Mermaid source to local SVG before passing Markdown to Marp.

Opt-in only. Preserve the original Markdown; never treat SVG as editable PPTX shapes.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

_FENCE = re.compile(r"(?m)^```mermaid[ \t]*\r?\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)


def render_mermaid(source, directory, *, mmdc="mmdc"):
    """Return (transformed Markdown, SVG paths); reject unsupported fenced variants."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    matches = list(_FENCE.finditer(source))
    if not matches:
        return source, []
    executable = shutil.which(mmdc)
    if executable is None:
        raise RuntimeError("Mermaid CLI (mmdc) not installed")
    rendered = []
    output = []
    previous = 0
    for index, match in enumerate(matches, 1):
        diagram = match.group(1)
        if not diagram.strip():
            raise ValueError("empty Mermaid diagram")
        digest = hashlib.sha256(diagram.encode("utf-8")).hexdigest()[:16]
        stem = f"mermaid-{index}-{digest}"
        source_file = directory / f"{stem}.mmd"
        svg = directory / f"{stem}.svg"
        if svg.exists() or source_file.exists():
            raise ValueError("Mermaid render output already exists")
        source_file.write_text(diagram, encoding="utf-8")
        result = subprocess.run([executable, "-i", str(source_file), "-o", str(svg)],
                                capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or not svg.is_file():
            raise RuntimeError(f"Mermaid SVG conversion failed: {result.stderr.strip()}")
        if "<svg" not in svg.read_text(encoding="utf-8"):
            raise RuntimeError("Mermaid renderer did not produce SVG")
        output.extend((source[previous:match.start()], f"![Diagram {index}](./{svg.name})"))
        previous = match.end()
        rendered.append(svg)
    output.append(source[previous:])
    return "".join(output), rendered
