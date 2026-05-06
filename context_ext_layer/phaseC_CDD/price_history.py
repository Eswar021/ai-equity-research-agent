import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import MARKET_DATA_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def fetch_history(
    ticker: str,
    period: str = "1y",
    start: str = None,
    end: str = None,
) -> dict:
    """
    Fetch daily OHLCV price history for a ticker.

    period  : "1mo" | "3mo" | "6mo" | "1y" | "2y" | "5y" | "max"
              Use "max" to get full history from listing day — first_day gives
              the closest proxy for the IPO / listing price.
    start / end : "YYYY-MM-DD" — overrides period when both are provided.
    """
    t    = yf.Ticker(ticker)
    info = t.info

    epoch        = info.get("firstTradeDateEpochUtc")
    listing_date = (
        datetime.fromtimestamp(epoch, tz=_IST).strftime("%Y-%m-%d")
        if epoch else None
    )

    if start and end:
        hist  = t.history(start=start, end=end)
        label = f"{start}_to_{end}"
    else:
        hist  = t.history(period=period)
        label = period

    records = [
        {
            "date":   dt.strftime("%Y-%m-%d"),
            "open":   round(float(row["Open"]),  2),
            "high":   round(float(row["High"]),  2),
            "low":    round(float(row["Low"]),   2),
            "close":  round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        }
        for dt, row in hist.iterrows()
    ]

    return {
        "ticker":        ticker,
        "name":          info.get("longName") or info.get("shortName", ""),
        "currency":      info.get("currency", ""),
        "period":        label,
        "listing_date":  listing_date,
        "first_day":     records[0] if (period == "max" and records) else None,
        "total_records": len(records),
        "history":       records,
        "fetched_at":    datetime.now(_IST).isoformat(),
    }


def save_history(
    ticker: str,
    period: str = "1y",
    start: str = None,
    end: str = None,
) -> str:
    data = fetch_history(ticker, period=period, start=start, end=end)

    MARKET_DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    slug     = ticker.replace(".", "_").upper()
    label    = data["period"].replace(" ", "_")
    filename = f"{slug}_history_{label}_{today}.json"

    out_file = MARKET_DATA_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "HDFCBANK.NS"

    # standard periods
    for period in ["3mo", "6mo", "1y"]:
        print(f"Fetching {ticker} | {period}")
        saved = save_history(ticker, period=period)
        with open(saved) as f:
            d = json.load(f)
        print(f"  Records : {d['total_records']}")
        print(f"  First   : {d['history'][0]}")
        print(f"  Last    : {d['history'][-1]}")
        print(f"  Saved   : {saved}\n")

    # full history — listing day / IPO proxy
    print(f"Fetching INFY.NS | max (full history)")
    saved = save_history("INFY.NS", period="max")
    with open(saved) as f:
        d = json.load(f)
    print(f"  Listing date : {d['listing_date']}")
    print(f"  First day    : {d['first_day']}")
    print(f"  Total records: {d['total_records']}")
    print(f"  Saved        : {saved}\n")

    # specific date range
    print(f"Fetching TCS.NS | 2024-01-01 → 2024-06-30")
    saved = save_history("TCS.NS", start="2024-01-01", end="2024-06-30")
    with open(saved) as f:
        d = json.load(f)
    print(f"  Records : {d['total_records']}")
    print(f"  Period  : {d['period']}")
    print(f"  Saved   : {saved}")
