"""
Bulk & block deals collector from NSE India archives.

Bulk deal  : trade of ≥0.5% of total shares in a single transaction (any client)
Block deal : large negotiated trade executed in a separate 35-min morning window

Data is sourced from NSE's publicly accessible CSV archives (no API key required).
The CSVs contain today's data only.
"""

import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import BULK_DEALS_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer":     "https://www.nseindia.com/",
}

_BULK_CSV_URL  = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
_BLOCK_CSV_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"


def _parse_csv(text: str) -> list[dict]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        # skip "NO RECORDS" filler rows
        if not row.get("Symbol") or row["Symbol"].strip() == "":
            continue
        clean = {k.strip(): v.strip() for k, v in row.items() if k}
        rows.append(clean)
    return rows


def _normalise_bulk(row: dict) -> dict:
    return {
        "date":        row.get("Date"),
        "symbol":      row.get("Symbol"),
        "scrip_name":  row.get("Security Name"),
        "client":      row.get("Client Name"),
        "buy_sell":    row.get("Buy/Sell"),
        "quantity":    row.get("Quantity Traded"),
        "trade_price": row.get("Trade Price / Wght. Avg. Price"),
        "remarks":     row.get("Remarks"),
    }


def _normalise_block(row: dict) -> dict:
    return {
        "date":        row.get("Date"),
        "symbol":      row.get("Symbol"),
        "scrip_name":  row.get("Security Name"),
        "client":      row.get("Client Name"),
        "buy_sell":    row.get("Buy/Sell"),
        "quantity":    row.get("Quantity Traded"),
        "trade_price": row.get("Trade Price / Wght. Avg. Price"),
    }


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_bulk_deals() -> list[dict]:
    """Fetch today's bulk deals from NSE CSV archive."""
    r = requests.get(_BULK_CSV_URL, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    return [_normalise_bulk(row) for row in _parse_csv(r.text)]


def fetch_block_deals() -> list[dict]:
    """Fetch today's block deals from NSE CSV archive."""
    r = requests.get(_BLOCK_CSV_URL, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    return [_normalise_block(row) for row in _parse_csv(r.text)]


def fetch_all_deals() -> dict:
    """Fetch today's bulk and block deals."""
    return {
        "bulk_deals":  fetch_bulk_deals(),
        "block_deals": fetch_block_deals(),
    }


def fetch_deals_for_symbol(ticker: str) -> dict:
    """
    Fetch today's bulk and block deals filtered to the given ticker.
    ticker: NSE symbol, e.g. "RELIANCE" or "RELIANCE.NS" (suffix stripped).
    """
    symbol = re.sub(r"\.(NS|BO)$", "", ticker.upper())
    all_   = fetch_all_deals()

    return {
        "ticker":      symbol,
        "bulk_deals":  [d for d in all_["bulk_deals"]  if d.get("symbol") == symbol],
        "block_deals": [d for d in all_["block_deals"] if d.get("symbol") == symbol],
    }


def save_bulk_deals() -> str:
    data = fetch_all_deals()

    BULK_DEALS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"bulk_block_deals_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = BULK_DEALS_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    print("Fetching bulk & block deals (today) ...\n")
    saved = save_bulk_deals()
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"── Bulk Deals ({len(d['bulk_deals'])} total) ───────────────────────────")
    for deal in d["bulk_deals"][:10]:
        print(f"  {deal['date']}  {deal['symbol']:15s}  {deal['buy_sell']}  qty={deal['quantity']}  price={deal['trade_price']}")
        print(f"    client: {deal['client']}")

    print(f"\n── Block Deals ({len(d['block_deals'])} total) ──────────────────────────")
    for deal in d["block_deals"][:10]:
        print(f"  {deal['date']}  {deal['symbol']:15s}  {deal['buy_sell']}  qty={deal['quantity']}  price={deal['trade_price']}")
        print(f"    client: {deal['client']}")
