"""
LLM loading service.

  - load_llm() → simple str→str callable for local or HF Inference API use.

Prefers local GPU when available, falls back to HF Inference API.
Cached so the same model is never loaded twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import torch
from app.config import HF_TOKEN

_PLAIN_CACHE: dict[tuple, Callable[..., str]] = {}


@dataclass(frozen=True)
class LLMConfig:
    model_name: str
    hf_token: Optional[str]
    prefer_local: bool = True
    max_new_tokens: int = 2048
    temperature: float = 0.0


def load_llm(
    *,
    model_name: str,
    default_system_prompt: str = "",
    hf_token: Optional[str] = None,
    prefer_local: bool = True,
    max_new_tokens: int = 2048,
    temperature: float = 0.0,
) -> Callable[[str, str], str]:
    """
    Return a text-generation callable:
        generate(prompt: str, system: str = default_system_prompt) -> str

    Backend:
        - GPU available + prefer_local → local transformers model
        - Otherwise                    → HF Inference API
    """
    token = hf_token if hf_token is not None else HF_TOKEN
    cache_key = (
        model_name, token is not None, prefer_local,
        max_new_tokens, temperature, default_system_prompt,
    )
    if cache_key in _PLAIN_CACHE:
        return _PLAIN_CACHE[cache_key]

    cfg = LLMConfig(
        model_name=model_name,
        hf_token=token,
        prefer_local=prefer_local,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )

    if cfg.prefer_local and torch.cuda.is_available():
        fn = _build_local_generator(cfg, default_system_prompt)
    else:
        fn = _build_api_generator(cfg, default_system_prompt)

    _PLAIN_CACHE[cache_key] = fn
    return fn


def _build_local_generator(
    cfg: LLMConfig, default_system_prompt: str
) -> Callable[[str, str], str]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model_name, trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        cfg.model_name,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype="auto",
    ).eval()

    def _generate(prompt: str, system: str = default_system_prompt) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=cfg.max_new_tokens,
                do_sample=False,
                temperature=1.0,
            )
        generated = out[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(generated, skip_special_tokens=True)

    return _generate


def _build_api_generator(
    cfg: LLMConfig, default_system_prompt: str
) -> Callable[[str, str], str]:
    from huggingface_hub import InferenceClient

    client = InferenceClient(model=cfg.model_name, token=cfg.hf_token)

    def _inst_prompt(prompt: str, system: str) -> str:
        return f"[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{prompt} [/INST]"

    def _generate(prompt: str, system: str = default_system_prompt) -> str:
        return client.text_generation(
            _inst_prompt(prompt, system),
            max_new_tokens=cfg.max_new_tokens,
            temperature=max(cfg.temperature, 0.01),  # API requires > 0
        )

    return _generate


