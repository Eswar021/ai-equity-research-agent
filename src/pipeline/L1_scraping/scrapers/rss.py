"""RSS feed scraper — returns news_article records from configured feeds."""

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

from src.config.settings import IST
from src.pipeline.L1_scraping.scrapers._utils import scrape_url

_SLEEP = 0.5


def _clean_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _parse_published(entry) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc).astimezone(IST)
                return dt.isoformat()
            except Exception:
                pass
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(IST).isoformat()
        except Exception:
            pass
    return None


def _feed_snippet(entry) -> str:
    for attr in ("summary", "description"):
        val = getattr(entry, attr, None)
        if val:
            return _clean_html(val)
    content = getattr(entry, "content", [])
    if content:
        return _clean_html(content[0].get("value", ""))
    return ""


def collect(cfg: dict) -> list[dict]:
    feeds = cfg.get("feeds")
    if not feeds:
        raise ValueError("rss config missing 'feeds' list")

    records = []
    for feed_cfg in feeds:
        name = feed_cfg["name"]
        url  = feed_cfg["url"]
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                link    = getattr(entry, "link", None)
                title   = getattr(entry, "title", "") or ""
                snippet = _feed_snippet(entry)

                if not (title or snippet):
                    continue

                # Scrape full article body from the URL; fall back to feed snippet
                body = scrape_url(link, title=title) if link else ""
                content = body if body else snippet
                time.sleep(_SLEEP)

                records.append({
                    "source":       "rss",
                    "source_type":  "news_article",
                    "title":        title,
                    "url":          link,
                    "published_at": _parse_published(entry),
                    "content":      content,
                    "metadata":     {
                        "feed_name":    name,
                        "feed_url":     url,
                        "full_scrape":  bool(body),
                    },
                })
        except Exception as e:
            print(f"  [rss] {name} failed: {e}")
    return records
