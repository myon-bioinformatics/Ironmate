# gradio_galleria.py
# __all__: 1
from __future__ import annotations

__all__ = ["build_ui"]

import csv, io, json
from pathlib import Path
from typing import Dict, Mapping, Optional

import gradio as gr

from ascii_art import (
    generate_diamond,
    generate_square,
    generate_triangle,
    get_template,
    list_templates,
)
from file_finder import DEFAULT_EXTENSIONS, find_files_as_map
from markdown_market import extract_sections, read_markdown, save_markdown


BASE_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# ASCII Art helpers
# ---------------------------------------------------------------------------

def _render_shape(shape: str, size: int, char: str) -> str:
    """Generate the requested shape."""
    char = char.strip() or "*"

    if shape == "Square":
        return generate_square(size, char)

    if shape == "Triangle":
        return generate_triangle(size, char)

    if shape == "Diamond":
        return generate_diamond(size, char)

    return ""


def _get_template(name: str) -> str:
    """Return a predefined ASCII template."""
    return get_template(name)


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def _save_md(content: str, filepath: str) -> str:
    """Save Markdown file."""
    filepath = filepath.strip()

    if not filepath:
        return "Please specify a file path."

    return save_markdown(content, filepath)


def _read_md(filepath: str, count_hashtags: bool) -> tuple[str, str]:
    """Read Markdown file."""
    filepath = filepath.strip()

    if not filepath:
        return "", "Please specify a file path."

    result = read_markdown(filepath, count_hashtags=count_hashtags)

    if not result["success"]:
        return "", result["content"]

    info = ""
    if count_hashtags:
        info = f"Total heading '#' characters: {result['hashtag_count']}"

    return result["content"], info


def _extract_sections_ui(content: str) -> str:
    """Extract Markdown sections."""
    if not content.strip():
        return "No content to analyze."

    sections = extract_sections(content)

    if not sections:
        return "No headings found."

    return "\n".join(
        f"{'  ' * (sec['level'] - 1)}{'#' * sec['level']} {sec['title']}"
        for sec in sections
    )


# ---------------------------------------------------------------------------
# File Viewer helpers
# ---------------------------------------------------------------------------

def _detect_kind(path: Path) -> str:
    """Detect file display type."""
    suffix = path.suffix.lower()

    if suffix == ".md":
        return "markdown"

    if suffix == ".csv":
        return "csv"

    if suffix == ".json":
        return "json"

    return "text"


def _format_json(text: str) -> str:
    """Pretty print JSON."""
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return text


