"""
llm_launchpad.py
Local dual-LLM runtime (Transformers) for Ironmate.

Design goals:
- GPU-first (GTX 2070 class): default to 4-bit quant (bitsandbytes) when available.
- Two models:
  - "light": ~2B for lightweight tasks (markdown drafts, ascii art ideas)
  - "tool" : ~8B for tool-JSON output that can trigger safe Python functions
- Lazy loading: load model/tokenizer only when first used.
- Safe tool execution protocol:
  Model returns a single line JSON like:
    {"tool":"save_markdown","args":{"content":"...","filepath":"notes/a.md"}}
  We only allow a small whitelist of tools (from markdown_market.py).

Notes:
- This module is CLI/library friendly (no gradio dependency).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

DEFAULT_LIGHT_MODEL = os.getenv("IRONMATE_LIGHT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
DEFAULT_TOOL_MODEL = os.getenv("IRONMATE_TOOL_MODEL", "Qwen/Qwen2.5-7B-Instruct")

# For GTX 2070 (8GB), 8B often needs 4-bit quant to fit comfortably.
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

        self._light = None  # (tokenizer, model)
        self._tool = None   # (tokenizer, model)

    # -----------------------
    # Model loading
    # -----------------------
    def _get_bnb_config(self):
        # Optional: bitsandbytes 4-bit quant config
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
        # Some models don't have pad token by default
        if tok.pad_token_id is None and tok.eos_token_id is not None:
            tok.pad_token_id = tok.eos_token_id

        kwargs = dict(
            device_map="auto",
            trust_remote_code=True,
        )

        # GTX 2070 is typically fp16; set float16 for safety.
        kwargs["torch_dtype"] = torch.float16

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

    # -----------------------
    # Prompting helpers
    # -----------------------
    def _chat_prompt(self, tokenizer, system: str, user: str) -> str:
        # Use chat template if available; fallback to simple format
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
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

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

    # -----------------------
    # Tool JSON parsing
    # -----------------------
    _JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

    def extract_first_json(self, text: str) -> Optional[Dict[str, Any]]:
        m = self._JSON_RE.search(text.strip())
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def default_tool_schema() -> str:
    return (
        "TOOL_SCHEMA (respond with ONE-LINE JSON only):\n"
        "Allowed tools:\n"
        "1) save_markdown: args={content:str, filepath:str}\n"
        "2) read_markdown: args={filepath:str, count_hashtags:bool}\n"
        "3) extract_sections: args={content:str}\n"
        "4) none: args={}\n"
        "\n"
        "Rules:\n"
        "- Output must be a single JSON object in one line.\n"
        "- Do not include explanations.\n"
        "- If user asks to run arbitrary bash/commands, refuse by returning tool=none.\n"
    )


def execute_allowed_tool(tool_json: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    tool = (tool_json.get("tool") or "").strip()
    args = tool_json.get("args") or {}
    if not isinstance(args, dict):
        args = {}

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

    return "No tool executed.", {"tool": "none", "result": {}}
