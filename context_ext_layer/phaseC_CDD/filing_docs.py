"""
NSE filing document extractor.

Downloads and extracts text from NSE filing attachments:
  - Earnings call transcripts (most recent N quarters)
  - Investor presentations (most recent N)
  - Annual reports (when available — sparse for Indian cos)

These are filed by companies with NSE and are publicly accessible.
Uses pdfplumber for text extraction.
"""

import io
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import EXCHANGE_FILINGS_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

_DOC_TYPES = {
    "transcript": [
        "analysts/institutional investor meet",
        "con. call",
        "concall",
    ],
    "presentation": [
        "investor presentation",
    ],
    "annual_report": [
        "annual report",
        "annual general meeting",
    ],
}


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=15)
    except Exception:
        pass
    return session


def _nse_symbol(ticker: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", ticker.upper())


def _classify(desc: str, subject: str) -> str | None:
    """Return doc type label or None if not a document of interest."""
    combined = (desc + " " + subject).lower()
    for label, keywords in _DOC_TYPES.items():
        if any(kw in combined for kw in keywords):
            return label
    return None


def _is_transcript(subject: str) -> bool:
    """Among concall filings, only ones that say 'transcript' have the actual text PDF."""
    return "transcript" in subject.lower()


def _extract_pdf_text(url: str, session: requests.Session, max_chars: int = 80_000) -> str | None:
    """Download a PDF from NSE and extract text with pdfplumber."""
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            return None
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t.strip())
            text = "\n\n".join(pages)
        return text[:max_chars] if text else None
    except Exception:
        return None


# ── Fetch announcements ───────────────────────────────────────────────────────

def _get_all_announcements(ticker: str, session: requests.Session) -> list[dict]:
    symbol = _nse_symbol(ticker)
    r = session.get(
        "https://www.nseindia.com/api/corporate-announcements",
        params={"index": "equities", "symbol": symbol},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ── Public functions ──────────────────────────────────────────────────────────

def fetch_concall_transcripts(ticker: str, last_n: int = 4) -> list[dict]:
    """
    Fetch and extract text from the most recent N earnings call transcripts.

    Concall transcripts are filed under 'Analysts/Institutional Investor Meet/Con. Call Updates'.
    Only filings whose subject mentions 'transcript' contain the actual text PDF.
    Audio recordings and meeting notices are skipped.

    Returns list of: {date, subject, pdf_url, text}
    """
    session = _nse_session()
    announcements = _get_all_announcements(ticker, session)

    results = []
    for item in announcements:
        desc    = item.get("desc", "")
        subject = item.get("attchmntText") or ""
        doc_type = _classify(desc, subject)

        if doc_type != "transcript":
            continue
        if not _is_transcript(subject):
            continue
        url = item.get("attchmntFile") or ""
        if not url or not url.lower().endswith(".pdf"):
            continue

        text = _extract_pdf_text(url, session)
        results.append({
            "date":    item.get("an_dt"),
            "subject": subject[:200],
            "pdf_url": url,
            "text":    text,
        })
        time.sleep(0.3)

        if len(results) >= last_n:
            break

    return results


def fetch_investor_presentations(ticker: str, last_n: int = 2) -> list[dict]:
    """
    Fetch and extract text from recent investor presentations.
    These are typically filed after quarterly results and contain slide-deck content.

    Returns list of: {date, subject, pdf_url, text}
    """
    session = _nse_session()
    announcements = _get_all_announcements(ticker, session)

    results = []
    for item in announcements:
        desc     = item.get("desc", "")
        subject  = item.get("attchmntText") or ""
        doc_type = _classify(desc, subject)

        if doc_type != "presentation":
            continue
        url = item.get("attchmntFile") or ""
        if not url or not url.lower().endswith(".pdf"):
            continue

        text = _extract_pdf_text(url, session)
        results.append({
            "date":    item.get("an_dt"),
            "subject": subject[:200],
            "pdf_url": url,
            "text":    text,
        })
        time.sleep(0.3)

        if len(results) >= last_n:
            break

    return results


def fetch_filing_docs(
    ticker: str,
    transcripts: int = 4,
    presentations: int = 2,
) -> dict:
    """
    Fetch concall transcripts and investor presentations for a stock.

    transcripts   : number of most-recent earnings call transcripts to fetch
    presentations : number of most-recent investor presentations to fetch
    """
    return {
        "ticker":          _nse_symbol(ticker),
        "transcripts":     fetch_concall_transcripts(ticker, last_n=transcripts),
        "presentations":   fetch_investor_presentations(ticker, last_n=presentations),
    }


def save_filing_docs(
    ticker: str,
    transcripts: int = 4,
    presentations: int = 2,
) -> str:
    symbol = _nse_symbol(ticker)
    data   = fetch_filing_docs(ticker, transcripts=transcripts, presentations=presentations)

    EXCHANGE_FILINGS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{symbol}_filing_docs_{today}.json"

    output = {
        "fetched_at": datetime.now(_IST).isoformat(),
        **data,
    }

    out_file = EXCHANGE_FILINGS_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "RELIANCE"

    print(f"Fetching filing docs for {ticker} ...\n")
    saved = save_filing_docs(ticker, transcripts=4, presentations=2)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    print(f"── Concall Transcripts ({len(d['transcripts'])}) ────────────────────────────")
    for t in d["transcripts"]:
        text_len = len(t["text"]) if t["text"] else 0
        print(f"  {t['date']}")
        print(f"  Subject: {t['subject'][:80]}")
        print(f"  Text: {text_len:,} chars extracted")
        if t["text"]:
            print(f"  Preview: {t['text'][:200]}")
        print()

    print(f"── Investor Presentations ({len(d['presentations'])}) ──────────────────────")
    for p in d["presentations"]:
        text_len = len(p["text"]) if p["text"] else 0
        print(f"  {p['date']}")
        print(f"  Subject: {p['subject'][:80]}")
        print(f"  Text: {text_len:,} chars extracted")
        print()
