"""RSS feed scraper — returns news_article records from configured feeds."""

import time
from datetime import datetime, timedelta, timezone
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

    days_back = int(cfg.get("days_back", 3))
    cutoff    = datetime.now(IST) - timedelta(days=days_back)

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

                published_at = _parse_published(entry)

                # Skip entries older than days_back — check BEFORE scraping the URL
                # so we don't waste HTTP requests on ancient cached feed items.
                if published_at:
                    try:
                        pub_dt = datetime.fromisoformat(published_at)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=IST)
                        if pub_dt < cutoff:
                            continue
                    except Exception:
                        pass

                # Scrape full article body from the URL; fall back to feed snippet
                body = scrape_url(link, title=title) if link else ""
                content = body if body else snippet
                time.sleep(_SLEEP)

                records.append({
                    "source":       "rss",
                    "source_type":  "news_article",
                    "title":        title,
                    "url":          link,
                    "published_at": published_at,
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
