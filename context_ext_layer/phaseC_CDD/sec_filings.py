"""
SEC EDGAR filing collector — no API key required.
Collects: key financials (XBRL), recent 10-K / 10-Q / 8-K metadata, optional filing text.

SEC rate limit: 10 req/sec  |  User-Agent header is mandatory.
"""

import json
import re
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import SEC_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_HEADERS = {
    "User-Agent":      "StockResearcher research@example.com",
    "Accept-Encoding": "gzip, deflate",
}
_SLEEP = 0.15   # keep well under 10 req/sec

_CIK_CACHE = Path(__file__).parent / "cik_cache.json"

# XBRL concept names to try, in priority order, for each metric
_XBRL_METRICS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_basic":  ["EarningsPerShareBasic"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "operating_income": ["OperatingIncomeLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
}


# ── CIK lookup ────────────────────────────────────────────────────────────────

def _load_cik_map(refresh: bool = False) -> dict:
    """Load ticker → CIK map, cached locally. Refreshes if older than 7 days."""
    if not refresh and _CIK_CACHE.exists():
        cache = json.loads(_CIK_CACHE.read_text())
        refreshed = date.fromisoformat(cache.get("refreshed", "2000-01-01"))
        if (date.today() - refreshed).days < 7:
            return cache["map"]

    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=_HEADERS, timeout=20
    )
    r.raise_for_status()
    raw = r.json()

    ticker_map = {
        v["ticker"].upper(): {
            "cik":  str(v["cik_str"]).zfill(10),
            "name": v["title"],
        }
        for v in raw.values()
    }

    _CIK_CACHE.write_text(json.dumps(
        {"refreshed": date.today().isoformat(), "map": ticker_map},
        ensure_ascii=False
    ))
    return ticker_map


def get_cik(ticker: str) -> tuple[str, str]:
    """
    Return (zero-padded CIK, company name) for a US ticker.
    Raises KeyError if not found.
    """
    cik_map = _load_cik_map()
    entry   = cik_map[ticker.upper()]
    return entry["cik"], entry["name"]


# ── XBRL key financials ───────────────────────────────────────────────────────

def _extract_metric(gaap: dict, concept_names: list[str], form_filter: str, last_n: int) -> list[dict]:
    """Try each concept name in order; return last_n entries matching form_filter."""
    for name in concept_names:
        if name not in gaap:
            continue
        units   = gaap[name]["units"]
        entries = units.get("USD") or units.get("USD/shares") or units.get("shares") or []
        filtered = [
            {"period_end": e["end"], "value": e["val"], "form": e["form"]}
            for e in entries
            if e.get("form") == form_filter
        ]
        # deduplicate by period_end (keep last occurrence)
        seen = {}
        for e in filtered:
            seen[e["period_end"]] = e
        deduped = sorted(seen.values(), key=lambda x: x["period_end"])
        if deduped:
            return deduped[-last_n:]
    return []


