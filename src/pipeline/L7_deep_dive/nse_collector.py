"""
NSE API collector — fetches corporate actions and material announcements.

Source: NSE corporate APIs (no API key, session-cookie required).
NSE blocks raw requests; a session warm-up GET is required before data calls.

Returns dicts with: corporate_actions, recent_filings.
Returns empty lists on failure — NSE API is less critical than yfinance/screener.
"""

from __future__ import annotations

import re

import requests

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_DEFAULT_MATERIAL_TYPES = {
    "board meeting", "financial results", "dividend", "buyback",
    "change in director", "change in management", "merger", "acquisition",
    "demerger", "rights issue", "bonus", "split", "open offer",
    "delisting", "credit rating", "order won", "loss of order",
    "outcome of board meeting", "press release",
}


def make_session() -> requests.Session:
    """Create an NSE session with cookies warmed up. Re-use across multiple fetch() calls."""
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


def _symbol(ticker: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", ticker.upper().strip())


def fetch(
    ticker: str,
    session: requests.Session,
    max_actions: int = 3,
    max_filings: int = 2,
    material_types: set[str] | None = None,
) -> dict:
    """
    Fetch corporate actions and material filings for an NSE ticker.
    Returns {"corporate_actions": [...], "recent_filings": [...]}.
    Returns empty lists on any API failure — never raises.
    material_types: keywords loaded from l7_config.yaml; falls back to built-in defaults.
    """
    _types          = material_types or _DEFAULT_MATERIAL_TYPES
    symbol          = _symbol(ticker)
    corporate_acts  = []
    recent_filings  = []

    # Corporate actions (dividends, bonus, splits, buybacks)
    try:
        r = session.get(
            "https://www.nseindia.com/api/corporates-corporateActions",
            params={"index": "equities", "symbol": symbol},
            timeout=15,
        )
        if r.status_code == 200:
            for item in r.json():
                purpose = item.get("purpose", "")
                corporate_acts.append({
                    "type":    purpose,
                    "ex_date": item.get("exDate") or item.get("ex_date", ""),
                    "amount":  item.get("faceVal") or item.get("dividendAmount"),
                    "purpose": purpose,
                })
                if len(corporate_acts) >= max_actions:
                    break
    except Exception:
        pass

    # Material announcements (board meetings, results, management changes)
    try:
        r = session.get(
            "https://www.nseindia.com/api/corporate-announcements",
            params={"index": "equities", "symbol": symbol},
            timeout=15,
        )
        if r.status_code == 200:
            for item in r.json():
                desc = item.get("desc", "")
                if not any(kw in desc.lower() for kw in _types):
                    continue
                recent_filings.append({
                    "date":    item.get("an_dt", ""),
                    "type":    desc,
                    "subject": (item.get("attchmntText") or "")[:200],
                })
                if len(recent_filings) >= max_filings:
                    break
    except Exception:
        pass

    return {
        "corporate_actions": corporate_acts,
        "recent_filings":    recent_filings,
    }
