import json
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
import trafilatura

import sys
sys.path.append(str(__import__("pathlib").Path(__file__).parent.parent.parent))
from config.paths import GENERIC_WEB_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def extract_article(url: str) -> dict:
    html = requests.get(url, headers=_HEADERS, timeout=15).text
    raw  = trafilatura.extract(html, with_metadata=True, output_format="json", url=url)
    data = json.loads(raw)
    return {
        "title":  data.get("title"),
        "author": data.get("author"),
        "date":   data.get("date"),
        "text":   data.get("text"),
    }


def save_article(url: str) -> str:
    article = extract_article(url)

    GENERIC_WEB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    domain   = urlparse(url).netloc.replace("www.", "")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{domain}_{url_hash}.json"

    output = {
        "url":          url,
        "extracted_at": datetime.now(_IST).isoformat(),
        **article,
    }

    output_file = GENERIC_WEB_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


if __name__ == "__main__":
    # Works well for: screener.in, tickertape.in, finshots.in, investing.com, open blogs
    # Does NOT work for: ET, Moneycontrol, Reuters, Bloomberg (paywalled/bot-protected)
    # test_url = "https://finshots.in/markets/why-did-the-stock-market-crash/"
    test_url = "https://finshots.in/archive/inside-indias-response-to-the-global-helium-shortage/"
    print(f"Extracting article from: {test_url}\n")
    saved_path = save_article(test_url)
    print(f"Saved to: {saved_path}\n")

    with open(saved_path) as f:
        data = json.load(f)

    print(f"Title:  {data['title']}")
    print(f"Author: {data['author']}")
    print(f"Date:   {data['date']}")
    print(f"Text length: {len(data['text'] or '')} chars")
    print(f"\n--- First 400 chars ---")
    print((data["text"] or "")[:400])
