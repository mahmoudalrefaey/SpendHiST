"""Chat endpoint — supervisor graph with per-user thread_id checkpointing."""

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_current_user_id
from app.core.rate_limit import limit_chat
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
@limit_chat
async def chat(
    request: Request,
    body: ChatRequest,
    user_id: int = Depends(get_current_user_id),
):
    reply, thread_id = await chat_service.chat_turn(
        user_id, body.message, body.thread_id
    )
    return ChatResponse(reply=reply, thread_id=thread_id)
