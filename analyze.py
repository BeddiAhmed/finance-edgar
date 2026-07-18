"""
analyze.py
----------
End-to-end vertical slice for ONE ticker:
  pull (EDGAR) -> normalize -> ratios + F-score -> valuation -> report.

Usage:
  export SEC_CONTACT="Your Name your@email.com"
  python analyze.py AAPL
  python analyze.py AAPL --price 195.00
  python analyze.py --facts-file fixtures/AAPL_facts.json --ticker AAPL --price 195.00
"""

from __future__ import annotations

import argparse

import pandas as pd

import edgar_client as ec
import normalize
import ratios as rt
import valuation as val

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 30)


def _fmt_money(x: float) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(x) >= div:
            return f"${x / div:,.2f}{unit}"
    return f"${x:,.0f}"


def run(ticker: str, price: float | None = None, facts_file: str | None = None):
    # 1. PULL
    if facts_file:
        facts = ec.load_facts_from_file(facts_file)
        name = facts.get("entityName", ticker)
    else:
        cik, name = ec.resolve_cik(ticker)
        print(f"Resolved {ticker} -> CIK {cik} ({name})")
        facts = ec.get_company_facts(cik)

    # 2. NORMALIZE
    frame = normalize.build_annual_frame(facts)

    # 3. RATIOS + QUALITY
    ratio_df = rt.compute_ratios(frame)
    fscore = rt.piotroski_f_score(frame)

    # 4. VALUATION
    if price is None and not facts_file:
        price = val.get_price(ticker)

    print("\n" + "=" * 72)
    print(f"  {name}  ({ticker.upper()})  -  fundamental snapshot")
    print("=" * 72)

    # --- Financials (latest 4 years, in readable units) ---
    show_cols = [c for c in ["revenue", "gross_profit", "operating_income",
                             "net_income", "operating_cash_flow",
                             "free_cash_flow", "total_assets", "equity",
                             "total_debt"] if c in frame.columns]
    fin = frame[show_cols].tail(4).T.map(_fmt_money)
    print("\nKEY FINANCIALS")
    print(fin.to_string())

    # --- Ratios (latest 4 years) ---
    pct = ["gross_margin", "operating_margin", "net_margin", "fcf_margin",
           "roe", "roa", "roic_approx", "fcf_yield"]
    rr = ratio_df.tail(4).T
    fmt = {}
    for idx in rr.index:
        if idx in pct:
            fmt[idx] = rr.loc[idx].map(lambda v: f"{v*100:,.1f}%" if pd.notna(v) else "n/a")
        else:
            fmt[idx] = rr.loc[idx].map(lambda v: f"{v:,.2f}" if pd.notna(v) else "n/a")
    print("\nRATIOS")
    print(pd.DataFrame(fmt).T.to_string())

    # --- Quality ---
    print("\nQUALITY")
    fs = fscore.dropna()
    if len(fs):
        latest_fs = int(fs.iloc[-1])
        print(f"  Piotroski F-score (latest): {latest_fs}/9  "
              f"({'strong' if latest_fs >= 7 else 'weak' if latest_fs <= 3 else 'middling'})")
        print(f"  F-score history: {dict(fs.astype(int))}")

    # --- Valuation ---
    print("\nVALUATION")
    if price:
        try:
            m = val.current_multiples(frame, price)
            print(f"  Price {m['price']:.2f}  |  Mkt cap {_fmt_money(m['market_cap'])}"
                  f"  |  EV {_fmt_money(m['enterprise_value'])}")
            print(f"  P/E {m['pe']:.1f}   P/S {m['ps']:.1f}   P/B {m['pb']:.1f}"
                  f"   EV/EBIT {m['ev_ebit']:.1f}   FCF yield {m['fcf_yield']*100:.1f}%")

            base_fcf = float(frame["free_cash_flow"].iloc[-1])
            implied_g = val.reverse_dcf(price, m["shares"], base_fcf)
            print(f"\n  Reverse-DCF: at ${price:.2f}, the market is pricing in "
                  f"~{implied_g*100:.1f}% annual FCF growth")
            print(f"  (10y two-stage, 9% discount, 2.5% terminal). "
                  f"Judge that against the {ratio_df['fcf_margin'].iloc[-1]*100:.0f}% "
                  f"FCF margin and history above.")
        except Exception as e:
            print(f"  [valuation skipped: {e}]")
    else:
        print("  No price available - pass --price to enable multiples & reverse-DCF.")

    print("\n" + "=" * 72)
    return frame, ratio_df, fscore


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker", nargs="?", help="e.g. AAPL")
    p.add_argument("--ticker", dest="ticker_opt", help="ticker when using --facts-file")
    p.add_argument("--price", type=float, default=None)
    p.add_argument("--facts-file", default=None, help="offline company-facts JSON")
    args = p.parse_args()

    ticker = args.ticker or args.ticker_opt
    if not ticker:
        p.error("provide a ticker (positional) or --ticker with --facts-file")
    run(ticker, price=args.price, facts_file=args.facts_file)


if __name__ == "__main__":
    main()
