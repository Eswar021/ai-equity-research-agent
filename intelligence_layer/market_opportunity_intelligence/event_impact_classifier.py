"""
intelligence_layer/market_opportunity_intelligence/event_impact_classifier.py — Layer 5

Rule-based classifier: maps each Layer 3 event to an event_impact_view.

Classifies:
  impact_direction        — positive / negative / neutral / mixed / unknown
  impact_strength         — low / medium / high
  temporary_or_structural — noise / temporary / medium_term / structural / unknown
  time_horizon            — short_term / medium_term / long_term / structural
  requires_deep_dive      — bool
  deep_dive_reason        — why deep dive is needed

Memory recurrence elevates importance: if the event's entity already appears
in watch or long-term memory, the event is treated as more material.

Design doc: docs/system_design_docs/layer_5.md §6 event_impact_classifier.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from intelligence_layer.market_opportunity_intelligence.intelligence_memory_loader import (
    entity_names_from_event,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_DIRECTION: dict[str, str] = {
    "earnings_beat":               "positive",
    "earnings_miss":               "negative",
    "guidance_raise":              "positive",
    "guidance_cut":                "negative",
    "margin_pressure":             "negative",
    "revenue_growth":              "positive",
    "revenue_decline":             "negative",
    "large_order_win":             "positive",
    "capex_announcement":          "positive",
    "merger_acquisition":          "mixed",
    "divestment":                  "mixed",
    "management_change":           "mixed",
    "regulatory_action":           "negative",
    "legal_issue":                 "negative",
    "fraud_or_accounting_concern": "negative",
    "credit_rating_change":        "mixed",
    "dividend":                    "positive",
    "buyback":                     "positive",
    "split_bonus":                 "positive",
    "bulk_deal":                   "mixed",
    "block_deal":                  "mixed",
    "policy_change":               "mixed",
    "rate_decision":               "mixed",
    "inflation_data":              "mixed",
    "currency_move":               "mixed",
    "commodity_move":              "mixed",
    "sector_rotation":             "mixed",
    "analyst_upgrade":             "positive",
    "analyst_downgrade":           "negative",
    "ipo_news":                    "neutral",
    "private_company_funding":     "neutral",
    "industrial_corridor":         "positive",
    "real_estate_policy":          "positive",
    "other":                       "unknown",
}

_STRUCTURAL: dict[str, str] = {
    "policy_change":               "structural",
    "industrial_corridor":         "structural",
    "real_estate_policy":          "structural",
    "regulatory_action":           "medium_term",
    "credit_rating_change":        "medium_term",
    "merger_acquisition":          "medium_term",
    "fraud_or_accounting_concern": "medium_term",
    "legal_issue":                 "medium_term",
    "capex_announcement":          "medium_term",
    "rate_decision":               "medium_term",
    "guidance_cut":                "medium_term",
    "guidance_raise":              "medium_term",
    "earnings_beat":               "temporary",
    "earnings_miss":               "temporary",
    "margin_pressure":             "temporary",
    "dividend":                    "temporary",
    "buyback":                     "temporary",
    "analyst_upgrade":             "temporary",
    "analyst_downgrade":           "temporary",
    "bulk_deal":                   "noise",
    "block_deal":                  "noise",
    "currency_move":               "temporary",
    "commodity_move":              "temporary",
    "sector_rotation":             "medium_term",
    "revenue_growth":              "temporary",
    "revenue_decline":             "temporary",
    "large_order_win":             "medium_term",
}

_TIME_HORIZON: dict[str, str] = {
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
    "margin_pressure":             "medium_term",
    "dividend":                    "short_term",
    "buyback":                     "short_term",
    "analyst_upgrade":             "short_term",
    "analyst_downgrade":           "short_term",
    "bulk_deal":                   "short_term",
    "block_deal":                  "short_term",
    "currency_move":               "short_term",
    "commodity_move":              "short_term",
    "rate_decision":               "medium_term",
    "sector_rotation":             "medium_term",
    "large_order_win":             "medium_term",
    "fraud_or_accounting_concern": "medium_term",
    "legal_issue":                 "medium_term",
}

_DEEP_DIVE_TYPES = {
    "guidance_cut", "guidance_raise", "earnings_miss", "earnings_beat",
    "fraud_or_accounting_concern", "legal_issue", "merger_acquisition",
    "regulatory_action", "credit_rating_change", "margin_pressure",
    "capex_announcement", "large_order_win", "policy_change",
    "industrial_corridor", "real_estate_policy",
}


def classify_all(events: list[dict], entity_memory_map: dict,
                 theme_memory_map: dict) -> list[dict]:
    return [classify(evt, entity_memory_map, theme_memory_map) for evt in events]


def classify(event: dict, entity_memory_map: dict, theme_memory_map: dict) -> dict:
    _CTR[0] += 1
    today    = datetime.now(_IST).strftime("%Y%m%d")
    imp_id   = f"EVT_IMPACT_{today}_{_CTR[0]:04d}"
    evt_type = event.get("event_type", "other")
    severity = event.get("severity", "low")
    l3_th    = event.get("time_horizon", "unknown")
    l3_struct = event.get("temporary_or_structural_hint", "unknown")
    conf     = float(event.get("confidence", 0.5))

    entity_names = entity_names_from_event(event)
    is_recurring = any(bool(entity_memory_map.get(n.lower())) for n in entity_names)

    direction = _DIRECTION.get(evt_type, event.get("business_impact", "unknown"))
    if direction == "unknown":
        direction = event.get("initial_sentiment", "unknown")

    strength = {"high": "high", "medium": "medium", "low": "low"}.get(severity, "low")
    if is_recurring and strength == "low":
        strength = "medium"

    struct = l3_struct if l3_struct not in ("unknown", "") else _STRUCTURAL.get(evt_type, "unknown")
    time_h = l3_th if l3_th not in ("unknown", "") else _TIME_HORIZON.get(evt_type, "unknown")

    needs_dd = (evt_type in _DEEP_DIVE_TYPES and severity in ("medium", "high")) or \
               (severity == "high") or is_recurring
    dd_reason = _deep_dive_reason(evt_type, severity, is_recurring)

    return {
        "event_impact_id":         imp_id,
        "event_id":                event.get("event_id", ""),
        "event_type":              evt_type,
        "event_title":             event.get("event_title", ""),
        "affected_entities":       entity_names,
        "impact_direction":        direction,
        "impact_strength":         strength,
        "temporary_or_structural": struct,
        "time_horizon":            time_h,
        "requires_deep_dive":      needs_dd,
        "deep_dive_reason":        dd_reason,
        "reasoning_summary":       _reasoning(evt_type, direction, strength, struct, is_recurring),
        "supporting_refs":         event.get("source_refs") or [],
        "data_gaps":               _gaps(evt_type),
        "confidence":              round(min(conf + (0.05 if is_recurring else 0), 0.95), 3),
        "memory_recurring":        is_recurring,
    }


def _deep_dive_reason(evt_type: str, severity: str, recurring: bool) -> str:
    if evt_type in {"fraud_or_accounting_concern", "legal_issue"}:
        return "High-risk event — source reliability and evidence must be verified."
    if evt_type in {"guidance_cut", "guidance_raise"}:
        return "Guidance change affects earnings trajectory — need concall/filing confirmation."
    if evt_type in {"policy_change", "industrial_corridor", "real_estate_policy"}:
        return "Structural event — need listed beneficiary mapping and implementation verification."
    if recurring:
        return "Recurring signal in memory — trend may be developing; verify with fundamentals."
    if severity == "high":
        return "High-severity event requires source and impact verification."
    return ""


def _reasoning(evt_type: str, direction: str, strength: str,
               struct: str, recurring: bool) -> list[str]:
    r = [f"{evt_type} classified as {direction} with {strength} impact."]
    if struct in ("structural", "medium_term"):
        r.append(f"Impact likely {struct} — not a one-day noise event.")
    if recurring:
        r.append("Entity/theme appears in prior memory — elevated significance.")
    return r


def _gaps(evt_type: str) -> list[str]:
    return {
        "margin_pressure":             ["Need latest margin trend", "Need management guidance"],
        "guidance_cut":                ["Need concall transcript or filing"],
        "earnings_miss":               ["Need quarterly results filing", "Need analyst revision"],
        "merger_acquisition":          ["Need regulatory approval status", "Need deal valuation"],
        "fraud_or_accounting_concern": ["Need official SEBI/MCA notice", "Need auditor statement"],
        "policy_change":               ["Need official notification", "Need listed beneficiary mapping"],
        "industrial_corridor":         ["Need corridor route details", "Need listed proxy mapping"],
    }.get(evt_type, [])
