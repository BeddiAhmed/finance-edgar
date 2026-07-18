# Equity Research — Fundamental Slice (US equities, EDGAR)

A single-ticker vertical slice: **pull → normalize → ratios → valuation → report**,
built on the SEC EDGAR XBRL APIs (free, official). Personal-research scope.

## Setup
```bash
pip install -r requirements.txt
export SEC_CONTACT="Your Name your@email.com"   # SEC requires a contact UA or you get 403'd
```

## Run
```bash
python analyze.py AAPL                  # live: fetch from EDGAR, price from yfinance
python analyze.py AAPL --price 195.00   # live fundamentals, manual price
python analyze.py --facts-file fixtures/AAPL_facts.json --ticker AAPL --price 195.00  # offline demo
```

## Files
| file | role |
|------|------|
| `edgar_client.py` | ticker→CIK, company-facts fetch, disk cache, polite rate limiting |
| `normalize.py`    | **the core** — maps messy XBRL tags → canonical annual frame |
| `ratios.py`       | profitability / leverage / liquidity / efficiency + Piotroski F-score |
| `valuation.py`    | multiples, forward DCF, reverse DCF (implied growth) |
| `analyze.py`      | orchestrator + report |
| `build_fixture.py`| generates the offline test fixture |

## Design notes
- **Caching**: every EDGAR response is cached under `.cache/`, so iteration hits zero network.
- **Normalization** is where the real work is. `CONCEPT_MAP` lists candidate tags in
  priority order per concept; we keep only 10-K / fp=FY facts and take the latest-filed
  value per fiscal year. Add a ticker that fails and you'll usually just add one tag alias.
- **Point-in-time**: we currently take latest-filed (cleanest *current* view). The `filed`
  date is preserved per fact, so switching to as-of-date selection (for bias-free backtests
  in the quant pillar later) is a small change in `normalize._extract_one`.
- **Reverse-DCF** is the most useful valuation output: it solves for the FCF growth the
  current price implies, rather than asking you to guess a fair value.

## Verified
The full pipeline was run against an Apple-like FY2020–2023 fixture and produces correct
financials, ratios, F-score, multiples, and reverse-DCF. Live EDGAR + yfinance calls run
on your machine (they're network-blocked in the build sandbox).

## Natural next steps
1. Peer comparables — run N tickers, rank on the same ratios.
2. Multiples vs. a company's *own* history (z-score how cheap/expensive it is now).
3. AI layer — pull the 10-K via `get_submissions`, summarize MD&A / risk factors,
   flag where narrative diverges from the numbers.
