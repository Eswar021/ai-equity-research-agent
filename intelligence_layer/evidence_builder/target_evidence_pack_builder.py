"""
intelligence_layer/evidence_builder/target_evidence_pack_builder.py — Layer 8

Assembles one evidence pack per target — the complete dossier that Layer 9
specialist agents draw from.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build(
    scope:            dict,
    feature_groups:   list[dict],
    evidence_cards:   list[dict],
    thesis_card:      dict,
    evidence_gaps:    list[dict],
    date_str:         str,
) -> dict:
    tid    = scope["target_id"]
    name   = scope["target_name"]
    ticker = scope["ticker"]

    feature_group_ids = [fg["feature_group_id"] for fg in feature_groups]
    evidence_card_ids = [c["evidence_id"] for c in evidence_cards]
    gap_ids           = [g["gap_id"] for g in evidence_gaps]

    # Summarize available modules
    available = scope.get("available_modules", [])
    total_modules = 6  # market_data, price_history, screener_in, peer_comparison, analyst_estimates, exchange_filings
    coverage_pct = len(available) / total_modules if total_modules else 0

    if coverage_pct >= 0.9:
        coverage_status = "full"
    elif coverage_pct >= 0.6:
        coverage_status = "partial"
    elif coverage_pct >= 0.3:
        coverage_status = "limited"
    else:
        coverage_status = "insufficient"

    ready = coverage_pct >= 0.5 and len(evidence_cards) > 0

    # Build evidence summary for quick inspection
    by_type: dict[str, int] = {}
    by_strength: dict[str, int] = {}
    for card in evidence_cards:
        by_type[card["evidence_type"]] = by_type.get(card["evidence_type"], 0) + 1
        lbl = card.get("strength_label", "unknown")
        by_strength[lbl] = by_strength.get(lbl, 0) + 1

    avg_strength = _avg_strength(evidence_cards)

    return {
        "target_evidence_pack_id":   f"TEPACK_{date_str}_{tid}",
        "target_id":                 tid,
        "target_name":               name,
        "target_type":               scope.get("target_type", "listed_company"),
        "ticker":                    ticker,
        "exchange":                  scope.get("exchange", "NSE"),
        "time_horizon":              scope.get("time_horizon", "unknown"),
        "opportunity_ids":           scope.get("opportunity_ids", []),
        "questions_to_answer":       scope.get("questions_to_answer", []),
        "why_selected":              scope.get("why_selected", []),
        "feature_group_ids":         feature_group_ids,
        "evidence_card_ids":         evidence_card_ids,
        "thesis_card_id":            thesis_card.get("thesis_card_id", ""),
        "evidence_gap_ids":          gap_ids,
        "available_modules":         available,
        "coverage_status":           coverage_status,
        "coverage_pct":              round(coverage_pct, 2),
        "ready_for_agents":          ready,
        "evidence_summary": {
            "total_cards":       len(evidence_cards),
            "by_type":           by_type,
            "by_strength":       by_strength,
            "avg_strength_score": avg_strength,
            "gap_count":         len(evidence_gaps),
        },
        "market_context": scope.get("market_context", {}),
        "created_at": datetime.now(_IST).isoformat(),
    }


def _avg_strength(cards: list[dict]) -> float | None:
    scores = [c.get("evidence_strength_score", 0) for c in cards
              if c.get("evidence_type") != "missing_data_gap"]
    return round(sum(scores) / len(scores), 3) if scores else None
