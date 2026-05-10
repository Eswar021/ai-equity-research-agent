"""
intelligence_layer/source_canonicalization/content_fingerprint.py — Layer 2

Creates hashes for deduplication and traceability. Used by both the
normalizers (to populate fingerprint fields) and the deduplicator (to
detect exact and near-exact duplicates).

Design doc: docs/system_design_docs/layer_2.md  §23 content_fingerprint.py

Note: simhash (fuzzy text similarity) is deferred. URL + content hash
covers the vast majority of real duplicates from Indian finance sources.
"""

import hashlib
import re
import unicodedata
from urllib.parse import urlparse, urlencode, parse_qsl

# UTM and tracking parameters to strip from URLs before hashing
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "referrer", "source", "fbclid", "gclid", "mc_eid",
    "mc_cid", "yclid", "_ga",
})


def _normalize_url(url: str) -> str:
    """Lowercase URL, strip tracking params, strip trailing slash."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip().lower())
        clean_qs = urlencode(
            [(k, v) for k, v in parse_qsl(parsed.query) if k not in _TRACKING_PARAMS]
        )
        normalized = parsed._replace(query=clean_qs, fragment="").geturl()
        return normalized.rstrip("/")
    except Exception:
        return url.strip().lower()


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/extra spaces for title comparison."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", title.lower())
    t = re.sub(r"[^\w\s]", " ", t)   # remove punctuation
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def hash_url(url: str) -> str:
    return _md5(_normalize_url(url)) if url else ""


def hash_title(title: str) -> str:
    return _md5(_normalize_title(title)) if title else ""


def hash_content(text: str) -> str:
    """Hash first 3000 chars of clean text — sufficient for dedup."""
    return _md5(text[:3000].strip()) if text else ""


def fingerprint(url: str = "", title: str = "", text: str = "") -> dict:
    """
    Build a fingerprint dict for a document.

    Returns:
        {
            "url_hash":     str,
            "title_hash":   str,
            "content_hash": str,
            "dedup_key":    str   # url_hash if url present, else content_hash
        }
    """
    uh = hash_url(url)
    th = hash_title(title)
    ch = hash_content(text)
    return {
        "url_hash":     uh,
        "title_hash":   th,
        "content_hash": ch,
        "dedup_key":    uh if uh else ch,
    }


def normalized_url(url: str) -> str:
    """Expose normalized URL for source ledger entries."""
    return _normalize_url(url)


def normalized_title(title: str) -> str:
    """Expose normalized title for near-dedup comparison."""
    return _normalize_title(title)
