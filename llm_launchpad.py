# llm_launchpad.py
# __all__: 4
from __future__ import annotations

import json, os, re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "GenerationResult",
    "TransformersDualLLM",
    "default_tool_schema",
    "execute_allowed_tool",
]


DEFAULT_LIGHT_MODEL = os.getenv("IRONMATE_LIGHT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
DEFAULT_TOOL_MODEL = os.getenv("IRONMATE_TOOL_MODEL", "Qwen/Qwen2.5-7B-Instruct")
DEFAULT_LOAD_4BIT = os.getenv("IRONMATE_LOAD_4BIT", "1").strip() not in ("0", "false", "False")
DEFAULT_MAX_NEW_TOKENS_LIGHT = int(os.getenv("IRONMATE_MAX_NEW_TOKENS_LIGHT", "512"))
DEFAULT_MAX_NEW_TOKENS_TOOL = int(os.getenv("IRONMATE_MAX_NEW_TOKENS_TOOL", "768"))
DEFAULT_TEMPERATURE_LIGHT = float(os.getenv("IRONMATE_TEMPERATURE_LIGHT", "0.7"))
DEFAULT_TEMPERATURE_TOOL = float(os.getenv("IRONMATE_TEMPERATURE_TOOL", "0.2"))


@dataclass
class GenerationResult:
    text: str
    raw: Dict[str, Any] | None = None


class TransformersDualLLM:
    def __init__(
        self,
        light_model: str = DEFAULT_LIGHT_MODEL,
        tool_model: str = DEFAULT_TOOL_MODEL,
        load_4bit: bool = DEFAULT_LOAD_4BIT,
    ) -> None:
        self.light_model_id = light_model
        self.tool_model_id = tool_model
        self.load_4bit = load_4bit
        self._light = None
        self._tool = None

    def _get_bnb_config(self):
        try:
            from transformers import BitsAndBytesConfig
        except Exception:
            return None

        if not self.load_4bit:
            return None

        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype="float16",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

    def _load(self, which: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        bnb_config = self._get_bnb_config()
        model_id = self.light_model_id if which == "light" else self.tool_model_id

        tok = AutoTokenizer.from_pretrained(model_id, use_fast=True)
        if tok.pad_token_id is None and tok.eos_token_id is not None:
            tok.pad_token_id = tok.eos_token_id

        kwargs = {
            "device_map": "auto",
            "trust_remote_code": True,
            "torch_dtype": torch.float16,
        }

        if bnb_config is not None:
            kwargs["quantization_config"] = bnb_config

        model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        model.eval()
        return tok, model

    def _ensure_light(self):
        if self._light is None:
            self._light = self._load("light")
        return self._light

    def _ensure_tool(self):
        if self._tool is None:
            self._tool = self._load("tool")
        return self._tool

    def _chat_prompt(self, tokenizer, system: str, user: str) -> str:
        if hasattr(tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return f"[SYSTEM]\n{system}\n\n[USER]\n{user}\n\n[ASSISTANT]\n"

    def generate_light(self, user_prompt: str) -> GenerationResult:
        tok, model = self._ensure_light()
        return self._generate(
            tok,
            model,
            system=(
                "You are Ironmate (light). You generate concise Markdown drafts and ASCII art ideas. "
                "You do not execute tools. Output plain text only."
            ),
            user=user_prompt,
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS_LIGHT,
            temperature=DEFAULT_TEMPERATURE_LIGHT,
        )

    def generate_tool(self, user_prompt: str, tool_schema: str) -> GenerationResult:
        tok, model = self._ensure_tool()
        return self._generate(
            tok,
            model,
            system=(
                "You are Ironmate (tool). You MUST respond with exactly one line of JSON, and nothing else. "
                "Follow the provided tool schema. If no tool is appropriate, respond with "
                "{\"tool\":\"none\",\"args\":{}}"
            ),
            user=f"{tool_schema}\n\nUSER_REQUEST:\n{user_prompt}",
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS_TOOL,
            temperature=DEFAULT_TEMPERATURE_TOOL,
        )

    def _generate(
        self,
        tok,
        model,
        system: str,
        user: str,
        max_new_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        import torch

        prompt = self._chat_prompt(tok, system=system, user=user)
        inputs = tok(prompt, return_tensors="pt")

        if hasattr(model, "device") and model.device is not None:
            inputs = {key: value.to(model.device) for key, value in inputs.items()}

        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=(temperature > 0),
                temperature=max(temperature, 1e-5),
                top_p=0.9,
                repetition_penalty=1.05,
                pad_token_id=tok.pad_token_id,
                eos_token_id=tok.eos_token_id,
            )

        text = tok.decode(out[0], skip_special_tokens=True)
        if text.startswith(prompt):
            text = text[len(prompt):]
        return GenerationResult(text=text.strip())

    _JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

    def extract_first_json(self, text: str) -> Optional[Dict[str, Any]]:
        match = self._JSON_RE.search(text.strip())
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


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
        "- ironmate\n"
        "- arc_reactor\n"
        "- helmet\n"
        "- welcome\n"
        "\n"
        "Tool selection rules:\n"
        "- Use save_ascii_art when the user asks to save a predefined ASCII template by name.\n"
        "- Use list_ascii_templates when the user asks what templates are available.\n"
        "- Use generate_ascii_art when the user asks for a new ASCII art generated from a free-form prompt.\n"
        "- Use save_generated_ascii when the user asks to generate ASCII art from a free-form prompt and save it to a file.\n"
        "- If the user names a known template and wants it saved, prefer save_ascii_art over save_generated_ascii.\n"
        "- If the requested predefined template name is unknown, prefer generate_ascii_art or save_generated_ascii when the request is still clear.\n"
        "- If user asks to run arbitrary bash/commands, refuse by returning tool=none.\n"
        "\n"
        "Output rules:\n"
        "- Output must be a single JSON object in one line.\n"
        "- Do not include explanations.\n"
        "- Valid JSON shape: {\"tool\":\"...\",\"args\":{...}}\n"
    )


def execute_allowed_tool(tool_json: Dict[str, Any], llm=None) -> Tuple[str, Dict[str, Any]]:
    tool = (tool_json.get("tool") or "").strip()
    args = tool_json.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    from ascii_art import get_template, list_templates, render_prompt_ascii
    from markdown_market import extract_sections, read_markdown, save_markdown

    if tool == "save_markdown":
        content = str(args.get("content", ""))
        filepath = str(args.get("filepath", "")).strip()
        msg = save_markdown(content, filepath)
        return msg, {"tool": tool, "result": msg}

    if tool == "read_markdown":
        filepath = str(args.get("filepath", "")).strip()
        count_hashtags = bool(args.get("count_hashtags", False))
        res = read_markdown(filepath, count_hashtags=count_hashtags)
        return "OK" if res.get("success") else "ERROR", {"tool": tool, "result": res}

    if tool == "extract_sections":
        content = str(args.get("content", ""))
        res = extract_sections(content)
        return "OK", {"tool": tool, "result": res}

    if tool == "save_ascii_art":
        filepath = str(args.get("filepath", "")).strip()
        name = str(args.get("name", "")).strip().lower()

        if not name:
            msg = "ASCII art name is required."
            return msg, {"tool": tool, "result": msg}

        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}

        content = get_template(name)
        if not content:
            available = list_templates()
            msg = f"Unknown ASCII art template: {name}. Available templates: {', '.join(available)}"
            return msg, {"tool": tool, "result": {"name": name, "available_templates": available}}

        msg = save_markdown(content.rstrip() + "\n", filepath)
        return msg, {"tool": tool, "result": {"name": name, "filepath": filepath, "message": msg}}

    if tool == "generate_ascii_art":
        prompt = str(args.get("prompt", "")).strip()

        if not prompt:
            msg = "ASCII art prompt is required."
            return msg, {"tool": tool, "result": msg}

        if llm is None:
            msg = "LLM instance is required for generate_ascii_art."
            return msg, {"tool": tool, "result": msg}

        content = render_prompt_ascii(prompt, llm)
        if not content:
            msg = "Failed to generate ASCII art."
            return msg, {"tool": tool, "result": msg}

        return "OK", {"tool": tool, "result": {"prompt": prompt, "content": content}}

    if tool == "save_generated_ascii":
        prompt = str(args.get("prompt", "")).strip()
        filepath = str(args.get("filepath", "")).strip()

        if not prompt:
            msg = "ASCII art prompt is required."
            return msg, {"tool": tool, "result": msg}

        if not filepath:
            msg = "File path is required."
            return msg, {"tool": tool, "result": msg}

        if llm is None:
            msg = "LLM instance is required for save_generated_ascii."
            return msg, {"tool": tool, "result": msg}

        content = render_prompt_ascii(prompt, llm)
        if not content:
            msg = "Failed to generate ASCII art."
            return msg, {"tool": tool, "result": msg}

        msg = save_markdown(content.rstrip() + "\n", filepath)
        return msg, {
            "tool": tool,
            "result": {"prompt": prompt, "filepath": filepath, "content": content, "message": msg},
        }

    if tool == "list_ascii_templates":
        res = list_templates()
        return "OK", {"tool": tool, "result": res}

    return "No tool executed.", {"tool": "none", "result": {}}
