"""FII/DII institutional flow data from NSE."""

from datetime import datetime

import requests

from src.config.settings import IST

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}
_ENDPOINT = "https://www.nseindia.com/api/fiidiiTradeReact"


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return s


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def _format_flows(data: list[dict]) -> str:
    lines = [f"FII/DII Flow Data — {datetime.now(IST).strftime('%Y-%m-%d')}"]
    for row in data[:5]:
        date = row.get("date", "")
        fii  = row.get("fii", {})
        dii  = row.get("dii", {})
        lines.append(
            f"  {date}: FII net={fii.get('net_cr')} cr | "
            f"DII net={dii.get('net_cr')} cr"
        )
    return "\n".join(lines)


def collect(cfg: dict = {}) -> list[dict]:
    session = _nse_session()
    resp = session.get(_ENDPOINT, timeout=15)
    resp.raise_for_status()

    raw_data = resp.json()
    if isinstance(raw_data, dict):
        raw_data = raw_data.get("data", raw_data.get("fiidii", []))

    if not raw_data:
        return []

    # NSE returns one row per category (FII/DII) per date
    # Group rows by date then pivot into {date, fii:{...}, dii:{...}}
    from collections import defaultdict
    by_date: dict = defaultdict(dict)
    for row in raw_data:
        date_str = row.get("date", "")
        category = row.get("category", "").upper().replace("FII/FPI", "FII")
        entry = {
            "buy_cr":  _to_float(row.get("buyValue")),
            "sell_cr": _to_float(row.get("sellValue")),
            "net_cr":  _to_float(row.get("netValue")),
        }
        by_date[date_str][category] = entry

    normalized = []
    for date_str, cats in by_date.items():
        normalized.append({
            "date": date_str,
            "fii":  cats.get("FII", {}),
            "dii":  cats.get("DII", {}),
        })
    normalized.sort(key=lambda x: x["date"], reverse=True)

    snapshot = {
        "fetched_at": datetime.now(IST).isoformat(),
        "data":       normalized,
    }

    return [{
        "source":       "fii_dii",
        "source_type":  "market_snapshot",
        "title":        f"FII/DII Flows {datetime.now(IST).strftime('%Y-%m-%d')}",
        "url":          None,
        "published_at": snapshot["fetched_at"],
        "content":      _format_flows(normalized),
        "metadata": {
            "snapshot_type": "fii_dii",
            "data":          snapshot,
        },
    }]
