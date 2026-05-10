"""
intelligence_layer/source_canonicalization/normalizers/text_normalizers.py — Layer 2

Normalizers for all text-based Layer 1 collectors. Each function takes
the raw collector JSON content (already loaded as a Python dict/list)
and returns a list of canonical_document dicts.

Covered collectors (design doc §5–9, §12):
    normalize_news_articles   → moneycontrol, economic_times
    normalize_rss_items       → rss
    normalize_newsletters     → gmail
    normalize_yt_transcripts  → yt_transcript
    normalize_filing_docs     → filing_docs
    normalize_news_api_items  → newsdata_io, mediastack
    normalize_generic_web     → generic_web, browser_scraped

All produce the canonical_document schema from layer_2.md §2.

Design doc: docs/system_design_docs/layer_2.md  §5-9
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from intelligence_layer.source_canonicalization.text_cleaner          import clean_text
from intelligence_layer.source_canonicalization.content_fingerprint   import fingerprint
from intelligence_layer.source_canonicalization.source_reliability_tagger import tag_reliability


def _base_doc(
    module: str,
    source_name: str,
    document_type: str,
    source_type: str,
    market: str = "india",
    target_context: dict | None = None,
) -> dict:
    """Return a canonical_document skeleton with required constant fields."""
    rel = tag_reliability(module=module, source_type=source_type)
    return {
        "document_type":     document_type,
        "source_type":       source_type,
        "source_name":       source_name,
        "source_reliability": rel["source_reliability"],
        "reliability_reason": rel["reliability_reason"],
        "market":            market,
        "language":          "en",
        "content_format":    "extracted_text",
        "target_context":    target_context or {
            "target_id": None, "target_type": None,
            "ticker": None, "entity_name": None,
        },
    }


# ── 1. News articles — Moneycontrol / Economic Times ─────────────────────────

def normalize_news_articles(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §5 (news_article_normalizer).
    Input: {"category": str, "articles": [{url, title, author, published, body}]}
    """
    articles = content.get("articles") or []
    docs: list[dict] = []
    for art in articles:
        raw_text = art.get("body") or art.get("description") or ""
        cleaned  = clean_text(raw_text, source_type="news_article")
        fp       = fingerprint(
            url   = art.get("url", ""),
            title = art.get("title", ""),
            text  = cleaned["clean_text"],
        )
        doc = {
            **_base_doc(module, source_name, "news_article", "news_article"),
            "title":        art.get("title", ""),
            "url":          art.get("url", ""),
            "author":       art.get("author") or art.get("authors", ""),
            "publisher":    source_name,
            "published_at": art.get("published") or art.get("modified") or "",
            "raw_text":     raw_text,
            "clean_text":   cleaned["clean_text"],
            "text_length_chars": len(cleaned["clean_text"]),
            "cleaning_notes":    cleaned["cleaning_notes"],
            "fingerprint":  fp,
            "duplicate_status": {
                "is_duplicate":              False,
                "duplicate_group_id":        None,
                "canonical_document_for_group": True,
            },
        }
        docs.append(doc)
    return docs


# ── 2. RSS items ──────────────────────────────────────────────────────────────

