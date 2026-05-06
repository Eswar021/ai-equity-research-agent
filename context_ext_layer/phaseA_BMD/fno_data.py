"""
F&O / Options data collector from NSE India.

Collects the full option chain for a stock or index, then derives:
  - PCR (Put-Call Ratio): total PE OI / total CE OI — above 1 is bearish, below 1 bullish
  - Max Pain: the strike price at which option writers lose the least money at expiry
  - Top OI strikes: where the most open interest is concentrated (support/resistance)
  - ATM implied volatility

NSE publishes live option chains during market hours.
Returns empty records outside market hours or on holidays.

Supported symbols:
  - Indices: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY
  - Equities: any NSE F&O stock (e.g. RELIANCE, HDFC, TCS)
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import FNO_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}


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


# ── Option chain fetch ────────────────────────────────────────────────────────

def fetch_option_chain(ticker: str) -> dict:
    """
    Fetch raw option chain from NSE for a stock or index.

    Returns the full records dict:
    {
      "underlying_value": float,
      "expiry_dates": [...],
      "timestamp": "...",
      "data": [
        {
          "strike_price": float,
          "expiry_date": str,
          "ce": { "oi": int, "change_oi": int, "volume": int, "iv": float, "ltp": float, "change": float },
          "pe": { ... same ... }
        }
      ]
    }
    Returns empty records (data=[]) outside market hours.
    """
    symbol  = _nse_symbol(ticker)
    session = _nse_session()

    endpoint = (
        "https://www.nseindia.com/api/option-chain-indices"
        if symbol in _INDEX_SYMBOLS
        else "https://www.nseindia.com/api/option-chain-equities"
    )

    r = session.get(endpoint, params={"symbol": symbol}, timeout=20)
    r.raise_for_status()

    raw = r.json()
    records = raw.get("records", {})

    data = []
    for item in records.get("data", []):
        entry = {
            "strike_price": item.get("strikePrice"),
            "expiry_date":  item.get("expiryDate"),
        }
        for side, key in [("ce", "CE"), ("pe", "PE")]:
            side_data = item.get(key, {})
            entry[side] = {
                "oi":        side_data.get("openInterest"),
                "change_oi": side_data.get("changeinOpenInterest"),
                "volume":    side_data.get("totalTradedVolume"),
                "iv":        side_data.get("impliedVolatility"),
                "ltp":       side_data.get("lastPrice"),
                "change":    side_data.get("change"),
                "pchange":   side_data.get("pChange"),
            }
        data.append(entry)

    return {
        "underlying_value": records.get("underlyingValue"),
        "expiry_dates":     records.get("expiryDates", []),
        "timestamp":        records.get("timestamp"),
        "data":             data,
    }


# ── Derived metrics ───────────────────────────────────────────────────────────

def _compute_pcr(data: list[dict]) -> float | None:
    """Put-Call Ratio = total PE OI / total CE OI across all strikes."""
    total_pe = sum((r["pe"]["oi"] or 0) for r in data if r.get("pe"))
    total_ce = sum((r["ce"]["oi"] or 0) for r in data if r.get("ce"))
    if total_ce == 0:
        return None
    return round(total_pe / total_ce, 4)


def _compute_max_pain(data: list[dict]) -> float | None:
    """
    Max Pain = strike price at which the total value of all expiring options
    (both CE and PE) is minimized — i.e. where option buyers lose the most.
    """
    strikes = sorted({r["strike_price"] for r in data if r.get("strike_price")})
    if not strikes:
        return None

    min_pain = float("inf")
    max_pain_strike = None

    for test_strike in strikes:
        # CE writers lose when spot > strike
        ce_loss = sum(
            max(0, test_strike - r["strike_price"]) * (r["ce"]["oi"] or 0)
            for r in data if r.get("ce") and r["strike_price"]
        )
        # PE writers lose when spot < strike
        pe_loss = sum(
            max(0, r["strike_price"] - test_strike) * (r["pe"]["oi"] or 0)
            for r in data if r.get("pe") and r["strike_price"]
        )
        total_loss = ce_loss + pe_loss
        if total_loss < min_pain:
            min_pain = total_loss
            max_pain_strike = test_strike

    return max_pain_strike


def _top_oi_strikes(data: list[dict], top_n: int = 5) -> dict:
    """Top N strikes by CE and PE open interest."""
    ce_oi = sorted(
        [{"strike": r["strike_price"], "oi": r["ce"]["oi"] or 0, "expiry": r["expiry_date"]}
         for r in data if r.get("ce") and r["ce"].get("oi")],
        key=lambda x: x["oi"], reverse=True
    )[:top_n]

    pe_oi = sorted(
        [{"strike": r["strike_price"], "oi": r["pe"]["oi"] or 0, "expiry": r["expiry_date"]}
         for r in data if r.get("pe") and r["pe"].get("oi")],
        key=lambda x: x["oi"], reverse=True
    )[:top_n]

    return {"top_ce_oi": ce_oi, "top_pe_oi": pe_oi}


def _atm_iv(data: list[dict], underlying: float | None) -> dict | None:
    """IV of the nearest-to-money strike (nearest expiry)."""
    if not underlying or not data:
        return None
    nearest = min(data, key=lambda r: abs((r["strike_price"] or 0) - underlying))
    return {
        "strike":  nearest["strike_price"],
        "expiry":  nearest["expiry_date"],
        "ce_iv":   nearest["ce"].get("iv") if nearest.get("ce") else None,
        "pe_iv":   nearest["pe"].get("iv") if nearest.get("pe") else None,
    }


# ── Combined snapshot ─────────────────────────────────────────────────────────

def fetch_fno_snapshot(ticker: str) -> dict:
    """
    Full F&O snapshot: raw option chain + derived metrics (PCR, max pain, top OI, ATM IV).
    """
    chain = fetch_option_chain(ticker)
    data  = chain["data"]

    return {
        "ticker":          _nse_symbol(ticker),
        "underlying_value": chain["underlying_value"],
        "timestamp":       chain["timestamp"],
        "expiry_dates":    chain["expiry_dates"],
        "pcr":             _compute_pcr(data)       if data else None,
        "max_pain":        _compute_max_pain(data)  if data else None,
        "atm_iv":          _atm_iv(data, chain["underlying_value"]) if data else None,
        "top_oi_strikes":  _top_oi_strikes(data)    if data else {},
        "option_chain":    data,
    }


def save_fno_snapshot(ticker: str) -> str:
    data = fetch_fno_snapshot(ticker)

    FNO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    symbol   = _nse_symbol(ticker)
    filename = f"{symbol}_fno_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = FNO_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    # Works during market hours (Mon–Fri, 9:15 AM – 3:30 PM IST)
    # Returns empty option chain outside market hours
    ticker = "NIFTY"

    print(f"Fetching F&O snapshot for {ticker} ...\n")
    saved = save_fno_snapshot(ticker)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"Ticker:    {d['ticker']}")
    print(f"Spot:      {d['underlying_value']}")
    print(f"Timestamp: {d['timestamp']}")
    print(f"Expiries:  {d['expiry_dates'][:4]}")
    print(f"\nPCR:       {d['pcr']}  (>1 = more puts = bearish bias)")
    print(f"Max Pain:  {d['max_pain']}")

    if d.get("atm_iv"):
        iv = d["atm_iv"]
        print(f"ATM IV:    CE={iv['ce_iv']}%  PE={iv['pe_iv']}%  @ strike {iv['strike']} ({iv['expiry']})")

    oi = d.get("top_oi_strikes", {})
    print(f"\nTop CE OI strikes (resistance):")
    for s in oi.get("top_ce_oi", []):
        print(f"  {s['strike']:>8}  OI={s['oi']:>10,}  ({s['expiry']})")
    print(f"\nTop PE OI strikes (support):")
    for s in oi.get("top_pe_oi", []):
        print(f"  {s['strike']:>8}  OI={s['oi']:>10,}  ({s['expiry']})")

    print(f"\nOption chain rows: {len(d['option_chain'])}")
