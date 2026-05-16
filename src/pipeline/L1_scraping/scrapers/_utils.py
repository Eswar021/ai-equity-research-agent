"""
Shared URL scraping utility for L1 scrapers.
Used by rss, newsdata, and mediastack — all have a URL but only a short snippet
as content. This fetches the full article body from the URL.
"""

import re
import json

import requests
import trafilatura

_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 20


def scrape_url(url: str, title: str = "") -> str:
    """
    Fetch URL (following HTTP redirects) and extract main article text.
    Falls back to empty string on any failure — callers decide what to do with that.
    Works for normal article URLs and Google News redirect URLs alike.
    """
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()

        raw = trafilatura.extract(
            resp.text,
            url=resp.url,
            favor_recall=True,
            output_format="json",
            with_metadata=True,
        )
        if not raw:
            return ""

        text = json.loads(raw).get("text", "") or ""

        # Noise filter: at least one significant word from the title must appear in the body
        if title:
            title_words = {w.lower() for w in re.findall(r"\b\w{5,}\b", title)}
            if title_words and not any(w in text.lower() for w in title_words):
                return ""

        return text
    except Exception:
        return ""


def clean_html_snippets(text: str) -> str:
    """
    Clean aggregated HTML snippet content (e.g. Google News multi-source blurbs).
    Strips &nbsp; entities and collapses whitespace.
    Used as fallback when URL scraping fails.
    """
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text
