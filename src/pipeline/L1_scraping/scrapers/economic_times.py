"""Economic Times news scraper — article listing + full body extraction."""

import json
import re
import time
from datetime import datetime, timedelta

import requests
import trafilatura
from bs4 import BeautifulSoup

from src.config.settings import IST

_BASE    = "https://economictimes.indiatimes.com"
_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (compatible; StockResearcher/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}
_SLEEP   = 0.5
_TIMEOUT = 20

_CATEGORY_PATHS = {
    "stocks_news":  "/markets/stocks/news",
    "expert_view":  "/markets/expert-view",
    "stocks_recos": "/markets/stocks/recos",
    "commodities":  "/markets/commodities/news",
}


def _get(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _page_url(base_path: str, page: int) -> str:
    path = base_path.rstrip("/")
    return _BASE + (path if page <= 1 else f"{path}/{page}")


def _extract_jsonld(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", tag.string or "")
            data = json.loads(cleaned)
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") in ("NewsArticle", "Article"):
                return data
        except Exception:
            continue
    return {}


def _traf_body(html: str, url: str, title: str) -> str:
    try:
        raw = trafilatura.extract(html, url=url, favor_recall=True,
                                  output_format="json", with_metadata=True)
        if not raw:
            return ""
        text = json.loads(raw).get("text", "") or ""
        title_words = {w.lower() for w in re.findall(r"\b\w{5,}\b", title)}
        if title_words and not any(w in text.lower() for w in title_words):
            return ""
        return text
    except Exception:
        return ""


def _listing_items(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for story in soup.select(".eachStory"):
        a = story.find("a", href=True)
        h = story.find(["h3", "h4", "p"])
        if not a:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = _BASE + href
        items.append({
            "url":   href.split("?")[0],
            "title": (h or a).get_text(strip=True),
        })
    return items


def _scrape_article(url: str) -> dict:
    html  = _get(url)
    ld    = _extract_jsonld(html)
    title = ld.get("headline", "")
    body  = ld.get("articleBody", "") or _traf_body(html, url, title)
    author_raw = ld.get("author", {})
    return {
        "title":        title,
        "published_at": ld.get("datePublished", "") or None,
        "body":         body,
        "author":       author_raw.get("name", "") if isinstance(author_raw, dict) else "",
    }


def _scrape_category(category: str, days_back: int, max_pages: int) -> list[dict]:
    cat_path  = _CATEGORY_PATHS[category]
    from_date = (datetime.now(IST).date() - timedelta(days=days_back - 1)) if days_back else None
    articles  = []

    for page in range(1, max_pages + 1):
        html  = _get(_page_url(cat_path, page))
        items = _listing_items(html)
        if not items:
            break

        stop = False
        for item in items:
            try:
                art = _scrape_article(item["url"])
                pub_str = art.get("published_at") or ""
                if from_date and pub_str:
                    try:
                        pub_date = datetime.fromisoformat(pub_str).date()
                        if pub_date < from_date:
                            stop = True
                            break
                    except Exception:
                        pass
                listing_title = item.get("title", "")
                item.update(art)
                if not item.get("title"):
                    item["title"] = listing_title
                articles.append(item)
            except Exception:
                articles.append(item)
            time.sleep(_SLEEP)

        if stop:
            break
        time.sleep(_SLEEP)

    return articles


def collect(cfg: dict) -> list[dict]:
    days_back = cfg.get("days_back", 2)
    max_pages = cfg.get("max_pages", 5)
    categories = cfg.get("categories", list(_CATEGORY_PATHS.keys()))

    records = []
    for cat in categories:
        if cat not in _CATEGORY_PATHS:
            continue
        try:
            articles = _scrape_category(cat, days_back, max_pages)
            for art in articles:
                records.append({
                    "source":       "economic_times",
                    "source_type":  "news_article",
                    "title":        art.get("title", ""),
                    "url":          art.get("url"),
                    "published_at": art.get("published_at"),
                    "content":      art.get("body", ""),
                    "metadata":     {
                        "author":   art.get("author", ""),
                        "category": cat,
                    },
                })
        except Exception as e:
            print(f"  [economic_times] {cat} failed: {e}")

    return records
