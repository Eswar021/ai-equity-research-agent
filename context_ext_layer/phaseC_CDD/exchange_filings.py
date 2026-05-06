"""
NSE exchange filings / corporate announcements collector.

Fetches structured announcements filed by companies with NSE:
board meetings, financial results, dividend declarations, buybacks,
management changes, SAST disclosures, trading window notices, etc.

Source: NSE corporate-announcements API (no API key required, session-based).
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import EXCHANGE_FILINGS_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

# Announcement types considered material for investment research
_MATERIAL_TYPES = {
    "board meeting",
    "financial results",
    "dividend",
    "buyback",
    "change in director",
    "change in management",
    "merger",
    "acquisition",
    "demerger",
    "rights issue",
    "bonus",
    "split",
    "open offer",
    "delisting",
    "credit rating",
    "loss of order",
    "order won",
    "allotment",
    "outcome of board meeting",
    "press release",
}


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


def _nse_symbol(ticker: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", ticker.upper())


def _is_material(desc: str) -> bool:
    desc_lower = desc.lower()
    return any(kw in desc_lower for kw in _MATERIAL_TYPES)


def fetch_announcements(
    ticker: str,
    limit: int = 50,
    material_only: bool = False,
) -> list[dict]:
    """
    Fetch NSE corporate announcements for a stock.

    ticker        : NSE symbol, e.g. "RELIANCE" or "RELIANCE.NS"
    limit         : max number of most-recent announcements to return
    material_only : if True, return only announcements relevant to investment decisions
                    (filters out routine items like trading window closures)
    """
    symbol  = _nse_symbol(ticker)
    session = _nse_session()

    r = session.get(
        "https://www.nseindia.com/api/corporate-announcements",
        params={"index": "equities", "symbol": symbol},
        timeout=15,
    )
    r.raise_for_status()

    announcements = []
    for item in r.json():
        desc = item.get("desc", "")
        if material_only and not _is_material(desc):
            continue

        announcements.append({
            "date":            item.get("an_dt"),
            "type":            desc,
            "subject":         item.get("attchmntText") or "",
            "attachment_url":  item.get("attchmntFile") or "",
            "has_xbrl":        item.get("hasXbrl", False),
        })

        if len(announcements) >= limit:
            break

    return announcements


def save_announcements(
    ticker: str,
    limit: int = 50,
    material_only: bool = False,
) -> str:
    symbol = _nse_symbol(ticker)
    data   = fetch_announcements(ticker, limit=limit, material_only=material_only)

    EXCHANGE_FILINGS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{symbol}_announcements_{today}.json"

    output = {
        "ticker":       symbol,
        "fetched_at":   datetime.now(_IST).isoformat(),
        "total_returned": len(data),
        "material_only":  material_only,
        "announcements":  data,
    }

    out_file = EXCHANGE_FILINGS_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "RELIANCE"

    print(f"Fetching NSE announcements for {ticker} ...\n")
    saved = save_announcements(ticker, limit=50, material_only=True)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"Company: {ticker}  |  Total returned: {d['total_returned']}  (material_only={d['material_only']})")
    print(f"\n── Recent Announcements ──────────────────────────────────────────")
    for a in d["announcements"][:15]:
        subject = a["subject"][:70] if a["subject"] else ""
        print(f"  {a['date']}  [{a['type']}]")
        if subject:
            print(f"    {subject}")