def _read_text(path: Path, size_limit_bytes: int = 5 * 1024 * 1024) -> str:
    """Read text file safely."""
    if not path.exists():
        return f"[missing] {path}"

    try:
        size = path.stat().st_size
    except OSError as e:
        return f"[error] stat failed: {e}"

    if size > size_limit_bytes:
        return f"[too_large] {path} ({size} bytes)"

    for enc in ("utf-8", "utf-8-sig", "cp932", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError as e:
            return f"[error] read failed: {e}"

    return "[error] decode failed"


def _read_csv_as_table(path: Path) -> str | dict:
    """Read CSV file as table."""
    raw = _read_text(path)

    if raw.startswith(("[error]", "[missing]", "[too_large]")):
        return raw

    try:
        rows = list(csv.reader(io.StringIO(raw)))
    except Exception as e:
        return f"[error] csv parse failed: {e}"

    if not rows:
        return {"headers": [], "data": []}

    return {
        "headers": rows[0],
        "data": rows[1:],
    }


def _load_for_display(
    label: str,
    files: Mapping[str, Path],
) -> tuple[str, str, Optional[dict]]:
    """Load file for UI display."""
    path = files.get(label)

    if path is None:
        return "text", f"[error] unknown label: {label}", None

    kind = _detect_kind(path)

    if kind == "csv":
        csv_value = _read_csv_as_table(path)

        if isinstance(csv_value, str):
            return "text", csv_value, None

        return "csv", "", csv_value

    raw = _read_text(path)

    if kind == "markdown":
        return "markdown", raw, None

    if kind == "json":
        return "text", _format_json(raw), None

    return "text", raw, None


def _scan_repo_files() -> Dict[str, Path]:
    """Scan repository files."""
    return find_files_as_map(BASE_DIR, extensions=list(DEFAULT_EXTENSIONS))


def _to_view_updates(kind: str, text_value: str = "", csv_value: Optional[dict] = None):
    """Convert file content into Gradio update objects."""

    if kind == "markdown":
        return (
            gr.update(visible=False, value=""),
            gr.update(visible=True, value=text_value),
            gr.update(visible=False, headers=None, value=None),
        )

    if kind == "csv" and csv_value is not None:
        return (
            gr.update(visible=False, value=""),
            gr.update(visible=False, value=""),
            gr.update(
                visible=True,
                headers=csv_value["headers"],
                value=csv_value["data"],
            ),
        )

    return (
        gr.update(visible=True, value=text_value),
        gr.update(visible=False, value=""),
        gr.update(visible=False, headers=None, value=None),
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def build_ui() -> gr.Blocks:
    """Build Gradio UI."""
    templates = list_templates()

    files = _scan_repo_files()
    labels = list(files) or ["(no files)"]
    default_label = labels[0]

    def on_change(label: str):
        if label == "(no files)":
            return _to_view_updates("text", "ファイルが見つかりません。")

        kind, text_value, csv_value = _load_for_display(label, files)

        return _to_view_updates(kind, text_value, csv_value)

    with gr.Blocks(title="Ironmate — Gradio Galleria") as demo:

        gr.Markdown("# 🦾 Ironmate — Gradio Galleria")

        gr.Markdown(
            "Your J.A.R.V.I.S-inspired assistant for ASCII art, Markdown management, and file viewing."
        )

        with gr.Tabs():

            # ASCII Art
            with gr.Tab("ASCII Art"):

                gr.Markdown("## Dynamic Shape Generator")

                with gr.Row():

                    shape_choice = gr.Radio(
                        choices=["Square", "Triangle", "Diamond"],
                        value="Square",
                        label="Shape",
                    )

                    size_slider = gr.Slider(
                        minimum=1,
                        maximum=20,
                        value=5,
                        step=1,
                        label="Size / Height",
                    )

                    char_input = gr.Textbox(
                        value="*",
                        max_lines=1,
                        label="Character",
                    )

                shape_output = gr.Textbox(
                    label="Generated Shape",
                    lines=10,
                    interactive=False,
                )

                generate_btn = gr.Button("Generate Shape")

                generate_btn.click(
                    fn=_render_shape,
                    inputs=[shape_choice, size_slider, char_input],
                    outputs=shape_output,
                )

                gr.Markdown("## Pre-defined Templates")

                template_choice = gr.Dropdown(
                    choices=templates,
                    value=templates[0] if templates else None,
                    label="Template",
                )

                template_output = gr.Textbox(
                    label="Template Art",
                    lines=10,
                    interactive=False,
                )

                load_template_btn = gr.Button("Load Template")

                load_template_btn.click(
                    fn=_get_template,
                    inputs=template_choice,
                    outputs=template_output,
                )

            # Markdown
            with gr.Tab("Markdown Manager"):

                gr.Markdown("## Save Markdown")

                md_filepath_save = gr.Textbox(
                    label="File Path (e.g. notes/my_doc.md)",
                    max_lines=1,
                )

                md_content_save = gr.Textbox(
                    label="Markdown Content",
                    lines=10,
                    placeholder="# Hello\nWrite your markdown here...",
                )

                save_status = gr.Textbox(label="Status", interactive=False)

                save_btn = gr.Button("Save")

                save_btn.click(
                    fn=_save_md,
                    inputs=[md_content_save, md_filepath_save],
                    outputs=save_status,
                )

                gr.Markdown("## Read Markdown")

                md_filepath_read = gr.Textbox(
                    label="File Path to Read",
                    max_lines=1,
                )

                count_hashtags_cb = gr.Checkbox(
                    label="Count heading '#' characters",
                    value=False,
                )

                md_content_read = gr.Textbox(
                    label="File Content",
                    lines=10,
                    interactive=False,
                )

                read_info = gr.Textbox(label="Info", interactive=False)

                read_btn = gr.Button("Read")

                read_btn.click(
                    fn=_read_md,
                    inputs=[md_filepath_read, count_hashtags_cb],
                    outputs=[md_content_read, read_info],
                )

                gr.Markdown("## Extract Sections")

                sections_input = gr.Textbox(
                    label="Paste Markdown Content",
                    lines=8,
                    placeholder="# Section 1\n## Sub-section\n...",
                )

                sections_output = gr.Textbox(
                    label="Sections Found",
                    lines=8,
                    interactive=False,
                )

                extract_btn = gr.Button("Extract Sections")

                extract_btn.click(
                    fn=_extract_sections_ui,
                    inputs=sections_input,
                    outputs=sections_output,
                )

            # File Viewer
            with gr.Tab("File Viewer"):

                gr.Markdown("## File Viewer")

                gr.Markdown(
                    "このタブは、`gradio_galleria.py` と同じディレクトリ以下をスキャンして、"
                    "プルダウンでファイル内容を表示します。"
                )

                selector = gr.Dropdown(
                    choices=labels,
                    value=default_label,
                    label="ファイル選択",
                    interactive=True,
                )

                text_view = gr.Textbox(
                    label="Text",
                    lines=28,
                    max_lines=40,
                    visible=True,
                )

                markdown_view = gr.Markdown(visible=False)

                csv_view = gr.Dataframe(
                    label="CSV",
                    visible=False,
                    wrap=True,
                    interactive=False,
                )

                selector.change(
                    fn=on_change,
                    inputs=selector,
                    outputs=[text_view, markdown_view, csv_view],
                )

                demo.load(
                    fn=lambda: on_change(default_label),
                    outputs=[text_view, markdown_view, csv_view],
                )

    return demo


if __name__ == "__main__":
    ui = build_ui()
    ui.launch()
