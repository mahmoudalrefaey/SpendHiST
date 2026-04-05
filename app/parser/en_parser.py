"""
en_parser.py — English receipt parser via OpenAI-compatible chat API (G0I).

Handles English and Latin-script receipts.
Called by dispatcher.py; do not call directly from the pipeline.
"""

import json
import re
from typing import Optional

from app.parser.chat_llm import parser_invoke

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ═════════════════════════════════════════════════════════════════════════════
#  PROMPTS
# ═════════════════════════════════════════════════════════════════════════════

# Compact prompts: one system block (rules + schema), user = OCR only → fewer tokens per call.

_SYSTEM_PROMPT = """\
You output a single JSON object only — no markdown, no keys beyond the schema.

Schema:
{"merchant_name":string,"receipt_date":"YYYY-MM-DD"|null,"currency":"XXX"|null,"subtotal":num|null,"total_taxes":num|null,"other":num|null,"total_amount":num|null,"items":[{"item_name":string,"quantity":int>=1,"unit_price":num,"line_total":num}]}

Rules:
- merchant_name: required non-empty string; infer from header, footer, "Powered by X", or brand (never null).
- Unknown scalars → null. quantity default 1 (round fractional qty to int ≥1). Derive missing unit_price or line_total from the other using qty.
- Shown item price may be unit or line: when ambiguous (esp. qty>1), pick the reading where Σ line_totals matches subtotal/total on the slip.
- Do not list subtotal, tax/VAT, total, cash, change, or thanks lines as items.
- other: tips, service, delivery only (not tax). Cross-check subtotal+taxes≈total when those lines exist.

Currency (else null): $ USD, € EUR, £ GBP, EGP/LE/ج.م/جنيه EGP, SAR/ريال SAR, AED/درهم AED, ₹/Rs INR.
"""

_USER_PROMPT = """\
<<<
{raw_text}
>>>
"""

_FIX_JSON_PROMPT = """\
Fix to valid JSON only (same object shape). No markdown or text outside the object.

{broken_json}
"""


# ═════════════════════════════════════════════════════════════════════════════
#  JSON HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> str:
    """Find the first balanced { ... } block in the text."""
    start = text.find("{")
    if start == -1:
        return text
    depth, in_string, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return text[start:]


def _try_parse_json(raw: str) -> Optional[dict]:
    cleaned = _strip_fences(raw)
    cleaned = _extract_json_object(cleaned)
    cleaned = cleaned.translate(_ARABIC_DIGITS)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  TYPE COERCION + POST-PROCESSING
# ═════════════════════════════════════════════════════════════════════════════

def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.translate(_ARABIC_DIGITS)
        s = re.sub(r"[^\d.\-,]", "", s)
        s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _infer_currency(raw_text: str) -> Optional[str]:
    """
    Scan raw text for currency symbols/codes.
    Unambiguous symbols checked first to avoid false positives.
    """
    patterns = [
        (r"\$",                                      "USD"),
        (r"€",                                       "EUR"),
        (r"£",                                       "GBP"),
        (r"₹",                                       "INR"),
        (r"\bUSD\b",                                 "USD"),
        (r"\bEUR\b",                                 "EUR"),
        (r"\bGBP\b",                                 "GBP"),
        (r"\bINR\b|\bRs\b",                          "INR"),
        (r"\bSAR\b|\bSR\b|ر\.س|ريال",               "SAR"),
        (r"\bAED\b|د\.إ|درهم",                       "AED"),
        # 'LE' checked last — prone to false matches (bottle, Apple, etc.)
        (r"\bEGP\b|(?<![a-zA-Z])LE\b|ج\.م|جنيه",   "EGP"),
    ]
    for pattern, code in patterns:
        if re.search(pattern, raw_text, re.IGNORECASE):
            return code
    return None


