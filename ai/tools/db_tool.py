import json

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal


@tool
async def db_tool(sql_query: str) -> str:
    """
    Execute a read-only SELECT against PostgreSQL.

    receipt columns: receipt_id, user_id, merchant_name, receipt_date (not "date"),
    total_amount, total_taxes, other, currency, raw_text, created_at.
    receipt_items: item_id, receipt_id, item_name, quantity, unit_price, line_total, taxes.
    """

    db = SessionLocal()
    try:
        result = db.execute(text(sql_query.strip()))
        rows = result.fetchall()
        columns = result.keys()
        output = [dict(zip(columns, row)) for row in rows]
        return json.dumps(output, default=str)
    except SQLAlchemyError as e:
        db.rollback()
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        return (
            "DATABASE_ERROR: "
            + msg
            + " Common fix: use receipt.receipt_date for ordering/filtering dates (column `date` does not exist)."
        )
    finally:
        db.close()
