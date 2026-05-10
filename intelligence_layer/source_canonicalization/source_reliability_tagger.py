"""
intelligence_layer/source_canonicalization/source_reliability_tagger.py — Layer 2

Assigns source reliability metadata. This is NOT investment analysis —
it is source quality metadata used by later layers to weight evidence.

Five tiers (design doc §26):
    high          — NSE filings, SEC filings, official exchange/macro data
    medium_high   — Established Indian financial news (MC, ET, BS, etc.)
    medium        — Newsletters, analyst commentary, news APIs
    medium_low    — YouTube transcripts, blogs, generic web pages
    low           — Unknown / unsourced commentary

Design doc: docs/system_design_docs/layer_2.md  §26 source_reliability_tagger.py
"""

# module_name → (reliability, reason)
_MODULE_RELIABILITY: dict[str, tuple[str, str]] = {
    # Official / exchange data  → high
    "fii_dii":         ("high",        "official_nse_institutional_flow"),
    "bulk_deals":      ("high",        "official_nse_exchange_data"),
    "fno_data":        ("high",        "official_nse_options_chain"),
    "india_macro":     ("high",        "official_statistical_macro_data"),
    "us_macro":        ("high",        "official_fred_macro_data"),
    "exchange_filings":("high",        "official_nse_corporate_disclosure"),
    "filing_docs":     ("high",        "official_nse_concall_filing"),
    "sec_filings":     ("high",        "official_sec_disclosure"),
    "market_data":     ("high",        "official_exchange_price_data"),
    "price_history":   ("high",        "official_exchange_ohlcv"),
    "screener_in":     ("medium_high", "aggregated_public_financial_data"),
    "peer_comparison": ("medium_high", "aggregated_public_financial_data"),
    "analyst_estimates":("medium",     "third_party_analyst_consensus"),
    "corporate_actions":("high",       "official_nse_corporate_actions"),
    # News scrapers → medium_high
    "moneycontrol":    ("medium_high", "established_indian_financial_news"),
    "economic_times":  ("medium_high", "established_indian_financial_news"),
    # RSS / news APIs → medium  (title+summary only, unknown publisher mix)
    "rss":             ("medium",      "mixed_publisher_rss_feed"),
    "newsdata_io":     ("medium",      "news_api_mixed_publishers"),
    "mediastack":      ("medium",      "news_api_mixed_publishers"),
    # Newsletters → medium
    "gmail":           ("medium",      "curated_newsletter_opinion_based"),
    # YouTube → medium_low (often opinion / analysis, not primary source)
    "yt_transcript":   ("medium_low",  "youtube_video_transcript"),
    "youtube":         ("medium_low",  "youtube_video_transcript"),
    # Generic web scrape → medium_low
    "generic_web":     ("medium_low",  "generic_web_extraction"),
    "browser_scraped": ("medium_low",  "browser_scraped_web_page"),
}

# source_name fallback lookup (used when module is unknown)
_SOURCE_NAME_RELIABILITY: dict[str, tuple[str, str]] = {
    "moneycontrol":        ("medium_high", "established_indian_financial_news"),
    "the economic times":  ("medium_high", "established_indian_financial_news"),
    "economic times":      ("medium_high", "established_indian_financial_news"),
    "business standard":   ("medium_high", "established_indian_financial_news"),
    "livemint":            ("medium_high", "established_indian_financial_news"),
    "mint":                ("medium_high", "established_indian_financial_news"),
    "hindu businessline":  ("medium_high", "established_indian_financial_news"),
    "financialexpress":    ("medium_high", "established_indian_financial_news"),
    "nse":                 ("high",        "official_nse_exchange_data"),
    "bse":                 ("high",        "official_bse_exchange_data"),
    "sebi":                ("high",        "official_regulator"),
    "rbi":                 ("high",        "official_central_bank"),
    "fred":                ("high",        "official_fred_macro_data"),
}


def tag_reliability(
    module: str = "",
    source_name: str = "",
    source_type: str = "",
) -> dict:
    """
    Return reliability metadata for a source.

    Lookup priority:
      1. module_name exact match
      2. source_name lowercase match
      3. source_type default
      4. fallback → "low"

    Returns:
        {"source_reliability": str, "reliability_reason": str}
    """
    module_key = (module or "").lower().strip()
    if module_key in _MODULE_RELIABILITY:
        rel, reason = _MODULE_RELIABILITY[module_key]
        return {"source_reliability": rel, "reliability_reason": reason}

    name_key = (source_name or "").lower().strip()
    if name_key in _SOURCE_NAME_RELIABILITY:
        rel, reason = _SOURCE_NAME_RELIABILITY[name_key]
        return {"source_reliability": rel, "reliability_reason": reason}

    # source_type fallbacks
    type_defaults: dict[str, tuple[str, str]] = {
        "news_article":       ("medium_high", "financial_news_article"),
        "rss_item":           ("medium",      "rss_feed_item"),
        "newsletter":         ("medium",      "newsletter_opinion_based"),
        "youtube_transcript": ("medium_low",  "youtube_transcript"),
        "news_api":           ("medium",      "news_api_item"),
        "macro_snapshot":     ("high",        "official_macro_data"),
        "institutional_flow": ("high",        "official_institutional_data"),
        "bulk_block_deals":   ("high",        "official_exchange_data"),
        "derivatives_snapshot":("high",       "official_options_chain"),
        "market_snapshot":    ("high",        "official_market_data"),
        "price_history":      ("high",        "official_ohlcv_data"),
        "fundamental_data":   ("medium_high", "public_financial_data"),
        "peer_data":          ("medium_high", "public_financial_data"),
        "analyst_consensus":  ("medium",      "analyst_consensus"),
        "regulatory_filing":  ("high",        "official_regulatory_filing"),
        "filing_document":    ("high",        "official_filing_document"),
        "corporate_action":   ("high",        "official_corporate_action"),
        "generic_web":        ("medium_low",  "generic_web_page"),
    }
    type_key = (source_type or "").lower().strip()
    if type_key in type_defaults:
        rel, reason = type_defaults[type_key]
        return {"source_reliability": rel, "reliability_reason": reason}

    return {"source_reliability": "low", "reliability_reason": "unknown_source"}
