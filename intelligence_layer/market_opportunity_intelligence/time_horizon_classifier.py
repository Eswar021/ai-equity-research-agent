"""
intelligence_layer/market_opportunity_intelligence/time_horizon_classifier.py — Layer 5

Rule-based time horizon classifier.
Validates/enriches LLM-assigned time horizons on each opportunity hypothesis
using origin event types and theme type rules.

Outputs one time_horizon_view per hypothesis.

Design doc: docs/system_design_docs/layer_5.md §10 time_horizon_classifier.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

# Event-type → canonical horizon
_EVT_HORIZON: dict[str, str] = {
    "policy_change":               "long_term",
    "industrial_corridor":         "long_term",
    "real_estate_policy":          "long_term",
    "capex_announcement":          "medium_term",
    "merger_acquisition":          "medium_term",
    "regulatory_action":           "medium_term",
    "credit_rating_change":        "medium_term",
    "guidance_cut":                "medium_term",
    "guidance_raise":              "medium_term",
    "earnings_beat":               "short_term",
    "earnings_miss":               "short_term",
    "dividend":                    "short_term",
    "buyback":                     "short_term",
    "analyst_upgrade":             "short_term",
    "analyst_downgrade":           "short_term",
    "bulk_deal":                   "short_term",
    "block_deal":                  "short_term",
    "margin_pressure":             "medium_term",
    "large_order_win":             "medium_term",
    "fraud_or_accounting_concern": "medium_term",
    "legal_issue":                 "medium_term",
    "revenue_growth":              "short_term",
    "revenue_decline":             "short_term",
    "rate_decision":               "medium_term",
    "sector_rotation":             "medium_term",
}

# Theme type → canonical horizon
_THEME_HORIZON: dict[str, str] = {
    "macro_theme":        "medium_term",
    "policy_theme":       "long_term",
    "technology_theme":   "long_term",
    "cross_domain_theme": "long_term",
    "sector_theme":       "medium_term",
    "regional_theme":     "long_term",
    "commodity_theme":    "short_term",
    "other":              "medium_term",
}

_STRUCTURAL_TYPES = {"policy_change", "industrial_corridor", "real_estate_policy"}

_HORIZON_ORDER = ["short_term", "medium_term", "long_term", "structural"]


def classify_all(hypotheses: list[dict], signal_groups: list[dict]) -> list[dict]:
    """
    Produce one time_horizon_view per hypothesis.
    Uses origin signal group event types to validate/override LLM horizon.
    """
    grp_by_id: dict[str, dict] = {
        g["signal_group_id"]: g for g in signal_groups
    }
    return [_classify(hyp, grp_by_id) for hyp in hypotheses]


def _classify(hyp: dict, grp_by_id: dict[str, dict]) -> dict:
    _CTR[0] += 1
    today  = datetime.now(_IST).strftime("%Y%m%d")
    thv_id = f"THV_{today}_{_CTR[0]:04d}"

    origin        = hyp.get("origin") or {}
    grp_id        = origin.get("signal_group_id", "")
    grp           = grp_by_id.get(grp_id, {})
    events_detail = grp.get("events_detail") or []
    theme_type    = grp.get("theme_type", "other") or "other"

    # Derive horizon from event types
    event_horizons = [
        _EVT_HORIZON.get(e.get("event_type", ""), "medium_term")
        for e in events_detail
    ]
    rule_horizon = _majority_horizon(event_horizons) if event_horizons else \
                   _THEME_HORIZON.get(theme_type, "medium_term")

    # Structural override: any structural event → at least long_term
    has_structural = any(
        e.get("event_type") in _STRUCTURAL_TYPES for e in events_detail
    )
    if has_structural and rule_horizon not in ("long_term", "structural"):
        rule_horizon = "long_term"

    # LLM-assigned horizon (from hypothesis generator)
    llm_horizon = hyp.get("time_horizon", "medium_term") or "medium_term"

    # Take the longer of rule vs LLM (more conservative / forward-looking)
    primary = _longer(rule_horizon, llm_horizon)

    # Secondary: add the shorter if different
    secondary: list[str] = []
    if rule_horizon != primary:
        secondary.append(rule_horizon)
    if llm_horizon != primary and llm_horizon not in secondary:
        secondary.append(llm_horizon)

    reason = _build_reason(rule_horizon, llm_horizon, primary, theme_type, has_structural)

    return {
        "time_horizon_view_id":   thv_id,
        "object_id":              hyp.get("opportunity_id", ""),
        "object_type":            "opportunity_hypothesis",
        "primary_time_horizon":   primary,
        "secondary_time_horizons": secondary,
        "rule_derived_horizon":   rule_horizon,
        "llm_assigned_horizon":   llm_horizon,
        "horizon_reason":         reason,
        "confidence":             round(hyp.get("confidence", 0.5), 3),
    }


def _majority_horizon(horizons: list[str]) -> str:
    if not horizons:
        return "medium_term"
    counts: dict[str, int] = {}
    for h in horizons:
        counts[h] = counts.get(h, 0) + 1
    return max(counts, key=lambda k: counts[k])


def _longer(a: str, b: str) -> str:
    ia = _HORIZON_ORDER.index(a) if a in _HORIZON_ORDER else 1
    ib = _HORIZON_ORDER.index(b) if b in _HORIZON_ORDER else 1
    return _HORIZON_ORDER[max(ia, ib)]


def _build_reason(rule: str, llm: str, final: str,
                  theme_type: str, has_structural: bool) -> list[str]:
    r: list[str] = []
    if has_structural:
        r.append("Structural event detected (policy/corridor) — horizon at least long_term.")
    r.append(f"Rule-based horizon (from event types / theme '{theme_type}'): {rule}.")
    if llm != rule:
        r.append(f"LLM-assigned horizon: {llm}. Adopted the longer ({final}).")
    else:
        r.append(f"LLM and rule-based horizons agree: {final}.")
    return r
