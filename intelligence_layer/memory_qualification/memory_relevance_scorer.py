"""
intelligence_layer/memory_qualification/memory_relevance_scorer.py — Layer 4

10-dimension future-usefulness scorer. Max 100 points.
Pure rule-based — no LLM.

Dimensions:
  structural_score          0-20
  recurrence_score          0-15
  source_reliability_score  0-15
  actionability_score       0-15
  entity_importance_score   0-10
  theme_importance_score    0-10
  novelty_score             0-10
  time_horizon_score        0-10
  portfolio_or_watch_score  0-10
  evidence_quality_score    0-10

Design doc: docs/system_design_docs/layer_4.md §5 memory_relevance_scorer.py
"""

from __future__ import annotations

_STRUCTURAL_EVENT_TYPES = {
    "policy_change", "industrial_corridor", "real_estate_policy",
    "regulatory_action", "credit_rating_change", "merger_acquisition",
    "fraud_or_accounting_concern", "legal_issue", "rate_decision",
    "capex_announcement",
}
_HIGH_VALUE_FACT_TYPES = {
    "macro_policy_fact", "regulatory_fact", "earnings_fact",
    "revenue_fact", "institutional_flow_fact",
}
_STRUCTURAL_THEME_TYPES = {
    "macro_theme", "policy_theme", "technology_theme", "cross_domain_theme",
}


def score(candidate: dict, recurrence: dict | None = None,
          novelty_status: str = "new", watch_tickers: set | None = None) -> dict:
    """
    Score a memory candidate on 10 dimensions.

    Args:
        candidate:       memory candidate dict from memory_candidate_builder
        recurrence:      output from recurrence_tracker (may be None)
        novelty_status:  one of: new, duplicate, recurring, update_to_existing, contradiction
        watch_tickers:   set of tickers the user is watching (for portfolio_or_watch_score)

    Returns:
        {candidate_id, memory_score, score_breakdown, score_reason}
    """
    obj      = candidate.get("_obj") or {}
    obj_type = candidate.get("source_object_type", "")
    cid      = candidate["candidate_id"]

    s = _structural_score(obj, obj_type)
    r = _recurrence_score(recurrence)
    sr = _source_reliability_score(candidate, obj)
    a = _actionability_score(obj, obj_type)
    ei = _entity_importance_score(candidate)
    ti = _theme_importance_score(candidate, obj, obj_type)
    n = _novelty_score(novelty_status)
    th = _time_horizon_score(candidate, obj)
    pw = _portfolio_watch_score(candidate, watch_tickers)
    eq = _evidence_quality_score(candidate, obj)

    total = s + r + sr + a + ei + ti + n + th + pw + eq

    reasons = _build_reasons(s, r, sr, a, ei, ti, n, th, pw, eq, obj, obj_type, novelty_status)

    return {
        "candidate_id": cid,
        "memory_score": total,
        "score_breakdown": {
            "structural_score":         s,
            "recurrence_score":         r,
            "source_reliability_score": sr,
            "actionability_score":      a,
            "entity_importance_score":  ei,
            "theme_importance_score":   ti,
            "novelty_score":            n,
            "time_horizon_score":       th,
            "portfolio_or_watch_score": pw,
            "evidence_quality_score":   eq,
        },
        "score_reason": reasons,
    }


# ── Individual dimension scorers ─────────────────────────────────────────────

def _structural_score(obj: dict, obj_type: str) -> int:
    """0-20: is this a structural / long-lasting signal?"""
    if obj_type == "event":
        if obj.get("event_type") in _STRUCTURAL_EVENT_TYPES:
            return 18 if obj.get("severity") == "high" else 14
        if obj.get("temporary_or_structural_hint") == "structural":
            return 12
        return 4
    if obj_type == "theme":
        if obj.get("theme_type") in _STRUCTURAL_THEME_TYPES:
            return 16
        return 6
    if obj_type == "fact":
        if obj.get("fact_type") in _HIGH_VALUE_FACT_TYPES:
            return 10
        return 4
    if obj_type == "claim":
        return 6
    if obj_type == "market_signal":
        return 3
    return 4


def _recurrence_score(recurrence: dict | None) -> int:
    """0-15: how many times has this appeared before?"""
    if not recurrence:
        return 0
    level = recurrence.get("recurrence_level", "none")
    return {"high": 15, "medium": 10, "low": 5, "none": 0}.get(level, 0)


