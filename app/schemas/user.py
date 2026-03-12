"""Pydantic request/response schemas for users."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)
    phone_number: Optional[str] = Field(None, max_length=30)
    full_name: Optional[str] = Field(None, max_length=255)


class UserLogin(BaseModel):
    email: str = Field(..., max_length=255)
    password: str


class UserResponse(BaseModel):
    user_id: int
    email: str
    phone_number: Optional[str]
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
