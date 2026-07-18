"""
normalize.py
------------
The hard part of fundamentals tooling: turning EDGAR's inconsistent XBRL tags
into a clean, canonical, annual time series.

Two problems this solves:
  1. Tag drift   - the same economic concept is tagged differently across
                   companies/years (e.g. Revenues vs RevenueFromContractWith...).
                   CONCEPT_MAP lists candidate tags in priority order; we take
                   the first that has data.
  2. Period mess - facts mix annual/quarterly, durations vs instants, and
                   multiple restatements of the same period. We keep only
                   fiscal-year (10-K, fp=FY) figures and, for each fiscal year,
                   take the most-recently-filed value (current restated view).

NOTE on point-in-time: taking the latest-filed value gives the cleanest *current*
picture of history, which is what you want for ratio analysis. For bias-free
backtesting you'd instead pick the value as-of a given date using `filed`. The
`filed` date is preserved per period to make that upgrade easy later.
"""

from __future__ import annotations

import pandas as pd

# Canonical concept -> ordered candidate us-gaap tags, plus the fact "kind".
#   kind="duration" -> income statement / cash flow (entry has start & end)
#   kind="instant"  -> balance sheet (entry has end only)
#   unit: "USD" (default), "shares", or "USD/shares"
CONCEPT_MAP: dict[str, dict] = {
    # --- Income statement (duration) ---
    "revenue": {"kind": "duration", "tags": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]},
    "cogs": {"kind": "duration", "tags": [
        "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]},
    "gross_profit": {"kind": "duration", "tags": ["GrossProfit"]},
    "operating_income": {"kind": "duration", "tags": [
        "OperatingIncomeLoss"]},
    "interest_expense": {"kind": "duration", "tags": [
        "InterestExpense", "InterestExpenseDebt",
        "InterestAndDebtExpense"]},
    "net_income": {"kind": "duration", "tags": ["NetIncomeLoss"]},
    "eps_diluted": {"kind": "duration", "unit": "USD/shares", "tags": [
        "EarningsPerShareDiluted"]},
    "eps_basic": {"kind": "duration", "unit": "USD/shares", "tags": [
        "EarningsPerShareBasic"]},
    "shares_diluted": {"kind": "duration", "unit": "shares", "tags": [
        "WeightedAverageNumberOfDilutedSharesOutstanding"]},

    # --- Balance sheet (instant) ---
    "total_assets": {"kind": "instant", "tags": ["Assets"]},
    "total_liabilities": {"kind": "instant", "tags": ["Liabilities"]},
    "equity": {"kind": "instant", "tags": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]},
    "current_assets": {"kind": "instant", "tags": ["AssetsCurrent"]},
    "current_liabilities": {"kind": "instant", "tags": ["LiabilitiesCurrent"]},
    "cash": {"kind": "instant", "tags": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]},
    "inventory": {"kind": "instant", "tags": ["InventoryNet"]},
    "receivables": {"kind": "instant", "tags": [
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]},
    "long_term_debt": {"kind": "instant", "tags": [
        "LongTermDebtNoncurrent", "LongTermDebt"]},
    "short_term_debt": {"kind": "instant", "tags": [
        "LongTermDebtCurrent", "DebtCurrent",
        "ShortTermBorrowings"]},
    "shares_outstanding": {"kind": "instant", "unit": "shares", "tags": [
        "CommonStockSharesOutstanding"]},

    # --- Cash flow (duration) ---
    "operating_cash_flow": {"kind": "duration", "tags": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]},
    "capex": {"kind": "duration", "tags": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets"]},
    "dividends_paid": {"kind": "duration", "tags": [
        "PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]},
}

_DEI_TAGS = {"shares_outstanding": ["EntityCommonStockSharesOutstanding"]}


def _unit_key(unit: str) -> str:
    return {"USD": "USD", "shares": "shares", "USD/shares": "USD/shares"}[unit]


def _extract_one(facts: dict, spec: dict, concept: str) -> dict[int, dict]:
    """Return {fiscal_year: {'val':..., 'filed':...}} for the first tag with data."""
    unit = spec.get("unit", "USD")
    ukey = _unit_key(unit)
    kind = spec["kind"]

    namespaces = [("us-gaap", spec["tags"])]
    if concept in _DEI_TAGS:
        namespaces.append(("dei", _DEI_TAGS[concept]))

    for ns, tags in namespaces:
        ns_facts = facts.get("facts", {}).get(ns, {})
        for tag in tags:
            node = ns_facts.get(tag)
            if not node:
                continue
            entries = node.get("units", {}).get(ukey, [])
            picked: dict[int, dict] = {}
            for e in entries:
                if e.get("form", "") not in ("10-K", "10-K/A"):
                    continue
                if e.get("fp") != "FY":
                    continue
                has_start = "start" in e
                if kind == "duration" and not has_start:
                    continue
                if kind == "instant" and has_start:
                    continue
                fy = e.get("fy")
                if fy is None:
                    continue
                # Keep the most recently filed value for each fiscal year.
                prev = picked.get(fy)
                if prev is None or e.get("filed", "") > prev["filed"]:
                    picked[fy] = {"val": e["val"], "filed": e.get("filed", "")}
            if picked:
                return picked
    return {}


def build_annual_frame(facts: dict) -> pd.DataFrame:
    """Build a tidy annual DataFrame: index = fiscal year, columns = canonical concepts.

    Also returns a parallel `*_filed` is NOT included to keep the frame clean;
    filed dates are dropped here but available via `_extract_one` if needed.
    """
    series: dict[str, pd.Series] = {}
    for concept, spec in CONCEPT_MAP.items():
        picked = _extract_one(facts, spec, concept)
        if picked:
            series[concept] = pd.Series({fy: d["val"] for fy, d in picked.items()})

    if not series:
        raise ValueError("No recognized annual concepts found in facts.")

    df = pd.DataFrame(series).sort_index()
    df.index.name = "fiscal_year"

    # Derived fields where a direct tag was missing.
    if "gross_profit" not in df and {"revenue", "cogs"} <= set(df.columns):
        df["gross_profit"] = df["revenue"] - df["cogs"]
    if {"long_term_debt", "short_term_debt"} & set(df.columns):
        df["total_debt"] = df.get("long_term_debt", 0).fillna(0) + \
                           df.get("short_term_debt", 0).fillna(0)
    if {"operating_cash_flow", "capex"} <= set(df.columns):
        # capex is reported as a positive outflow; FCF = OCF - capex
        df["free_cash_flow"] = df["operating_cash_flow"] - df["capex"]

    return df
