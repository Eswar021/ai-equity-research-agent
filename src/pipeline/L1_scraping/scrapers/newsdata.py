"""Newsdata.io scraper — latest India market news. Scrapes full article body from URL."""

import os
import time
from datetime import datetime, timezone

import requests

from src.config.settings import IST
from src.pipeline.L1_scraping.scrapers._utils import scrape_url

_API_KEY  = os.getenv("NEWSDATA_API", "")
_BASE_URL = "https://newsdata.io/api/1/latest"
_API_SLEEP = 1.0
_SCRAPE_SLEEP = 0.5


def _fetch_query(query: str) -> list[dict]:
    params = {
        "apikey":   _API_KEY,
        "q":        query,
        "country":  "in",
        "language": "en",
        "category": "business",
    }
    resp = requests.get(_BASE_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results", [])


def collect(cfg: dict) -> list[dict]:
    if not _API_KEY:
        raise RuntimeError("NEWSDATA_API env var not set")

    queries = cfg.get("queries")
    if not queries:
        raise ValueError("newsdata_io config missing 'queries' list")

    seen_urls: set[str] = set()
    records = []

    for query in queries:
        try:
            items = _fetch_query(query)
            for item in items:
                url = item.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                api_description = item.get("description") or item.get("title", "")
                title = item.get("title", "")

                # Try scraping the full article; fall back to API description
                body = scrape_url(url, title=title) if url else ""
                content = body if body else api_description
                time.sleep(_SCRAPE_SLEEP)

                # newsdata.io returns pubDate as "YYYY-MM-DD HH:MM:SS" in UTC (no tz marker).
                # Parse explicitly so downstream fromisoformat() gets a timezone-aware string.
                raw_pub = item.get("pubDate")
                try:
                    published_at = (
                        datetime.strptime(raw_pub, "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=timezone.utc)
                        .astimezone(IST)
                        .isoformat()
                    )
                except Exception:
                    published_at = raw_pub or None

                records.append({
                    "source":       "newsdata_io",
                    "source_type":  "news_article",
                    "title":        title,
                    "url":          url or None,
                    "published_at": published_at,
                    "content":      content,
                    "metadata": {
                        "author":       (item.get("creator") or [""])[0] if isinstance(item.get("creator"), list) else "",
                        "category":     query,
                        "source":       item.get("source_id", ""),
                        "full_scrape":  bool(body),
                    },
                })
            time.sleep(_API_SLEEP)
        except Exception as e:
            print(f"  [newsdata_io] query '{query}' failed: {e}")

    return records
