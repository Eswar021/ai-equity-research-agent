"""
intelligence_layer/canonical_intelligence_extraction/post_processors/confidence_scorer.py — Layer 3

Adjusts extraction confidence for all intelligence objects based on:
  - source reliability
  - document quality score
  - whether supporting_text is present
  - whether the object is rule-extracted (deterministic) or LLM-inferred

Design doc: docs/system_design_docs/layer_3.md §18 confidence_scorer.py
"""

from __future__ import annotations

# Source reliability → confidence adjustment
_RELIABILITY_DELTA: dict[str, float] = {
    "high":         +0.03,
    "medium_high":   0.00,
    "medium":       -0.02,
    "medium_low":   -0.05,
    "low":          -0.10,
    "medium_opinion_based": -0.08,
}


def score_object(obj: dict, doc_quality: float | None = None) -> dict:
    """
    Adjust confidence on a single intelligence object.

    Args:
        obj:         Any intelligence object dict (entity/fact/claim/event/theme/signal).
                     Must have 'confidence' and 'source_refs' fields.
        doc_quality: quality_score from the source document (0.0–1.0). None = skip.

    Returns:
        The same object dict with 'confidence' adjusted and 'confidence_reasons' added.
    """
    base_conf = float(obj.get("confidence", 0.70))
    delta     = 0.0
    reasons   = []

    # 1. Source reliability
    refs = obj.get("source_refs", [])
    if refs:
        rel = refs[0].get("source_reliability", "medium")
        d   = _RELIABILITY_DELTA.get(rel, 0.0)
        if d != 0:
            delta += d
            reasons.append(f"source_reliability={rel} ({d:+.2f})")

    # 2. Supporting text present / absent
    has_supporting = any(
        len(r.get("supporting_text", "").strip()) > 10
        for r in refs
    )
    if not has_supporting and obj.get("_extraction_source") != "rule":
        delta -= 0.12
        reasons.append("supporting_text_absent (-0.12)")
    elif has_supporting:
        reasons.append("supporting_text_present")

    # 3. Document quality score (only for text-derived objects)
    if doc_quality is not None and obj.get("_extraction_source") != "rule":
        if doc_quality < 0.30:
            delta -= 0.20
            reasons.append(f"doc_quality={doc_quality:.2f} (-0.20)")
        elif doc_quality < 0.50:
            delta -= 0.10
            reasons.append(f"doc_quality={doc_quality:.2f} (-0.10)")

    # 4. Rule-extracted objects get high baseline confidence
    if obj.get("_extraction_source") == "rule":
        base_conf = 0.95
        reasons.append("rule_based_extraction (conf=0.95)")

    final_conf = max(0.0, min(1.0, base_conf + delta))
    obj["confidence"]         = round(final_conf, 4)
    obj["confidence_reasons"] = reasons
    return obj


def score_all(
    entities: list[dict],
    facts:    list[dict],
    claims:   list[dict],
    events:   list[dict],
    themes:   list[dict],
    signals:  list[dict],
    doc_quality_map: dict[str, float] | None = None,
) -> None:
    """
    Score all intelligence objects in-place.

    Args:
        doc_quality_map: document_id → quality_score, for text-derived objects.
                         Pass None to skip document quality adjustment.
    """
    doc_quality_map = doc_quality_map or {}

    def _doc_q(obj: dict) -> float | None:
        refs = obj.get("source_refs", [])
        if refs:
            return doc_quality_map.get(refs[0].get("document_id", ""))
        return None

    for obj in entities + facts + claims + events + themes:
        score_object(obj, _doc_q(obj))
    for sig in signals:
        sig["_extraction_source"] = "rule"
        score_object(sig, None)
