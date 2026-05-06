"""
Peer comparison for Indian equities.

Approach:
  1. Get target stock's industry via yfinance.
  2. Map industry/sector → NSE sectoral index (NIFTY OIL AND GAS, NIFTY IT, etc.).
  3. Fetch index constituents from NSE equity-stockIndices API.
  4. Pull key ratios for each constituent via yfinance.
  5. Return a side-by-side comparison table.

No Playwright needed — pure requests + yfinance.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PEER_COMPARISON_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

# Maps (sector, industry) substrings → NSE sectoral index symbol
# Checked against NSE's allIndices endpoint
_SECTOR_INDEX_MAP = [
    # Energy / Oil & Gas
    (("oil", "gas", "refin", "petro", "energy"),        "NIFTY OIL AND GAS"),
    # Banking & Finance
    (("bank",),                                           "NIFTY BANK"),
    (("financ", "insurance", "nbfc"),                    "NIFTY FIN SERVICE"),
    # IT / Technology
    (("software", "information technology", "it "),      "NIFTY IT"),
    # Auto
    (("auto", "automobile", "vehicle"),                  "NIFTY AUTO"),
    # FMCG / Consumer
    (("fmcg", "consumer staples", "food", "beverage",
      "household", "personal products"),                 "NIFTY FMCG"),
    # Pharma / Healthcare
    (("pharma", "drug", "healthcare", "hospital",
      "biotech", "medical"),                             "NIFTY HEALTHCARE"),
    # Metals / Mining
    (("metal", "steel", "aluminium", "copper", "zinc",
      "mining", "iron"),                                 "NIFTY METAL"),
    # Realty
    (("real estate", "realty", "construction"),          "NIFTY REALTY"),
    # Media
    (("media", "entertainment", "broadcast"),            "NIFTY MEDIA"),
    # Chemicals
    (("chemical", "fertiliser", "fertilizer"),          "NIFTY CHEMICALS"),
    # Telecom (included in broader IT index)
    (("telecom", "communication services"),              "NIFTY IT"),
]

_RATIO_KEYS = [
    "trailingPE",
    "priceToBook",
    "marketCap",
    "revenueGrowth",
    "profitMargins",
    "returnOnEquity",
    "debtToEquity",
    "dividendYield",
    "currentRatio",
    "sector",
    "industry",
    "longName",
]


def _nse_symbol(ticker: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", ticker.upper())


def _yf_ticker(nse_symbol: str) -> str:
    return f"{nse_symbol}.NS"


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


def _detect_sector_index(ticker_yf: str) -> str | None:
    """Return the NSE sectoral index most relevant for a stock."""
    try:
        info = yf.Ticker(ticker_yf).info
        sector   = (info.get("sector")   or "").lower()
        industry = (info.get("industry") or "").lower()
        combined = sector + " " + industry
        for keywords, index_name in _SECTOR_INDEX_MAP:
            if any(kw in combined for kw in keywords):
                return index_name
    except Exception:
        pass
    return None


def _get_index_constituents(index_name: str, session: requests.Session) -> list[str]:
    """Return NSE symbols of all index constituents (excluding the index itself)."""
    encoded = index_name.replace(" ", "%20")
    try:
        r = session.get(
            f"https://www.nseindia.com/api/equity-stockIndices?index={encoded}",
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        return [
            item["symbol"]
            for item in data
            if item.get("symbol") and item["symbol"] != index_name
        ]
    except Exception:
        return []


def _fetch_ratios(nse_symbol: str) -> dict:
    """Fetch key ratios for one stock via yfinance."""
    try:
        info = yf.Ticker(_yf_ticker(nse_symbol)).info
        result = {"symbol": nse_symbol}
        for key in _RATIO_KEYS:
            result[key] = info.get(key)
        return result
    except Exception:
        return {"symbol": nse_symbol}


def fetch_peer_comparison(ticker: str, max_peers: int = 15) -> dict:
    """
    Fetch peer comparison data for a stock.

    Returns:
        {
          ticker, sector_index,
          target: {symbol, ratios...},
          peers: [{symbol, ratios...}, ...]   (sorted by market cap desc)
        }
    """
    symbol   = _nse_symbol(ticker)
    yf_tick  = _yf_ticker(symbol)
    session  = _nse_session()

    index_name = _detect_sector_index(yf_tick)

    if not index_name:
        # Fall back to NIFTY 50 if no sector mapping found
        index_name = "NIFTY 50"

    constituents = _get_index_constituents(index_name, session)

    # Ensure target is in the list
    if symbol not in constituents:
        constituents.insert(0, symbol)

    # Limit peers (target + up to max_peers others)
    peer_symbols = [s for s in constituents if s != symbol][:max_peers]
    all_symbols  = [symbol] + peer_symbols

    peers_data = []
    for sym in all_symbols:
        data = _fetch_ratios(sym)
        peers_data.append(data)
        time.sleep(0.2)   # gentle rate limit

    target = peers_data[0]
    peers  = sorted(
        peers_data[1:],
        key=lambda x: x.get("marketCap") or 0,
        reverse=True,
    )

    return {
        "ticker":       symbol,
        "sector_index": index_name,
        "target":       target,
        "peers":        peers,
    }


def save_peer_comparison(ticker: str, max_peers: int = 15) -> str:
    symbol = _nse_symbol(ticker)
    data   = fetch_peer_comparison(ticker, max_peers=max_peers)

    PEER_COMPARISON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{symbol}_peers_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = PEER_COMPARISON_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "RELIANCE"

    print(f"Fetching peer comparison for {ticker} ...\n")
    saved = save_peer_comparison(ticker, max_peers=15)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    target = d["target"]
    print(f"Sector index: {d['sector_index']}")
    print(f"\n{'Symbol':<20} {'PE':>8} {'PB':>7} {'Mkt Cap (Cr)':>14} {'Rev Gr':>8} {'Margins':>9} {'ROE':>7}")
    print("-" * 78)

    def _fmt_row(s: dict) -> str:
        pe  = f"{s['trailingPE']:.1f}"    if s.get("trailingPE")    else "—"
        pb  = f"{s['priceToBook']:.2f}"   if s.get("priceToBook")   else "—"
        mc  = f"{s['marketCap']/1e7:,.0f}" if s.get("marketCap")    else "—"
        rg  = f"{s['revenueGrowth']*100:.1f}%" if s.get("revenueGrowth") else "—"
        pm  = f"{s['profitMargins']*100:.1f}%" if s.get("profitMargins") else "—"
        roe = f"{s['returnOnEquity']*100:.1f}%" if s.get("returnOnEquity") else "—"
        name = (s.get("longName") or s["symbol"])[:19]
        return f"{name:<20} {pe:>8} {pb:>7} {mc:>14} {rg:>8} {pm:>9} {roe:>7}"

    print(_fmt_row(target) + "  ← TARGET")
    for p in d["peers"]:
        print(_fmt_row(p))
