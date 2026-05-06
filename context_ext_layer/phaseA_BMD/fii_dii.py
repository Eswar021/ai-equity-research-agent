"""
FII/DII daily flow collector from NSE India.

Returns the most recent trading day's FII (Foreign Institutional Investors)
and DII (Domestic Institutional Investors) buy/sell/net values in crores.

NSE publishes this after market close each trading day.
Running this daily and saving snapshots builds historical context over time.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import FII_DII_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


def fetch_fii_dii() -> dict:
    """
    Fetch the most recent trading day's FII and DII activity from NSE.

    Returns:
        {
          "date": "30-Apr-2026",
          "fii": {"buy": 15049.55, "sell": 17432.10, "net": -2382.55},
          "dii": {"buy": 18252.89, "sell": 14765.79, "net": 3487.10}
        }
    All values are in crores (INR).
    """
    session = _nse_session()
    r = session.get(
        "https://www.nseindia.com/api/fiidiiTradeReact",
        timeout=15,
    )
    r.raise_for_status()

    result = {"date": None, "fii": {}, "dii": {}}

    for item in r.json():
        category = item.get("category", "")
        entry = {
            "buy":  float(item.get("buyValue",  0) or 0),
            "sell": float(item.get("sellValue", 0) or 0),
            "net":  float(item.get("netValue",  0) or 0),
        }
        if not result["date"]:
            result["date"] = item.get("date")

        if "FII" in category.upper() or "FPI" in category.upper():
            result["fii"] = entry
        elif "DII" in category.upper():
            result["dii"] = entry

    return result


def save_fii_dii() -> str:
    data = fetch_fii_dii()

    FII_DII_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"fii_dii_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = FII_DII_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    print("Fetching FII/DII flows ...\n")
    saved = save_fii_dii()
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"Date: {d['date']}")
    print(f"\n── FII/FPI (₹ crore) ──────────────────────")
    print(f"  Buy:  {d['fii'].get('buy', 'N/A'):>12,.2f}")
    print(f"  Sell: {d['fii'].get('sell', 'N/A'):>12,.2f}")
    net_fii = d['fii'].get('net', 0)
    print(f"  Net:  {net_fii:>12,.2f}  {'(NET BUYER)' if net_fii >= 0 else '(NET SELLER)'}")

    print(f"\n── DII (₹ crore) ───────────────────────────")
    print(f"  Buy:  {d['dii'].get('buy', 'N/A'):>12,.2f}")
    print(f"  Sell: {d['dii'].get('sell', 'N/A'):>12,.2f}")
    net_dii = d['dii'].get('net', 0)
    print(f"  Net:  {net_dii:>12,.2f}  {'(NET BUYER)' if net_dii >= 0 else '(NET SELLER)'}")
