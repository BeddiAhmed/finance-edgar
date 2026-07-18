"""
valuation.py
------------
Valuation on top of the canonical frame. Needs a current price + shares to
compute market-based multiples; everything else comes from EDGAR.

Price source is pluggable:
  - get_price() tries yfinance if installed and online,
  - otherwise pass price explicitly (offline / testing).

The reverse-DCF is the most useful piece: instead of guessing a fair value,
it solves for the FCF growth rate the *current* price is implying, so you can
judge whether the market's embedded expectation is reasonable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def get_price(ticker: str) -> float | None:
    """Best-effort latest close via yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist):
            return float(hist["Close"].iloc[-1])
    except Exception as e:  # offline, not installed, or rate-limited
        print(f"  [info] price fetch failed ({e}); pass price= manually.")
    return None


def current_multiples(df: pd.DataFrame, price: float,
                      shares: float | None = None) -> dict:
    """Trailing multiples using the latest fiscal year's figures."""
    latest = df.iloc[-1]
    if shares is None:
        shares = latest.get("shares_outstanding") or latest.get("shares_diluted")
    if not shares or np.isnan(shares):
        raise ValueError("Need shares outstanding to compute multiples.")

    market_cap = price * shares
    debt = float(latest.get("total_debt", 0) or 0)
    cash = float(latest.get("cash", 0) or 0)
    ev = market_cap + debt - cash

    ni = latest.get("net_income")
    rev = latest.get("revenue")
    equity = latest.get("equity")
    op = latest.get("operating_income")
    fcf = latest.get("free_cash_flow")

    out = {
        "price": price,
        "shares": shares,
        "market_cap": market_cap,
        "enterprise_value": ev,
        "pe": market_cap / ni if ni else np.nan,
        "ps": market_cap / rev if rev else np.nan,
        "pb": market_cap / equity if equity else np.nan,
        "ev_ebit": ev / op if op else np.nan,
        "fcf_yield": fcf / market_cap if fcf else np.nan,
    }
    return out


def reverse_dcf(price: float, shares: float, base_fcf: float,
                discount_rate: float = 0.09, years: int = 10,
                terminal_growth: float = 0.025) -> float:
    """Solve for the constant FCF growth rate implied by the current price.

    Two-stage model: `years` of growth at g, then a Gordon terminal value.
    Returns the implied annual growth g (e.g. 0.08 == 8%).
    """
    market_cap = price * shares

    def pv(g: float) -> float:
        total = 0.0
        fcf = base_fcf
        for t in range(1, years + 1):
            fcf *= (1 + g)
            total += fcf / (1 + discount_rate) ** t
        terminal_fcf = fcf * (1 + terminal_growth)
        tv = terminal_fcf / (discount_rate - terminal_growth)
        total += tv / (1 + discount_rate) ** years
        return total

    # Bisection on g in [-20%, +60%]
    lo, hi = -0.20, 0.60
    for _ in range(100):
        mid = (lo + hi) / 2
        if pv(mid) < market_cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def forward_dcf(base_fcf: float, growth: float, shares: float,
                discount_rate: float = 0.09, years: int = 10,
                terminal_growth: float = 0.025) -> float:
    """Intrinsic value per share for an assumed FCF growth rate."""
    total, fcf = 0.0, base_fcf
    for t in range(1, years + 1):
        fcf *= (1 + growth)
        total += fcf / (1 + discount_rate) ** t
    terminal_fcf = fcf * (1 + terminal_growth)
    tv = terminal_fcf / (discount_rate - terminal_growth)
    total += tv / (1 + discount_rate) ** years
    return total / shares
