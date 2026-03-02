"""
ar_parser.py — Arabic receipt parser using Qwen2.5-1.5B-Instruct.

"""

import re
from typing import Optional

# Reuse all shared utilities from en_parser (model loader, helpers, etc.)
from .en_parser import (
    _FIX_JSON_PROMPT,
    _coerce_types,
    _to_float,
    _try_parse_json,
    load_qwen,
)

# ═════════════════════════════════════════════════════════════════════════════
#  ARABIC-SPECIFIC FORBIDDEN LABELS
#  Numbers appearing on these lines must NEVER become total_amount / other.
# ═════════════════════════════════════════════════════════════════════════════

# Arabic labels meaning "paid" or "change/remaining" — ignore their amounts
_PAID_LABELS = [
    "المدفوع", "الباقي", "الباقي عليه", "الباقي لك",
    "المتبقي", "الفرق", "الباقي (فكة)", "الباقي (فكه)",
    "paid", "cash", "change", "balance", "remaining",
]

# Arabic labels that represent the true receipt total
_TOTAL_LABELS = [
    "الإجمالي", "الاجمالي", "الإجمالى", "المجموع",
    "total", "grand total",
]

# ═════════════════════════════════════════════════════════════════════════════
#  ARABIC SYSTEM PROMPT
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
#  SAFETY POST-PROCESSING
# ═════════════════════════════════════════════════════════════════════════════

def _extract_paid_change_values(raw_text: str) -> set:
    """
    Extract all numeric values that appear on المدفوع/الباقي/paid/change lines.
    These are forbidden from appearing as total_amount.
    """
    forbidden_values: set = set()
    lines = raw_text.splitlines()
    for line in lines:
        line_lower = line.lower()
        if any(label.lower() in line_lower for label in _PAID_LABELS):
            # Pull every number from this line
            for m in re.finditer(r"[\d,٠-٩]+\.?[\d,٠-٩]*", line):
                raw_num = m.group(0).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
                raw_num = raw_num.replace(",", "")
                try:
                    forbidden_values.add(float(raw_num))
                except ValueError:
                    continue
    return forbidden_values


def _extract_valid_total(raw_text: str) -> Optional[float]:
    """
    Scan the receipt text for a number on a valid total line
    (الإجمالي / المجموع / Total / Grand Total).
    Returns the first match, or None.
    """
    lines = raw_text.splitlines()
    for line in lines:
        line_lower = line.lower()
        if any(lbl.lower() in line_lower for lbl in _TOTAL_LABELS):
            nums = re.findall(r"[\d,٠-٩]+\.?[\d,٠-٩]*", line)
            for n in nums:
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
    Post-processing guard for Arabic receipts.

    1. Collect all numbers from المدفوع / الباقي / paid / change lines.
    2. If total_amount equals one of those → reject it and replace with
       a value from a valid total label (or null if none found).
    3. Also clear 'other' if it came from a paid/change line number.
    4. Light sanity: if total_amount < subtotal, prefer null over a wrong value.
    """
    forbidden = _extract_paid_change_values(raw_text)

    current_total = _to_float(parsed.get("total_amount"))
    if current_total is not None and current_total in forbidden:
        # Try to get the real total from valid labels in the raw text
        real_total = _extract_valid_total(raw_text)
        parsed["total_amount"] = real_total  # may be None — that is correct

    # Guard 'other' too
    current_other = _to_float(parsed.get("other"))
    if current_other is not None and current_other in forbidden:
        parsed["other"] = None

    # Sanity: total_amount should not be less than subtotal
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
    Called by router.py.
    """
    generate = load_qwen()

    # First attempt with Arabic-specific system + user prompt
    raw_response = generate(_AR_USER_PROMPT.format(raw_text=raw_text), system=_AR_SYSTEM_PROMPT)
    parsed = _try_parse_json(raw_response)

    # Retry with fix prompt if JSON is broken
    if parsed is None:
        fix_prompt = _FIX_JSON_PROMPT.format(broken_json=raw_response)
        parsed = _try_parse_json(generate(fix_prompt, system=_AR_SYSTEM_PROMPT))

    if parsed is None:
        parsed = {
            "merchant_name": None, "receipt_date": None, "currency": None,
            "subtotal": None, "total_taxes": None, "other": None,
            "total_amount": None, "items": [],
        }

    # Apply Arabic-specific total guards before coercing types
    parsed = _guard_arabic_totals(parsed, raw_text)

    return _coerce_types(parsed, raw_text)
