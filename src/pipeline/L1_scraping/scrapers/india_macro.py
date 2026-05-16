"""India macro snapshot — NSE indices, yfinance rates/commodities, World Bank, RBI."""

import re
import time
from datetime import datetime

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from src.config.settings import IST

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_BROAD_INDICES = {
    "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMLCAP 100",
    "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO", "NIFTY FMCG",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY OIL AND GAS",
    "NIFTY FIN SERVICE", "NIFTY HEALTHCARE INDEX",
    "NIFTY PSU BANK", "NIFTY INFRA", "NIFTY MEDIA",
}
_BREADTH_INDEX = "NIFTY 500"

_MARKET_TICKERS = {
    "usd_inr":      ("INR=X",    "INR/USD"),
    "us_10y_yield": ("^TNX",     "%"),
    "india_vix":    ("^INDIAVIX","index"),
    "nifty_50":     ("^NSEI",    "index"),
    "sensex":       ("^BSESN",   "index"),
}

_COMMODITY_TICKERS = {
    "gold_usd":        ("GC=F",  "USD/oz"),
    "silver_usd":      ("SI=F",  "USD/oz"),
    "crude_wti_usd":   ("CL=F",  "USD/barrel"),
    "crude_brent_usd": ("BZ=F",  "USD/barrel"),
    "natural_gas_usd": ("NG=F",  "USD/MMBtu"),
    "copper_usd":      ("HG=F",  "USD/lb"),
    "aluminium_usd":   ("ALI=F", "USD/MT"),
    "iron_ore_usd":    ("TIO=F", "USD/MT"),
    "coal_usd":        ("MTF=F", "USD/MT"),
}

_WB_INDICATORS = {
    "india_cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "india_gdp_growth_pct":    "NY.GDP.MKTP.KD.ZG",
}


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return s


def _to_int(v):
    try:    return int(v)
    except: return None

def _to_float(v):
    try:    return float(v)
    except: return None


def _fetch_nse_indices() -> tuple[list[dict], dict]:
    session = _nse_session()
    r = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
    r.raise_for_status()

    indices, breadth_raw = [], None
    for entry in r.json().get("data", []):
        name = entry.get("indexSymbol") or entry.get("index", "")
        if name == _BREADTH_INDEX:
            breadth_raw = entry
        if name not in _BROAD_INDICES:
            continue
        indices.append({
            "name":           name,
            "last":           entry.get("last"),
            "change_pct":     entry.get("percentChange"),
            "change_pct_1y":  entry.get("perChange365d"),
            "advances":       _to_int(entry.get("advances")),
            "declines":       _to_int(entry.get("declines")),
            "pe":             _to_float(entry.get("pe")),
            "pb":             _to_float(entry.get("pb")),
            "dividend_yield": _to_float(entry.get("dy")),
            "year_high":      entry.get("yearHigh"),
            "year_low":       entry.get("yearLow"),
        })

    indices.sort(key=lambda x: (x["change_pct"] or 0), reverse=True)

    breadth = {}
    if breadth_raw:
        adv = _to_int(breadth_raw.get("advances")) or 0
        dec = _to_int(breadth_raw.get("declines")) or 0
        breadth = {
            "index":      _BREADTH_INDEX,
            "advances":   adv,
            "declines":   dec,
            "unchanged":  _to_int(breadth_raw.get("unchanged")),
            "ad_ratio":   round(adv / dec, 2) if dec else None,
            "change_pct": breadth_raw.get("percentChange"),
        }
    return indices, breadth


def _fetch_yf_prices(tickers: dict) -> dict:
    result = {}
    for key, (symbol, unit) in tickers.items():
        try:
            info  = yf.Ticker(symbol).info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            result[key] = {"symbol": symbol, "value": price, "unit": unit}
        except Exception:
            result[key] = {"symbol": symbol, "value": None, "unit": unit}
    return result


def _fetch_world_bank() -> dict:
    result = {}
    for key, indicator in _WB_INDICATORS.items():
        try:
            r = requests.get(
                f"https://api.worldbank.org/v2/country/IN/indicator/{indicator}",
                params={"format": "json", "mrv": 3, "per_page": 3},
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


def _fetch_rbi_repo() -> str | None:
    try:
        r = requests.get(
            "https://www.rbi.org.in/Scripts/KeyRates.aspx",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ", strip=True)
        m = re.search(r"Policy Repo Rate[^\d]*(\d+\.?\d*\s*%)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def _format_snapshot(data: dict) -> str:
    lines = [f"India Macro Snapshot — {data['fetched_at']}"]

    mb = data.get("market_breadth", {})
    if mb:
        lines.append(
            f"Market Breadth (NIFTY 500): Advances={mb.get('advances')} "
            f"Declines={mb.get('declines')} A/D={mb.get('ad_ratio')} "
            f"Change={mb.get('change_pct')}%"
        )

    top_indices = data.get("nse_indices", [])[:5]
    for idx in top_indices:
        chg = f"{idx['change_pct']:+.2f}%" if idx.get("change_pct") is not None else "N/A"
        lines.append(f"  {idx['name']}: {idx['last']} ({chg}) PE={idx.get('pe')}")

    mr = data.get("market_rates", {})
    if mr.get("usd_inr", {}).get("value"):
        lines.append(f"USD/INR: {mr['usd_inr']['value']}")
    if mr.get("us_10y_yield", {}).get("value"):
        lines.append(f"US 10Y Yield: {mr['us_10y_yield']['value']}%")
    if mr.get("india_vix", {}).get("value"):
        lines.append(f"India VIX: {mr['india_vix']['value']}")

    for key in ("crude_brent_usd", "gold_usd"):
        c = data.get("commodity_prices", {}).get(key, {})
        if c.get("value"):
            lines.append(f"  {key}: {c['value']} {c.get('unit','')}")

    if data.get("rbi_repo_rate"):
        lines.append(f"RBI Repo Rate: {data['rbi_repo_rate']}")

    return "\n".join(lines)


def collect(cfg: dict = {}) -> list[dict]:
    indices, breadth = _fetch_nse_indices()
    market_rates     = _fetch_yf_prices(_MARKET_TICKERS)
    commodities      = _fetch_yf_prices(_COMMODITY_TICKERS)
    world_bank       = _fetch_world_bank()
    repo_rate        = _fetch_rbi_repo()

    snapshot = {
        "fetched_at":       datetime.now(IST).isoformat(),
        "market_breadth":   breadth,
        "nse_indices":      indices,
        "market_rates":     market_rates,
        "commodity_prices": commodities,
        "india_macro":      world_bank,
        "rbi_repo_rate":    repo_rate,
    }

    return [{
        "source":       "india_macro",
        "source_type":  "market_snapshot",
        "title":        f"India Macro Snapshot {datetime.now(IST).strftime('%Y-%m-%d')}",
        "url":          None,
        "published_at": snapshot["fetched_at"],
        "content":      _format_snapshot(snapshot),
        "metadata": {
            "snapshot_type": "india_macro",
            "data":          snapshot,
        },
    }]
