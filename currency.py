"""
Live currency conversion so prices (stored in USD in the database) can be
shown in the user's own currency — INR, EUR, GBP, JPY, etc.

Uses https://open.er-api.com — a free, no-API-key exchange rate API.
Rates are cached in memory for an hour so we don't hit the API on every
single page render.
"""
import time
import requests

RATES_URL = "https://open.er-api.com/v6/latest/USD"
CACHE_TTL_SECONDS = 3600

_cache = {"rates": None, "fetched_at": 0}

SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$", "label": "US Dollar"},
    "INR": {"symbol": "₹", "label": "Indian Rupee"},
    "EUR": {"symbol": "€", "label": "Euro"},
    "GBP": {"symbol": "£", "label": "British Pound"},
    "JPY": {"symbol": "¥", "label": "Japanese Yen"},
    "AUD": {"symbol": "A$", "label": "Australian Dollar"},
    "CAD": {"symbol": "C$", "label": "Canadian Dollar"},
    "SGD": {"symbol": "S$", "label": "Singapore Dollar"},
    "AED": {"symbol": "AED", "label": "UAE Dirham"},
    "BRL": {"symbol": "R$", "label": "Brazilian Real"},
}

# Fallback rates (approximate) used only if the live API is unreachable —
# keeps the site fully usable offline / without internet access.
FALLBACK_RATES = {
    "USD": 1.0, "INR": 83.0, "EUR": 0.92, "GBP": 0.79, "JPY": 151.0,
    "AUD": 1.52, "CAD": 1.36, "SGD": 1.34, "AED": 3.67, "BRL": 5.1,
}


def _get_rates():
    now = time.time()
    if _cache["rates"] and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
        return _cache["rates"]

    try:
        resp = requests.get(RATES_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates", {})
        if rates:
            _cache["rates"] = rates
            _cache["fetched_at"] = now
            return rates
    except Exception:
        pass

    # live fetch failed — fall back to static approximate rates
    return FALLBACK_RATES


def convert(amount, currency_code, from_currency="USD"):
    """Converts `amount` (in `from_currency`) into `currency_code`.
    Defaults to from_currency='USD' for backward compatibility with the
    older rows/callers that always stored USD."""
    if amount is None:
        return None
    if currency_code not in SUPPORTED_CURRENCIES:
        currency_code = "USD"
    if from_currency not in SUPPORTED_CURRENCIES:
        from_currency = "USD"

    if from_currency == currency_code:
        return amount

    rates = _get_rates()
    from_rate = rates.get(from_currency, FALLBACK_RATES.get(from_currency, 1.0))
    to_rate = rates.get(currency_code, FALLBACK_RATES.get(currency_code, 1.0))

    amount_in_usd = amount / from_rate
    return amount_in_usd * to_rate


def format_price(amount, currency_code, from_currency="USD"):
    if amount is None:
        return "Unavailable"
    converted = convert(amount, currency_code, from_currency)
    symbol = SUPPORTED_CURRENCIES.get(currency_code, {"symbol": "$"})["symbol"]

    # Yen conventionally has no decimal places
    if currency_code == "JPY":
        return f"{symbol}{converted:,.0f}"
    return f"{symbol}{converted:,.2f}"
