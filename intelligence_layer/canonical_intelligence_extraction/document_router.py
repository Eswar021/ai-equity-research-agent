"""
intelligence_layer/canonical_intelligence_extraction/document_router.py — Layer 3

Routes canonical text documents to the correct extraction strategy.
A news article, YouTube transcript, newsletter, and filing use different prompts
because their structure, language, and expected intelligence objects differ.

Design doc: docs/system_design_docs/layer_3.md §3 document_router.py
"""

from __future__ import annotations

# ── Extraction profile registry ────────────────────────────────────────────────
# Each profile maps to a key in prompt_registry.
# chunk_strategy: "none" | "sentence_boundary" | "speaker" | "heading"

_PROFILES: dict[str, dict] = {
    "news_extraction": {
        "extraction_profile": "news_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_500,
        "chunk_strategy":    "sentence_boundary",
        "expected_outputs":  ["entities", "facts", "claims", "events", "themes"],
    },
    "newsletter_extraction": {
        "extraction_profile": "newsletter_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_500,
        "chunk_strategy":    "sentence_boundary",
        "expected_outputs":  ["entities", "claims", "themes"],
    },
    "transcript_extraction": {
        "extraction_profile": "transcript_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_000,
        "chunk_strategy":    "speaker",
        "expected_outputs":  ["entities", "facts", "claims", "events", "themes"],
    },
    "concall_extraction": {
        "extraction_profile": "concall_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_000,
        "chunk_strategy":    "speaker",
        "expected_outputs":  ["entities", "facts", "claims", "events", "themes"],
    },
    "filing_extraction": {
        "extraction_profile": "filing_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_000,
        "chunk_strategy":    "heading",
        "expected_outputs":  ["entities", "facts", "events"],
    },
    "headline_extraction": {
        "extraction_profile": "headline_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   1_500,
        "chunk_strategy":    "none",
        "expected_outputs":  ["entities", "events"],
    },
    "generic_extraction": {
        "extraction_profile": "generic_extraction",
        "requires_llm":      True,
        "max_chunk_chars":   3_500,
        "chunk_strategy":    "sentence_boundary",
        "expected_outputs":  ["entities", "facts", "claims", "events", "themes"],
    },
}

# ── document_type → profile key ────────────────────────────────────────────────
_TYPE_TO_PROFILE: dict[str, str] = {
    "news_article":            "news_extraction",
    "newsletter":              "newsletter_extraction",
    "email_newsletter":        "newsletter_extraction",
    "youtube_transcript":      "transcript_extraction",
    "youtube":                 "transcript_extraction",
    "concall_transcript":      "concall_extraction",
    "earnings_transcript":     "concall_extraction",
    "investor_presentation":   "filing_extraction",
    "filing_document":         "filing_extraction",
    "exchange_filing":         "filing_extraction",
    "rss_item":                "headline_extraction",
    "rss_article":             "headline_extraction",
    "generic_web":             "generic_extraction",
    "browser_scraped":         "generic_extraction",
    "web_article":             "generic_extraction",
}


def route(document: dict) -> dict:
    """
    Route a canonical document to its extraction profile.

    Args:
        document: canonical_document dict with at minimum 'document_type' and 'document_id'.

    Returns:
        routing_decision dict:
        {
          "document_id":        str,
          "document_type":      str,
          "extraction_profile": str,
          "requires_llm":       bool,
          "max_chunk_chars":    int,
          "chunk_strategy":     str,
          "expected_outputs":   list[str],
          "source_reliability": str,
          "skip":               bool,  # True if clean_text is too short
          "skip_reason":        str | None,
        }
    """
    doc_id   = document.get("document_id", "")
    doc_type = (document.get("document_type") or document.get("source_type") or "").lower()

    profile_key  = _TYPE_TO_PROFILE.get(doc_type, "generic_extraction")
    profile      = _PROFILES[profile_key].copy()

    # Skip docs with no usable text
    clean_text = document.get("clean_text") or document.get("body") or ""
    skip        = len(clean_text.strip()) < 40
    skip_reason = "text_too_short" if skip else None

    return {
        "document_id":        doc_id,
        "document_type":      doc_type,
        "source_reliability": document.get("source_reliability", "medium"),
        "skip":               skip,
        "skip_reason":        skip_reason,
        **profile,
    }


def route_all(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Route all documents. Returns (routed, skipped) lists of routing decisions.
    Skipped docs have skip=True and should not be sent to extractors.
    """
    routed:  list[dict] = []
    skipped: list[dict] = []
    for doc in documents:
        decision = route(doc)
        (skipped if decision["skip"] else routed).append(decision)
    return routed, skipped
