"""
NSE equity symbol list — fetches, caches, and fuzzy-matches company names to NSE tickers.

Source: https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv (~2360 stocks)
Cache:  db/nse_equity_cache.json (auto-refreshed every 7 days)

Public API:
    load_nse_symbols(refresh_days)          -> dict {simplified: ticker}
    lookup_ticker(name, symbols, aliases)   -> str | None  (NSE ticker without .NS)

Aliases are loaded from l7_config.yaml (company_aliases key) and passed in by the runner.
Adding a new alias requires only a YAML edit — no code change.
"""

import csv
import io
import json
import re
from datetime import date
from pathlib import Path

import requests

from src.config.settings import PROJECT_ROOT

_CACHE    = PROJECT_ROOT / "db" / "nse_equity_cache.json"
_NSE_CSV  = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":     "text/html,application/xhtml+xml,*/*",
}

_NOISE = re.compile(
    r"\b(limited|ltd|industries|industry|corporation|corp|company|co|pvt|private|"
    r"enterprises|enterprise|holdings|holding|group|india|indian|international|"
    r"national|services|technologies|technology|solutions|systems|system|"
    r"financials|financial|finance|bank|banking|capital|asset|management)\b\.?",
    re.IGNORECASE,
)


def _simplify(name: str) -> str:
    name = name.lower()
    name = _NOISE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def _refresh(cache_path: Path) -> dict:
    resp = requests.get(_NSE_CSV, headers=_HEADERS, timeout=60)
    resp.raise_for_status()

    simplified_to_ticker: dict[str, str] = {}
    ambiguous: set[str] = set()

    for row in csv.DictReader(io.StringIO(resp.text)):
        symbol = row.get("SYMBOL", "").strip()
        name   = row.get("NAME OF COMPANY", "").strip()
        if not symbol or not name:
            continue
        s = _simplify(name)
        if not s or len(s) < 4:
            continue
        if s in simplified_to_ticker:
            ambiguous.add(s)
        simplified_to_ticker[s] = symbol

    for s in ambiguous:
        del simplified_to_ticker[s]

    cache = {
        "refreshed": date.today().isoformat(),
        "count":     len(simplified_to_ticker),
        "symbols":   simplified_to_ticker,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return simplified_to_ticker


def load_nse_symbols(refresh_days: int = 7) -> dict[str, str]:
    """
    Returns {simplified_company_name: NSE_ticker} for all ~2360 listed stocks.
    Auto-refreshes if cache is missing or older than refresh_days.
    """
    if _CACHE.exists():
        cache     = json.loads(_CACHE.read_text())
        refreshed = date.fromisoformat(cache.get("refreshed", "2000-01-01"))
        if (date.today() - refreshed).days < refresh_days:
            return cache["symbols"]
    return _refresh(_CACHE)


def lookup_ticker(
    company_name: str,
    symbols: dict[str, str],
    aliases: dict[str, str] | None = None,
) -> str | None:
    """
    Resolve a company name to an NSE ticker (without .NS suffix).
    Two-pass: aliases dict first, then rapidfuzz token_sort_ratio against NSE list.
    Returns None if no confident match found.

    aliases: loaded from l7_config.yaml company_aliases — pass {} if unavailable.
    """
    name_lower = company_name.lower().strip()
    _aliases   = aliases or {}

    # Pass 1 — exact alias match (longest first to avoid substring shadowing)
    for alias in sorted(_aliases, key=len, reverse=True):
        if alias == name_lower or alias in name_lower:
            return _aliases[alias]

    # Pass 2 — fuzzy match against simplified NSE names
    # symbols = {simplified_name: ticker}
    # We match query against the KEYS (simplified names), not the values (tickers).
    try:
        from rapidfuzz import process, fuzz
        query   = _simplify(company_name)
        # Build {ticker: simplified_name} so rapidfuzz matches against values (simplified names)
        # and returns (best_simplified, score, ticker) via the key
        inverted = {ticker: simplified for simplified, ticker in symbols.items()}
        match    = process.extractOne(query, inverted, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 82:
            _best_simplified, score, ticker = match
            return ticker
    except ImportError:
        # rapidfuzz not installed — exact simplified name lookup only
        query = _simplify(company_name)
        if query in symbols:
            return symbols[query]

    return None
