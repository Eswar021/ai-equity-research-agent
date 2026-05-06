"""
Corporate actions collector for NSE-listed stocks.

Sources:
  - NSE India API  → dividends, bonus, splits, rights, buybacks (session-based)
  - yfinance       → dividends and splits history (fallback / cross-check)
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
from config.paths import CORPORATE_ACTIONS_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}


def _nse_symbol(ticker: str) -> str:
    """Strip .NS / .BO suffix to get bare NSE symbol."""
    return re.sub(r"\.(NS|BO)$", "", ticker.upper())


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


# ── NSE corporate actions ─────────────────────────────────────────────────────

def fetch_nse_corporate_actions(ticker: str) -> list[dict]:
    """
    Fetch corporate actions from NSE API.
    Returns a list of events: dividends, bonus, splits, rights, buybacks.
    """
    symbol  = _nse_symbol(ticker)
    session = _nse_session()

    r = session.get(
        "https://www.nseindia.com/api/corporates-corporateActions",
        params={"index": "equities", "symbol": symbol},
        timeout=15,
    )
    r.raise_for_status()

    actions = []
    for item in r.json():
        actions.append({
            "symbol":      item.get("symbol"),
            "series":      item.get("series"),
            "purpose":     item.get("subject"),
            "ex_date":     item.get("exDate"),
            "record_date": item.get("recDate"),
            "bc_start":    item.get("bcStartDate"),
            "bc_end":      item.get("bcEndDate"),
            "face_value":  item.get("faceVal"),
            "company":     item.get("comp"),
        })
    return actions


# ── yfinance dividends & splits ───────────────────────────────────────────────

def fetch_yf_corporate_actions(ticker: str) -> dict:
    """
    Fetch dividend and split history via yfinance.
    ticker should include .NS for NSE stocks (e.g. "RELIANCE.NS") or be a US ticker.
    """
    t = yf.Ticker(ticker)

    dividends = []
    try:
        for date, value in t.dividends.items():
            dividends.append({
                "date":   date.strftime("%Y-%m-%d"),
                "amount": round(float(value), 4),
            })
    except Exception:
        pass

    splits = []
    try:
        for date, ratio in t.splits.items():
            splits.append({
                "date":  date.strftime("%Y-%m-%d"),
                "ratio": float(ratio),
            })
    except Exception:
        pass

    return {
        "dividends": dividends,
        "splits":    splits,
    }


# ── Combined ──────────────────────────────────────────────────────────────────

def fetch_corporate_actions(ticker: str) -> dict:
    """
    Collect corporate actions for a ticker.

    For NSE stocks (ticker ending in .NS or bare symbol):
      - Tries NSE API for full action history (dividends, bonus, splits, rights, buybacks)
      - Also fetches yfinance dividends/splits for cross-reference

    For US stocks (no suffix):
      - Only yfinance
    """
    is_nse = ticker.upper().endswith(".NS") or (
        not ticker.upper().endswith(".BO") and "." not in ticker
    )

    nse_actions = []
    if is_nse:
        try:
            nse_actions = fetch_nse_corporate_actions(ticker)
        except Exception:
            pass

    yf_ticker = ticker if "." in ticker else ticker + ".NS" if is_nse else ticker
    yf_data   = fetch_yf_corporate_actions(yf_ticker)

    return {
        "ticker":      ticker.upper(),
        "nse_actions": nse_actions,
        "yf_dividends": yf_data["dividends"],
        "yf_splits":    yf_data["splits"],
    }


def save_corporate_actions(ticker: str) -> str:
    data = fetch_corporate_actions(ticker)

    CORPORATE_ACTIONS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    symbol   = re.sub(r"\.(NS|BO)$", "", ticker.upper())
    filename = f"{symbol}_corporate_actions_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = CORPORATE_ACTIONS_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "RELIANCE.NS"

    print(f"Fetching corporate actions for {ticker} ...\n")
    saved = save_corporate_actions(ticker)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"── NSE Corporate Actions ({len(d['nse_actions'])} total) ──────────────")
    for a in d["nse_actions"][:10]:
        print(f"  {a['ex_date']:12s}  {a['purpose']}")
    if len(d["nse_actions"]) > 10:
        print(f"  ... ({len(d['nse_actions']) - 10} more)")

    print(f"\n── yfinance Dividends ({len(d['yf_dividends'])} entries) ──────────────")
    for div in d["yf_dividends"][-5:]:
        print(f"  {div['date']}  ₹{div['amount']}")

    print(f"\n── yfinance Splits ({len(d['yf_splits'])} entries) ──────────────")
    for sp in d["yf_splits"]:
        print(f"  {sp['date']}  ratio: {sp['ratio']}")
