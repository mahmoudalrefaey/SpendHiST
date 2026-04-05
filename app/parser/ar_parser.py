"""Arabic receipt parser — shares model and helpers with en_parser."""

import re
from typing import Optional

from app.parser.chat_llm import parser_invoke
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
Single JSON object only — no markdown, no extra keys.

Schema:
{"merchant_name":string,"receipt_date":"YYYY-MM-DD"|null,"currency":"XXX"|null,"subtotal":num|null,"total_taxes":num|null,"other":num|null,"total_amount":num|null,"items":[{"item_name":string,"quantity":int>=1,"unit_price":num,"line_total":num}]}

Arabic/mixed receipts:
- merchant_name required (infer top/bottom/Powered by); other unknowns → null.
- Never use numbers from المدفوع/الباقي/المتبقي/الفرق or paid/cash/change/balance for total_amount or other.
- total_amount only from الإجمالي|الاجمالي|الإجمالى|المجموع|Total|Grand Total.
- other: tips/service/delivery only — not paid/change.
- Item price: if ambiguous, choose unit vs line so Σ line_totals matches subtotal/إجمالي.
- Exclude totals, tax, payment lines from items. Currency: ج.م/LE/جنيه→EGP; $€£ as usual.

"""

_AR_USER_PROMPT = """\
<<<
{raw_text}
>>>
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
    user_prompt = _AR_USER_PROMPT.format(raw_text=raw_text)
    raw_response = parser_invoke(user_prompt, system_prompt=_AR_SYSTEM_PROMPT)
    parsed = _try_parse_json(raw_response)

    if parsed is None:
        fix_prompt = _FIX_JSON_PROMPT.format(broken_json=raw_response)
        parsed = _try_parse_json(
            parser_invoke(fix_prompt, system_prompt=_AR_SYSTEM_PROMPT)
        )

    if parsed is None:
        parsed = {
            "merchant_name": None, "receipt_date": None, "currency": None,
            "subtotal": None, "total_taxes": None, "other": None,
            "total_amount": None, "items": [],
        }

    parsed = _guard_arabic_totals(parsed, raw_text)
    return _coerce_types(parsed, raw_text)
