"""Business logic for receipt CRUD operations."""

from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.receipt import Receipt, ReceiptItem
from app.schemas.receipt import ReceiptCreate


def create_receipt(db: Session, payload: ReceiptCreate) -> Receipt:
    receipt = Receipt(
        user_id=payload.user_id,
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


def list_receipts(db: Session, user_id: Optional[int] = None) -> List[Receipt]:
    q = db.query(Receipt)
    if user_id is not None:
        q = q.filter(Receipt.user_id == user_id)
    return q.order_by(Receipt.created_at.desc()).all()


def search_receipts(db: Session, term: str, user_id: Optional[int] = None) -> List[Receipt]:
    pattern = f"%{term}%"
    q = (
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
    )
    if user_id is not None:
        q = q.filter(Receipt.user_id == user_id)
    return q.order_by(Receipt.created_at.desc()).distinct().all()


def get_receipt_by_id(
    db: Session, receipt_id: int, user_id: Optional[int] = None
) -> Optional[Receipt]:
    q = db.query(Receipt).filter(Receipt.receipt_id == receipt_id)
    if user_id is not None:
        q = q.filter(Receipt.user_id == user_id)
    return q.first()


def delete_receipt_by_id(
    db: Session, receipt_id: int, user_id: Optional[int] = None
) -> Optional[Receipt]:
    receipt = get_receipt_by_id(db, receipt_id, user_id)
    if receipt:
        db.delete(receipt)
        db.commit()
    return receipt


def delete_all_receipts(db: Session, user_id: Optional[int] = None) -> int:
    q = db.query(Receipt)
    if user_id is not None:
        q = q.filter(Receipt.user_id == user_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return deleted


def summarise_receipts(db: Session, term: str = "", user_id: Optional[int] = None) -> str:
    """
    Aggregate receipts: count and total by currency.
    Optionally filter by search term and/or user_id.
    """
    if term.strip():
        receipts = search_receipts(db, term.strip(), user_id=user_id)
    else:
        receipts = list_receipts(db, user_id=user_id)
    if not receipts:
        return "No receipts to summarise."
    by_currency: dict = {}
    for r in receipts:
        c = r.currency or "?"
        by_currency[c] = by_currency.get(c, 0) + float(r.total_amount)
    lines = [f"Count: {len(receipts)} receipt(s)."]
    for c, total in sorted(by_currency.items()):
        lines.append(f"  Total {c}: {total:.2f}")
    return "\n".join(lines)
