import json
from datetime import datetime, timezone, timedelta

import feedparser
from bs4 import BeautifulSoup

import sys
sys.path.append(str(__import__("pathlib").Path(__file__).parent.parent.parent))
from config.paths import RSS_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def _clean(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(strip=True)


def _get_summary(entry) -> str:
    # RSS feeds use different field names — try each in priority order
    for field in ("summary", "description", "content"):
        val = entry.get(field)
        if isinstance(val, list):           # feedparser wraps 'content' in a list
            val = val[0].get("value", "")
        cleaned = _clean(val or "")
        if cleaned:
            return cleaned
    return ""


def fetch_feed(url: str) -> list[dict]:
    feed = feedparser.parse(url)
    articles = []
    for e in feed.entries:
        articles.append({
            "title":     _clean(e.get("title", "")),
            "url":       e.get("link", ""),
            "published": e.get("published", ""),
            "summary":   _get_summary(e),
        })
    return articles


def save_feed(feed_name: str, url: str) -> str:
    articles = fetch_feed(url)

    RSS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{feed_name}_{today}.json"

    output = {
        "feed_name":  feed_name,
        "url":        url,
        "fetched_at": datetime.now(_IST).isoformat(),
        "total":      len(articles),
        "articles":   articles,
    }

    output_file = RSS_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


def save_all_feeds(feeds: dict) -> list[str]:
    return [save_feed(name, url) for name, url in feeds.items()]


if __name__ == "__main__":
    import yaml
    from pathlib import Path
    cfg   = yaml.safe_load((Path(__file__).parent.parent.parent / "config" / "phase_a.yaml").read_text())
    feeds = cfg["rss_feeds"]

    print("Fetching all feeds...\n")
    paths = save_all_feeds(feeds)

    for path in paths:
        with open(path) as f:
            data = json.load(f)
        name    = data["feed_name"]
        total   = data["total"]
        empty   = sum(1 for a in data["articles"] if not a["summary"])
        has_sum = total - empty
        print(f"[{name}]  {total} articles | {has_sum} with summary | {empty} title-only")
        if data["articles"]:
            print(f"  Latest: {data['articles'][0]['title'][:75]}")
        print()
