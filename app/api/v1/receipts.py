"""Receipt API endpoints — /receipts and /receipts/upload."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_id, get_db
from app.core.rate_limit import limit_upload
from app.config import (
    DEFAULT_RECEIPT_PAGE_SIZE,
    MAX_RECEIPT_PAGE_SIZE,
    SEARCH_RESULTS_CAP,
)
from app.schemas.receipt import (
    DeleteAllReceiptsBody,
    PaginatedReceiptsResponse,
    ReceiptCreate,
    ReceiptResponse,
    ReceiptSearchResponse,
)
from app.services import receipt_service, upload_service

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptResponse, status_code=201)
async def create_receipt(
    payload: ReceiptCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create a receipt from a structured JSON payload (user_id from JWT)."""
    payload.user_id = user_id
    return receipt_service.create_receipt(db, payload)


@router.get("", response_model=PaginatedReceiptsResponse)
async def list_receipts(
    limit: int = Query(default=DEFAULT_RECEIPT_PAGE_SIZE, ge=1, le=MAX_RECEIPT_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Paginated receipt list (no line items); use GET /receipts/{id} for items."""
    limit = min(limit, MAX_RECEIPT_PAGE_SIZE)
    rows, total = receipt_service.list_receipts_page(
        db, user_id, limit=limit, offset=offset
    )
    return PaginatedReceiptsResponse(
        items=rows,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=ReceiptSearchResponse)
async def search_receipts(
    q: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(default=SEARCH_RESULTS_CAP, ge=1, le=MAX_RECEIPT_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    include_raw: bool = Query(
        default=True,
        description="If false, skip matching on raw_text (faster at scale).",
    ),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Search receipts (capped). Omits line items; use GET /receipts/{id} for detail."""
    if not q or not q.strip():
        return ReceiptSearchResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            include_raw_text_in_search=include_raw,
        )
    limit = min(limit, MAX_RECEIPT_PAGE_SIZE)
    rows, total = receipt_service.search_receipts(
        db,
        q.strip(),
        user_id=user_id,
        include_raw=include_raw,
        limit=limit,
        offset=offset,
    )
    return ReceiptSearchResponse(
        items=rows,
        total=total,
        limit=limit,
        offset=offset,
        include_raw_text_in_search=include_raw,
    )


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Fetch a single receipt by ID scoped to the authenticated user."""
    receipt = receipt_service.get_receipt_by_id(db, receipt_id, user_id=user_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete a single receipt scoped to the authenticated user."""
    receipt = receipt_service.delete_receipt_by_id(db, receipt_id, user_id=user_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"message": "Receipt deleted", "receipt_id": receipt_id}


@router.delete("")
async def delete_all_receipts(
    body: DeleteAllReceiptsBody,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete all receipts for the user; requires explicit confirmation in JSON body."""
    deleted = receipt_service.delete_all_receipts(db, user_id=user_id)
    return {"message": "Receipts deleted", "deleted": deleted}


@router.post("/upload")
@limit_upload
async def upload_receipts(
    request: Request,
    files: List[UploadFile] = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Upload image/PDF files, run OCR + parsing, save receipts for the authenticated user."""
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
