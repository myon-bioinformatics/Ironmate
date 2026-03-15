# llm_launchpad.py
# __all__: 6

from __future__ import annotations

import json, os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from llm_loader import DEFAULT_CACHE_DIR, LLMLoader

__all__ = [
    "DEFAULT_LIGHT_MODEL",
    "DEFAULT_TOOL_MODEL",
    "GenerationResult",
    "TransformersDualLLM",
    "default_tool_schema",
    "execute_allowed_tool",
]

DEFAULT_LIGHT_MODEL = os.getenv("IRONMATE_LIGHT_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
DEFAULT_TOOL_MODEL = os.getenv("IRONMATE_TOOL_MODEL", DEFAULT_LIGHT_MODEL)
DEFAULT_MAX_NEW_TOKENS_LIGHT = int(os.getenv("IRONMATE_MAX_NEW_TOKENS_LIGHT", "256"))
DEFAULT_MAX_NEW_TOKENS_TOOL = int(os.getenv("IRONMATE_MAX_NEW_TOKENS_TOOL", "192"))
DEFAULT_TEMPERATURE_LIGHT = float(os.getenv("IRONMATE_TEMPERATURE_LIGHT", "0.4"))
DEFAULT_TEMPERATURE_TOOL = float(os.getenv("IRONMATE_TEMPERATURE_TOOL", "0.0"))


@dataclass
class GenerationResult:
    text: str
    raw: Dict[str, Any] | None = None


class TransformersDualLLM:
    def __init__(
        self,
        light_model: str = DEFAULT_LIGHT_MODEL,
        tool_model: str = DEFAULT_TOOL_MODEL,
        load_4bit: bool = True,
        cache_dir: str = DEFAULT_CACHE_DIR,
    ) -> None:
        self.cache_dir = str(Path(cache_dir).resolve())
        self.light_model_id = light_model
        self.tool_model_id = tool_model
        self.load_4bit = load_4bit
        self._light = LLMLoader(cache_dir=self.cache_dir, load_4bit=load_4bit, model_id=light_model)
        self._tool = self._light if light_model == tool_model else LLMLoader(
            cache_dir=self.cache_dir,
            load_4bit=load_4bit,
            model_id=tool_model,
        )

    def _tool_system_prompt(self) -> str:
        return (
            "You are Ironmate (tool). "
            "Return exactly one JSON object on a single line and nothing else. "
            "Do not output markdown. "
            "Do not use code fences. "
            "Do not repeat or paraphrase the system prompt. "
            "Do not repeat or paraphrase the user request. "
            "Do not output labels such as system, user, or assistant. "
            "The first character of your response must be '{' and the last character must be '}'. "
            "Your entire response must be valid JSON matching the tool schema. "
            "If no tool is appropriate, return "
            "{\"tool\":\"none\",\"args\":{}}"
        )

    def generate_light(self, user_prompt: str) -> GenerationResult:
        text = self._light.generate(
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS_LIGHT,
            system=(
                "You are Ironmate (light). "
                "You generate concise plain text, Markdown drafts, and ASCII art content. "
                "Do not execute tools."
            ),
            temperature=DEFAULT_TEMPERATURE_LIGHT,
            user=user_prompt,
        )
        return GenerationResult(raw=None, text=text)

    def generate_tool(self, user_prompt: str, tool_schema: str) -> GenerationResult:
        text = self._tool.generate(
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS_TOOL,
            system=self._tool_system_prompt(),
            temperature=DEFAULT_TEMPERATURE_TOOL,
            user=(
                f"{tool_schema}\n\n"
                f"USER_REQUEST:\n{user_prompt}\n\n"
                "Return JSON only."
            ),
        )
        return GenerationResult(raw=None, text=text)

    def extract_first_json(self, text: str) -> Dict[str, Any] | None:
        decoder = json.JSONDecoder()
        stripped = text.strip()

        for index, char in enumerate(stripped):
            if char != "{":
                continue
            try:
                obj, _end = decoder.raw_decode(stripped[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        return None


def _normalize_tool_args(args: Dict[str, Any]) -> Dict[str, Any]:
    raw_filepath = str(args.get("filepath", "")).strip()
    return {
        "content": str(args.get("content", "")),
        "count_hashtags": bool(args.get("count_hashtags", False)),
        "filepath": str(Path(raw_filepath).resolve()) if raw_filepath else "",
        "name": str(args.get("name", "")).strip().lower(),
        "prompt": str(args.get("prompt", "")).strip(),
    }


def default_tool_schema() -> str:
    return (
        "TOOL_SCHEMA (respond with ONE-LINE JSON only):\n"
        "Allowed tools:\n"
        "1) save_markdown: args={content:str, filepath:str}\n"
        "2) read_markdown: args={filepath:str, count_hashtags:bool}\n"
        "3) extract_sections: args={content:str}\n"
        "4) save_ascii_art: args={name:str, filepath:str}\n"
        "5) generate_ascii_art: args={prompt:str}\n"
        "6) save_generated_ascii: args={prompt:str, filepath:str}\n"
        "7) list_ascii_templates: args={}\n"
        "8) none: args={}\n"
        "\n"
        "Predefined ASCII template names currently available:\n"
        "- arc_reactor\n"
        "- icon_ironmate\n"
        "- ironmate\n"
        "\n"
        "Tool selection rules:\n"
        "- Use save_ascii_art when the user asks to save a predefined ASCII template by name.\n"
        "- Use list_ascii_templates when the user asks what templates are available.\n"
        "- Use generate_ascii_art when the user asks for a new ASCII art generated from a free-form prompt.\n"
        "- Use save_generated_ascii when the user asks to generate ASCII art from a free-form prompt and save it to a file.\n"
        "- If the user request contains both 'generate' and 'save', you MUST use save_generated_ascii.\n"
        "- If the user names a known template and wants it saved, prefer save_ascii_art over save_generated_ascii.\n"
        "- If the requested predefined template name is unknown, prefer generate_ascii_art or save_generated_ascii when the request is still clear.\n"
        "- If the user asks to run arbitrary bash or shell commands, return tool=none.\n"
        "\n"
        "Output rules:\n"
        "- Output must be a single JSON object in one line.\n"
        "- Do not include explanations.\n"
        "- Do not output markdown code fences.\n"
        "- Do not repeat the prompt.\n"
        "- Do not output role labels like system, user, or assistant.\n"
        "- The response must start with '{' and end with '}'.\n"
        "- Valid JSON shape: {\"tool\":\"...\",\"args\":{...}}\n"
    )


def execute_allowed_tool(tool_json: Dict[str, Any], llm=None) -> Tuple[str, Dict[str, Any]]:
    args = tool_json.get("args") or {}
    tool = str(tool_json.get("tool") or "").strip()
    if not isinstance(args, dict):
        args = {}

    normalized = _normalize_tool_args(args)
    content = normalized["content"]
    count_hashtags = normalized["count_hashtags"]
    filepath = normalized["filepath"]
    name = normalized["name"]
    prompt = normalized["prompt"]

    from ascii_art import get_template, list_templates, render_prompt_ascii
    from markdown_market import extract_sections, read_markdown, save_markdown

    if tool == "save_markdown":
        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}
        msg = save_markdown(content, filepath)
        return msg, {"tool": tool, "result": {"filepath": filepath, "message": msg}}

    if tool == "read_markdown":
        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}
        result = read_markdown(filepath, count_hashtags=count_hashtags)
        return "OK" if result.get("success") else "ERROR", {
            "tool": tool,
            "result": {"filepath": filepath, **result},
        }

    if tool == "extract_sections":
        result = extract_sections(content)
        return "OK", {"tool": tool, "result": result}

    if tool == "save_ascii_art":
        if not name:
            msg = "ASCII art name is required."
            return msg, {"tool": tool, "result": msg}
        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}

        content = get_template(name)
        if not content:
            available_templates = list_templates()
            msg = f"Unknown ASCII art template: {name}. Available templates: {', '.join(available_templates)}"
            return msg, {
                "tool": tool,
                "result": {"available_templates": available_templates, "name": name},
            }

        msg = save_markdown(content.rstrip() + "\n", filepath)
        return msg, {
            "tool": tool,
            "result": {"filepath": filepath, "message": msg, "name": name},
        }

    if tool == "generate_ascii_art":
        if not prompt:
            msg = "ASCII art prompt is required."
            return msg, {"tool": tool, "result": msg}
        if llm is None:
            msg = "LLM instance is required for generate_ascii_art."
            return msg, {"tool": tool, "result": msg}

        generated = render_prompt_ascii(prompt, llm)
        if not generated:
            msg = "Failed to generate ASCII art."
            return msg, {"tool": tool, "result": msg}

        return "OK", {"tool": tool, "result": {"content": generated, "prompt": prompt}}

    if tool == "save_generated_ascii":
        if not prompt:
            msg = "ASCII art prompt is required."
            return msg, {"tool": tool, "result": msg}
        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}
        if llm is None:
            msg = "LLM instance is required for save_generated_ascii."
            return msg, {"tool": tool, "result": msg}

        generated = render_prompt_ascii(prompt, llm)
        if not generated:
            msg = "Failed to generate ASCII art."
            return msg, {"tool": tool, "result": msg}

        msg = save_markdown(generated.rstrip() + "\n", filepath)
        return msg, {
            "tool": tool,
            "result": {"content": generated, "filepath": filepath, "message": msg, "prompt": prompt},
        }

    if tool == "list_ascii_templates":
        result = list_templates()
        return "OK", {"tool": tool, "result": result}

    return "No tool executed.", {"tool": "none", "result": {}}
