"""US macro snapshot — 6 FRED series (rates, inflation, FX, yield spread)."""

import os
from datetime import datetime

import requests

from src.config.settings import IST

_FRED_KEY  = os.getenv("FRED_API_KEY", "")
_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

_SERIES = {
    "fed_funds_rate":     ("DFF",      "Fed Funds Rate (%)", "daily"),
    "us_10y_yield":       ("DGS10",    "10Y Treasury Yield (%)", "daily"),
    "us_2y_yield":        ("DGS2",     "2Y Treasury Yield (%)", "daily"),
    "us_cpi_yoy":         ("CPIAUCSL", "CPI (YoY index)", "monthly"),
    "yield_spread_10y2y": ("T10Y2Y",   "10Y-2Y Spread (%)", "daily"),
    "usd_inr":            ("DEXINUS",  "USD/INR (INR per USD)", "daily"),
}


def _fetch_series(series_id: str, last_n: int = 5) -> list[dict]:
    params = {
        "series_id":     series_id,
        "api_key":       _FRED_KEY,
        "file_type":     "json",
        "sort_order":    "desc",
        "limit":         last_n,
        "observation_end": "9999-12-31",
    }
    resp = requests.get(_FRED_BASE, params=params, timeout=15)
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    result = []
    for o in obs:
        try:
            val = float(o["value"]) if o["value"] != "." else None
        except (ValueError, TypeError):
            val = None
        result.append({"date": o["date"], "value": val})
    return result


def _format_snapshot(data: dict) -> str:
    lines = [f"US Macro Snapshot — {data['fetched_at']}"]
    for key, info in data["series"].items():
        latest = info.get("latest")
        label  = info.get("label", key)
        val_str = f"{latest['value']}" if latest and latest.get("value") is not None else "N/A"
        date_str = f" ({latest['date']})" if latest else ""
        lines.append(f"  {label}: {val_str}{date_str}")
    return "\n".join(lines)


def collect(cfg: dict = {}) -> list[dict]:
    if not _FRED_KEY:
        raise RuntimeError("FRED_API_KEY env var not set")

    series_data = {}
    for key, (series_id, label, freq) in _SERIES.items():
        try:
            obs = _fetch_series(series_id, last_n=5)
            series_data[key] = {
                "series_id":  series_id,
                "label":      label,
                "frequency":  freq,
                "latest":     obs[0] if obs else None,
                "history":    obs,
            }
        except Exception as e:
            series_data[key] = {"series_id": series_id, "label": label, "error": str(e)}

    snapshot = {
        "fetched_at": datetime.now(IST).isoformat(),
        "series":     series_data,
    }

    return [{
        "source":       "us_macro",
        "source_type":  "market_snapshot",
        "title":        f"US Macro Snapshot {datetime.now(IST).strftime('%Y-%m-%d')}",
        "url":          None,
        "published_at": snapshot["fetched_at"],
        "content":      _format_snapshot(snapshot),
        "metadata": {
            "snapshot_type": "us_macro",
            "data":          snapshot,
        },
    }]
