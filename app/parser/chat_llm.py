"""OpenAI-compatible chat client for receipt parsers (G0I gateway)."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import G0I_API_KEY, PARSER_MODEL

G0I_BASE_URL = "https://g0i.shop/v1"


@lru_cache(maxsize=1)
def _parser_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=PARSER_MODEL,
        base_url=G0I_BASE_URL,
        api_key=G0I_API_KEY,
        temperature=0
    )


def parser_invoke(user_prompt: str, *, system_prompt: str) -> str:
    """Run one chat completion; returns assistant text."""
    llm = _parser_llm()
    msg = llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "".join(parts).strip()
    return (str(content) if content else "").strip()
