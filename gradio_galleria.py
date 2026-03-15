# gradio_galleria.py
# __all__: 1

__all__ = ["build_ui"]

import gradio as gr

from ascii_art import (
    generate_diamond,
    generate_square,
    generate_triangle,
    get_template,
    list_templates,
)
from markdown_market import extract_sections, read_markdown, save_markdown

# ---------------------------------------------------------------------------
# ASCII Art tab helpers
# ---------------------------------------------------------------------------


def _render_shape(shape: str, size: int, char: str) -> str:
    """Generate the requested shape and return it as a string."""
    char = char.strip() or "*"
    if shape == "Square":
        return generate_square(size, char)
    if shape == "Triangle":
        return generate_triangle(size, char)
    if shape == "Diamond":
        return generate_diamond(size, char)
    return ""


def _get_template(name: str) -> str:
    """Return a pre-defined ASCII art template."""
    return get_template(name)


# ---------------------------------------------------------------------------
# Markdown tab helpers
# ---------------------------------------------------------------------------


def _save_md(content: str, filepath: str) -> str:
    """Save Markdown content and return a status message."""
    if not filepath.strip():
        return "Please specify a file path."
    return save_markdown(content, filepath.strip())


def _read_md(filepath: str, count_hashtags: bool) -> tuple:
    """Read a Markdown file and return (content, info_message)."""
    if not filepath.strip():
        return "", "Please specify a file path."
    result = read_markdown(filepath.strip(), count_hashtags=count_hashtags)
    if not result["success"]:
        return "", result["content"]
    info = ""
    if count_hashtags:
        info = f"Total heading '#' characters: {result['hashtag_count']}"
    return result["content"], info


def _extract_sections_ui(content: str) -> str:
    """Extract sections from Markdown content and format as a readable list."""
    if not content.strip():
        return "No content to analyze."
    sections = extract_sections(content)
    if not sections:
        return "No headings found."
    lines = []
    for sec in sections:
        indent = "  " * (sec["level"] - 1)
        lines.append(f"{indent}{'#' * sec['level']} {sec['title']}")
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    """Build and return the Gradio Blocks interface."""
    templates = list_templates()

    with gr.Blocks(title="Ironmate — Gradio Galleria") as demo:
        gr.Markdown("# 🦾 Ironmate — Gradio Galleria")
        gr.Markdown(
            "Your J.A.R.V.I.S-inspired assistant for ASCII art and Markdown management."
        )

        with gr.Tabs():
            # ------------------------------------------------------------------
            # Tab 1: ASCII Art Generator
            # ------------------------------------------------------------------
            with gr.Tab("ASCII Art"):
                gr.Markdown("## Dynamic Shape Generator")
                with gr.Row():
                    shape_choice = gr.Radio(
                        choices=["Square", "Triangle", "Diamond"],
                        value="Square",
                        label="Shape",
                    )
                    size_slider = gr.Slider(
                        minimum=1, maximum=20, value=5, step=1, label="Size / Height"
                    )
                    char_input = gr.Textbox(
                        value="*", max_lines=1, label="Character"
                    )
                shape_output = gr.Textbox(
                    label="Generated Shape", lines=10, interactive=False
                )
                generate_btn = gr.Button("Generate Shape")
                generate_btn.click(
                    fn=_render_shape,
                    inputs=[shape_choice, size_slider, char_input],
                    outputs=shape_output,
                )

                gr.Markdown("## Pre-defined Templates")
                template_choice = gr.Dropdown(
                    choices=templates, value=templates[0] if templates else None,
                    label="Template"
                )
                template_output = gr.Textbox(
                    label="Template Art", lines=10, interactive=False
                )
                load_template_btn = gr.Button("Load Template")
                load_template_btn.click(
                    fn=_get_template,
                    inputs=template_choice,
                    outputs=template_output,
                )

            # ------------------------------------------------------------------
            # Tab 2: Markdown Manager
            # ------------------------------------------------------------------
            with gr.Tab("Markdown Manager"):
                gr.Markdown("## Save Markdown")
                md_filepath_save = gr.Textbox(
                    label="File Path (e.g. notes/my_doc.md)", max_lines=1
                )
                md_content_save = gr.Textbox(
                    label="Markdown Content", lines=10, placeholder="# Hello\nWrite your markdown here..."
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
                    label="File Path to Read", max_lines=1
                )
                count_hashtags_cb = gr.Checkbox(
                    label="Count heading '#' characters", value=False
                )
                md_content_read = gr.Textbox(
                    label="File Content", lines=10, interactive=False
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
                    label="Paste Markdown Content", lines=8,
                    placeholder="# Section 1\n## Sub-section\n..."
                )
                sections_output = gr.Textbox(
                    label="Sections Found", lines=8, interactive=False
                )
                extract_btn = gr.Button("Extract Sections")
                extract_btn.click(
                    fn=_extract_sections_ui,
                    inputs=sections_input,
                    outputs=sections_output,
                )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ui = build_ui()
    ui.launch()
