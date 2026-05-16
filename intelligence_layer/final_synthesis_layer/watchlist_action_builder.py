"""
intelligence_layer/final_synthesis_layer/watchlist_action_builder.py — Layer 10

Converts final action labels into structured watchlist/monitor/avoid actions.
Pure Python, no LLM.
"""

from __future__ import annotations
from datetime import date, timedelta


_REVIEW_DAYS = {
    "research_candidate":    14,
    "watchlist":             30,
    "wait_for_confirmation": 30,
    "avoid_for_now":         60,
    "too_speculative":       90,
}

_ACTION_TYPES = {
    "research_candidate":    "add_to_research_list",
    "watchlist":             "add_to_watchlist",
    "wait_for_confirmation": "add_to_watchlist",
    "avoid_for_now":         "mark_avoid",
    "too_speculative":       "mark_avoid",
}


def build_all(final_cards: list[dict], today: str) -> list[dict]:
    today_date = date.fromisoformat(today)
    actions = []
    for i, card in enumerate(final_cards):
        action = _build_one(card, today_date, i + 1)
        actions.append(action)
    return actions


def _build_one(card: dict, today_date: date, seq: int) -> dict:
    tid          = card["target_id"]
    name         = card.get("target_name", "")
    ticker       = card.get("ticker", "")
    action_label = card.get("action_label", "watchlist")
    action_type  = _ACTION_TYPES.get(action_label, "add_to_watchlist")
    review_days  = _REVIEW_DAYS.get(action_label, 30)
    review_date  = (today_date + timedelta(days=review_days)).isoformat()

    scenario = card.get("scenario_analysis", {})
    monitoring_triggers = scenario.get("monitoring_triggers", [])
    if not monitoring_triggers:
        monitoring_triggers = ["Next quarterly result", "Management commentary"]

    reason = _build_reason(card)

    return {
        "watch_action_id":     f"WATCH_{today_date.strftime('%Y%m%d')}_{seq:04d}",
        "target_id":           tid,
        "target_name":         name,
        "ticker":              ticker,
        "action_type":         action_type,
        "action_label":        action_label,
        "reason":              reason,
        "monitoring_triggers": monitoring_triggers[:4],
        "review_after_days":   review_days,
        "review_date":         review_date,
        "final_opportunity_score": card.get("final_opportunity_score", 0),
        "confidence_label":    card.get("confidence_label", "medium"),
    }


def _build_reason(card: dict) -> str:
    label = card.get("action_label", "watchlist")
    name  = card.get("target_name", "")
    score = card.get("final_opportunity_score", 0)
    conf  = card.get("confidence_label", "medium")
    action_reasons = card.get("action_reasons", [])
    if action_reasons:
        return action_reasons[0]

    if label == "research_candidate":
        return f"{name} ranks #{card.get('rank','')} with score {score:.0f}; strong evidence supports deeper research."
    elif label in ("watchlist", "wait_for_confirmation"):
        return f"{name} is a {conf}-confidence watch; monitoring for confirmation signals."
    elif label == "avoid_for_now":
        return f"{name} has unfavourable risk/reward under current evidence; revisit in {_REVIEW_DAYS[label]} days."
    return f"{name} is too speculative; requires significantly stronger evidence."