def fetch_key_financials(cik: str, annual_periods: int = 5, quarterly_periods: int = 8) -> dict:
    """
    Fetch structured financial metrics from SEC XBRL company facts.
    Returns annual (10-K) and quarterly (10-Q) data for each key metric.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r   = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(_SLEEP)

    gaap = r.json().get("facts", {}).get("us-gaap", {})

    result = {}
    for metric, concepts in _XBRL_METRICS.items():
        result[metric] = {
            "annual":    _extract_metric(gaap, concepts, "10-K", annual_periods),
            "quarterly": _extract_metric(gaap, concepts, "10-Q", quarterly_periods),
        }
    return result


# ── Filing list ───────────────────────────────────────────────────────────────

def fetch_recent_filings(
    cik: str,
    form_types: list[str] = None,
    limit_per_type: int = 5,
) -> dict[str, list[dict]]:
    """
    Return recent filings grouped by form type.
    form_types defaults to ["10-K", "10-Q", "8-K"].
    Each entry: {accession_no, filing_date, report_date, primary_doc, doc_url, description}
    """
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r   = requests.get(url, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    time.sleep(_SLEEP)

    recent = r.json()["filings"]["recent"]
    cik_int = str(int(cik))   # no leading zeros for the archive URL path

    filings_by_type: dict[str, list] = {ft: [] for ft in form_types}

    n = len(recent["form"])
    for i in range(n):
        form = recent["form"][i]
        if form not in form_types:
            continue
        if len(filings_by_type[form]) >= limit_per_type:
            continue

        accession  = recent["accessionNumber"][i]
        acc_clean  = accession.replace("-", "")
        primary    = recent["primaryDocument"][i]
        doc_url    = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary}"

        filings_by_type[form].append({
            "accession_no":  accession,
            "filing_date":   recent["filingDate"][i],
            "report_date":   recent.get("reportDate", [""] * n)[i],
            "primary_doc":   primary,
            "doc_url":       doc_url,
            "items":         recent.get("items", [""] * n)[i],  # 8-K item codes
        })

    return filings_by_type


# ── Filing text extraction ────────────────────────────────────────────────────

def fetch_filing_text(doc_url: str, max_chars: int = 50_000) -> str:
    """
    Download a filing HTML document and extract clean text.
    Truncated to max_chars to keep context manageable.
    """
    r = requests.get(doc_url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(_SLEEP)

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "ix:hidden"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


# ── Save ──────────────────────────────────────────────────────────────────────

def save_sec_data(
    ticker: str,
    fetch_financials: bool = True,
    fetch_filings: bool = True,
    fetch_texts: bool = False,
    text_form_types: list[str] = None,
    limit_per_type: int = 5,
) -> str:
    """
    Collect and save SEC data for a US-listed ticker.

    fetch_financials : pull key financial metrics from XBRL
    fetch_filings    : pull recent 10-K / 10-Q / 8-K filing metadata
    fetch_texts      : download and extract text from the most recent filing
                       of each type in text_form_types (default: ["8-K"])
    """
    if text_form_types is None:
        text_form_types = ["8-K"]

    cik, company_name = get_cik(ticker)

    output: dict = {
        "ticker":       ticker.upper(),
        "cik":          cik,
        "company_name": company_name,
        "fetched_at":   datetime.now(_IST).isoformat(),
    }

    if fetch_financials:
        output["key_financials"] = fetch_key_financials(cik)

    if fetch_filings:
        output["recent_filings"] = fetch_recent_filings(cik, limit_per_type=limit_per_type)

        if fetch_texts and output.get("recent_filings"):
            filing_texts = {}
            for form_type in text_form_types:
                filings = output["recent_filings"].get(form_type, [])
                if filings:
                    most_recent = filings[0]
                    filing_texts[form_type] = {
                        "filing_date": most_recent["filing_date"],
                        "doc_url":     most_recent["doc_url"],
                        "text":        fetch_filing_text(most_recent["doc_url"]),
                    }
            output["filing_texts"] = filing_texts

    SEC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{ticker.upper()}_{today}.json"

    out_file = SEC_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "AAPL"

    print(f"Fetching SEC data for {ticker} ...\n")
    saved = save_sec_data(ticker, fetch_financials=True, fetch_filings=True, fetch_texts=False)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"Company : {d['company_name']}  (CIK {d['cik']})")

    print("\n── Key Financials ──────────────────────")
    for metric, data in d["key_financials"].items():
        annual = data["annual"]
        if annual:
            latest = annual[-1]
            print(f"  {metric:25s} latest annual: {latest['value']:>20,}  ({latest['period_end']})")

    print("\n── Recent Filings ──────────────────────")
    for form_type, filings in d["recent_filings"].items():
        print(f"  {form_type}:")
        for f_ in filings[:3]:
            print(f"    {f_['filing_date']}  {f_['doc_url']}")
