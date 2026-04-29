"""
Currency normalization — every collector converts spend to USD before
writing to BigQuery.

SAR is officially pegged to USD at 1 USD = 3.75 SAR (Saudi Central Bank,
since June 1986). AED and KWD are similarly pegged. Other currencies
pass through with a warning — the dashboard assumes USD.

If the native currency is unknown (None / empty), we default to SAR
because the business is Saudi-based; this is the safest assumption
and can always be overridden by the caller.
"""
from __future__ import annotations

# Central config is the source of truth for the SAR peg and default currency.
# Importing late-safely: we only read constants, never circular logic.
try:
    from config import USD_SAR_PEG, DEFAULT_NATIVE_CURRENCY
except Exception:   # allow this module to stand alone in tests
    USD_SAR_PEG = 3.75
    DEFAULT_NATIVE_CURRENCY = "SAR"

# 1 unit of native -> USD
PEG_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "SAR": 1 / USD_SAR_PEG,   # pegged — see config.USD_SAR_PEG
    "AED": 1 / 3.6725,        # ≈ 0.272294  (pegged)
    "KWD": 3.25,              # floating peg vs basket — approx as of 2026
    "BHD": 1 / 0.376,         # ≈ 2.659574  (pegged)
    "QAR": 1 / 3.64,          # ≈ 0.274725  (pegged)
    "OMR": 1 / 0.3845,        # ≈ 2.600780  (pegged)
    "EGP": 1 / 49.0,          # floating — approx; override if precision matters
    "EUR": 1.08,              # floating — approx; override if precision matters
    "GBP": 1.27,              # floating — approx; override if precision matters
}

DEFAULT_NATIVE = DEFAULT_NATIVE_CURRENCY   # backwards-compat alias


def to_usd(amount: float | int | None, native_currency: str | None) -> float:
    """Convert `amount` in `native_currency` to USD.

    Unknown currencies pass through unchanged with a printed warning so
    you notice and can add the pair to PEG_RATES_TO_USD.
    """
    if amount in (None, 0, 0.0):
        return 0.0
    cur  = (native_currency or DEFAULT_NATIVE).upper()
    rate = PEG_RATES_TO_USD.get(cur)
    if rate is None:
        print(f"[currency] WARNING unknown currency '{cur}' — passing through as USD")
        return float(amount)
    return float(amount) * rate


def normalize_currency(cur: str | None) -> str:
    """Normalize a currency code: uppercase, default to SAR if blank."""
    return (cur or DEFAULT_NATIVE).upper()
