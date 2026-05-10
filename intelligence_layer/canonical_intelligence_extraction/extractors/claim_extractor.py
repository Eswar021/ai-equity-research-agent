"""
intelligence_layer/canonical_intelligence_extraction/extractors/claim_extractor.py — Layer 3

Formats claim items from LLM output into canonical claim card objects.
Claims are opinions, forecasts, analyst views, rumors — NOT verified facts.

Design doc: docs/system_design_docs/layer_3.md §9 claim_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_claim_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"CLAIM_{today}_{_COUNTER[0]:04d}"


# Source reliability → adjusted claim confidence
# Opinion-based sources should have lower baseline
_RELIABILITY_CLAIM_WEIGHT: dict[str, float] = {
    "high":         0.90,
    "medium_high":  0.78,
    "medium":       0.65,
    "medium_low":   0.55,
    "low":          0.40,
}


def format_claims(
    llm_claims: list,   # list[ClaimItem]
    document:   dict,
    chunk:      dict,
) -> list[dict]:
    """
    Convert raw LLM claim items into canonical claim card objects.

    Returns:
        list of claim card dicts matching design doc claim card schema.
    """
    doc_id      = document.get("document_id", "")
    source_id   = (document.get("lineage") or {}).get("source_module", "")
    reliability = document.get("source_reliability", "medium")
    published   = document.get("published_at", "")

    # For newsletters/youtube/opinion, claims carry a reliability flag
    source_reliability_for_claim = (
        "medium_opinion_based"
        if reliability in ("medium_low", "low")
        else reliability
    )

    # Clamp confidence using the source reliability weight
    max_conf = _RELIABILITY_CLAIM_WEIGHT.get(reliability, 0.65)

    claims = []
    for item in llm_claims:
        claim_id = _next_claim_id()
        conf     = min(max_conf, max(0.0, float(item.confidence)))

        claims.append({
            "claim_id":              claim_id,
            "claim_type":            item.claim_type,
            "claim_text":            item.claim_text.strip(),
            "entities":              [e.strip() for e in item.entities if e.strip()],
            "requires_verification": item.requires_verification,
            "evidence_strength":     item.evidence_strength,
            "source_reliability":    source_reliability_for_claim,
            "source_refs": [{
                "document_id":       doc_id,
                "source_id":         source_id,
                "chunk_id":          chunk.get("chunk_id", ""),
                "supporting_text":   item.supporting_text or "",
                "published_at":      published,
                "source_reliability": reliability,
            }],
            "published_at":  published,
            "confidence":    conf,
        })
    return claims
