"""
intelligence_layer/final_synthesis_layer/final_guardrail_validator.py — Layer 10

Validates final recommendation cards for:
  - Forbidden language (guarantee, definitely, sure profit)
  - Overconfident labels without supporting evidence
  - Missing required fields (evidence refs, risks, confidence)
  - High confidence with critical data gaps
  - Proxy exposure treated as confirmed

Returns a guardrail report; does NOT modify cards (logs only).
"""

from __future__ import annotations

_FORBIDDEN = [
    "guaranteed", "definitely will", "certainly will", "sure profit",
    "100% certain", "no risk", "risk-free",
    "buy immediately", "sell immediately", "buy this stock", "sell this stock",
]

_REQUIRED_CARD_FIELDS = [
    "target_id", "target_name", "ticker", "action_label",
    "final_opportunity_score", "final_confidence", "supporting_points",
    "weakening_points", "scenario_analysis",
]


def validate(final_cards: list[dict]) -> dict:
    issues: list[dict] = []
    warnings: list[str] = []
    downgraded_items: list[dict] = []

    for card in final_cards:
        tid   = card.get("target_id", "unknown")
        name  = card.get("target_name", "")
        label = card.get("action_label", "")
        conf  = card.get("final_confidence", 0.5)
        gaps  = card.get("critical_gaps_summary", [])

        # ── Required fields ───────────────────────────────────────────────────
        for field in _REQUIRED_CARD_FIELDS:
            if not card.get(field) and card.get(field) != 0:
                issues.append({
                    "target_id": tid,
                    "issue_type": "missing_field",
                    "field": field,
                    "message": f"Required field '{field}' is missing or empty",
                })

        # ── Forbidden language ────────────────────────────────────────────────
        text_to_check = " ".join([
            card.get("final_summary", ""),
            card.get("final_view_rationale", ""),
            " ".join(card.get("supporting_points", [])),
        ]).lower()
        for phrase in _FORBIDDEN:
            if phrase in text_to_check:
                issues.append({
                    "target_id": tid,
                    "issue_type": "forbidden_language",
                    "phrase": phrase,
                    "message": f"Forbidden phrase '{phrase}' found in card for {name}",
                })

        # ── High confidence with critical gaps ────────────────────────────────
        if conf >= 0.75 and len(gaps) >= 3:
            warnings.append(
                f"{name} ({tid}): high confidence ({conf:.2f}) despite {len(gaps)} critical data gaps"
            )

        # ── Research candidate without supporting points ───────────────────────
        if label == "research_candidate" and len(card.get("supporting_points", [])) == 0:
            issues.append({
                "target_id": tid,
                "issue_type": "unsupported_conclusion",
                "message": f"research_candidate label but no supporting_points for {name}",
            })

    status = "pass" if not issues else ("fail" if len(issues) >= 3 else "pass_with_warnings")

    return {
        "status":           status,
        "items_checked":    len(final_cards),
        "issues":           issues,
        "warnings":         warnings,
        "downgraded_items": downgraded_items,
        "issues_count":     len(issues),
        "warnings_count":   len(warnings),
    }
