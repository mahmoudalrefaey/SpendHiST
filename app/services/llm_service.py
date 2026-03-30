"""
LLM loading service.

Two layers:
  - load_llm()      → simple str→str callable (parsers, OCR post-proc, SQL gen)
  - load_chat_llm() → LangChain ChatModel with bind_tools() + chat-template
                      (agents, tool-calling workflows)

Both prefer local GPU when available, fall back to HF Inference API.
Both are cached so the same model is never loaded twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import torch
from app.config import HF_TOKEN

# ── Cache stores ──────────────────────────────────────────────────────────────
_PLAIN_CACHE: dict[tuple, Callable[..., str]] = {}
_CHAT_CACHE: dict[tuple, object] = {}   # values are ChatHuggingFace instances


# ── Shared config dataclass ───────────────────────────────────────────────────
@dataclass(frozen=True)
class LLMConfig:
    model_name: str
    hf_token: Optional[str]
    prefer_local: bool = True
    max_new_tokens: int = 2048
    temperature: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 1. PLAIN LLM  ─  simple callable, used by parsers
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# 2. CHAT LLM  ─  LangChain ChatModel, supports bind_tools() and chat templates
# ─────────────────────────────────────────────────────────────────────────────

def load_chat_llm(
    *,
    model_name: str,
    hf_token: Optional[str] = None,
    prefer_local: bool = True,
    max_new_tokens: int = 2048,
    temperature: float = 0.0,
):
    """
    Return a LangChain ChatHuggingFace instance that:
      - Applies the model's own chat template automatically
      - Supports .bind_tools([...]) for agentic / tool-calling workflows
      - Can be used directly inside LangGraph / LCEL chains

    Backend:
        - GPU available + prefer_local → HuggingFacePipeline (fully offline)
        - Otherwise                    → HuggingFaceEndpoint (HF Inference API)

    Example — bind tools and invoke:
        llm = load_chat_llm(model_name="MadeAgents/Hammer2.1-3b")
        agent_llm = llm.bind_tools([search_tool, currency_tool])
        response  = agent_llm.invoke([HumanMessage(content="...")])
    """
    token = hf_token if hf_token is not None else HF_TOKEN
    cache_key = (model_name, token is not None, prefer_local, max_new_tokens, temperature)
    if cache_key in _CHAT_CACHE:
        return _CHAT_CACHE[cache_key]

    cfg = LLMConfig(
        model_name=model_name,
        hf_token=token,
        prefer_local=prefer_local,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )

    if cfg.prefer_local and torch.cuda.is_available():
        chat_llm = _build_local_chat_llm(cfg)
    else:
        chat_llm = _build_api_chat_llm(cfg)

    _CHAT_CACHE[cache_key] = chat_llm
    return chat_llm


def _build_local_chat_llm(cfg: LLMConfig):
    """
    Local backend: transformers pipeline → HuggingFacePipeline → ChatHuggingFace.
    The model's chat template is applied automatically by ChatHuggingFace.
    """
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline as hf_pipeline
    from langchain_huggingface import HuggingFacePipeline, ChatHuggingFace

    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model_name, trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        cfg.model_name,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype="auto",
    ).eval()

    pipe = hf_pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=cfg.max_new_tokens,
        # do_sample=False is greedy; set True + temperature for sampling
        do_sample=cfg.temperature > 0.0,
        temperature=cfg.temperature if cfg.temperature > 0.0 else None,
        return_full_text=False,     # return only the newly generated tokens
    )

    llm = HuggingFacePipeline(pipeline=pipe)

    # ChatHuggingFace wraps the pipeline, applies the tokenizer's chat template,
    # and exposes bind_tools() / with_structured_output() from BaseChatModel.
    return ChatHuggingFace(llm=llm, tokenizer=tokenizer)


def _build_api_chat_llm(cfg: LLMConfig):
    """
    API backend: HuggingFaceEndpoint → ChatHuggingFace.
    Uses the serverless Inference API — no local GPU needed.
    """
    from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace

    endpoint = HuggingFaceEndpoint(
        repo_id=cfg.model_name,
        huggingfacehub_api_token=cfg.hf_token,
        max_new_tokens=cfg.max_new_tokens,
        temperature=max(cfg.temperature, 0.01),  # API requires > 0
        task="text-generation",
    )

    return ChatHuggingFace(llm=endpoint)
