"""Pydantic request/response schemas for receipts."""

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class DeleteAllReceiptsBody(BaseModel):
    """Required body for destructive bulk delete."""

    confirm: Literal["DELETE_ALL_RECEIPTS"]


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


class ReceiptSummary(BaseModel):
    """List/search row without line items (avoids N+1 and large payloads)."""

    receipt_id: int
    user_id: int
    merchant_name: str
    receipt_date: datetime
    total_amount: Decimal
    total_taxes: Decimal
    other: Decimal
    currency: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedReceiptsResponse(BaseModel):
    items: List[ReceiptSummary]
    total: int
    limit: int
    offset: int


class ReceiptSearchResponse(BaseModel):
    """Capped full-text search; total is count of distinct matching receipts."""

    items: List[ReceiptSummary]
    total: int
    limit: int
    offset: int
    include_raw_text_in_search: bool
