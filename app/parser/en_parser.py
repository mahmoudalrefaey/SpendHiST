"""
en_parser.py — English receipt parser using Qwen2.5-1.5B-Instruct.

Handles English and Latin-script receipts.
Called by dispatcher.py; do not call directly from the pipeline.
"""

import json
import re
from typing import Optional

import torch

from app.config import HF_TOKEN, PARSER_MODEL

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ═════════════════════════════════════════════════════════════════════════════
#  PROMPTS
# ═════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
You are a receipt parsing engine. You must output valid JSON only that matches \
the provided schema. Do not include explanations, markdown, or extra keys. \
If a value is unknown, use null — EXCEPT merchant_name: it must NEVER be null.

Critical reasoning rules (use internally, never show your reasoning):
- merchant_name is REQUIRED. Always infer it from the receipt text. Look for: \
the store or business name at the top; "Powered by X" or "by X" at the bottom \
(then use "X" as merchant_name); brand name; restaurant or shop name; footer \
logos or text. If only a platform name like "Foodics" appears, use that. \
Never output null for merchant_name.
- Receipts vary widely in layout and language (English/Arabic/mixed).
- Item price columns may represent unit price OR line total.
- You MUST test both interpretations when quantity > 1 appears and choose the one \
that best matches subtotal/total in the receipt.
  Interpretation A: shown price = unit_price, so line_total = qty * shown_price.
  Interpretation B: shown price = line_total, so unit_price = shown_price / qty.
  Sum all line_totals under each interpretation. The one whose sum is closest to \
the receipt subtotal (or total minus taxes) is correct.
- Before finalizing JSON, cross-check:
  * Sum of item line_totals should be close to subtotal (if subtotal exists).
  * subtotal + taxes should be close to total (if both exist).
- If mismatch is large, revise your extraction (especially unit-vs-line price \
interpretation) and re-check.
- Non-item lines (Subtotal, Total, VAT, Tax, Cash, Change, Thank you) must NOT appear as items.
- Dates: normalize to YYYY-MM-DD.
- Currency: detect from symbols/keywords in the receipt text.
  * $ → "USD",
  * € → "EUR",
  * £ → "GBP",
  * EGP, LE, ج.م, جنيه → "EGP"
  * SAR, ر.س, ريال → "SAR"
  * AED, د.إ, درهم → "AED"
  * ₹, Rs, INR → "INR"
  * If no symbol found, use null.
- "other": sum of all extra charges that are NOT items and NOT tax/VAT. \
This includes tips, service charges, delivery fees, gratuity, surcharges, etc. \
If none found, use null.
- Quantity defaults to 1 if not shown. Quantity can be a decimal (weights).

Output: JSON only. No chain-of-thought. No commentary.\
"""

_USER_PROMPT = """\
Extract structured receipt data from the following OCR text.

OCR TEXT:
<<<
{raw_text}
>>>

Rules:
- Output JSON only (no markdown fences, no explanation).
- Follow this schema exactly:
  {{
    "merchant_name": "string (REQUIRED — never null; infer from store name, 'Powered by X', brand, or any business name on the receipt)",
    "receipt_date": "YYYY-MM-DD or null",
    "currency": "3-letter code or null",
    "subtotal": number or null,
    "total_taxes": number or null,
    "other": number or null (tips, service charges, delivery fees, gratuity — NOT items, NOT tax),
    "total_amount": number or null,
    "items": [
      {{
        "item_name": "string",
        "quantity": integer (default 1, must be > 0),
        "unit_price": number (required, compute if needed),
        "line_total": number (required, compute if needed)
      }}
    ]
  }}
- quantity must be a whole integer (round if decimal, minimum 1).
- unit_price and line_total are required for every item. If one is missing, \
compute it from the other: line_total = quantity * unit_price.

- Items: detect qty, description, and shown price for each item line.
- IMPORTANT: The shown "price" in item lines may be unit price OR line total.
  Try both:
    A) line_total = qty * shown_price  (shown_price is unit_price)
    B) line_total = shown_price, unit_price = shown_price / qty  (shown_price is line_total)
  Choose the interpretation whose sum of line_totals aligns best with the \
receipt subtotal or total.
- If totals exist and your computed sum disagrees strongly, revise your \
interpretation and correct the items before outputting.
- Do NOT include summary lines (subtotal, total, tax, payment, etc.) as items.
- merchant_name: REQUIRED. Never use null. Infer from header, footer, "Powered by X", \
or any business/brand name on the receipt.
- Use null for other missing values. Do not invent data.

Return final JSON only.\
"""

_FIX_JSON_PROMPT = """\
The following text was supposed to be valid JSON but has syntax errors.
Fix it and return ONLY the corrected JSON. No explanation, no markdown fences.

Broken JSON:
\"\"\"
{broken_json}
\"\"\"
"""


# ═════════════════════════════════════════════════════════════════════════════
#  MODEL LOADER  (shared singleton — imported by ar_parser too)
# ═════════════════════════════════════════════════════════════════════════════

_client = None


def load_qwen():
    """
    Return a callable:  prompt_str -> response_str.
    Auto-selects local GPU (transformers) or HF Inference API fallback.
    Cached globally so both parsers share the same loaded model.
    """
    global _client
    if _client is not None:
        return _client
    if torch.cuda.is_available():
        _client = _build_local_client()
    else:
        _client = _build_api_client()
    return _client


def _build_local_client():
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(PARSER_MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        PARSER_MODEL,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype="auto",
    ).eval()

    def _generate(prompt: str, system: str = _SYSTEM_PROMPT) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=False,
                temperature=1.0,
            )
        generated = out[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(generated, skip_special_tokens=True)

    return _generate


def _build_api_client():
    from huggingface_hub import InferenceClient

    client = InferenceClient(model=PARSER_MODEL, token=HF_TOKEN or None)

    def _generate(prompt: str, system: str = _SYSTEM_PROMPT) -> str:
        full_prompt = f"[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{prompt} [/INST]"
        return client.text_generation(full_prompt, max_new_tokens=2048, temperature=0.1)

    return _generate


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
    generate = load_qwen()
    prompt = _USER_PROMPT.format(raw_text=raw_text)
    parsed = _try_parse_json(generate(prompt))

    if parsed is None:
        fix_prompt = _FIX_JSON_PROMPT.format(broken_json=generate(prompt))
        parsed = _try_parse_json(generate(fix_prompt))

    if parsed is None:
        parsed = {
            "merchant_name": None, "receipt_date": None, "currency": None,
            "subtotal": None, "total_taxes": None, "other": None,
            "total_amount": None, "items": [],
        }

    return _coerce_types(parsed, raw_text)
