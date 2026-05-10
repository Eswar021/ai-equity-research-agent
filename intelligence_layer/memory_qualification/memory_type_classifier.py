"""
intelligence_layer/memory_qualification/memory_type_classifier.py — Layer 4

Rule-based classifier that decides which memory bucket should store a candidate.

Memory buckets:
  working_memory              — current run only
  short_term_market_memory    — 7-30 trading days
  watch_memory                — 1-12 months
  long_term_investment_memory — 1-5 years
  thesis_memory               — open-ended investment thesis
  portfolio_memory            — user positions (deferred)

Design doc: docs/system_design_docs/layer_4.md §8 memory_type_classifier.py
"""

from __future__ import annotations

# ── Structural event/theme types that deserve long-term memory ───────────────
_LT_EVENT_TYPES = {
    "policy_change", "industrial_corridor", "real_estate_policy",
    "regulatory_action", "credit_rating_change", "merger_acquisition",
    "fraud_or_accounting_concern", "legal_issue", "rate_decision",
}
_LT_THEME_TYPES = {
    "macro_theme", "policy_theme", "technology_theme", "cross_domain_theme",
}
# Event types that make good thesis seeds
_THESIS_EVENT_TYPES = {
    "policy_change", "industrial_corridor", "capex_announcement",
    "large_order_win", "technology_theme",
}


def classify(candidate: dict, memory_score: int,
             novelty_status: str, recurrence: dict | None) -> dict:
    """
    Classify a scored memory candidate into a memory type and retention policy.

    Returns:
        {candidate_id, memory_type, retention_days, decay_policy, reason}
    """
    cid      = candidate["candidate_id"]
    obj      = candidate.get("_obj") or {}
    obj_type = candidate.get("source_object_type", "")
    th       = candidate.get("initial_time_horizon", "unknown")
    recurrence_level = (recurrence or {}).get("recurrence", {}).get("recurrence_level", "none")

    mem_type, ret_days, decay = _classify_impl(
        obj, obj_type, th, memory_score, novelty_status, recurrence_level
    )
    return {
        "candidate_id":  cid,
        "memory_type":   mem_type,
        "retention_days": ret_days,
        "decay_policy":  decay,
        "reason":        _reason(mem_type, obj_type, obj),
    }


# ── Core classification logic ─────────────────────────────────────────────────

def _classify_impl(obj: dict, obj_type: str, time_horizon: str,
                   score: int, novelty: str, recurrence_level: str) -> tuple[str, int, str]:
    evt_type   = obj.get("event_type", "")
    theme_type = obj.get("theme_type", "")
    severity   = obj.get("severity", "low")

    # Market signals → always short-term
    if obj_type == "market_signal":
        sig_type = obj.get("signal_type", "")
        if "derivatives" in sig_type or "fno" in sig_type.lower():
            return "short_term_market_memory", 5, "fast_decay"
        return "short_term_market_memory", 14, "medium_decay"

    # Thesis-worthy structural events with long horizon
    if (obj_type == "event" and evt_type in _THESIS_EVENT_TYPES
            and time_horizon in ("long_term", "medium_term")
            and score >= 70):
        return "thesis_memory", 0, "no_decay"  # thesis has no fixed retention

    # Long-term structural
    if obj_type == "event" and evt_type in _LT_EVENT_TYPES and score >= 60:
        return "long_term_investment_memory", 1095, "slow_decay"

    if obj_type == "theme" and theme_type in _LT_THEME_TYPES and score >= 60:
        return "long_term_investment_memory", 730, "slow_decay"

    # Watch memory: developing, recurring, or high-severity
    if score >= 65 or recurrence_level in ("medium", "high"):
        ret = 180 if time_horizon in ("medium_term", "long_term") else 90
        return "watch_memory", ret, "medium_decay"

    if severity in ("medium", "high") and obj_type in ("event", "claim"):
        return "watch_memory", 90, "medium_decay"

    # Recurring short-term
    if recurrence_level == "low" and obj_type in ("event", "theme", "market_signal"):
        return "short_term_market_memory", 30, "medium_decay"

    # Facts: short-term unless structural
    if obj_type == "fact":
        if obj.get("fact_type") in {"macro_policy_fact", "regulatory_fact"}:
            return "long_term_investment_memory", 365, "slow_decay"
        return "short_term_market_memory", 30, "fast_decay"

    # Claims: watch
    if obj_type == "claim":
        if obj.get("requires_verification"):
            return "watch_memory", 60, "medium_decay"
        return "short_term_market_memory", 14, "fast_decay"

    # Fallback
    if score >= 50:
        return "short_term_market_memory", 30, "medium_decay"
    return "working_memory", 1, "fast_decay"


def _reason(mem_type: str, obj_type: str, obj: dict) -> str:
    evt_type = obj.get("event_type") or obj.get("theme_type") or obj_type
    return {
        "long_term_investment_memory": f"Structural {evt_type} with multi-year relevance",
        "thesis_memory":               f"Investment hypothesis seed from {evt_type}",
        "watch_memory":                f"Developing {obj_type} requiring monitoring",
        "short_term_market_memory":    f"Short-term {obj_type} signal",
        "working_memory":              f"Low-signal {obj_type} — current run only",
        "portfolio_memory":            f"Portfolio-related {obj_type}",
    }.get(mem_type, f"Classified as {mem_type}")
