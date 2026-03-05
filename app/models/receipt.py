"""SQLAlchemy ORM models for receipts and their line items."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Receipt(Base):
    __tablename__ = "receipt"

    receipt_id = Column(BigInteger, primary_key=True, index=True)
    merchant_name = Column(String(150), nullable=False)
    receipt_date = Column(DateTime(timezone=True), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    total_taxes = Column(Numeric(10, 2), nullable=False, default=0)
    other = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_text = Column(Text)

    items = relationship(
        "ReceiptItem",
        back_populates="receipt",
        cascade="all, delete",
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    item_id = Column(BigInteger, primary_key=True, index=True)
    receipt_id = Column(
        BigInteger,
        ForeignKey("receipt.receipt_id", ondelete="CASCADE"),
        nullable=False,
    )
    item_name = Column(String(150), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)
    taxes = Column(Numeric(10, 2), nullable=False, default=0)

    receipt = relationship("Receipt", back_populates="items")
