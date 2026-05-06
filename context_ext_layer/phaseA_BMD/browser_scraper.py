import json
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import trafilatura
from playwright.sync_api import sync_playwright

import sys
sys.path.append(str(__import__("pathlib").Path(__file__).parent.parent.parent))
from config.paths import BROWSER_SCRAPER_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": _UA})
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
    return html


def extract_page(url: str) -> dict:
    html = fetch_html(url)
    raw  = trafilatura.extract(html, with_metadata=True, output_format="json", url=url)
    data = json.loads(raw) if raw else {}
    return {
        "title":  data.get("title"),
        "author": data.get("author"),
        "date":   data.get("date"),
        "text":   data.get("text"),
    }


def save_page(url: str) -> str:
    page_data = extract_page(url)

    BROWSER_SCRAPER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    domain   = urlparse(url).netloc.replace("www.", "")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{domain}_{url_hash}.json"

    output = {
        "url":          url,
        "extracted_at": datetime.now(_IST).isoformat(),
        **page_data,
    }

    output_file = BROWSER_SCRAPER_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


if __name__ == "__main__":
    # Works for JS-rendered sites (tickertape, trendlyne)
    # Does NOT bypass bot protection (moneycontrol, ET use Akamai)
    test_url = "https://tickertape.in/stocks/reliance-industries-RELI"

    print(f"Loading page: {test_url}\n")
    saved_path = save_page(test_url)
    print(f"Saved to: {saved_path}\n")

    with open(saved_path) as f:
        data = json.load(f)

    print(f"Title:  {data['title']}")
    print(f"Date:   {data['date']}")
    print(f"Text length: {len(data['text'] or '')} chars")
    print(f"\n--- First 500 chars ---")
    print((data["text"] or "")[:500])
