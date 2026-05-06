import json
import os
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

import sys
sys.path.append(str(__import__("pathlib").Path(__file__).parent.parent.parent))
from config.paths import NEWSDATA_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

load_dotenv()
_API_KEY = os.getenv("NEWSDATA_API")
_BASE    = "https://newsdata.io/api/1/latest"

# Free tier: 200 credits/day — each call uses 1 credit
# description is free; content/sentiment/ai_tag are paid-only


def fetch_news(query: str, country: str = "in", language: str = "en", limit: int = 10) -> list[dict]:
    resp = requests.get(_BASE, params={
        "apikey":   _API_KEY,
        "q":        query,
        "country":  country,
        "language": language,
        "size":     limit,
    }, timeout=15)
    resp.raise_for_status()
    articles = []
    for a in resp.json().get("results", []):
        articles.append({
            "title":       a.get("title", ""),
            "description": a.get("description", ""),
            "url":         a.get("link", ""),
            "source":      a.get("source_name", ""),
            "published":   a.get("pubDate", ""),
            "keywords":    a.get("keywords") or [],
        })
    return articles


def save_news(query: str, country: str = "in", language: str = "en", limit: int = 10) -> str:
    articles = fetch_news(query, country, language, limit)

    NEWSDATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    slug     = query.replace(" ", "_").lower()[:40]
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{slug}_{today}.json"

    output = {
        "query":      query,
        "fetched_at": datetime.now(_IST).isoformat(),
        "total":      len(articles),
        "articles":   articles,
    }

    output_file = NEWSDATA_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


if __name__ == "__main__":
    query = "Nifty Sensex stock market India"

    print(f"Searching: '{query}'\n")
    saved_path = save_news(query, limit=10)
    print(f"Saved to: {saved_path}\n")

    with open(saved_path) as f:
        data = json.load(f)

    print(f"Total: {data['total']} articles\n")
    for a in data["articles"][:5]:
        print(f"[{a['source']}] {a['title'][:70]}")
        print(f"  {(a['description'] or '')[:100]}...")
        print()
