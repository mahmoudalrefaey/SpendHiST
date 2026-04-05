from __future__ import annotations

import requests
from langchain_core.tools import tool

from app.config import CURRENCYFREAKS_API_KEY

_LATEST_URL = "https://api.currencyfreaks.com/v2.0/rates/latest"


@tool
def currency_tool(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert an amount from one currency to another using CurrencyFreaks (USD-based rates).

    Args:
        amount: Amount to convert (e.g. 100.0).
        from_currency: Source currency code (e.g. USD, EUR, EGP).
        to_currency: Target currency code (e.g. EUR, EGP, GBP).

    Returns:
        str: Conversion result or error message.
    """
    if not CURRENCYFREAKS_API_KEY:
        return (
            "Currency conversion unavailable: set CURRENCYFREAKS_API_KEY in .env "
            "(sign up at currencyfreaks.com)."
        )

    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()
    if from_currency == to_currency:
        return f"{amount} {from_currency} = {amount} {to_currency} (same currency)."

    try:
        symbols = ",".join(sorted({from_currency, to_currency, "USD"}))
        r = requests.get(
            _LATEST_URL,
            params={
                "apikey": CURRENCYFREAKS_API_KEY,
                "symbols": symbols,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        rates_raw = data.get("rates") or {}
        rates = {k: float(v) for k, v in rates_raw.items()}

        r_from = rates.get(from_currency)
        r_to = rates.get(to_currency)
        if r_from is None or r_from == 0:
            return f"Source currency '{from_currency}' not found or invalid in API response."
        if r_to is None:
            return f"Target currency '{to_currency}' not found in API response."

        result = round(amount * (r_to / r_from), 2)
        date = data.get("date", "?")
        return f"{amount} {from_currency} = {result} {to_currency} (rate as of {date})."
    except requests.RequestException as e:
        return f"Currency conversion failed: {e}"