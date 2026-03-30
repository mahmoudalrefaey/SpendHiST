"""Arabic receipt parser — shares model and helpers with en_parser."""

import re
from typing import Optional

from app.config import HF_TOKEN, PARSER_MODEL
from app.services.llm_service import load_llm
from app.parser.en_parser import (
    _FIX_JSON_PROMPT,
    _coerce_types,
    _to_float,
    _try_parse_json,
)

# ═════════════════════════════════════════════════════════════════════════════
#  ARABIC-SPECIFIC FORBIDDEN LABELS
#  Numbers on these lines must NEVER become total_amount or other.
# ═════════════════════════════════════════════════════════════════════════════

_PAID_LABELS = [
    "المدفوع", "الباقي", "الباقي عليه", "الباقي لك",
    "المتبقي", "الفرق", "الباقي (فكة)", "الباقي (فكه)",
    "paid", "cash", "change", "balance", "remaining",
]

_TOTAL_LABELS = [
    "الإجمالي", "الاجمالي", "الإجمالى", "المجموع",
    "total", "grand total",
]

# ═════════════════════════════════════════════════════════════════════════════
#  ARABIC PROMPTS
# ═════════════════════════════════════════════════════════════════════════════

_AR_SYSTEM_PROMPT = """\
You are a receipt parsing engine specialized in Arabic and mixed-language receipts. \
Output valid JSON only. No markdown, no explanation, no extra keys. \
If a value is unknown use null — EXCEPT merchant_name which must NEVER be null.

Critical reasoning rules (internal only, never shown in output):
- merchant_name is REQUIRED. Infer from: business name at top or bottom, \
"Powered by X" footer (use X), brand name. Never output null for merchant_name.
- Item price columns may be unit price OR line total. Test both interpretations \
and pick the one whose sum matches subtotal/الإجمالي/المجموع.
- Do NOT include these as JSON fields or values: \
المدفوع، الباقي، الباقي عليه، الباقي لك، المتبقي، الفرق، \
paid, cash, change, balance, remaining. \
These are payment/change lines — completely ignore their numbers.
- total_amount must come ONLY from labels: \
الإجمالي / الاجمالي / الإجمالى / المجموع / Total / Grand Total. \
Do not use the number from المدفوع or الباقي as total_amount under any circumstances.
- other: tips, service charges, delivery fees only. NOT paid/change lines.
- Dates: normalize to YYYY-MM-DD.
- Currency: EGP / ج.م / جنيه / LE → "EGP"; $ → "USD"; € → "EUR"; etc.
- Non-item lines (الإجمالي، المجموع، ضريبة، المدفوع، الباقي، etc.) \
must NOT appear as items.

Output: JSON only. No chain-of-thought.\
"""

_AR_USER_PROMPT = """\
Extract structured receipt data from the following Arabic/mixed OCR text.

OCR TEXT:
<<<
{raw_text}
>>>

Rules:
- Output JSON only (no markdown fences, no explanation).
- Schema:
  {{
    "merchant_name": "string (REQUIRED, never null)",
    "receipt_date": "YYYY-MM-DD or null",
    "currency": "3-letter code or null",
    "subtotal": number or null,
    "total_taxes": number or null,
    "other": number or null,
    "total_amount": number or null,
    "items": [
      {{
        "item_name": "string",
        "quantity": integer (minimum 1),
        "unit_price": number (required),
        "line_total": number (required)
      }}
    ]
  }}

CRITICAL — Arabic-specific rules:
- المدفوع / الباقي / الباقي عليه / الباقي لك / المتبقي / الفرق / paid / cash / change:
  IGNORE COMPLETELY. Do NOT use their numbers anywhere in the JSON.
- total_amount must come from: الإجمالي / الاجمالي / المجموع / Total / Grand Total only.
- other: delivery fees, tips, service charges only — NOT paid/change.
- Items: extract name, qty, unit_price, line_total. Test unit-price vs line-total \
interpretation using the total to decide.
- Use null for unknown values except merchant_name.

Return final JSON only.\
"""


# ═════════════════════════════════════════════════════════════════════════════
#  ARABIC SAFETY POST-PROCESSING
# ═════════════════════════════════════════════════════════════════════════════

def _extract_paid_change_values(raw_text: str) -> set:
    """Collect all numeric values from paid/change lines — these are forbidden as totals."""
    forbidden: set = set()
    for line in raw_text.splitlines():
        if any(label.lower() in line.lower() for label in _PAID_LABELS):
            for m in re.finditer(r"[\d,٠-٩]+\.?[\d,٠-٩]*", line):
                raw_num = m.group(0).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
                raw_num = raw_num.replace(",", "")
                try:
                    forbidden.add(float(raw_num))
                except ValueError:
                    continue
    return forbidden


def _extract_valid_total(raw_text: str) -> Optional[float]:
    """Return the first positive number found on a recognised total label line."""
    for line in raw_text.splitlines():
        if any(lbl.lower() in line.lower() for lbl in _TOTAL_LABELS):
            for n in re.findall(r"[\d,٠-٩]+\.?[\d,٠-٩]*", line):
                raw_num = n.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
                raw_num = raw_num.replace(",", "")
                try:
                    val = float(raw_num)
                    if val > 0:
                        return val
                except ValueError:
                    continue
    return None


def _guard_arabic_totals(parsed: dict, raw_text: str) -> dict:
    """
    Post-processing guard for Arabic receipts:
    1. Reject total_amount if it matches a paid/change line value.
    2. Replace with a value from a valid total label (or null).
    3. Also clear 'other' if it came from a paid/change line.
    4. Nullify total_amount if it's less than subtotal.
    """
    forbidden = _extract_paid_change_values(raw_text)

    current_total = _to_float(parsed.get("total_amount"))
    if current_total is not None and current_total in forbidden:
        parsed["total_amount"] = _extract_valid_total(raw_text)

    current_other = _to_float(parsed.get("other"))
    if current_other is not None and current_other in forbidden:
        parsed["other"] = None

    subtotal = _to_float(parsed.get("subtotal"))
    total = _to_float(parsed.get("total_amount"))
    if total is not None and subtotal is not None and total < subtotal:
        parsed["total_amount"] = None

    return parsed


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRYPOINT
# ═════════════════════════════════════════════════════════════════════════════

def parse_ar(raw_text: str) -> dict:
    """
    Parse an Arabic or mixed-language receipt into a structured dict.
    Called by dispatcher.py.
    """
    generate = load_llm(
        model_name=PARSER_MODEL,
        hf_token=HF_TOKEN,
        default_system_prompt=_AR_SYSTEM_PROMPT,
    )

    raw_response = generate(_AR_USER_PROMPT.format(raw_text=raw_text), system=_AR_SYSTEM_PROMPT)
    parsed = _try_parse_json(raw_response)

    if parsed is None:
        fix_prompt = _FIX_JSON_PROMPT.format(broken_json=raw_response)
        parsed = _try_parse_json(generate(fix_prompt, system=_AR_SYSTEM_PROMPT))

    if parsed is None:
        parsed = {
            "merchant_name": None, "receipt_date": None, "currency": None,
            "subtotal": None, "total_taxes": None, "other": None,
            "total_amount": None, "items": [],
        }

    parsed = _guard_arabic_totals(parsed, raw_text)
    return _coerce_types(parsed, raw_text)
