"""
context_ext_layer/utils/portfolio.py

Lightweight portfolio loader. The portfolio file is OPTIONAL — the system runs
fine without it. When present, downstream modules (evidence builder, analyst)
get a per-ticker flag of held / watchlisted / avoided / none.

Path: config/portfolio.json (gitignored — see config/portfolio.example.json)
"""

import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PORTFOLIO_FILE


def load_portfolio() -> dict:
    """Return portfolio dict. Empty dict if file missing or unparseable."""
    if not PORTFOLIO_FILE.exists():
        return {}
    try:
        return json.loads(PORTFOLIO_FILE.read_text())
    except Exception:
        return {}


def held_tickers() -> set[str]:
    p = load_portfolio()
    return {h.get("ticker", "") for h in p.get("holdings", []) if h.get("ticker")}


def watchlist_tickers() -> set[str]:
    return set(load_portfolio().get("watchlist", []))


def avoid_tickers() -> set[str]:
    return set(load_portfolio().get("avoid_list", []))


def portfolio_flag(ticker: str) -> str:
    """One of: 'held', 'watchlisted', 'avoided', 'none'."""
    if ticker in held_tickers():
        return "held"
    if ticker in watchlist_tickers():
        return "watchlisted"
    if ticker in avoid_tickers():
        return "avoided"
    return "none"


def holding_details(ticker: str) -> dict | None:
    """Return the holding entry (qty, avg_price, type) for a ticker, or None."""
    for h in load_portfolio().get("holdings", []):
        if h.get("ticker") == ticker:
            return h
    return None


if __name__ == "__main__":
    p = load_portfolio()
    if not p:
        print(f"  No portfolio file at {PORTFOLIO_FILE}")
        print(f"  Create one (see config/portfolio.example.json) to enable portfolio-aware analysis.")
    else:
        print(f"  Portfolio loaded from {PORTFOLIO_FILE}")
        print(f"    Holdings    : {len(p.get('holdings', []))}")
        print(f"    Watchlist   : {len(p.get('watchlist', []))}")
        print(f"    Avoid list  : {len(p.get('avoid_list', []))}")
        for t in ["HDFCBANK.NS", "BHEL.NS", "YESBANK.NS"]:
            print(f"    {t:15s} → {portfolio_flag(t)}")
