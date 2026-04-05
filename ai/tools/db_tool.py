"""Read-only SQL tool for sql_agent — bounded, SELECT-only, wrapped with LIMIT."""

import json
import re
from typing import Optional, Tuple

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import (
    DB_TOOL_MAX_JSON_BYTES,
    DB_TOOL_MAX_LIMIT,
    DB_TOOL_STATEMENT_TIMEOUT_MS,
)
from app.core.database import SessionLocal

# Disallow obvious write / DDL tokens as whole words (not substrings like "created_at").
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|execute|call|copy)\b",
    re.IGNORECASE,
)


def _validate_sql(raw: str) -> Tuple[bool, str]:
    """Return (ok, error_message)."""
    sql = raw.strip()
    if not sql:
        return False, "Empty query."

    # Single statement only (strip one trailing semicolon).
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    if ";" in sql:
        return False, "Multiple SQL statements are not allowed."

    if _FORBIDDEN_KEYWORDS.search(sql):
        return False, "Only read-only SELECT-style queries are allowed."

    # Must be SELECT or WITH ... SELECT (CTE).
    head = sql.lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        return False, "Query must start with SELECT or WITH (CTE then SELECT)."

    return True, sql


def _extract_limit_value(sql: str) -> Optional[int]:
    """Best-effort: find trailing LIMIT n (may misfire on subqueries; subquery is wrapped anyway)."""
    m = re.search(r"\blimit\s+(\d+)\s*$", sql, re.IGNORECASE | re.DOTALL)
    if m:
        return int(m.group(1))
    return None


def _wrap_with_limit(inner_sql: str) -> str:
    """Force a hard row cap via subquery wrapper."""
    existing = _extract_limit_value(inner_sql)
    cap = DB_TOOL_MAX_LIMIT
    if existing is not None:
        cap = min(existing, DB_TOOL_MAX_LIMIT)
    # Strip trailing LIMIT for cleaner wrap when we replace cap
    inner = re.sub(r"\s+limit\s+\d+\s*$", "", inner_sql, flags=re.IGNORECASE | re.DOTALL)
    inner = inner.strip()
    return f"SELECT * FROM ({inner}) AS _db_tool_sub LIMIT {cap}"


@tool
async def db_tool(sql_query: str) -> str:
    """
    Execute a read-only SELECT against PostgreSQL (via bounded subquery wrapper).

    receipt columns: receipt_id, user_id, merchant_name, receipt_date (not "date"),
    total_amount, total_taxes, other, currency, raw_text, created_at.
    receipt_items: item_id, receipt_id, item_name, quantity, unit_price, line_total, taxes.
    """

    ok, msg_or_sql = _validate_sql(sql_query)
    if not ok:
        return f"QUERY_REJECTED: {msg_or_sql}"

    inner = msg_or_sql
    wrapped = _wrap_with_limit(inner)

    db = SessionLocal()
    try:
        timeout_ms = max(100, int(DB_TOOL_STATEMENT_TIMEOUT_MS))
        db.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
        result = db.execute(text(wrapped))
        columns = list(result.keys())
        rows = result.fetchall()
        output = [dict(zip(columns, row)) for row in rows]
        payload = json.dumps(output, default=str)
        if len(payload.encode("utf-8")) > DB_TOOL_MAX_JSON_BYTES:
            return (
                f"RESULT_TOO_LARGE: serialized JSON exceeds {DB_TOOL_MAX_JSON_BYTES} bytes "
                f"({len(payload)} chars). Narrow your SELECT or add stricter filters."
            )
        return payload
    except SQLAlchemyError as e:
        db.rollback()
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        return (
            "DATABASE_ERROR: "
            + msg
            + " Common fix: use receipt.receipt_date for ordering/filtering dates "
            "(column `date` does not exist)."
        )
    finally:
        db.close()
