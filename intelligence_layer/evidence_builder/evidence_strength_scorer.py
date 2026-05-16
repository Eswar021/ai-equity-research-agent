"""
intelligence_layer/evidence_builder/evidence_strength_scorer.py — Layer 8

Scores each evidence card's strength and appends strength_label.

Scoring factors:
  - source reliability (official/structured > analyst > article)
  - evidence_type weight
  - confidence field
  - is it missing_data_gap → always "missing"
"""

from __future__ import annotations

_TYPE_BASE: dict[str, float] = {
    "numeric_feature":  0.85,
    "filing_fact":      0.88,
    "analyst_estimate": 0.70,
    "peer_comparison":  0.80,
    "market_signal":    0.65,
    "missing_data_gap": 0.00,
}

_LABEL_THRESHOLDS = [
    (0.80, "strong"),
    (0.60, "moderate"),
    (0.40, "weak"),
    (0.01, "speculative"),
    (0.00, "missing"),
]


def score_all(evidence_cards: list[dict]) -> list[dict]:
    """Annotates each card with evidence_strength_score + strength_label. Returns same list."""
    for card in evidence_cards:
        _score_card(card)
    return evidence_cards


def _score_card(card: dict) -> None:
    if card["evidence_type"] == "missing_data_gap":
        card["evidence_strength_score"] = 0.0
        card["strength_label"] = "missing"
        card["score_reason"] = ["Missing data — no source"]
        return

    base    = _TYPE_BASE.get(card["evidence_type"], 0.65)
    conf    = card.get("confidence", 0.75)
    has_src = bool(card.get("source_refs"))
    has_data = bool(card.get("data"))

    score = base * 0.6 + conf * 0.4
    if not has_src:
        score *= 0.7
    if not has_data:
        score *= 0.85

    score = round(min(score, 1.0), 3)
    label = "speculative"
    for threshold, lbl in _LABEL_THRESHOLDS:
        if score >= threshold:
            label = lbl
            break

    reason = [f"Type base score: {base}", f"Confidence: {conf}"]
    if not has_src:
        reason.append("No source reference — downgraded")

    card["evidence_strength_score"] = score
    card["strength_label"]          = label
    card["score_reason"]            = reason
