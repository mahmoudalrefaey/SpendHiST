from langchain_core.tools import tool
from typing import Optional

from app.core.database import SessionLocal
from app.services.receipt_service import summarise_receipts


@tool
def summarise_tool(query: str = "", user_id: Optional[int] = None) -> str:
    """
    Tool for agents: Aggregates receipts (count and total by currency).

    Args:
        query (str): Optional search term; if empty, all receipts are summarised.
        user_id (int, optional): Scope summary to a specific user's receipts.

    Returns:
        str: Summary text (count and totals per currency).
    """
    db = SessionLocal()
    try:
        return summarise_receipts(db, query, user_id=user_id)
    finally:
        db.close()
