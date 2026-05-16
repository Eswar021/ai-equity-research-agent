"""F&O option chain snapshot — PCR, max pain, ATM IV, top OI strikes."""

from datetime import datetime

import requests

from src.config.settings import IST

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}

_MARKET_OPEN_IST  = (9, 15)
_MARKET_CLOSE_IST = (15, 30)




def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return s


def _is_market_open() -> bool:
    now = datetime.now(IST)
    open_h, open_m   = _MARKET_OPEN_IST
    close_h, close_m = _MARKET_CLOSE_IST
    t = now.hour * 60 + now.minute
    return (open_h * 60 + open_m) <= t <= (close_h * 60 + close_m)


def _fetch_option_chain(session: requests.Session, symbol: str) -> dict | None:
    is_index = symbol.upper() in _INDEX_SYMBOLS
    if is_index:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    else:
        url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _derive_metrics(chain_data: dict) -> dict:
    records   = chain_data.get("records", {})
    data      = records.get("data", [])
    spot      = records.get("underlyingValue", 0)
    exp_dates = records.get("expiryDates", [])

    if not data or not spot:
        return {}

    nearest_exp = exp_dates[0] if exp_dates else None
    near_exp_data = [r for r in data if r.get("expiryDate") == nearest_exp] if nearest_exp else data

    total_call_oi = sum((r.get("CE", {}).get("openInterest", 0) or 0) for r in near_exp_data)
    total_put_oi  = sum((r.get("PE", {}).get("openInterest", 0) or 0) for r in near_exp_data)
    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi else None

    strikes = sorted({r.get("strikePrice") for r in near_exp_data if r.get("strikePrice")})
    atm_strike = min(strikes, key=lambda s: abs(s - spot)) if strikes else None

    top_call_oi = sorted(near_exp_data, key=lambda r: r.get("CE", {}).get("openInterest", 0) or 0, reverse=True)[:3]
    top_put_oi  = sorted(near_exp_data, key=lambda r: r.get("PE", {}).get("openInterest", 0) or 0, reverse=True)[:3]

    atm_iv = None
    if atm_strike:
        for r in near_exp_data:
            if r.get("strikePrice") == atm_strike:
                atm_iv = r.get("CE", {}).get("impliedVolatility") or r.get("PE", {}).get("impliedVolatility")
                break

    max_pain_strike = None
    if near_exp_data:
        pain = {}
        for strike in strikes:
            call_loss = sum(
                max(0, (r.get("strikePrice", 0) - strike)) * (r.get("CE", {}).get("openInterest", 0) or 0)
                for r in near_exp_data
            )
            put_loss = sum(
                max(0, (strike - r.get("strikePrice", 0))) * (r.get("PE", {}).get("openInterest", 0) or 0)
                for r in near_exp_data
            )
            pain[strike] = call_loss + put_loss
        if pain:
            max_pain_strike = min(pain, key=pain.get)

    return {
        "spot":              spot,
        "nearest_expiry":    nearest_exp,
        "pcr":               pcr,
        "atm_strike":        atm_strike,
        "atm_iv":            atm_iv,
        "max_pain":          max_pain_strike,
        "total_call_oi":     total_call_oi,
        "total_put_oi":      total_put_oi,
        "top_call_oi_strikes": [r.get("strikePrice") for r in top_call_oi],
        "top_put_oi_strikes":  [r.get("strikePrice") for r in top_put_oi],
    }


def _format_metrics(symbol: str, m: dict) -> str:
    return (
        f"F&O Snapshot — {symbol} | Spot: {m.get('spot')} | "
        f"Expiry: {m.get('nearest_expiry')} | PCR: {m.get('pcr')} | "
        f"ATM Strike: {m.get('atm_strike')} | ATM IV: {m.get('atm_iv')} | "
        f"Max Pain: {m.get('max_pain')} | "
        f"Top Call OI strikes: {m.get('top_call_oi_strikes')} | "
        f"Top Put OI strikes: {m.get('top_put_oi_strikes')}"
    )


def collect(cfg: dict = {}) -> list[dict]:
    if not _is_market_open():
        print("  [fno] market closed — skipping option chain fetch")
        return []

    symbols  = cfg.get("symbols", ["NIFTY", "BANKNIFTY"])
    session  = _nse_session()
    records  = []
    fetched_at = datetime.now(IST).isoformat()

    for symbol in symbols:
        try:
            chain_data = _fetch_option_chain(session, symbol)
            if not chain_data:
                continue
            metrics = _derive_metrics(chain_data)
            if not metrics:
                continue
            records.append({
                "source":       "fno",
                "source_type":  "market_snapshot",
                "title":        f"F&O Snapshot {symbol} {datetime.now(IST).strftime('%Y-%m-%d')}",
                "url":          None,
                "published_at": fetched_at,
                "content":      _format_metrics(symbol, metrics),
                "metadata": {
                    "snapshot_type": "fno",
                    "symbol":        symbol,
                    "data":          metrics,
                },
            })
        except Exception as e:
            print(f"  [fno] {symbol} failed: {e}")

    return records
