"""Receipt API endpoints — /receipts and /receipts/upload."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.receipt import ReceiptCreate, ReceiptResponse
from app.services import receipt_service, upload_service

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptResponse, status_code=201)
async def create_receipt(payload: ReceiptCreate, db: Session = Depends(get_db)):
    """Create a receipt from a structured JSON payload (user_id required in body)."""
    return receipt_service.create_receipt(db, payload)


@router.get("", response_model=List[ReceiptResponse])
async def list_receipts(
    user_id: Optional[int] = Query(None, description="Filter receipts by user"),
    db: Session = Depends(get_db),
):
    """Return receipts; optionally scoped to a user."""
    return receipt_service.list_receipts(db, user_id=user_id)


@router.get("/search", response_model=List[ReceiptResponse])
async def search_receipts(
    q: Optional[str] = Query(None, description="Search term (merchant, items, currency, etc.)"),
    user_id: Optional[int] = Query(None, description="Scope search to a user"),
    db: Session = Depends(get_db),
):
    """Full-text search across merchant name, items, currency, and raw OCR text."""
    if not q or not q.strip():
        return []
    return receipt_service.search_receipts(db, q.strip(), user_id=user_id)


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: int,
    user_id: Optional[int] = Query(None, description="Scope lookup to a user"),
    db: Session = Depends(get_db),
):
    """Fetch a single receipt by ID; optionally scoped to a user."""
    receipt = receipt_service.get_receipt_by_id(db, receipt_id, user_id=user_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: int,
    user_id: Optional[int] = Query(None, description="Scope deletion to a user"),
    db: Session = Depends(get_db),
):
    """Delete a single receipt and all its items; optionally scoped to a user."""
    receipt = receipt_service.delete_receipt_by_id(db, receipt_id, user_id=user_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"message": "Receipt deleted", "receipt_id": receipt_id}


@router.delete("")
async def delete_all_receipts(
    user_id: Optional[int] = Query(None, description="Delete only receipts belonging to a user"),
    db: Session = Depends(get_db),
):
    """Delete receipts; optionally scoped to a user."""
    deleted = receipt_service.delete_all_receipts(db, user_id=user_id)
    return {"message": "Receipts deleted", "deleted": deleted}


@router.post("/upload")
async def upload_receipts(
    user_id: int = Form(..., description="Owner user ID"),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload image/PDF files, run OCR + parsing, and save receipts under user_id."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    saved: List[str] = []
    for uploaded_file in files:
        name = (uploaded_file.filename or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Invalid or missing filename")
        filename = await upload_service.process_uploaded_file(uploaded_file, db, user_id)
        saved.append(filename)

    return {"message": "Files uploaded successfully", "files": saved}
