"""
intelligence_layer/memory_qualification/memory_qualification_agent.py — Layer 4

Final store / ignore / update decision engine.
Rule-based for v1 (no LLM needed for the basic qualification decision).

Decision options:
  store_new               — write as new memory record
  update_existing         — update a matched existing record
  store_as_watch          — store in watch_memory (lower conviction)
  store_as_thesis_update  — update or create thesis memory
  store_as_short_term     — short-term market memory only
  ignore_noise            — do not store
  quarantine              — store separately for review (conflicting evidence, low support)

Design doc: docs/system_design_docs/layer_4.md §9 memory_qualification_agent.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

# Override types: always store regardless of score
_ALWAYS_STORE_EVENT_TYPES = {
    "fraud_or_accounting_concern", "legal_issue", "regulatory_action",
    "credit_rating_change", "merger_acquisition",
}


def decide(candidate: dict, memory_score: int, novelty_result: dict,
           recurrence_result: dict, classification: dict,
           min_score: int = 35) -> dict:
    """
    Make the final memory decision for a candidate.

    Returns:
        {
            memory_decision_id, candidate_id, decision, memory_type,
            memory_score, decision_reason, retention_days, decay_policy,
            matched_memory_ids, confidence, review_required
        }
    """
    _CTR[0] += 1
    today   = datetime.now(_IST).strftime("%Y%m%d")
    dec_id  = f"MEMDEC_{today}_{_CTR[0]:04d}"

    cid          = candidate["candidate_id"]
    obj          = candidate.get("_obj") or {}
    obj_type     = candidate.get("source_object_type", "")
    novelty      = novelty_result.get("novelty_status", "new")
    matched_ids  = novelty_result.get("matched_memory_ids", [])
    mem_type     = classification.get("memory_type", "short_term_market_memory")
    ret_days     = classification.get("retention_days", 30)
    decay        = classification.get("decay_policy", "medium_decay")
    conf         = candidate.get("source_confidence", 0.5)
    source_refs  = candidate.get("source_refs") or []
    evt_type     = obj.get("event_type", "")
    review_req   = False

    # Hallucination guard: no source_refs → quarantine
    if not source_refs:
        return _dec(dec_id, cid, "quarantine", mem_type, memory_score,
                    "No source_refs — cannot verify provenance", ret_days, decay,
                    matched_ids, conf, review_required=True)

    # Override: high-severity official event always stored
    if obj_type == "event" and evt_type in _ALWAYS_STORE_EVENT_TYPES:
        decision = "update_existing" if matched_ids else "store_new"
        return _dec(dec_id, cid, decision, mem_type, memory_score,
                    f"Override: {evt_type} always stored regardless of score",
                    ret_days, decay, matched_ids, conf)

    # Duplicate → ignore
    if novelty == "duplicate":
        return _dec(dec_id, cid, "ignore_noise", mem_type, memory_score,
                    "Duplicate of existing memory — not stored again",
                    ret_days, decay, matched_ids, conf)

    # Score-based decision
    if memory_score < min_score:
        return _dec(dec_id, cid, "ignore_noise", mem_type, memory_score,
                    f"Score {memory_score} below minimum {min_score}",
                    ret_days, decay, matched_ids, conf)

    # Contradiction → quarantine for review
    if novelty == "contradiction":
        review_req = True
        return _dec(dec_id, cid, "quarantine", mem_type, memory_score,
                    "Contradicts existing memory — stored for review",
                    ret_days, decay, matched_ids, conf, review_required=True)

    # Thesis memory
    if mem_type == "thesis_memory":
        decision = "store_as_thesis_update" if matched_ids else "store_new"
        return _dec(dec_id, cid, decision, mem_type, memory_score,
                    "Thesis-worthy event — creating or updating thesis",
                    ret_days, decay, matched_ids, conf)

    # Recurring / update → update existing
    if novelty in ("recurring", "update_to_existing") and matched_ids:
        return _dec(dec_id, cid, "update_existing", mem_type, memory_score,
                    f"Recurring/updating existing memory ({matched_ids[0]})",
                    ret_days, decay, matched_ids, conf)

    # Score thresholds
    if memory_score >= 80:
        decision = "store_new"
        reason   = f"High relevance score {memory_score} — storing as {mem_type}"
    elif memory_score >= 65:
        if mem_type in ("long_term_investment_memory", "thesis_memory"):
            decision = "store_as_watch"
            mem_type = "watch_memory"
        else:
            decision = "store_new"
        reason = f"Score {memory_score} — moderate relevance"
    elif memory_score >= 50:
        decision = "store_as_short_term"
        mem_type = "short_term_market_memory"
        reason   = f"Score {memory_score} — short-term only"
    else:
        decision = "ignore_noise"
        reason   = f"Score {memory_score} — insufficient relevance"

    return _dec(dec_id, cid, decision, mem_type, memory_score, reason,
                ret_days, decay, matched_ids, conf, review_required=review_req)


def _dec(dec_id: str, cid: str, decision: str, mem_type: str, score: int,
         reason: str, ret_days: int, decay: str, matched: list,
         conf: float, review_required: bool = False) -> dict:
    return {
        "memory_decision_id":     dec_id,
        "candidate_id":           cid,
        "decision":               decision,
        "memory_type":            mem_type,
        "memory_score":           score,
        "decision_reason":        reason,
        "retention_days":         ret_days,
        "decay_policy":           decay,
        "matched_memory_ids":     matched,
        "confidence":             round(conf, 3),
        "review_required":        review_required,
    }
