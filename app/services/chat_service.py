"""Run one turn through the LangGraph supervisor (checkpointed by thread_id)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from langchain_core.messages import HumanMessage

from ai.agents.supervisor import supervisor, supervisor_invoke_config


def _last_assistant_text(messages: list[Any]) -> str:
    for m in reversed(messages):
        content = getattr(m, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


async def chat_turn(
    user_id: int,
    message: str,
    thread_id: Optional[str],
) -> tuple[str, str]:
    """
    Returns (assistant_reply, thread_id).
    thread_id is new UUID if the client did not send one.
    """
    client_thread = thread_id.strip() if thread_id and thread_id.strip() else str(uuid.uuid4())
    scoped_thread = f"{user_id}:{client_thread}"

    config = supervisor_invoke_config(thread_id=scoped_thread, user_id=user_id)
    user_text = f"(user_id={user_id})\n{message.strip()}"

    payload = {"messages": [HumanMessage(content=user_text)]}
    state = await supervisor.ainvoke(payload, config=config)

    reply = _last_assistant_text(state.get("messages") or [])
    return reply, client_thread
