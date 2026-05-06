"""
Downloads and caches the full NSE equity list (~2100 stocks).
Auto-refreshes every 7 days.
"""

import csv
import io
import json
import re
from datetime import date
from pathlib import Path

import requests

_CACHE    = Path(__file__).parent / "nse_equity_cache.json"
_NSE_CSV  = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Words to strip when simplifying company names for text matching
_NOISE = re.compile(
    r"\b(limited|ltd|industries|industry|corporation|corp|company|co|pvt|private|"
    r"enterprises|enterprise|holdings|holding|group|india|indian|international|"
    r"national|services|technologies|technology|solutions|systems|system|"
    r"financials|financial|finance|bank|banking|capital|asset|management)\b\.?",
    re.IGNORECASE,
)


# Common short forms → official NSE name equivalents
_EXPAND = re.compile(r"\bpharma\b")

def _simplify(name: str) -> str:
    """Strip noise words and normalise whitespace for fuzzy / exact matching."""
    name = _EXPAND.sub("pharmaceutical", name.lower())
    name = _NOISE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def refresh_symbols() -> dict:
    """Download fresh NSE equity CSV and rebuild cache. Returns symbols dict."""
    resp = requests.get(_NSE_CSV, headers=_HEADERS, timeout=60)
    resp.raise_for_status()

    symbols = {}
    for row in csv.DictReader(io.StringIO(resp.text)):
        symbol = row.get("SYMBOL", "").strip()
        name   = row.get("NAME OF COMPANY", "").strip()
        if not symbol or not name:
            continue
        ticker = f"{symbol}.NS"
        symbols[ticker] = {
            "ticker":     ticker,
            "name":       name,
            "simplified": _simplify(name),
        }

    cache = {
        "refreshed": date.today().isoformat(),
        "count":     len(symbols),
        "symbols":   symbols,
    }
    _CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    print(f"NSE symbol cache refreshed: {len(symbols)} stocks")
    return symbols


def load_symbols(auto_refresh_days: int = 7) -> dict:
    """
    Load symbols from local cache.
    Auto-downloads if cache is missing or older than auto_refresh_days.
    Returns { ticker: {ticker, name, simplified} }
    """
    if _CACHE.exists():
        cache     = json.loads(_CACHE.read_text())
        refreshed = date.fromisoformat(cache.get("refreshed", "2000-01-01"))
        if (date.today() - refreshed).days < auto_refresh_days:
            return cache["symbols"]
    return refresh_symbols()


if __name__ == "__main__":
    symbols = refresh_symbols()
    print(f"\nTotal NSE stocks: {len(symbols)}")
    sample = list(symbols.values())[:5]
    for s in sample:
        print(f"  {s['ticker']:20s} | {s['name']:50s} | simplified: {s['simplified']}")