def _extract_tax_percent(raw_text: str) -> Optional[float]:
    """Extract VAT/Tax percentage from text, e.g. VAT(14%) or Tax 14%."""
    match = re.search(
        r"(?:vat|tax|ضريبة)\s*\(?\s*([\d.]+)\s*%",
        raw_text, re.IGNORECASE,
    )
    if match:
        try:
            pct = float(match.group(1))
            if 0 < pct < 100:
                return pct
        except ValueError:
            pass
    return None


def _extract_other_charges(raw_text: str) -> Optional[float]:
    """Sum non-item, non-tax charges: tips, service fees, delivery, etc."""
    keywords = [
        "tip", "gratuity", "بقشيش", "إكرامية",
        "service charge", "service fee", "رسوم خدمة",
        "delivery", "delivery fee", "توصيل",
        "surcharge",
    ]
    text = raw_text.translate(_ARABIC_DIGITS)
    total, found = 0.0, False
    for kw in keywords:
        pattern = re.compile(
            rf"{re.escape(kw)}\s*[:\-]?\s*"
            r"(?:[A-Z]{{2,3}}\s*|[$€£₹]\s*)?"
            r"([\d,]+\.?\d*)",
            re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    total += val
                    found = True
            except ValueError:
                continue
    return round(total, 2) if found else None


def _coerce_types(parsed: dict, raw_text: str) -> dict:
    """
    Align types with DB schema, apply currency override,
    and compute per-item taxes when a VAT % is found in the text.
    """
    merchant_name = (parsed.get("merchant_name") or "").strip() or "Unknown"

    text_currency = _infer_currency(raw_text)
    currency = text_currency or parsed.get("currency") or None

    llm_other = _to_float(parsed.get("other"))
    other = llm_other if llm_other else _extract_other_charges(raw_text)

    result = {
        "merchant_name": merchant_name,
        "receipt_date": parsed.get("receipt_date") or None,
        "currency": currency,
        "subtotal": _to_float(parsed.get("subtotal")),
        "total_taxes": _to_float(parsed.get("total_taxes")),
        "other": other,
        "total_amount": _to_float(parsed.get("total_amount")),
        "items": [],
        "raw_text": raw_text,
    }

    for item in (parsed.get("items") or []):
        name = (item.get("item_name") or "").strip()
        if not name:
            continue
        qty = max(1, int(round(_to_float(item.get("quantity")) or 1.0)))
        unit_price = _to_float(item.get("unit_price"))
        line_total = _to_float(item.get("line_total"))

        if unit_price is not None and line_total is None:
            line_total = round(qty * unit_price, 2)
        elif line_total is not None and unit_price is None:
            unit_price = round(line_total / qty, 2)
        elif unit_price is None and line_total is None:
            unit_price = 0.0
            line_total = 0.0

        result["items"].append({
            "item_name": name,
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total,
            "taxes": 0.0,
        })

    # Distribute per-item taxes if a VAT % is present in the raw text
    tax_pct = _extract_tax_percent(raw_text)
    if tax_pct and result["items"]:
        rate = tax_pct / 100.0
        for item in result["items"]:
            item["taxes"] = round(item["line_total"] * rate, 2)

    return result


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRYPOINT
# ═════════════════════════════════════════════════════════════════════════════

def parse_en(raw_text: str) -> dict:
    """
    Parse an English/Latin receipt into a structured dict.
    Called by dispatcher.py.
    """
    prompt = _USER_PROMPT.format(raw_text=raw_text)
    raw_response = parser_invoke(prompt, system_prompt=_SYSTEM_PROMPT)
    parsed = _try_parse_json(raw_response)

    if parsed is None:
        fix_prompt = _FIX_JSON_PROMPT.format(broken_json=raw_response)
        parsed = _try_parse_json(
            parser_invoke(fix_prompt, system_prompt=_SYSTEM_PROMPT)
        )

    if parsed is None:
        parsed = {
            "merchant_name": None, "receipt_date": None, "currency": None,
            "subtotal": None, "total_taxes": None, "other": None,
            "total_amount": None, "items": [],
        }

    return _coerce_types(parsed, raw_text)
