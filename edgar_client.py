"""
edgar_client.py
---------------
Thin client over the SEC EDGAR REST APIs (data.sec.gov / www.sec.gov).

Endpoints used:
  - https://www.sec.gov/files/company_tickers.json        (ticker -> CIK map)
  - https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json  (all XBRL facts)
  - https://data.sec.gov/submissions/CIK##########.json   (filing metadata; for the AI layer later)

SEC rules to stay un-blocked:
  - You MUST send a descriptive User-Agent that includes a contact email.
  - Keep requests to <= ~10/sec. We cache to disk so repeat runs hit zero network.

Set your contact once via env var:  export SEC_CONTACT="Your Name your@email.com"
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

CACHE_DIR = Path(os.environ.get("EDGAR_CACHE", ".cache"))
CACHE_DIR.mkdir(exist_ok=True)

_CONTACT = os.environ.get("SEC_CONTACT", "").strip()
_HEADERS = {
    "User-Agent": _CONTACT or "equity-research-tool contact-unset@example.com",
    "Accept-Encoding": "gzip, deflate",
}

_LAST_CALL = 0.0
_MIN_INTERVAL = 0.12  # seconds between calls (~8/sec, safely under SEC's limit)


def _throttle() -> None:
    global _LAST_CALL
    wait = _MIN_INTERVAL - (time.time() - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.time()


def _get(url: str, cache_key: str, max_age_hours: float = 24.0) -> dict:
    """GET JSON with a simple on-disk cache keyed by `cache_key`."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        age_h = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_h < max_age_hours:
            return json.loads(cache_file.read_text())

    if not _CONTACT:
        print("  [warn] SEC_CONTACT env var not set. SEC may 403 you. "
              'Set: export SEC_CONTACT="Your Name your@email.com"')

    _throttle()
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data))
    return data


def resolve_cik(ticker: str) -> tuple[str, str]:
    """Return (zero-padded 10-digit CIK, official entity name) for a ticker."""
    ticker = ticker.upper().strip()
    data = _get("https://www.sec.gov/files/company_tickers.json",
                cache_key="company_tickers", max_age_hours=24 * 7)
    for row in data.values():
        if row["ticker"].upper() == ticker:
            return str(row["cik_str"]).zfill(10), row["title"]
    raise ValueError(f"Ticker {ticker!r} not found in SEC ticker map.")


def get_company_facts(cik: str) -> dict:
    """Fetch the full XBRL company-facts blob for a 10-digit CIK."""
    cik = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    return _get(url, cache_key=f"facts_{cik}")


def get_submissions(cik: str) -> dict:
    """Filing metadata (form types, dates, accession numbers, document URLs)."""
    cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    return _get(url, cache_key=f"subs_{cik}")


def load_facts_from_file(path: str) -> dict:
    """Load a previously-saved company-facts JSON (offline / testing path)."""
    return json.loads(Path(path).read_text())
