from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from datetime import datetime
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session
from pathlib import Path

from ocr import extract_text
from parser.router import parse_receipt_text

from db import SessionLocal
from models import Receipt, ReceiptItem


app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# Receipt Item Schemas
# -----------------------------

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

# -----------------------------
# Receipt Schemas
# -----------------------------

class ReceiptBase(BaseModel):
    merchant_name: str = Field(..., max_length=150)
    receipt_date: datetime
    total_amount: Decimal = Field(..., ge=0)
    total_taxes: Decimal = Field(0, ge=0)
    other: Decimal = Field(0, ge=0)
    currency: str = Field(..., max_length=10)
    raw_text: Optional[str] = None

class ReceiptCreate(ReceiptBase):
    items: List[ReceiptItemCreate]


class ReceiptResponse(ReceiptBase):
    receipt_id: int
    created_at: datetime
    items: List[ReceiptItemResponse]
    
    class Config:
        from_attributes = True
        
@app.post("/receipts", response_model=ReceiptResponse)
async def create_receipt(payload: ReceiptCreate, db: Session = Depends(get_db)):

    # Create receipt object
    new_receipt = Receipt(
        merchant_name=payload.merchant_name,
        receipt_date=payload.receipt_date,
        total_amount=payload.total_amount,
        total_taxes=payload.total_taxes,
        other=payload.other,
        currency=payload.currency,
        raw_text=payload.raw_text
    )

    db.add(new_receipt)
    db.flush()  # Get receipt_id before commit

    # Add items
    for item in payload.items:
        new_item = ReceiptItem(
            receipt_id=new_receipt.receipt_id,
            item_name=item.item_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
            taxes=item.taxes
        )
        db.add(new_item)

    db.commit()
    db.refresh(new_receipt)

    return new_receipt

@app.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(receipt_id: int, db: Session = Depends(get_db)):

    receipt = db.query(Receipt).filter(
        Receipt.receipt_id == receipt_id
    ).first()

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return receipt
        
# Uploads dir: project root, so it's fixed regardless of cwd
_BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = _BASE_DIR / "receipts_img"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RAW_TEXT_DIR = _BASE_DIR / "receipts_raw"
RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/upload-receipt")
async def upload_receipt(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    saved = []
    for uploaded_file in files:
        
        # _______________ upload & save images ______________
        name = Path(uploaded_file.filename or "unnamed").name
        if not name or name == "unnamed":
            raise HTTPException(status_code=400, detail="Invalid or missing filename")
        dest = UPLOAD_DIR / name
        content = await uploaded_file.read()
        dest.write_bytes(content)
        saved.append(name)
        
        # _______________ extract ocr text ______________
        ocr_text = extract_text(dest)
        
        # _______________ parse ocr text ______________
        parsed_text = parse_receipt_text(ocr_text)
        
        # _______________ create receipt ______________
        new_receipt = Receipt(
            merchant_name=parsed_text["merchant_name"],
            receipt_date=parsed_text["receipt_date"],
            total_amount=parsed_text["total_amount"],
            total_taxes=parsed_text["total_taxes"],
            other=parsed_text["other"],
            currency=parsed_text["currency"],
            raw_text=ocr_text
        )
        db.add(new_receipt)
        db.flush()
        
        # _______________ create receipt items ______________
        for item in parsed_text["items"]:
            new_item = ReceiptItem(
                receipt_id=new_receipt.receipt_id,
                item_name=item["item_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                line_total=item["line_total"],
                taxes=item["taxes"]
            )
            db.add(new_item)
        db.commit()
        db.refresh(new_receipt)
        
    return {"message": "Files uploaded successfully", "files": saved}
