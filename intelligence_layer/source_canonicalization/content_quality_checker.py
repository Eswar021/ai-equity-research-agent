"""
intelligence_layer/source_canonicalization/content_quality_checker.py — Layer 2

Scores each canonical document/record for content quality.
Does NOT classify investment relevance — only data completeness and usability.

Quality statuses (design doc §25):
    usable               — good to use, no significant gaps
    usable_with_warnings — usable but one or more minor issues
    partial              — significant gaps, use with caution
    unusable             — empty or fundamentally broken

Design doc: docs/system_design_docs/layer_2.md  §25 content_quality_checker.py
"""

# Minimum character counts for text documents
_MIN_USABLE_CHARS   = 200
_MIN_PARTIAL_CHARS  = 80

# Required fields for each record_type (structured records)
_REQUIRED_STRUCTURED_FIELDS: dict[str, list[str]] = {
    "market_snapshot":          ["price"],
    "price_history":            ["history"],
    "indian_company_fundamentals": ["key_ratios"],
    "peer_comparison":          ["target"],
    "analyst_estimates":        ["price_targets"],
    "macro_snapshot":           ["data"],
    "institutional_flow":       ["fii", "dii"],
    "bulk_block_deals":         ["bulk_deals"],
    "derivatives_snapshot":     ["underlying_value", "pcr"],
    "corporate_actions":        [],   # optional — no hard required fields
    "sec_company_facts":        ["key_financials"],
}


def check_document_quality(doc: dict) -> dict:
    """
    Check quality of a canonical_document (text-based source).

    Input: canonical_document dict (partially or fully populated).
    Returns: {"quality_score": float, "quality_status": str, "warnings": list[str]}
    """
    warnings: list[str] = []
    score = 1.0

    clean_text = doc.get("clean_text") or doc.get("raw_text") or ""
    text_len   = len(clean_text.strip())
    doc_type   = doc.get("document_type", "")

    # Text length checks
    if text_len == 0:
        warnings.append("empty_body")
        score -= 0.6
    elif text_len < _MIN_PARTIAL_CHARS:
        warnings.append("body_too_short")
        score -= 0.4
    elif text_len < _MIN_USABLE_CHARS:
        warnings.append("body_short")
        score -= 0.15

    # RSS/summary-only sources
    if doc_type == "rss_item" and text_len < 200:
        warnings.append("summary_only")
        score -= 0.1

    # Missing metadata
    if not doc.get("url"):
        warnings.append("missing_url")
        score -= 0.1
    if not doc.get("published_at"):
        warnings.append("missing_date")
        score -= 0.1
    if not doc.get("title"):
        warnings.append("missing_title")
        score -= 0.05

    # YouTube: empty transcript
    if doc_type == "youtube_transcript" and text_len < 100:
        warnings.append("transcript_unavailable_or_short")
        score -= 0.3

    score = max(0.0, round(score, 2))

    if score >= 0.8:
        status = "usable"
    elif score >= 0.5:
        status = "usable_with_warnings" if warnings else "usable"
    elif score >= 0.2:
        status = "partial"
    else:
        status = "unusable"

    # Override: empty body is always unusable
    if "empty_body" in warnings:
        status = "unusable"

    return {
        "quality_score":  score,
        "quality_status": status,
        "warnings":       warnings,
    }


def check_structured_quality(record: dict) -> dict:
    """
    Check quality of a canonical_structured_record.

    Input: canonical_structured_record dict.
    Returns: {"quality_score": float, "quality_status": str, "warnings": list[str], "missing_fields": list[str]}
    """
    warnings: list[str]     = []
    missing_fields: list[str] = []
    score = 1.0

    record_type = record.get("record_type", "")
    data        = record.get("data") or {}

    required = _REQUIRED_STRUCTURED_FIELDS.get(record_type, [])
    for field in required:
        val = data.get(field)
        # A value is missing if None or empty list/dict
        if val is None or val == [] or val == {}:
            missing_fields.append(field)
            warnings.append(f"missing_field:{field}")
            score -= 0.2

    if not data:
        warnings.append("empty_data")
        score -= 0.5

    score = max(0.0, round(score, 2))
    status = "usable" if score >= 0.8 else \
             "usable_with_warnings" if score >= 0.5 else \
             "partial" if score >= 0.2 else "unusable"

    return {
        "quality_score":  score,
        "quality_status": status,
        "warnings":       warnings,
        "missing_fields": missing_fields,
    }


def check_quality(record: dict, kind: str = "document") -> dict:
    """
    Unified entry point.

    Args:
        record: canonical_document or canonical_structured_record dict
        kind:   "document" | "structured"
    """
    if kind == "structured":
        return check_structured_quality(record)
    return check_document_quality(record)
