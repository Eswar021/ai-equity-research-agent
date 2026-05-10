"""
intelligence_layer/source_canonicalization/normalizer_registry.py — Layer 2

Maps every Layer 1 module name to its normalizer function and record kind.
The runner uses this to dispatch each bundle item to the correct normalizer.

Design doc: docs/system_design_docs/layer_2.md  §4 normalizer_registry.py
"""

from __future__ import annotations
from typing import Callable

from intelligence_layer.source_canonicalization.normalizers.text_normalizers import (
    normalize_news_articles,
    normalize_rss_items,
    normalize_newsletters,
    normalize_yt_transcripts,
    normalize_filing_docs,
    normalize_news_api_items,
    normalize_generic_web,
)
from intelligence_layer.source_canonicalization.normalizers.structured_normalizers import (
    normalize_market_data,
    normalize_price_history,
    normalize_screener,
    normalize_peer_comparison,
    normalize_analyst_estimates,
    normalize_macro_snapshot,
    normalize_institutional_flow,
    normalize_bulk_deals,
    normalize_derivatives,
    normalize_corporate_actions,
    normalize_sec_filings,
)

# Each entry: module_name → (normalizer_fn, record_kind, source_display_name)
# record_kind = "document" | "structured"
#
# normalizer_fn signature:
#   text normalizers:       fn(content, module, source_name) → list[dict]
#   structured normalizers: fn(content, module)               → list[dict]
#   (runner will call the right form based on record_kind)
#
# Design doc §4 registry:
_REGISTRY: dict[str, tuple[Callable, str, str]] = {
    # ── Text-based sources ────────────────────────────────────────────────────
    "moneycontrol":    (normalize_news_articles,  "document",   "Moneycontrol"),
    "economic_times":  (normalize_news_articles,  "document",   "Economic Times"),
    "rss":             (normalize_rss_items,       "document",   "RSS Feed"),
    "gmail":           (normalize_newsletters,     "document",   "Gmail Newsletter"),
    "newsdata_io":     (normalize_news_api_items,  "document",   "Newsdata.io"),
    "mediastack":      (normalize_news_api_items,  "document",   "Mediastack"),
    "yt_transcript":   (normalize_yt_transcripts,  "document",   "YouTube"),
    "youtube":         (normalize_yt_transcripts,  "document",   "YouTube"),
    "filing_docs":     (normalize_filing_docs,     "document",   "NSE Filing"),
    "generic_web":     (normalize_generic_web,     "document",   "Generic Web"),
    "browser_scraped": (normalize_generic_web,     "document",   "Browser Scraped"),

    # ── Structured data sources ───────────────────────────────────────────────
    "market_data":        (normalize_market_data,         "structured", "NSE/Yahoo Finance"),
    "price_history":      (normalize_price_history,       "structured", "Yahoo Finance"),
    "screener_in":        (normalize_screener,            "structured", "Screener.in"),
    "peer_comparison":    (normalize_peer_comparison,     "structured", "Yahoo Finance"),
    "analyst_estimates":  (normalize_analyst_estimates,   "structured", "Yahoo Finance"),
    "india_macro":        (normalize_macro_snapshot,      "structured", "NSE / RBI"),
    "us_macro":           (normalize_macro_snapshot,      "structured", "FRED"),
    "fii_dii":            (normalize_institutional_flow,  "structured", "NSE"),
    "bulk_deals":         (normalize_bulk_deals,          "structured", "NSE"),
    "fno_data":           (normalize_derivatives,         "structured", "NSE"),
    "corporate_actions":  (normalize_corporate_actions,   "structured", "NSE"),
    "sec_filings":        (normalize_sec_filings,         "structured", "SEC EDGAR"),
}


def lookup(module_name: str) -> tuple[Callable, str, str] | None:
    """
    Return (normalizer_fn, record_kind, source_display_name) for a module.
    Returns None if module is not registered.
    """
    return _REGISTRY.get(module_name.lower().strip())


def registered_modules() -> list[str]:
    return sorted(_REGISTRY.keys())
