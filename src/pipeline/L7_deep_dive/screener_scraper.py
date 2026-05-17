"""
Screener.in scraper — fetches fundamentals, quarterly trend, ownership, and peers.

URL pattern: https://www.screener.in/company/{TICKER}/consolidated/
Requires 1–2 second delay between requests to avoid rate-limiting.

Returns a dict with: fundamentals, quarterly_trend, ownership, peers.
Returns None on fetch failure (non-200, parse error) — caller logs and marks partial.
"""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup, Tag

_BASE    = "https://www.screener.in"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _num(text: str) -> float | None:
    """Parse a screener value string like '2,345.67' or '23.4%' or '₹1,234 Cr' to float."""
    if not text:
        return None
    cleaned = re.sub(r"[₹,%\sCr]", "", text).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_key_ratios(soup: BeautifulSoup) -> dict:
    ratios = {}
    ul = soup.find(id="top-ratios")
    if not ul:
        return ratios
    for li in ul.find_all("li"):
        parts = [s.strip() for s in li.get_text(separator="|").split("|") if s.strip()]
        if len(parts) >= 2:
            key = parts[0].strip()
            val = " ".join(parts[1:]).strip()
            ratios[key] = val
    return ratios


def _parse_quarterly_table(soup: BeautifulSoup) -> list[dict]:
    """Extract last 4 quarters of revenue, PAT, OPM from the quarters section."""
    section = soup.find(id="quarters")
    if not section:
        return []
    table = section.find("table")
    if not table:
        return []

    thead = table.find("thead")
    if not thead:
        return []
    quarters = [th.get_text(strip=True) for th in thead.find_all("th")][1:]
    quarters = quarters[:4]  # last 4 quarters only

    rows_by_metric: dict[str, list] = {}
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            metric = cells[0].get_text(strip=True).rstrip("+").strip()
            values = [cells[i + 1].get_text(strip=True) if (i + 1) < len(cells) else "" for i in range(len(quarters))]
            rows_by_metric[metric] = values

    revenue_row = rows_by_metric.get("Sales", rows_by_metric.get("Revenue", []))
    pat_row     = rows_by_metric.get("Net Profit", rows_by_metric.get("PAT", []))
    opm_row     = rows_by_metric.get("OPM %", rows_by_metric.get("Operating Profit Margin %", []))

    result = []
    for i, quarter in enumerate(quarters):
        result.append({
            "quarter":    quarter,
            "revenue_cr": _num(revenue_row[i]) if i < len(revenue_row) else None,
            "pat_cr":     _num(pat_row[i])     if i < len(pat_row)     else None,
            "opm_pct":    _num(opm_row[i])     if i < len(opm_row)     else None,
        })
    return result


def _parse_shareholding(soup: BeautifulSoup) -> dict:
    """
    Extract promoter %, pledge %, FII %, DII % from the quarterly shareholding table.
    Returns the most recent quarter's values plus FII QoQ change.
    """
    section = soup.find(id="shareholding")
    if not section:
        return {}

    # Try quarterly shareholding sub-section first
    qshp = section.find(id="quarterly-shp")
    table = qshp.find("table") if qshp else section.find("table")
    if not table:
        return {}

    thead = table.find("thead")
    tbody = table.find("tbody")
    if not thead or not tbody:
        return {}

    quarters = [th.get_text(strip=True) for th in thead.find_all("th")][1:]

    rows: dict[str, list[str]] = {}
    for tr in tbody.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label  = cells[0].get_text(strip=True)
        values = [cells[i + 1].get_text(strip=True) if (i + 1) < len(cells) else "" for i in range(len(quarters))]
        rows[label] = values

    def _latest(key: str) -> float | None:
        for label, values in rows.items():
            if key.lower() in label.lower() and values:
                return _num(values[0])  # most recent quarter is first column
        return None

    def _prev(key: str) -> float | None:
        for label, values in rows.items():
            if key.lower() in label.lower() and len(values) >= 2:
                return _num(values[1])
        return None

    promoter_pct  = _latest("Promoters")
    fii_pct       = _latest("FII")
    dii_pct       = _latest("DII")

    fii_prev  = _prev("FII")
    fii_change = None
    if fii_pct is not None and fii_prev is not None:
        fii_change = round(fii_pct - fii_prev, 2)

    # Pledge % — sometimes in a sub-table or separate row
    pledge_pct = _latest("Pledg")  # "Pledged" or "Pledge %"

    return {
        "promoter_pct":       promoter_pct,
        "promoter_pledge_pct": pledge_pct,
        "fii_pct":            fii_pct,
        "dii_pct":            dii_pct,
        "fii_change_qoq_pct": fii_change,
    }


