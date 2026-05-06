"""
US macro data via FRED (Federal Reserve Economic Data).

Requires env var: FRED_API_KEY
Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html

Series fetched:
  DFF       — Fed Funds Rate (daily)
  DGS10     — 10-Year Treasury Rate (daily)
  DGS2      — 2-Year Treasury Rate (daily)
  CPIAUCSL  — US CPI (monthly)
  T10Y2Y    — 10Y-2Y Treasury Spread / yield curve (daily)
  DEXINUS   — USD/INR exchange rate (daily)
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import MACRO_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

_SERIES = {
    "fed_funds_rate":       ("DFF",      "%",           "Fed Funds Rate"),
    "us_10y_treasury":      ("DGS10",    "%",           "10-Year Treasury Rate"),
    "us_2y_treasury":       ("DGS2",     "%",           "2-Year Treasury Rate"),
    "us_cpi":               ("CPIAUCSL", "index",       "US CPI (1982-84=100)"),
    "yield_curve_10y_2y":   ("T10Y2Y",   "pct_points",  "10Y-2Y Treasury Spread"),
    "usd_inr":              ("DEXINUS",  "INR per USD", "USD/INR Exchange Rate"),
}


def fetch_fred_series(series_id: str, count: int = 5) -> list[dict] | None:
    """
    Fetch the last `count` observations for a FRED series.
    Returns a list of {"date": ..., "value": ...} dicts, or None on failure.
    """
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "FRED_API_KEY environment variable is not set. "
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    try:
        r = requests.get(
            FRED_BASE_URL,
            params={
                "series_id":        series_id,
                "api_key":          api_key,
                "file_type":        "json",
                "sort_order":       "desc",
                "limit":            count,
                "observation_start": "1900-01-01",
            },
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json().get("observations", [])
        observations = []
        for obs in raw:
            val = obs.get("value")
            observations.append({
                "date":  obs.get("date"),
                "value": float(val) if val not in (None, ".", "") else None,
            })
        return observations
    except Exception:
        return None


def fetch_us_macro(count: int = 5) -> dict:
    """
    Fetch all configured FRED series. Returns a dict with the latest
    value per series plus the last `count` observations for context.
    """
    result: dict = {"fetched_at": datetime.now(_IST).isoformat()}

    for key, (series_id, unit, label) in _SERIES.items():
        observations = fetch_fred_series(series_id, count=count)

        if observations is None:
            result[key] = {
                "series_id":    series_id,
                "label":        label,
                "unit":         unit,
                "latest_date":  None,
                "latest_value": None,
                "observations": [],
            }
            continue

        # most recent non-null observation
        latest = next(
            (obs for obs in observations if obs["value"] is not None),
            observations[0] if observations else {"date": None, "value": None},
        )

        result[key] = {
            "series_id":    series_id,
            "label":        label,
            "unit":         unit,
            "latest_date":  latest["date"],
            "latest_value": latest["value"],
            "observations": list(reversed(observations)),  # chronological order
        }

    return result


def save_us_macro(count: int = 5) -> str:
    data = fetch_us_macro(count=count)

    MACRO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"us_macro_{today}.json"

    out_file = MACRO_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    print("Fetching US macro data from FRED...\n")
    saved = save_us_macro()
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print("── US Macro (FRED) ──────────────────────────────────────────")
    for key, entry in d.items():
        if key == "fetched_at":
            print(f"  Fetched at: {entry}")
            continue
        status = f"{entry['latest_value']} {entry['unit']}" if entry["latest_value"] is not None else "N/A"
        print(f"  {entry['label']:35s}  {status}  (as of {entry['latest_date']})")
