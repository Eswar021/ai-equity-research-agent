import json
import re
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import requests
import trafilatura
from bs4 import BeautifulSoup

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import ET_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MCNewsMonitor/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}
_BASE  = "https://economictimes.indiatimes.com"
_SLEEP = 0.5

# Add / remove categories here
CATEGORIES = {
    "stocks_news":  "/markets/stocks/news",
    "expert_view":  "/markets/expert-view",
    "stocks_recos": "/markets/stocks/recos",
    "commodities":  "/markets/commodities/news",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _page_url(base_path: str, page: int) -> str:
    # ET pagination: /markets/stocks/news  →  /markets/stocks/news/2
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


def _parse_date(iso_str: str) -> date | None:
    try:
        return datetime.fromisoformat(iso_str).date()
    except Exception:
        return None


def _traf_body(html: str, url: str, title: str) -> str:
    """
    Extract article body via trafilatura. Returns empty string if extraction
    looks like sidebar noise (no significant title words found in result).
    """
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
        a       = story.find("a", href=True)
        h       = story.find(["h3", "h4", "p"])
        time_el = story.find("time")
        if not a:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = _BASE + href
        items.append({
            "url":       href.split("?")[0],
            "title":     (h or a).get_text(strip=True),
            "timestamp": time_el.get_text(strip=True) if time_el else "",
        })
    return items


# ── core functions ────────────────────────────────────────────────────────────

def scrape_article(url: str) -> dict:
    html   = _get(url)
    ld     = _extract_jsonld(html)
    author = ld.get("author", {})
    title  = ld.get("headline", "")
    body   = ld.get("articleBody", "") or _traf_body(html, url, title)
    return {
        "url":         url,
        "title":       title,
        "author":      author.get("name", "") if isinstance(author, dict) else "",
        "published":   ld.get("datePublished", ""),
        "modified":    ld.get("dateModified", ""),
        "description": ld.get("description", ""),
        "body":        body,
    }


def scrape_listing(cat_path: str, from_date: date | None = None, max_pages: int = 5) -> list[dict]:
    """
    Fetch articles with full body text.
    from_date: include articles published on or after this date; stop pagination
               when an article older than from_date is confirmed. None = no filter.
    """
    all_items = []

    for page in range(1, max_pages + 1):
        html  = _get(_page_url(cat_path, page))
        items = _listing_items(html)
        if not items:
            break

        stop = False
        for item in items:
            try:
                art = scrape_article(item["url"])
                pub = _parse_date(art.get("published", ""))
                time.sleep(_SLEEP)
                if from_date is not None and pub is not None and pub < from_date:
                    stop = True
                    break                  # confirmed older — stop this page
                item.update(art)
                all_items.append(item)
            except Exception:
                all_items.append(item)    # body fetch failed — keep listing data

        if stop:
            break
        time.sleep(_SLEEP)

    return all_items


def save_category(category_name: str, days_back: int = 1, max_pages: int = 5) -> str:
    """
    days_back: fetch articles from the last N days (1 = today, 2 = today+yesterday, 0 = no filter).
    Always fetches full article body for every article.
    """
    cat_path  = CATEGORIES[category_name]
    from_date = (datetime.now(_IST).date() - timedelta(days=days_back - 1)) if days_back else None
    articles  = scrape_listing(cat_path, from_date=from_date, max_pages=max_pages)

    ET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{category_name}_{today}.json"

    output = {
        "category":   category_name,
        "fetched_at": datetime.now(_IST).isoformat(),
        "days_back":  days_back,
        "total":      len(articles),
        "articles":   articles,
    }

    out_file = ET_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    category = "stocks_news"

    print(f"Scraping ET › {category} | last 2 days\n")
    saved = save_category(category, days_back=2, max_pages=3)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        data = json.load(f)

    print(f"Articles fetched: {data['total']}\n")
    for a in data["articles"][:3]:
        print(f"Title:     {a.get('title','')[:70]}")
        print(f"Published: {a.get('published','')}")
        print(f"Author:    {a.get('author','')}")
        print(f"Body:      {len(a.get('body',''))} chars")
        print()
