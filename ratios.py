"""
ratios.py
---------
Compute fundamental ratios as annual time series from the canonical frame
produced by normalize.build_annual_frame().

Everything is defensive: a ratio is only computed when its inputs exist,
otherwise the column is left as NaN rather than raising.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df.columns else pd.Series(np.nan, index=df.index)


def _avg(s: pd.Series) -> pd.Series:
    """Average of this year and prior year (for balance-sheet denominators)."""
    return (s + s.shift(1)) / 2


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    rev = _safe(df, "revenue")
    gp = _safe(df, "gross_profit")
    op = _safe(df, "operating_income")
    ni = _safe(df, "net_income")
    assets = _safe(df, "total_assets")
    equity = _safe(df, "equity")
    debt = _safe(df, "total_debt")
    cur_a = _safe(df, "current_assets")
    cur_l = _safe(df, "current_liabilities")
    inv = _safe(df, "inventory")
    rec = _safe(df, "receivables")
    cogs = _safe(df, "cogs")
    ocf = _safe(df, "operating_cash_flow")
    fcf = _safe(df, "free_cash_flow")
    int_exp = _safe(df, "interest_expense")
    cash = _safe(df, "cash")

    r = pd.DataFrame(index=df.index)

    # Profitability (margins)
    r["gross_margin"] = gp / rev
    r["operating_margin"] = op / rev
    r["net_margin"] = ni / rev
    r["fcf_margin"] = fcf / rev

    # Returns (use average balances)
    r["roe"] = ni / _avg(equity)
    r["roa"] = ni / _avg(assets)
    # ROIC ~ NOPAT / invested capital; approximate NOPAT with op income (pre-tax-adj omitted)
    invested = _avg(debt.fillna(0) + equity)
    r["roic_approx"] = op / invested

    # Leverage / solvency
    r["debt_to_equity"] = debt / equity
    r["debt_to_assets"] = debt / assets
    r["interest_coverage"] = op / int_exp.replace(0, np.nan)

    # Liquidity
    r["current_ratio"] = cur_a / cur_l
    r["quick_ratio"] = (cur_a - inv) / cur_l

    # Efficiency
    r["asset_turnover"] = rev / _avg(assets)
    r["inventory_turnover"] = cogs / _avg(inv)
    r["days_sales_outstanding"] = 365 * _avg(rec) / rev
    r["cash_conversion"] = ocf / ni  # >1 is healthy (earnings backed by cash)

    return r


def piotroski_f_score(df: pd.DataFrame) -> pd.Series:
    """Piotroski F-score (0-9). High score = improving fundamental quality.

    9 binary tests across profitability, leverage/liquidity, and efficiency,
    each comparing the current year to the prior year.
    """
    ni = _safe(df, "net_income")
    assets = _safe(df, "total_assets")
    ocf = _safe(df, "operating_cash_flow")
    debt = _safe(df, "long_term_debt")
    cur_a = _safe(df, "current_assets")
    cur_l = _safe(df, "current_liabilities")
    shares = _safe(df, "shares_diluted")
    gp = _safe(df, "gross_profit")
    rev = _safe(df, "revenue")

    roa = ni / _avg(assets)
    score = pd.Series(0, index=df.index, dtype="float")

    # --- Profitability (4) ---
    score += (ni > 0).astype(int)                                  # positive net income
    score += (ocf > 0).astype(int)                                 # positive operating cash flow
    score += (roa > roa.shift(1)).astype(int)                      # rising ROA
    score += (ocf > ni).astype(int)                                # accruals: CFO > NI

    # --- Leverage, liquidity, dilution (3) ---
    lev = debt / _avg(assets)
    score += (lev < lev.shift(1)).astype(int)                      # falling leverage
    curr = cur_a / cur_l
    score += (curr > curr.shift(1)).astype(int)                    # rising current ratio
    score += (shares <= shares.shift(1) * 1.001).astype(int)       # no meaningful dilution

    # --- Operating efficiency (2) ---
    gm = gp / rev
    score += (gm > gm.shift(1)).astype(int)                        # rising gross margin
    at = rev / _avg(assets)
    score += (at > at.shift(1)).astype(int)                        # rising asset turnover

    score.iloc[0] = np.nan  # first year has no prior comparison
    score.name = "piotroski_f"
    return score
