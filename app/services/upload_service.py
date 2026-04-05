"""Handles file upload, OCR extraction, parsing, and DB persistence."""

import os
import shutil
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES, RECEIPTS_IMG_DIR
from app.models.receipt import Receipt, ReceiptItem
from app.ocr.engine import extract_text
from app.parser.dispatcher import parse_receipt_text
from app.services.receipt_validate import missing_persist_fields, normalize_taxes_and_other

UPLOAD_DIR = Path(RECEIPTS_IMG_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def process_uploaded_file(
    uploaded_file: UploadFile, db: Session, user_id: int
) -> str:
    """
    Save to a temp file, run OCR, parse, validate, then move to a unique name and commit.
    Returns the stored filename (UUID-based to avoid collisions).
    """
    original_name = Path(uploaded_file.filename or "unnamed").name
    content = await uploaded_file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "message": "File too large",
                "max_bytes": MAX_UPLOAD_BYTES,
                "size_bytes": len(content),
            },
        )

    suffix = Path(original_name).suffix or ".bin"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=UPLOAD_DIR)
    os.close(fd)
    tmp_path: Path | None = Path(tmp_name)
    final_path: Path | None = None
    try:
        tmp_path.write_bytes(content)
        try:
            ocr_text = extract_text(str(tmp_path))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"message": str(e)}) from e
        parsed = parse_receipt_text(ocr_text)

        missing = missing_persist_fields(parsed)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Parsed receipt is missing required fields for persistence.",
                    "missing_fields": missing,
                    "hint": "Use POST /receipts with a JSON body to supply values manually.",
                },
            )

        parsed = normalize_taxes_and_other(parsed)
        stored_name = f"{uuid.uuid4().hex}_{original_name}"
        final_path = UPLOAD_DIR / stored_name
        shutil.move(str(tmp_path), str(final_path))
        tmp_path = None  # moved; do not delete in finally

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
                    taxes=Decimal(str(item.get("taxes", 0))),
                )
            )

        db.commit()
        db.refresh(receipt)
        return stored_name
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        if final_path and final_path.exists():
            try:
                final_path.unlink()
            except OSError:
                pass
        raise
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
