"""Pydantic request/response schemas for receipts."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class ReceiptItemBase(BaseModel):
    item_name: str = Field(..., max_length=150)
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    line_total: Decimal = Field(..., ge=0)
    taxes: Decimal = Field(0, ge=0)


class ReceiptItemCreate(ReceiptItemBase):
    pass


class ReceiptItemResponse(ReceiptItemBase):
    item_id: int
    receipt_id: int

    class Config:
        from_attributes = True


class ReceiptBase(BaseModel):
    merchant_name: str = Field(..., max_length=150)
    receipt_date: datetime
    total_amount: Decimal = Field(..., ge=0)
    total_taxes: Decimal = Field(0, ge=0)
    other: Decimal = Field(0, ge=0)
    currency: str = Field(..., max_length=10)
    raw_text: Optional[str] = None


class ReceiptCreate(ReceiptBase):
    user_id: Optional[int] = None  # injected from JWT in the endpoint
    items: List[ReceiptItemCreate]


class ReceiptResponse(ReceiptBase):
    receipt_id: int
    user_id: int
    created_at: datetime
    items: List[ReceiptItemResponse]

    class Config:
        from_attributes = True