def _parse_peers(soup: BeautifulSoup, max_peers: int = 4) -> list[dict]:
    """Extract top-N peer comparison rows from the peers table."""
    section = soup.find(id="peers")
    if not section:
        return []
    table = section.find("table")
    if not table:
        return []

    thead = table.find("thead")
    if not thead:
        return []
    headers = [th.get_text(strip=True) for th in thead.find_all("th")]

    def _col(row_cells: list, col_name: str) -> float | None:
        for i, h in enumerate(headers):
            if col_name.lower() in h.lower() and i < len(row_cells):
                return _num(row_cells[i].get_text(strip=True))
        return None

    def _ticker_from_row(row: Tag) -> str:
        a = row.find("a")
        if a and a.get("href"):
            # /company/HDFCBANK/ → HDFCBANK
            m = re.search(r"/company/([^/]+)/", a["href"])
            if m:
                return m.group(1)
        return row.find(["td", "th"]).get_text(strip=True) if row.find(["td", "th"]) else ""

    tbody = table.find("tbody")
    if not tbody:
        return []

    peers = []
    for tr in tbody.find_all("tr")[:max_peers + 1]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        ticker = _ticker_from_row(tr)
        if not ticker or ticker.lower() in ("company", "name", ""):
            continue
        peers.append({
            "ticker":       ticker,
            "pe":           _col(cells, "P/E"),
            "pb":           _col(cells, "P/B"),
            "roe":          _col(cells, "ROE"),
            "market_cap_cr": _col(cells, "Mar Cap"),
        })
        if len(peers) >= max_peers:
            break
    return peers


def fetch(ticker: str, request_delay_s: float = 1.5, max_peers: int = 4) -> dict | None:
    """
    Scrape fundamentals, quarterly trend, ownership, and peers for an NSE ticker.
    Tries consolidated view first, falls back to standalone.
    Returns None on HTTP error or if no meaningful data parsed.
    """
    symbol = ticker.upper().replace(".NS", "").replace(".BO", "")
    url    = f"{_BASE}/company/{symbol}/consolidated/"

    try:
        time.sleep(request_delay_s)
        resp = requests.get(url, headers=_HEADERS, timeout=20)

        if resp.status_code == 404:
            # Try standalone (some companies don't have consolidated)
            url  = f"{_BASE}/company/{symbol}/"
            time.sleep(request_delay_s)
            resp = requests.get(url, headers=_HEADERS, timeout=20)

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        ratios = _parse_key_ratios(soup)

        def _r(key: str) -> float | None:
            return _num(ratios.get(key))

        fundamentals = {
            "market_cap_cr":          _r("Market Cap"),
            "pe_ttm":                 _r("Stock P/E"),
            "pb":                     _r("Price to Book value"),
            "roe_pct":                _r("Return on equity"),
            "roce_pct":               _r("ROCE"),
            "revenue_growth_ttm_pct": _r("Sales growth (3Yrs)"),
            "net_npa_pct":            _r("Net NPA"),        # banks
            "nim_pct":                _r("Net Interest Margin"),  # banks
            "dividend_yield_pct":     _r("Dividend Yield"),
        }

        quarterly_trend = _parse_quarterly_table(soup)
        ownership       = _parse_shareholding(soup)
        peers           = _parse_peers(soup, max_peers=max_peers)

        # Require at least market cap or P/E to consider this a valid scrape
        if not fundamentals["market_cap_cr"] and not fundamentals["pe_ttm"]:
            return None

        return {
            "fundamentals":    fundamentals,
            "quarterly_trend": quarterly_trend,
            "ownership":       ownership,
            "peers":           peers,
        }

    except requests.RequestException:
        return None
    except Exception:
        return None
