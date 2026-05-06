import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import MARKET_DATA_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def fetch_stock(ticker: str) -> dict:
    """
    Fetch current market data for a ticker (e.g. 'RELIANCE.NS', 'AAPL').
    Returns price, daily change, 52W range, period returns, volume, market cap.
    """
    t    = yf.Ticker(ticker)
    info = t.info

    price     = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    day_change_pct = round((price - prev_close) / prev_close * 100, 2) if price and prev_close else None

    hist = t.history(period="1y")

    def _period_return(days: int) -> float | None:
        if len(hist) < days:
            return None
        start_price = hist["Close"].iloc[-days]
        end_price   = hist["Close"].iloc[-1]
        return round((end_price - start_price) / start_price * 100, 2)

    return {
        "ticker":           ticker,
        "name":             info.get("longName") or info.get("shortName", ""),
        "exchange":         info.get("exchange", ""),
        "currency":         info.get("currency", ""),
        "price":            price,
        "day_change_pct":   day_change_pct,
        "52w_high":         info.get("fiftyTwoWeekHigh"),
        "52w_low":          info.get("fiftyTwoWeekLow"),
        "return_1m":        _period_return(21),
        "return_3m":        _period_return(63),
        "return_1y":        _period_return(len(hist) - 1) if len(hist) > 1 else None,
        "volume":           info.get("regularMarketVolume"),
        "market_cap":       info.get("marketCap"),
        "sector":           info.get("sector", ""),
        "industry":         info.get("industry", ""),
        "fetched_at":       datetime.now(_IST).isoformat(),
    }


def save_stock(ticker: str) -> str:
    data = fetch_stock(ticker)

    MARKET_DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    slug     = ticker.replace(".", "_").upper()
    filename = f"{slug}_{today}.json"

    out_file = MARKET_DATA_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    for ticker in ["RELIANCE.NS", "HDFCBANK.NS", "AAPL"]:
        print(f"Fetching {ticker} ...")
        saved = save_stock(ticker)
        print(f"Saved to: {saved}")

        with open(saved) as f:
            d = json.load(f)

        print(f"  Name:        {d['name']}")
        print(f"  Price:       {d['price']} {d['currency']}")
        print(f"  Day change:  {d['day_change_pct']}%")
        print(f"  52W H/L:     {d['52w_high']} / {d['52w_low']}")
        print(f"  Return 1M:   {d['return_1m']}%")
        print(f"  Return 3M:   {d['return_3m']}%")
        print(f"  Return 1Y:   {d['return_1y']}%")
        print(f"  Market Cap:  {d['market_cap']}")
        print()
