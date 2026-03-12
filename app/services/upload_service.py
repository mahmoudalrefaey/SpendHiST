"""Handles file upload, OCR extraction, parsing, and DB persistence."""

from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import RECEIPTS_IMG_DIR
from app.models.receipt import Receipt, ReceiptItem
from app.ocr.engine import extract_text
from app.parser.dispatcher import parse_receipt_text

# Ensure upload directory exists at import time
UPLOAD_DIR = Path(RECEIPTS_IMG_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def process_uploaded_file(
    uploaded_file: UploadFile, db: Session, user_id: int
) -> str:
    """
    Save the file, run OCR, parse, persist to DB under user_id.
    Returns the saved filename.
    """
    name = Path(uploaded_file.filename or "unnamed").name
    dest = UPLOAD_DIR / name
    content = await uploaded_file.read()
    dest.write_bytes(content)

    ocr_text = extract_text(str(dest))
    parsed = parse_receipt_text(ocr_text)

    receipt = Receipt(
        user_id=user_id,
        merchant_name=parsed["merchant_name"],
        receipt_date=parsed["receipt_date"],
        total_amount=parsed["total_amount"],
        total_taxes=parsed["total_taxes"],
        other=parsed["other"],
        currency=parsed["currency"],
        raw_text=ocr_text,
    )
    db.add(receipt)
    db.flush()

    for item in parsed.get("items", []):
        db.add(
            ReceiptItem(
                receipt_id=receipt.receipt_id,
                item_name=item["item_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                line_total=item["line_total"],
                taxes=item["taxes"],
            )
        )

    db.commit()
    db.refresh(receipt)
    return name
