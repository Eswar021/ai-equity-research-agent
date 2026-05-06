import io
import json
import hashlib
import re
import time
from datetime import datetime, timezone, timedelta

import pdfplumber
import requests
from bs4 import BeautifulSoup

import sys
sys.path.append(str(__import__("pathlib").Path(__file__).parent.parent.parent))
from config.paths import SCREENER_IN_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
_BASE = "https://www.screener.in"


def _parse_table(section) -> list[dict]:
    """
    Parse a financial table from a screener section.
    Cells that contain only an <a> link (e.g. Raw PDF row) are stored as
    the absolute URL instead of empty text.
    """
    table = section.find("table") if section else None
    if not table:
        return []

    thead = table.find("thead")
    if not thead:
        return []

    year_cols = [th.get_text(strip=True) for th in thead.find_all("th")][1:]

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True).rstrip("+").strip()
        row = {"metric": label}
        for i, year in enumerate(year_cols):
            if (i + 1) < len(cells):
                td  = cells[i + 1]
                a   = td.find("a", href=True)
                if a:
                    href = a["href"]
                    row[year] = (_BASE + href) if href.startswith("/") else href
                else:
                    row[year] = td.get_text(strip=True)
            else:
                row[year] = ""
        rows.append(row)

    return rows


def _parse_growth_tables(section) -> dict:
    """Extract the CAGR summary blocks (Sales Growth, Profit Growth, etc.)."""
    result = {}
    for table in section.find_all("table")[1:]:
        rows = table.find_all("tr")
        title_row = rows[0].get_text(strip=True) if rows else ""
        data = {}
        for tr in rows[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) == 2:
                data[cells[0]] = cells[1]
        if title_row and data:
            result[title_row] = data
    return result


def _fetch_quarterly_pdf(source_url: str) -> dict:
    """
    Follow the screener source URL redirect to the actual BSE/NSE PDF,
    download it, and extract text with pdfplumber.
    Returns {"pdf_url": ..., "text": ...} or {"pdf_url": None, "text": None} on failure.
    """
    try:
        resp = requests.get(source_url, headers=_HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type:
            return {"pdf_url": resp.url, "text": None}

        pdf_url = resp.url
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
            text = "\n\n".join(pages_text)

        return {"pdf_url": pdf_url, "text": text}

    except Exception as e:
        return {"pdf_url": None, "text": None}


def extract_company(url: str, fetch_pdfs: bool = False, pdf_quarters: int = None) -> dict:
    """
    Scrape company data from screener.in.

    fetch_pdfs   : if True, download and extract text from quarterly result PDFs.
    pdf_quarters : how many most-recent quarters to fetch (None = all available).
    """
    html = requests.get(url, headers=_HEADERS, timeout=15).text
    soup = BeautifulSoup(html, "html.parser")

    # Company name
    h1 = soup.find("h1")
    company_name = h1.get_text(strip=True) if h1 else ""

    # Description
    profile     = soup.find("div", class_="company-profile")
    description = profile.get_text(separator=" ", strip=True) if profile else ""
    description = re.sub(r"^About\s*", "", description).strip()

    # Key ratios
    key_ratios = {}
    ratios_ul  = soup.find(id="top-ratios")
    if ratios_ul:
        for li in ratios_ul.find_all("li"):
            parts = [s.strip() for s in li.get_text(separator="|").split("|") if s.strip()]
            if len(parts) >= 2:
                key_ratios[parts[0]] = " ".join(parts[1:])

    # Pros and cons
    analysis = soup.find(id="analysis")
    pros = [li.get_text(strip=True) for li in analysis.find("div", class_="pros").find_all("li")] if analysis else []
    cons = [li.get_text(strip=True) for li in analysis.find("div", class_="cons").find_all("li")] if analysis else []

    # Financial tables
    pl_section = soup.find(id="profit-loss")
    growth     = _parse_growth_tables(pl_section) if pl_section else {}

    quarterly_results = _parse_table(soup.find(id="quarters"))

    # ── PDF extraction ────────────────────────────────────────────────────────
    quarterly_pdfs = []
    if fetch_pdfs:
        # find the Raw PDF row
        pdf_row = next((r for r in quarterly_results if r.get("metric") == "Raw PDF"), None)
        if pdf_row:
            # collect (quarter, url) pairs, skip empty / non-URL values, take last N
            quarter_links = [
                (q, v) for q, v in pdf_row.items()
                if q != "metric" and v and v.startswith("http")
            ]
            selected = quarter_links if pdf_quarters is None else quarter_links[-pdf_quarters:]
            for quarter, source_url in selected:
                result = _fetch_quarterly_pdf(source_url)
                quarterly_pdfs.append({
                    "quarter":    quarter,
                    "source_url": source_url,
                    "pdf_url":    result["pdf_url"],
                    "text":       result["text"],
                })
                time.sleep(0.5)

    return {
        "company_name":           company_name,
        "description":            description,
        "key_ratios":             key_ratios,
        "pros":                   pros,
        "cons":                   cons,
        "quarterly_results":      quarterly_results,
        "quarterly_pdfs":         quarterly_pdfs,
        "profit_loss":            _parse_table(pl_section),
        "balance_sheet":          _parse_table(soup.find(id="balance-sheet")),
        "cash_flow":              _parse_table(soup.find(id="cash-flow")),
        "ratios":                 _parse_table(soup.find(id="ratios")),
        "growth_metrics":         growth,
        "shareholding_quarterly": _parse_table(soup.find(id="quarterly-shp")),
        "shareholding_yearly":    _parse_table(soup.find(id="yearly-shp")),
    }


def save_company(url: str, fetch_pdfs: bool = False, pdf_quarters: int = None) -> str:
    data = extract_company(url, fetch_pdfs=fetch_pdfs, pdf_quarters=pdf_quarters)

    SCREENER_IN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    url_hash     = hashlib.md5(url.encode()).hexdigest()[:8]
    company_slug = re.sub(r"\s+", "_", data["company_name"]).lower()[:30]
    filename     = f"{company_slug}_{url_hash}.json"

    output = {
        "url":          url,
        "extracted_at": datetime.now(_IST).isoformat(),
        **data,
    }

    output_file = SCREENER_IN_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


if __name__ == "__main__":
    test_url = "https://www.screener.in/company/RELIANCE/consolidated/"

    print(f"Extracting: {test_url}\n")
    saved_path = save_company(test_url)  # fetch_pdfs=False by default; pass fetch_pdfs=True to extract PDFs
    print(f"Saved to: {saved_path}\n")

    with open(saved_path) as f:
        data = json.load(f)

    print(f"Company:     {data['company_name']}")
    print(f"Quarterly:   {len(data['quarterly_results'])} rows")

    # Show Raw PDF row
    pdf_row = next((r for r in data["quarterly_results"] if r.get("metric") == "Raw PDF"), {})
    if pdf_row:
        quarters = [k for k in pdf_row if k != "metric"]
        print(f"\nRaw PDF row ({len(quarters)} quarters):")
        for q in quarters[-3:]:
            print(f"  {q}: {pdf_row[q][:80]}")

    # Show extracted PDFs
    print(f"\nExtracted PDFs: {len(data['quarterly_pdfs'])}")
    for p in data["quarterly_pdfs"]:
        text_len = len(p["text"]) if p["text"] else 0
        print(f"  {p['quarter']}: {p['pdf_url']}")
        print(f"    Text: {text_len} chars")
        if p["text"]:
            print(f"    Preview: {p['text'][:200]}")
        print()
