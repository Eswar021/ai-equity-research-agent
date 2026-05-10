"""
intelligence_layer/canonical_intelligence_extraction/structured_record_router.py — Layer 3

Routes canonical structured records to the correct rule-based extractors.
No LLM is used for structured data — only deterministic code.

Design doc: docs/system_design_docs/layer_3.md §4 structured_record_router.py
"""

from __future__ import annotations

# ── record_type → ordered list of extractor names ─────────────────────────────
# Extractor names match functions in the extractors/ subpackage.
# Order matters: structured_fact_extractor usually runs first, then signal builder.

_RECORD_TYPE_TO_EXTRACTORS: dict[str, list[str]] = {
    # ── FII/DII flows ─────────────────────────────────────────────────────────
    "institutional_flow":       ["structured_fact_extractor", "market_signal_builder"],

    # ── Macro snapshots (India + US) ──────────────────────────────────────────
    "macro_snapshot":           ["structured_fact_extractor", "market_signal_builder"],

    # ── Price / market snapshots ──────────────────────────────────────────────
    "market_snapshot":          ["numeric_observation_extractor"],
    "price_history":            ["numeric_observation_extractor"],

    # ── Derivatives / F&O ─────────────────────────────────────────────────────
    "derivatives_snapshot":     ["market_signal_builder"],

    # ── Fundamental data ──────────────────────────────────────────────────────
    "indian_company_fundamentals": ["structured_fact_extractor"],
    "fundamental_data":            ["structured_fact_extractor"],

    # ── Peer / analyst data ───────────────────────────────────────────────────
    "peer_comparison":          ["structured_fact_extractor"],
    "peer_data":                ["structured_fact_extractor"],
    "analyst_estimates":        ["structured_fact_extractor"],
    "analyst_consensus":        ["structured_fact_extractor"],

    # ── Corporate actions ─────────────────────────────────────────────────────
    "corporate_actions":        ["structured_fact_extractor", "filing_metadata_extractor"],
    "corporate_action":         ["structured_fact_extractor", "filing_metadata_extractor"],

    # ── Bulk/block deals ──────────────────────────────────────────────────────
    "bulk_block_deals":         ["structured_fact_extractor", "market_signal_builder"],

    # ── SEC / regulatory filings ──────────────────────────────────────────────
    "sec_company_facts":        ["structured_fact_extractor"],
    "regulatory_filing":        ["structured_fact_extractor", "filing_metadata_extractor"],
}

_DEFAULT_EXTRACTORS = ["structured_fact_extractor"]


def route(record: dict) -> dict:
    """
    Route a canonical structured record to its extractor list.

    Returns:
        {
          "record_id":   str,
          "record_type": str,
          "extractors":  list[str],   # ordered list of extractor names to run
          "requires_llm": False,
        }
    """
    rec_id   = record.get("record_id", "")
    rec_type = (record.get("record_type") or record.get("source_type") or "").lower()

    extractors = _RECORD_TYPE_TO_EXTRACTORS.get(rec_type, _DEFAULT_EXTRACTORS)

    return {
        "record_id":    rec_id,
        "record_type":  rec_type,
        "extractors":   extractors,
        "requires_llm": False,
    }


def route_all(records: list[dict]) -> list[dict]:
    """Route all structured records. Returns list of routing decisions."""
    return [route(rec) for rec in records]
