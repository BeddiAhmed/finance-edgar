"""Build a realistic EDGAR company-facts fixture (Apple-like, FY2020-2023)."""
import json
from pathlib import Path

# (val in $millions unless noted). gross_profit intentionally omitted -> tests derivation.
DATA = {
    2020: dict(end="2020-09-26", start="2019-09-29", filed="2020-10-30",
               revenue=274515, cogs=169559, operating_income=66288, net_income=57411,
               interest_expense=2873, eps_diluted=3.28, shares_diluted=17528214000,
               assets=323888, liabilities=258549, equity=65339,
               current_assets=143713, current_liabilities=105392, cash=38016,
               inventory=4061, receivables=16120, long_term_debt=98667,
               short_term_debt=13769, shares_outstanding=16976763000,
               ocf=80674, capex=7309, dividends=14081),
    2021: dict(end="2021-09-25", start="2020-09-27", filed="2021-10-29",
               revenue=365817, cogs=212981, operating_income=108949, net_income=94680,
               interest_expense=2645, eps_diluted=5.61, shares_diluted=16864919000,
               assets=351002, liabilities=287912, equity=63090,
               current_assets=134836, current_liabilities=125481, cash=34940,
               inventory=6580, receivables=26278, long_term_debt=109106,
               short_term_debt=15613, shares_outstanding=16426786000,
               ocf=104038, capex=11085, dividends=14467),
    2022: dict(end="2022-09-24", start="2021-09-26", filed="2022-10-28",
               revenue=394328, cogs=223546, operating_income=119437, net_income=99803,
               interest_expense=2931, eps_diluted=6.11, shares_diluted=16325819000,
               assets=352755, liabilities=302083, equity=50672,
               current_assets=135405, current_liabilities=153982, cash=23646,
               inventory=4946, receivables=28184, long_term_debt=98959,
               short_term_debt=21110, shares_outstanding=15943425000,
               ocf=122151, capex=10708, dividends=14841),
    2023: dict(end="2023-09-30", start="2022-09-25", filed="2023-11-03",
               revenue=383285, cogs=214137, operating_income=114301, net_income=96995,
               interest_expense=3933, eps_diluted=6.13, shares_diluted=15812547000,
               assets=352583, liabilities=290437, equity=62146,
               current_assets=143566, current_liabilities=145308, cash=29965,
               inventory=6331, receivables=29508, long_term_debt=95281,
               short_term_debt=15807, shares_outstanding=15550061000,
               ocf=110543, capex=10959, dividends=15025),
}

# canonical key -> (namespace, tag, unit, kind, scale)
M = 1_000_000
TAGMAP = {
    "revenue": ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", "dur", M),
    "cogs": ("us-gaap", "CostOfGoodsAndServicesSold", "USD", "dur", M),
    "operating_income": ("us-gaap", "OperatingIncomeLoss", "USD", "dur", M),
    "net_income": ("us-gaap", "NetIncomeLoss", "USD", "dur", M),
    "interest_expense": ("us-gaap", "InterestExpense", "USD", "dur", M),
    "eps_diluted": ("us-gaap", "EarningsPerShareDiluted", "USD/shares", "dur", 1),
    "shares_diluted": ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "dur", 1),
    "ocf": ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD", "dur", M),
    "capex": ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD", "dur", M),
    "dividends": ("us-gaap", "PaymentsOfDividendsCommonStock", "USD", "dur", M),
    "assets": ("us-gaap", "Assets", "USD", "inst", M),
    "liabilities": ("us-gaap", "Liabilities", "USD", "inst", M),
    "equity": ("us-gaap", "StockholdersEquity", "USD", "inst", M),
    "current_assets": ("us-gaap", "AssetsCurrent", "USD", "inst", M),
    "current_liabilities": ("us-gaap", "LiabilitiesCurrent", "USD", "inst", M),
    "cash": ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD", "inst", M),
    "inventory": ("us-gaap", "InventoryNet", "USD", "inst", M),
    "receivables": ("us-gaap", "AccountsReceivableNetCurrent", "USD", "inst", M),
    "long_term_debt": ("us-gaap", "LongTermDebtNoncurrent", "USD", "inst", M),
    "short_term_debt": ("us-gaap", "LongTermDebtCurrent", "USD", "inst", M),
    "shares_outstanding": ("us-gaap", "CommonStockSharesOutstanding", "shares", "inst", 1),
}

facts = {"cik": 320193, "entityName": "Apple Inc.", "facts": {"us-gaap": {}}}

for key, (ns, tag, unit, kind, scale) in TAGMAP.items():
    entries = []
    for fy, d in DATA.items():
        e = {"end": d["end"], "val": round(d[key] * scale, 2),
             "accn": f"000-{fy}", "fy": fy, "fp": "FY", "form": "10-K",
             "filed": d["filed"]}
        if kind == "dur":
            e["start"] = d["start"]
        entries.append(e)
    facts["facts"][ns].setdefault(tag, {"label": key, "units": {}})["units"][unit] = entries

out = Path("fixtures"); out.mkdir(exist_ok=True)
(out / "AAPL_facts.json").write_text(json.dumps(facts, indent=1))
print(f"wrote fixtures/AAPL_facts.json with {len(TAGMAP)} tags x {len(DATA)} years")