def normalize_rss_items(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §6 (rss_item_normalizer).
    Input: {"feed_name": str, "articles": [{title, url, published, summary}]}
    """
    feed_name = content.get("feed_name") or source_name
    articles  = content.get("articles") or []
    docs: list[dict] = []
    for art in articles:
        raw_text = (art.get("summary") or art.get("description") or "").strip()
        if art.get("title"):
            raw_text = art["title"] + ". " + raw_text
        cleaned  = clean_text(raw_text, source_type="rss_item")
        fp       = fingerprint(
            url   = art.get("url", "") or art.get("link", ""),
            title = art.get("title", ""),
            text  = cleaned["clean_text"],
        )
        doc = {
            **_base_doc(module, feed_name, "rss_item", "rss_item"),
            "title":        art.get("title", ""),
            "url":          art.get("url") or art.get("link") or "",
            "author":       art.get("author", ""),
            "publisher":    feed_name,
            "published_at": art.get("published") or art.get("pub_date") or "",
            "raw_text":     raw_text,
            "clean_text":   cleaned["clean_text"],
            "text_length_chars": len(cleaned["clean_text"]),
            "cleaning_notes":    cleaned["cleaning_notes"],
            "content_quality_status": "summary_only",
            "needs_full_article_fetch": True,
            "fingerprint":  fp,
            "duplicate_status": {
                "is_duplicate": False, "duplicate_group_id": None,
                "canonical_document_for_group": True,
            },
        }
        docs.append(doc)
    return docs


# ── 3. Newsletters — Gmail ────────────────────────────────────────────────────

def normalize_newsletters(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §7 (newsletter_normalizer).
    Input: {"newsletters": [{subject, sender, date, body}]}
    """
    newsletters = content.get("newsletters") or []
    docs: list[dict] = []
    for nl in newsletters:
        raw_text = nl.get("body") or ""
        cleaned  = clean_text(raw_text, source_type="newsletter")
        sender   = nl.get("sender") or nl.get("from_domain") or source_name
        fp       = fingerprint(
            title = nl.get("subject", ""),
            text  = cleaned["clean_text"],
        )
        doc = {
            **_base_doc(module, sender, "newsletter", "newsletter"),
            "title":        nl.get("subject", ""),
            "url":          "",
            "author":       sender,
            "publisher":    sender,
            "published_at": nl.get("date") or nl.get("received_at") or "",
            "raw_text":     raw_text,
            "clean_text":   cleaned["clean_text"],
            "text_length_chars": len(cleaned["clean_text"]),
            "cleaning_notes":    cleaned["cleaning_notes"],
            "fingerprint":  fp,
            "duplicate_status": {
                "is_duplicate": False, "duplicate_group_id": None,
                "canonical_document_for_group": True,
            },
        }
        docs.append(doc)
    return docs


# ── 4. YouTube transcripts ────────────────────────────────────────────────────

def normalize_yt_transcripts(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §8 (youtube_transcript_normalizer).
    Input: single video dict with transcript segments list.
    Also handles: list of video dicts (save_all_channels output).
    """
    if isinstance(content, list):
        docs: list[dict] = []
        for item in content:
            docs.extend(normalize_yt_transcripts(item, module, source_name))
        return docs

    segments  = content.get("transcript") or []
    raw_text  = " ".join(seg.get("text", "") for seg in segments).strip()
    cleaned   = clean_text(raw_text, source_type="youtube_transcript")
    channel   = content.get("channel_name") or source_name

    fp = fingerprint(
        url   = content.get("url", "") or content.get("video_url", ""),
        title = content.get("title", ""),
        text  = cleaned["clean_text"],
    )
    return [{
        **_base_doc(module, channel, "youtube_transcript", "youtube_transcript"),
        "title":        content.get("title", ""),
        "url":          content.get("url") or content.get("video_url") or "",
        "author":       channel,
        "publisher":    channel,
        "published_at": content.get("published_at") or content.get("fetched_at") or "",
        "raw_text":     raw_text,
        "clean_text":   cleaned["clean_text"],
        "text_length_chars":  len(cleaned["clean_text"]),
        "cleaning_notes":     cleaned["cleaning_notes"],
        "transcript_segments": segments,
        "fingerprint":  fp,
        "duplicate_status": {
            "is_duplicate": False, "duplicate_group_id": None,
            "canonical_document_for_group": True,
        },
    }]


# ── 5. Filing documents (concall transcripts, investor presentations) ─────────

def normalize_filing_docs(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §9 (filing_doc_normalizer).
    Input: {"ticker": str, "transcripts": [{date, subject, pdf_url, text}],
                           "presentations": [{date, subject, pdf_url, text}]}
    """
    ticker = content.get("ticker", "")
    target_ctx = {
        "target_id": None, "target_type": "listed_company",
        "ticker": ticker, "entity_name": None,
    }
    docs: list[dict] = []
    for kind, doc_type in [("transcripts", "concall_transcript"),
                           ("presentations", "investor_presentation")]:
        for item in content.get(kind) or []:
            raw_text = item.get("text") or ""
            cleaned  = clean_text(raw_text, source_type="filing_document")
            fp = fingerprint(
                url   = item.get("pdf_url", ""),
                title = item.get("subject", ""),
                text  = cleaned["clean_text"],
            )
            doc = {
                **_base_doc(module, "NSE Filing", doc_type,
                            "filing_document", target_context=target_ctx),
                "title":        item.get("subject", ""),
                "url":          item.get("pdf_url") or item.get("url") or "",
                "author":       ticker,
                "publisher":    "NSE Filing",
                "published_at": item.get("date") or "",
                "raw_text":     raw_text,
                "clean_text":   cleaned["clean_text"],
                "text_length_chars": len(cleaned["clean_text"]),
                "cleaning_notes":    cleaned["cleaning_notes"],
                "fingerprint":  fp,
                "duplicate_status": {
                    "is_duplicate": False, "duplicate_group_id": None,
                    "canonical_document_for_group": True,
                },
            }
            docs.append(doc)
    return docs


# ── 6. News API items — newsdata_io / mediastack ──────────────────────────────

def normalize_news_api_items(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §4-5 (news_api source).
    Input: {"query": str, "articles": [{title, description, url, source, published}]}
    """
    articles = content.get("articles") or content.get("results") or []
    docs: list[dict] = []
    for art in articles:
        raw_text = (art.get("description") or art.get("content") or "").strip()
        if art.get("title"):
            raw_text = art["title"] + ". " + raw_text
        cleaned  = clean_text(raw_text, source_type="news_api")
        publisher = art.get("source") or art.get("source_name") or source_name
        fp = fingerprint(
            url   = art.get("url") or art.get("link") or "",
            title = art.get("title", ""),
            text  = cleaned["clean_text"],
        )
        doc = {
            **_base_doc(module, publisher, "news_api_item", "news_api"),
            "title":        art.get("title", ""),
            "url":          art.get("url") or art.get("link") or "",
            "author":       art.get("author", ""),
            "publisher":    publisher,
            "published_at": art.get("published") or art.get("published_at") or
                            art.get("pub_date") or "",
            "raw_text":     raw_text,
            "clean_text":   cleaned["clean_text"],
            "text_length_chars": len(cleaned["clean_text"]),
            "cleaning_notes":    cleaned["cleaning_notes"],
            "content_quality_status": "summary_only",
            "fingerprint":  fp,
            "duplicate_status": {
                "is_duplicate": False, "duplicate_group_id": None,
                "canonical_document_for_group": True,
            },
        }
        docs.append(doc)
    return docs


# ── 7. Generic web / browser-scraped pages ────────────────────────────────────

def normalize_generic_web(content: dict, module: str, source_name: str) -> list[dict]:
    """
    Design doc §generic_web (A9, A10).
    Input: single page dict {url, title, author, date, text} OR list of them.
    """
    if isinstance(content, list):
        docs: list[dict] = []
        for item in content:
            docs.extend(normalize_generic_web(item, module, source_name))
        return docs

    raw_text = content.get("text") or content.get("body") or ""
    cleaned  = clean_text(raw_text, source_type="generic_web")
    publisher = (
        content.get("source") or content.get("domain")
        or _domain_from_url(content.get("url", "")) or source_name
    )
    fp = fingerprint(
        url   = content.get("url", ""),
        title = content.get("title", ""),
        text  = cleaned["clean_text"],
    )
    return [{
        **_base_doc(module, publisher, "generic_web_page", "generic_web"),
        "title":        content.get("title", ""),
        "url":          content.get("url", ""),
        "author":       content.get("author", ""),
        "publisher":    publisher,
        "published_at": content.get("date") or content.get("extracted_at") or "",
        "raw_text":     raw_text,
        "clean_text":   cleaned["clean_text"],
        "text_length_chars": len(cleaned["clean_text"]),
        "cleaning_notes":    cleaned["cleaning_notes"],
        "fingerprint":  fp,
        "duplicate_status": {
            "is_duplicate": False, "duplicate_group_id": None,
            "canonical_document_for_group": True,
        },
    }]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return ""
