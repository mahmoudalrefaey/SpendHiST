"""Business logic for receipt CRUD operations."""

from typing import List, Optional, Tuple

from sqlalchemy import distinct, func, or_
from sqlalchemy.orm import Session, selectinload

from app.config import SEARCH_RESULTS_CAP
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
    return get_receipt_by_id(db, receipt.receipt_id, user_id=payload.user_id) or receipt


def list_receipts(db: Session, user_id: Optional[int] = None) -> List[Receipt]:
    """Unbounded list — prefer list_receipts_page for API hot paths."""
    q = db.query(Receipt)
    if user_id is not None:
        q = q.filter(Receipt.user_id == user_id)
    return q.order_by(Receipt.created_at.desc()).all()


def list_receipts_page(
    db: Session,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> Tuple[List[Receipt], int]:
    """Paginated receipts for one user; no items loaded."""
    base = db.query(Receipt).filter(Receipt.user_id == user_id)
    total = base.count()
    rows = (
        base.order_by(Receipt.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def _search_conditions(term: str, *, include_raw: bool):
    pattern = f"%{term}%"
    parts = [
        Receipt.merchant_name.ilike(pattern),
        Receipt.currency.ilike(pattern),
        ReceiptItem.item_name.ilike(pattern),
    ]
    if include_raw:
        parts.append(Receipt.raw_text.ilike(pattern))
    return or_(*parts)


def search_receipts(
    db: Session,
    term: str,
    user_id: Optional[int] = None,
    *,
    include_raw: bool = True,
    limit: int = SEARCH_RESULTS_CAP,
    offset: int = 0,
) -> Tuple[List[Receipt], int]:
    """
    Full-text-style search; returns (receipts, total_distinct_matches).
    Results capped by limit/offset on distinct receipts.
    """
    cond = _search_conditions(term, include_raw=include_raw)
    base = db.query(Receipt).outerjoin(Receipt.items).filter(cond)
    if user_id is not None:
        base = base.filter(Receipt.user_id == user_id)

    count_q = (
        db.query(func.count(distinct(Receipt.receipt_id)))
        .select_from(Receipt)
        .outerjoin(Receipt.items)
        .filter(cond)
    )
    if user_id is not None:
        count_q = count_q.filter(Receipt.user_id == user_id)
    total_count = int(count_q.scalar() or 0)

    receipts = (
        base.distinct()
        .order_by(Receipt.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return receipts, total_count


def get_receipt_by_id(
    db: Session, receipt_id: int, user_id: Optional[int] = None
) -> Optional[Receipt]:
    q = (
        db.query(Receipt)
        .options(selectinload(Receipt.items))
        .filter(Receipt.receipt_id == receipt_id)
    )
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
    Aggregate in SQL: distinct receipt count and SUM(total_amount) per currency.
    Search uses the same filters as search_receipts (including raw_text).
    """
    if term.strip():
        cond = _search_conditions(term.strip(), include_raw=True)
        subq = (
            db.query(Receipt.receipt_id.label("rid"))
            .outerjoin(Receipt.items)
            .filter(cond)
        )
        if user_id is not None:
            subq = subq.filter(Receipt.user_id == user_id)
        subq = subq.distinct().subquery()
        n = int(db.query(func.count()).select_from(subq).scalar() or 0)
        if n == 0:
            return "No receipts to summarise."
        rows = (
            db.query(Receipt.currency, func.coalesce(func.sum(Receipt.total_amount), 0))
            .join(subq, Receipt.receipt_id == subq.c.rid)
            .group_by(Receipt.currency)
            .all()
        )
    else:
        filtered = db.query(Receipt)
        if user_id is not None:
            filtered = filtered.filter(Receipt.user_id == user_id)
        n = filtered.count()
        if n == 0:
            return "No receipts to summarise."
        agg = db.query(
            Receipt.currency,
            func.coalesce(func.sum(Receipt.total_amount), 0),
        )
        if user_id is not None:
            agg = agg.filter(Receipt.user_id == user_id)
        rows = agg.group_by(Receipt.currency).all()

    lines = [f"Count: {n} receipt(s)."]
    for currency, total in sorted(rows, key=lambda r: (r[0] or "")):
        c = currency or "?"
        lines.append(f"  Total {c}: {float(total):.2f}")
    return "\n".join(lines)
