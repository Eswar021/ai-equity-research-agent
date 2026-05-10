"""
intelligence_layer/canonical_intelligence_extraction/validators/hallucination_precheck.py — Layer 3

Early hallucination detection for LLM-derived intelligence objects.

Rules (design doc §23):
  - If supporting_text is empty for a text-derived object → downgrade confidence, add warning
  - If supporting_text is very short (< 10 chars) → warning
  - If source is labeled "opinion" but object is marked as a fact → downgrade to claim
  - If object confidence > 0.95 for a text-derived object → cap at 0.92 (LLMs overconfident)

Rule-based objects (signals, structured facts) are skipped — they don't use LLM.

Design doc: docs/system_design_docs/layer_3.md §23 hallucination_precheck.py
"""

from __future__ import annotations

_MIN_SUPPORTING_TEXT_LEN = 10
_LLM_MAX_CONFIDENCE      = 0.92
_EMPTY_TEXT_PENALTY      = -0.15
_SHORT_TEXT_PENALTY      = -0.07


def precheck(obj: dict, obj_type: str) -> dict:
    """
    Apply hallucination precheck to a single intelligence object.
    Modifies and returns the object (confidence may be lowered, warnings added).

    Args:
        obj:      intelligence object dict
        obj_type: "entity" | "fact" | "claim" | "event" | "theme"

    Returns:
        modified obj with updated confidence and 'precheck_warnings' list.
    """
    # Rule-based objects are not LLM-derived — skip
    if obj.get("_extraction_source") == "rule":
        return obj

    warnings: list[str] = list(obj.get("precheck_warnings", []))
    conf = float(obj.get("confidence", 0.70))

    refs = obj.get("source_refs", [])
    supporting_texts = [r.get("supporting_text", "") for r in refs]
    best_text = max((t for t in supporting_texts if t), key=len, default="")

    # Rule 1: Cap LLM over-confidence
    if conf > _LLM_MAX_CONFIDENCE:
        conf = _LLM_MAX_CONFIDENCE
        warnings.append(f"confidence_capped_at_{_LLM_MAX_CONFIDENCE}")

    # Rule 2: Empty supporting_text
    if not best_text.strip():
        conf += _EMPTY_TEXT_PENALTY
        warnings.append(f"supporting_text_absent (penalty={_EMPTY_TEXT_PENALTY})")

    # Rule 3: Very short supporting_text
    elif len(best_text.strip()) < _MIN_SUPPORTING_TEXT_LEN:
        conf += _SHORT_TEXT_PENALTY
        warnings.append(f"supporting_text_too_short={len(best_text.strip())} chars (penalty={_SHORT_TEXT_PENALTY})")

    # Rule 4: Newsletter/YouTube claims labeled as facts → downgrade to claim
    if obj_type == "fact":
        for ref in refs:
            rel = ref.get("source_reliability", "")
            if rel in ("medium_opinion_based", "low", "medium_low"):
                warnings.append("opinion_source_labeled_as_fact_downgraded_confidence")
                conf -= 0.10
                break

    obj["confidence"]         = round(max(0.0, min(1.0, conf)), 4)
    obj["precheck_warnings"]  = warnings
    return obj


def precheck_all(
    entities: list[dict],
    facts:    list[dict],
    claims:   list[dict],
    events:   list[dict],
    themes:   list[dict],
) -> list[dict]:
    """
    Apply precheck to all text-derived objects.
    Returns a list of precheck warning records for the quality report.
    """
    all_warnings = []
    for obj in entities:
        precheck(obj, "entity")
        if obj.get("precheck_warnings"):
            all_warnings.append({"object_id": obj.get("entity_id"), "warnings": obj["precheck_warnings"]})
    for obj in facts:
        precheck(obj, "fact")
        if obj.get("precheck_warnings"):
            all_warnings.append({"object_id": obj.get("fact_id"), "warnings": obj["precheck_warnings"]})
    for obj in claims:
        precheck(obj, "claim")
        if obj.get("precheck_warnings"):
            all_warnings.append({"object_id": obj.get("claim_id"), "warnings": obj["precheck_warnings"]})
    for obj in events:
        precheck(obj, "event")
        if obj.get("precheck_warnings"):
            all_warnings.append({"object_id": obj.get("event_id"), "warnings": obj["precheck_warnings"]})
    for obj in themes:
        precheck(obj, "theme")
        if obj.get("precheck_warnings"):
            all_warnings.append({"object_id": obj.get("theme_id"), "warnings": obj["precheck_warnings"]})
    return all_warnings