def _source_reliability_score(candidate: dict, obj: dict) -> int:
    """0-15: how trustworthy is the source?"""
    rel = (candidate.get("source_reliability") or obj.get("source_reliability") or "medium").lower()
    return {"high": 15, "medium": 10, "low": 4, "unknown": 6}.get(rel, 6)


def _actionability_score(obj: dict, obj_type: str) -> int:
    """0-15: does this drive an investment action?"""
    if obj_type == "event":
        sev = obj.get("severity", "low")
        scope = obj.get("impact_scope") or []
        base = {"high": 12, "medium": 8, "low": 3}.get(sev, 3)
        if "company" in scope and ("macro" in scope or "sector" in scope):
            base = min(base + 3, 15)
        return base
    if obj_type == "market_signal":
        return 10
    if obj_type == "fact" and obj.get("metric_value"):
        return 8
    if obj_type == "claim" and obj.get("claim_type") in {"management_guidance", "forecast"}:
        return 8
    return 4


def _entity_importance_score(candidate: dict) -> int:
    """0-10: are listed companies involved?"""
    entities = candidate.get("linked_entities") or []
    obj      = candidate.get("_obj") or {}
    if not entities:
        return 0
    # if the source object has tickers resolved, score higher
    ticker = obj.get("ticker") or obj.get("ticker_hint")
    if ticker:
        return 10
    return min(len(entities) * 3, 8)


def _theme_importance_score(candidate: dict, obj: dict, obj_type: str) -> int:
    """0-10: is this a meaningful market theme?"""
    if obj_type == "theme":
        if obj.get("theme_type") in _STRUCTURAL_THEME_TYPES:
            return 10
        return 6
    themes = candidate.get("linked_themes") or []
    return min(len(themes) * 3, 8)


def _novelty_score(novelty_status: str) -> int:
    """0-10: how new is this to our memory?"""
    return {
        "new":                  10,
        "update_to_existing":   7,
        "contradiction":        8,
        "recurring":            5,
        "duplicate":            0,
    }.get(novelty_status, 5)


def _time_horizon_score(candidate: dict, obj: dict) -> int:
    """0-10: longer time horizon = more memory value."""
    th = (candidate.get("initial_time_horizon") or
          obj.get("time_horizon") or
          obj.get("time_horizon_hint") or "unknown")
    return {"long_term": 10, "medium_term": 7, "short_term": 4, "unknown": 3}.get(th, 3)


def _portfolio_watch_score(candidate: dict, watch_tickers: set | None) -> int:
    """0-10: is this about a ticker the user watches?"""
    if not watch_tickers:
        return 0
    obj    = candidate.get("_obj") or {}
    ticker = obj.get("ticker") or obj.get("ticker_hint")
    if ticker and ticker in watch_tickers:
        return 10
    entities = candidate.get("linked_entities") or []
    for e in entities:
        if e in watch_tickers:
            return 7
    return 0


def _evidence_quality_score(candidate: dict, obj: dict) -> int:
    """0-10: does the source have supporting text and source refs?"""
    score = 0
    if obj.get("supporting_text"):
        score += 5
    if candidate.get("source_refs"):
        score += 5
    return score


# ── Reason builder ────────────────────────────────────────────────────────────

def _build_reasons(s, r, sr, a, ei, ti, n, th, pw, eq,
                   obj: dict, obj_type: str, novelty_status: str) -> list[str]:
    reasons = []
    if s >= 14:
        reasons.append("Structural event/theme with long-term relevance")
    elif s >= 10:
        reasons.append("Moderately structural signal")
    if r >= 10:
        reasons.append("Recurring theme — seen multiple times")
    elif r >= 5:
        reasons.append("Some recurrence detected")
    if sr >= 14:
        reasons.append("High-reliability source")
    if a >= 10:
        reasons.append("High-severity actionable event")
    if novelty_status == "contradiction":
        reasons.append("Contradicts existing memory — review needed")
    elif novelty_status == "recurring":
        reasons.append("Recurrence of known pattern")
    if th >= 9:
        reasons.append("Long-term time horizon")
    if pw >= 7:
        reasons.append("Involves watched/held ticker")
    if not reasons:
        reasons.append(f"{obj_type} with moderate signal strength")
    return reasons
