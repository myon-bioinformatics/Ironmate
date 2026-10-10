"""Render fenced Mermaid source to local SVG before passing Markdown to Marp.

Opt-in only. Preserve the original Markdown; never treat SVG as editable PPTX shapes.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

_FENCE = re.compile(r"(?m)^```mermaid[ \t]*\r?\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)


def render_mermaid(source, directory, *, mmdc="mmdc", background="#FFFFFF", foreground=None):
    """Return (transformed Markdown, SVG paths); reject unsupported fenced variants."""
    if background is not None and (not isinstance(background, str) or len(background) != 7 or
            not background.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in background[1:])):
        raise ValueError("background must be #RRGGBB")
    if foreground is not None and (not isinstance(foreground, str) or len(foreground) != 7 or
            not foreground.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in foreground[1:])):
        raise ValueError("foreground must be #RRGGBB")
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
        if foreground is not None:
            # Mermaid theme variables belong to the diagram source, never Marp CSS.
            node_fill = "#243552" if foreground.upper() == "#FFFFFF" else "#FFF4DD"
            config = '%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "' + foreground + '", "lineColor": "' + foreground + '", "textColor": "' + foreground + '", "primaryColor": "' + node_fill + '", "secondaryColor": "' + node_fill + '", "tertiaryColor": "' + node_fill + '", "mainBkg": "' + node_fill + '"}}}%%\\n'
            diagram_for_render = config + diagram
        else:
            diagram_for_render = diagram
        source_file.write_text(diagram_for_render, encoding="utf-8")
        command = [executable, "-i", str(source_file), "-o", str(svg)]
        if background is not None:
            command.extend(["-b", background])
        result = subprocess.run(command,
                                capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or not svg.is_file():
            raise RuntimeError(f"Mermaid SVG conversion failed: {result.stderr.strip()}")
        if "<svg" not in svg.read_text(encoding="utf-8"):
            raise RuntimeError("Mermaid renderer did not produce SVG")
        output.extend((source[previous:match.start()], f"![Diagram {index} h:480](./{svg.name})"))
        previous = match.end()
        rendered.append(svg)
    output.append(source[previous:])
    return "".join(output), rendered
