from langchain_core.tools import tool
import requests

_BASE = "https://api.frankfurter.dev/v1/latest"


@tool
def currency_tool(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert an amount from one currency to another using Frankfurter API (ECB rates).

    Args:
        amount: Amount to convert (e.g. 100.0).
        from_currency: Source currency code (e.g. USD, EUR).
        to_currency: Target currency code (e.g. EUR, GBP).

    Returns:
        str: Conversion result or error message.
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()
    if from_currency == to_currency:
        return f"{amount} {from_currency} = {amount} {to_currency} (same currency)."
    try:
        r = requests.get(
            _BASE,
            params={"base": from_currency, "symbols": to_currency},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get(to_currency)
        if rate is None:
            return f"Target currency '{to_currency}' not found in API response."
        result = round(amount * rate, 2)
        date = data.get("date", "?")
        return f"{amount} {from_currency} = {result} {to_currency} (rate {date})."
    except requests.RequestException as e:
        return f"Currency conversion failed: {e}"