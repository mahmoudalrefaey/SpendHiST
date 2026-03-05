"""Business logic for receipt CRUD operations."""

from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.receipt import Receipt, ReceiptItem
from app.schemas.receipt import ReceiptCreate


def create_receipt(db: Session, payload: ReceiptCreate) -> Receipt:
    receipt = Receipt(
        merchant_name=payload.merchant_name,
        receipt_date=payload.receipt_date,
        total_amount=payload.total_amount,
        total_taxes=payload.total_taxes,
        other=payload.other,
        currency=payload.currency,
        raw_text=payload.raw_text,
    )
    db.add(receipt)
    db.flush()

    for item in payload.items:
        db.add(
            ReceiptItem(
                receipt_id=receipt.receipt_id,
                item_name=item.item_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                taxes=item.taxes,
            )
        )

    db.commit()
    db.refresh(receipt)
    return receipt


def list_receipts(db: Session) -> List[Receipt]:
    return db.query(Receipt).order_by(Receipt.created_at.desc()).all()


def search_receipts(db: Session, term: str) -> List[Receipt]:
    pattern = f"%{term}%"
    return (
        db.query(Receipt)
        .outerjoin(Receipt.items)
        .filter(
            or_(
                Receipt.merchant_name.ilike(pattern),
                Receipt.currency.ilike(pattern),
                Receipt.raw_text.ilike(pattern),
                ReceiptItem.item_name.ilike(pattern),
            )
        )
        .order_by(Receipt.created_at.desc())
        .distinct()
        .all()
    )


def get_receipt_by_id(db: Session, receipt_id: int) -> Optional[Receipt]:
    return db.query(Receipt).filter(Receipt.receipt_id == receipt_id).first()


def delete_receipt_by_id(db: Session, receipt_id: int) -> Optional[Receipt]:
    receipt = get_receipt_by_id(db, receipt_id)
    if receipt:
        db.delete(receipt)
        db.commit()
    return receipt


def delete_all_receipts(db: Session) -> int:
    deleted = db.query(Receipt).delete()
    db.commit()
    return deleted
