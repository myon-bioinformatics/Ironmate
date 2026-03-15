# ascii_art.py
# __all__: 6

__all__ = [
    "generate_square",
    "generate_triangle",
    "generate_diamond",
    "get_template",
    "list_templates",
    "render_prompt_ascii",
]

import re

from template_store import list_ascii_templates, load_ascii_template, load_prompt_template


def _sanitize_ascii_output(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()

    if "assistant\n```" in text:
        text = text.split("assistant\n```", 1)[1]
    elif "assistant\r\n```" in text:
        text = text.split("assistant\r\n```", 1)[1]
    elif "assistant\n" in text:
        text = text.split("assistant\n", 1)[1]

    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    lines = [line.rstrip() for line in text.splitlines()]

    filtered = []
    skip_prefixes = ("system", "user", "assistant", "[system]", "[user]", "[assistant]")

    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()

        if not stripped:
            filtered.append("")
            continue

        if lowered in skip_prefixes:
            continue

        if stripped in {"```", "~~~"}:
            continue

        if lowered in {
            "here's your ascii art:",
            "here is your ascii art:",
            "ascii art:",
        }:
            continue

        filtered.append(line)

    while filtered and not filtered[0].strip():
        filtered.pop(0)
    while filtered and not filtered[-1].strip():
        filtered.pop()

    return "\n".join(filtered).strip()


def generate_square(size: int, char: str = "*") -> str:
    """Generate a square of the given size using the specified character."""
    if size <= 0:
        return ""
    row = char * size
    return "\n".join(row for _ in range(size))


def generate_triangle(height: int, char: str = "*") -> str:
    """Generate a left-aligned triangle of the given height."""
    if height <= 0:
        return ""
    return "\n".join(char * i for i in range(1, height + 1))


def generate_diamond(half_height: int, char: str = "*") -> str:
    """Generate a diamond shape of the given half-height."""
    if half_height <= 0:
        return ""
    width = 2 * half_height - 1
    upper = [
        " " * ((width - (2 * i - 1)) // 2) + char * (2 * i - 1)
        for i in range(1, half_height + 1)
    ]
    lower = [
        " " * ((width - (2 * i - 1)) // 2) + char * (2 * i - 1)
        for i in range(half_height - 1, 0, -1)
    ]
    return "\n".join(upper + lower)


def get_template(name: str) -> str:
    """Load a predefined ASCII art template from templates_ascii/<name>.txt."""
    return load_ascii_template(name.strip().lower())


def list_templates() -> list[str]:
    """Return a sorted list of available ASCII template names."""
    return list_ascii_templates()


def render_prompt_ascii(prompt: str, llm) -> str:
    """Generate ASCII art from a free-form prompt via the light LLM."""
    prompt_data = load_prompt_template("ascii_prompt")
    template = prompt_data.get("ascii_basic", {})
    base_prompt = str(template.get("prompt", "")).strip()
    max_width = int(template.get("max_width", 60))

    user_prompt = prompt.strip()
    final_prompt = (
        f"{base_prompt}\n\n"
        f"USER_REQUEST:\n{user_prompt}\n\n"
        f"CONSTRAINTS:\n"
        f"- Keep width under {max_width} characters.\n"
        f"- Return ASCII art only.\n"
        f"- No explanations.\n"
    )

    result = llm.generate_light(final_prompt)
    return _sanitize_ascii_output(result.text)
