"""Request/response models for the chat endpoint."""

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    thread_id: Optional[str] = Field(
        default=None,
        description="Omit to start a new conversation; send the returned id to continue.",
    )


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
