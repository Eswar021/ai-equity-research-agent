"""
Macro data collector — no API key required.

Sources:
  - NSE India allIndices API  → Nifty 50 / Bank Nifty / Midcap PE, PB, DY, price
  - yfinance                  → USD/INR, US 10-Year yield, India VIX, Nifty, Sensex
                                + Gold, Brent/WTI Crude, Natural Gas, Copper, Aluminium,
                                  Silver, Iron Ore, Coal (commodity prices)
  - World Bank API            → India CPI inflation, GDP growth (annual, latest 3 years)
  - RBI KeyRates page         → Repo rate (best-effort scrape; None if unavailable)
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf
from bs4 import BeautifulSoup

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import MACRO_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}


# ── NSE indices ───────────────────────────────────────────────────────────────

# Sector + broad indices to track (for performance + valuation)
_NSE_INDICES_OF_INTEREST = {
    # Broad market
    "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMLCAP 100",
    # Sectors
    "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO", "NIFTY FMCG",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY OIL AND GAS",
    "NIFTY FIN SERVICE", "NIFTY HEALTHCARE INDEX",
    "NIFTY PSU BANK", "NIFTY INFRA", "NIFTY MEDIA",
}

# NIFTY 500 used only for market breadth (advances/declines across 500 stocks)
_BREADTH_INDEX = "NIFTY 500"


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return s


def _to_int(v) -> int | None:
    try:    return int(v)
    except: return None

def _to_float(v) -> float | None:
    try:    return float(v)
    except: return None


def fetch_nse_indices() -> tuple[list[dict], dict]:
    """
    Fetch sector/broad index data + market breadth from NSE allIndices API.
    Returns (indices_list, market_breadth_dict).
    NSE returns advances/declines/pe/pb as strings — cast them here.
    """
    r = _nse_session().get("https://www.nseindia.com/api/allIndices", timeout=15)
    r.raise_for_status()

    indices     = []
    breadth_raw = None

    for entry in r.json().get("data", []):
        name = entry.get("indexSymbol") or entry.get("index", "")

        if name == _BREADTH_INDEX:
            breadth_raw = entry

        if name not in _NSE_INDICES_OF_INTEREST:
            continue

        indices.append({
            "name":           name,
            "last":           entry.get("last"),
            "change_pct":     entry.get("percentChange"),     # today's % move (float)
            "change_pct_1y":  entry.get("perChange365d"),     # 1-year % move (float)
            "advances":       _to_int(entry.get("advances")),
            "declines":       _to_int(entry.get("declines")),
            "unchanged":      _to_int(entry.get("unchanged")),
            "pe":             _to_float(entry.get("pe")),
            "pb":             _to_float(entry.get("pb")),
            "dividend_yield": _to_float(entry.get("dy")),
            "year_high":      entry.get("yearHigh"),
            "year_low":       entry.get("yearLow"),
        })

    # Sort sectors by today's % change — hot sectors first
    indices.sort(key=lambda x: (x["change_pct"] or 0), reverse=True)

    # Market breadth from NIFTY 500
    market_breadth = {}
    if breadth_raw:
        adv = _to_int(breadth_raw.get("advances")) or 0
        dec = _to_int(breadth_raw.get("declines")) or 0
        unc = _to_int(breadth_raw.get("unchanged")) or 0
        market_breadth = {
            "index":      _BREADTH_INDEX,
            "advances":   adv,
            "declines":   dec,
            "unchanged":  unc,
            "ad_ratio":   round(adv / dec, 2) if dec else None,
            "change_pct": breadth_raw.get("percentChange"),
        }

    return indices, market_breadth


# ── Market rates: FX, yields, volatility, Indian indices (yfinance) ──────────

_MARKET_RATE_TICKERS = {
    "usd_inr":      ("INR=X",    "INR per USD"),
    "us_10y_yield": ("^TNX",     "%"),
    "vix_india":    ("^INDIAVIX","index"),
    "nifty_50":     ("^NSEI",    "index"),
    "sensex":       ("^BSESN",   "index"),
}

# ── Commodity prices (yfinance futures) ───────────────────────────────────────
# Relevant to Indian sector analysis:
#   Gold/Silver     → jewellery cos, inflation hedge
#   Crude/Brent     → oil & gas, paints, tyres (Brent = India's import benchmark)
#   Natural Gas     → GAIL, Petronet LNG, IGL, Gujarat Gas
#   Copper          → Hindalco, Vedanta, cable/wire cos
#   Aluminium       → Hindalco, NALCO, Vedanta
#   Iron Ore        → Tata Steel, JSW Steel, SAIL
#   Coal            → Coal India, NTPC, Adani Power

_COMMODITY_TICKERS = {
    "gold_usd":          ("GC=F",  "USD/oz"),
    "silver_usd":        ("SI=F",  "USD/oz"),
    "crude_wti_usd":     ("CL=F",  "USD/barrel"),
    "crude_brent_usd":   ("BZ=F",  "USD/barrel"),
    "natural_gas_usd":   ("NG=F",  "USD/MMBtu"),
    "copper_usd":        ("HG=F",  "USD/lb"),
    "aluminium_usd":     ("ALI=F", "USD/MT"),
    "iron_ore_usd":      ("TIO=F", "USD/MT"),
    "coal_usd":          ("MTF=F", "USD/MT"),
}


def _fetch_yf_prices(tickers: dict) -> dict:
    """Fetch current prices for a {key: (symbol, unit)} dict via yfinance."""
    result = {}
    for key, (symbol, unit) in tickers.items():
        try:
            info  = yf.Ticker(symbol).info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            result[key] = {"symbol": symbol, "value": price, "unit": unit}
        except Exception:
            result[key] = {"symbol": symbol, "value": None, "unit": unit}
    return result


def fetch_market_rates() -> dict:
    """Fetch FX, yield, volatility, and Indian index data via yfinance."""
    return _fetch_yf_prices(_MARKET_RATE_TICKERS)


def fetch_commodity_prices() -> dict:
    """Fetch global commodity futures prices relevant to Indian sector analysis."""
    return _fetch_yf_prices(_COMMODITY_TICKERS)


# ── India macro (World Bank) ──────────────────────────────────────────────────

_WB_INDICATORS = {
    "india_cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "india_gdp_growth_pct":    "NY.GDP.MKTP.KD.ZG",
}

def fetch_india_macro(last_n: int = 3) -> dict:
    """
    Fetch India CPI inflation and GDP growth from World Bank API.
    Returns the last_n annual data points for each indicator.
    """
    result = {}
    for key, indicator in _WB_INDICATORS.items():
        try:
            r = requests.get(
                f"https://api.worldbank.org/v2/country/IN/indicator/{indicator}",
                params={"format": "json", "mrv": last_n, "per_page": last_n},
                timeout=15,
            )
            r.raise_for_status()
            entries = r.json()[1] if len(r.json()) > 1 else []
            result[key] = [
                {"year": e["date"], "value": round(e["value"], 2) if e["value"] is not None else None}
                for e in entries if e.get("date")
            ]
        except Exception:
            result[key] = []
        time.sleep(0.2)
    return result


# ── RBI repo rate (best-effort) ───────────────────────────────────────────────

def fetch_rbi_repo_rate() -> str | None:
    """
    Scrape current RBI repo rate from the RBI KeyRates page.
    Returns rate string like "6.50%" or None if scraping fails.
    """
    try:
        r = requests.get(
            "https://www.rbi.org.in/Scripts/KeyRates.aspx",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # look for "Policy Repo Rate ... N.NN%"
        match = re.search(r"Policy Repo Rate[^\d]*(\d+\.?\d*\s*%)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


# ── Combined snapshot ─────────────────────────────────────────────────────────

def fetch_macro_snapshot() -> dict:
    indices, market_breadth = fetch_nse_indices()
    return {
        "fetched_at":        datetime.now(_IST).isoformat(),
        "market_breadth":    market_breadth,
        "nse_indices":       indices,
        "market_rates":      fetch_market_rates(),
        "commodity_prices":  fetch_commodity_prices(),
        "india_macro":       fetch_india_macro(),
        "rbi_repo_rate":     fetch_rbi_repo_rate(),
    }


def save_macro_snapshot() -> str:
    data = fetch_macro_snapshot()

    MACRO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"india_macro_{today}.json"

    out_file = MACRO_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    print("Fetching macro snapshot...\n")
    saved = save_macro_snapshot()
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print("── Market Breadth (NIFTY 500) ───────────────")
    mb = d["market_breadth"]
    print(f"  Advances: {mb.get('advances')}  Declines: {mb.get('declines')}  "
          f"Unchanged: {mb.get('unchanged')}  A/D ratio: {mb.get('ad_ratio')}  "
          f"Change: {mb.get('change_pct')}%")

    print("\n── NSE Indices (sorted by today's % change) ─")
    for idx in d["nse_indices"]:
        pe  = f"PE={idx['pe']}" if idx['pe'] else "PE=N/A"
        chg = f"{idx['change_pct']:+.2f}%" if idx['change_pct'] is not None else "N/A"
        print(f"  {idx['name']:25s}  {str(idx['last']):>10}  {chg:>8}  {pe}  PB={idx['pb']}  DY={idx['dividend_yield']}%")

    print("\n── Market Rates ─────────────────────────────")
    for key, val in d["market_rates"].items():
        print(f"  {key:20s}  {val['value']}  ({val['unit']})")

    print("\n── Commodity Prices ─────────────────────────")
    for key, val in d["commodity_prices"].items():
        print(f"  {key:22s}  {val['value']}  ({val['unit']})")

    print("\n── India Macro (World Bank, annual) ─────────")
    for key, entries in d["india_macro"].items():
        print(f"  {key}:")
        for e in entries:
            print(f"    {e['year']}: {e['value']}")

    print(f"\n── RBI Repo Rate: {d['rbi_repo_rate']} ────────────────────")
