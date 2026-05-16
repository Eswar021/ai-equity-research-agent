"""Mediastack scraper — India market news. Attempts full article scrape from URL."""

import os
import time

import requests

from src.pipeline.L1_scraping.scrapers._utils import scrape_url, clean_html_snippets

_API_KEY  = os.getenv("MEDIASTACK_API", "")
_BASE_URL = "http://api.mediastack.com/v1/news"
_API_SLEEP    = 1.0
_SCRAPE_SLEEP = 0.5


def _fetch_query(query: str) -> list[dict]:
    params = {
        "access_key": _API_KEY,
        "keywords":   query,
        "countries":  "in",
        "languages":  "en",
        "categories": "business",
        "limit":      25,
    }
    resp = requests.get(_BASE_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("data", [])


def collect(cfg: dict) -> list[dict]:
    if not _API_KEY:
        raise RuntimeError("MEDIASTACK_API env var not set")

    queries = cfg.get("queries")
    if not queries:
        raise ValueError("mediastack config missing 'queries' list")

    seen_urls: set[str] = set()
    records = []

    for query in queries:
        try:
            items = _fetch_query(query)
            for item in items:
                url = item.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title           = item.get("title", "")
                api_description = item.get("description") or title

                # For Google News redirect URLs and normal URLs alike — try scraping.
                # scrape_url follows HTTP redirects so Google News links often resolve
                # to the real article. Falls back to "" on failure.
                body = scrape_url(url, title=title) if url else ""

                if body:
                    content = body
                else:
                    # Fallback: clean the API description (strips &nbsp; noise)
                    content = clean_html_snippets(api_description)

                time.sleep(_SCRAPE_SLEEP)

                records.append({
                    "source":       "mediastack",
                    "source_type":  "news_article",
                    "title":        title,
                    "url":          url or None,
                    "published_at": item.get("published_at"),
                    "content":      content,
                    "metadata": {
                        "author":       item.get("author", ""),
                        "category":     query,
                        "source":       item.get("source", ""),
                        "full_scrape":  bool(body),
                    },
                })
            time.sleep(_API_SLEEP)
        except Exception as e:
            print(f"  [mediastack] query '{query}' failed: {e}")

    return records
