"""Validate parser output before persisting a receipt (NOT NULL / required fields)."""

from decimal import Decimal
from typing import Any, Dict, List


def missing_persist_fields(parsed: Dict[str, Any]) -> List[str]:
    """Return field names that must be present for DB insert (upload path)."""
    missing: List[str] = []
    if parsed.get("receipt_date") is None:
        missing.append("receipt_date")
    if parsed.get("total_amount") is None:
        missing.append("total_amount")
    cur = parsed.get("currency")
    if cur is None or (isinstance(cur, str) and not cur.strip()):
        missing.append("currency")
    merchant = parsed.get("merchant_name")
    if not merchant or not str(merchant).strip():
        missing.append("merchant_name")
    return missing


def normalize_taxes_and_other(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Fill auxiliary numerics so ORM never sees None on non-null columns."""
    out = dict(parsed)
    if out.get("total_taxes") is None:
        out["total_taxes"] = Decimal("0")
    if out.get("other") is None:
        out["other"] = Decimal("0")
    return out
