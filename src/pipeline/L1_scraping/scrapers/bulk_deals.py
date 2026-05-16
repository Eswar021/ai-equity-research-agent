"""Bulk and block deals scraper from NSE CSV endpoints."""

import csv
import io
from datetime import datetime

import requests

from src.config.settings import IST

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_BULK_URL  = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
_BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"

_BULK_FIELD_MAP = {
    "Deal Date":    "date",
    "Symbol":       "symbol",
    "Security Name":"security_name",
    "Client Name":  "client",
    "Buy/Sell":     "buy_sell",
    "Quantity Traded": "quantity",
    "Trade Price / Wt. Avg. Price": "price",
    "Remarks":      "remarks",
}

_BLOCK_FIELD_MAP = {
    "DEAL_DT":       "date",
    "SYMBOL":        "symbol",
    "SECURITY_NAME": "security_name",
    "CLIENT_NAME":   "client",
    "BUY_SELL":      "buy_sell",
    "QTY_TRD":       "quantity",
    "TRADE_PRICE":   "price",
}


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


def _to_int(v) -> int | None:
    try:
        return int(str(v).replace(",", ""))
    except Exception:
        return None


def _parse_csv(content: str, field_map: dict) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        normalized = {}
        for raw_key, new_key in field_map.items():
            normalized[new_key] = row.get(raw_key, "").strip()
        if not normalized.get("symbol"):
            continue
        if normalized.get("quantity"):
            normalized["quantity"] = _to_int(normalized["quantity"])
        if normalized.get("price"):
            normalized["price"] = _to_float(normalized["price"])
        rows.append(normalized)
    return rows


def _format_deal(deal: dict, deal_type: str) -> str:
    return (
        f"{deal_type.upper()} DEAL: {deal.get('symbol')} | "
        f"{deal.get('buy_sell', '')} | Client: {deal.get('client', '')} | "
        f"Qty: {deal.get('quantity')} | Price: {deal.get('price')} | "
        f"Date: {deal.get('date', '')}"
    )


def collect(cfg: dict = {}) -> list[dict]:
    session  = _nse_session()
    records  = []
    fetched_at = datetime.now(IST).isoformat()

    for url, field_map, deal_type in [
        (_BULK_URL, _BULK_FIELD_MAP, "bulk"),
        (_BLOCK_URL, _BLOCK_FIELD_MAP, "block"),
    ]:
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            deals = _parse_csv(resp.text, field_map)
            for deal in deals:
                records.append({
                    "source":       "bulk_deals",
                    "source_type":  "corporate_action",
                    "title":        f"{deal_type.title()} Deal: {deal.get('symbol', '')} {deal.get('buy_sell', '')}",
                    "url":          None,
                    "published_at": fetched_at,
                    "content":      _format_deal(deal, deal_type),
                    "metadata": {
                        "symbol":    deal.get("symbol", ""),
                        "client":    deal.get("client", ""),
                        "buy_sell":  deal.get("buy_sell", ""),
                        "quantity":  deal.get("quantity"),
                        "price":     deal.get("price"),
                        "deal_type": deal_type,
                        "date":      deal.get("date", ""),
                    },
                })
        except Exception as e:
            print(f"  [bulk_deals] {deal_type} fetch failed: {e}")

    return records
