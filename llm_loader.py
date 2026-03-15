# llm_loader.py
# __all__: 5

from __future__ import annotations

__all__ = [
    "DEFAULT_CACHE_DIR",
    "DEFAULT_MAX_NEW_TOKENS",
    "DEFAULT_MODEL_ID",
    "DEFAULT_TEMPERATURE",
    "LLMLoader",
]

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = str(Path(os.getenv("IRONMATE_CACHE_DIR", ".ironmate_cache")).resolve())
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("IRONMATE_MAX_NEW_TOKENS", "256"))
DEFAULT_MODEL_ID = os.getenv("IRONMATE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
DEFAULT_TEMPERATURE = float(os.getenv("IRONMATE_TEMPERATURE", "0.2"))


@dataclass
class _LoadState:
    config: Any | None = None
    model: Any | None = None
    tokenizer: Any | None = None


class LLMLoader:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        cache_dir: str = DEFAULT_CACHE_DIR,
        load_4bit: bool = True,
    ) -> None:
        self.cache_dir = str(Path(cache_dir).resolve())
        self.load_4bit = load_4bit
        self.model_id = model_id
        self._state = _LoadState()

    def _get_bnb_config(self):
        if not self.load_4bit:
            return None
        try:
            from transformers import BitsAndBytesConfig
        except Exception:
            return None
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype="float16",
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

    def is_loaded(self) -> bool:
        return self._state.model is not None and self._state.tokenizer is not None

    def load(self) -> None:
        if self.is_loaded():
            return

        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        config = AutoConfig.from_pretrained(
            self.model_id,
            cache_dir=self.cache_dir,
            trust_remote_code=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            cache_dir=self.cache_dir,
            trust_remote_code=True,
            use_fast=True,
        )
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token_id = tokenizer.eos_token_id

        kwargs: dict[str, Any] = {
            "cache_dir": self.cache_dir,
            "device_map": "auto",
            "dtype": torch.float16,
            "trust_remote_code": True,
        }

        bnb_config = self._get_bnb_config()
        if bnb_config is not None:
            kwargs["quantization_config"] = bnb_config

        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            config=config,
            **kwargs,
        )
        model.eval()

        self._state = _LoadState(config=config, model=model, tokenizer=tokenizer)

    @property
    def config(self):
        self.load()
        return self._state.config

    @property
    def model(self):
        self.load()
        return self._state.model

    @property
    def tokenizer(self):
        self.load()
        return self._state.tokenizer

    def build_chat_prompt(self, system: str, user: str) -> str:
        tokenizer = self.tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            return tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        return f"[SYSTEM]\n{system}\n\n[USER]\n{user}\n\n[ASSISTANT]\n"

    def generate(
        self,
        system: str,
        user: str,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        import torch

        model = self.model
        prompt = self.build_chat_prompt(system=system, user=user)
        tokenizer = self.tokenizer
        inputs = tokenizer(prompt, return_tensors="pt")

        if hasattr(model, "device") and model.device is not None:
            inputs = {key: value.to(model.device) for key, value in inputs.items()}

        with torch.no_grad():
            output = model.generate(
                **inputs,
                do_sample=(temperature > 0),
                eos_token_id=tokenizer.eos_token_id,
                max_new_tokens=max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
                repetition_penalty=1.05,
                temperature=max(temperature, 1e-5),
                top_p=0.9,
                use_cache=True,
            )

        text = tokenizer.decode(output[0], skip_special_tokens=True)
        if text.startswith(prompt):
            text = text[len(prompt):]
        return text.strip()
