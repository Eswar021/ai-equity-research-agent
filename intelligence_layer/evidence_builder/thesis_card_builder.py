"""
intelligence_layer/evidence_builder/thesis_card_builder.py — Layer 8

Builds a thesis card per target from L5 opportunity hypotheses + evidence.
The thesis card is NOT a final investment decision — it frames the research
question for Layer 9 specialist agents.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build(
    scope:          dict,
    evidence_cards: list[dict],
    evidence_gaps:  list[dict],
    date_str:       str,
) -> dict:
    tid    = scope["target_id"]
    name   = scope["target_name"]
    ticker = scope["ticker"]

    # ── Derive thesis statement from L5 hypotheses ────────────────────────────
    linked_hyps = scope.get("linked_hypotheses", [])
    if linked_hyps:
        # Primary hypothesis drives the thesis
        primary_hyp = linked_hyps[0]
        thesis_stmt = _build_thesis_statement(primary_hyp, name, scope)
        time_horizon = scope.get("time_horizon", "unknown")
    else:
        thesis_stmt  = f"{name} ({ticker}) is selected for deep-dive research based on market signals. No primary hypothesis attached."
        time_horizon = scope.get("time_horizon", "unknown")

    # ── Classify supporting vs weakening evidence ─────────────────────────────
    supporting_ids: list[str] = []
    weakening_ids: list[str] = []

    for card in evidence_cards:
        if card.get("evidence_type") == "missing_data_gap":
            continue
        strength = card.get("strength_label", "weak")
        if strength in ("strong", "moderate"):
            if any(s in card.get("supports", []) for s in
                   ("fundamental_analysis", "growth_analysis", "quality_analysis",
                    "valuation_analysis", "analyst_consensus")):
                supporting_ids.append(card["evidence_id"])
        if card.get("weakens"):
            weakening_ids.append(card["evidence_id"])

    gap_ids = [g["gap_id"] for g in evidence_gaps if g.get("severity") in ("high", "medium")]

    # ── Compute thesis confidence ─────────────────────────────────────────────
    base_confidence = _compute_confidence(scope, evidence_cards, evidence_gaps)

    # ── Invalidating conditions from L5 hypotheses ────────────────────────────
    invalidating: list[str] = list(scope.get("invalidating_conditions", []))

    return {
        "thesis_card_id":           f"THESIS_{date_str}_{tid}",
        "target_id":                tid,
        "target_name":              name,
        "ticker":                   ticker,
        "thesis_statement":         thesis_stmt,
        "thesis_type":              "listed_company_opportunity",
        "time_horizon":             time_horizon,
        "opportunity_ids":          scope.get("opportunity_ids", []),
        "why_selected":             scope.get("why_selected", []),
        "supporting_evidence_ids":  supporting_ids,
        "weakening_evidence_ids":   weakening_ids,
        "evidence_gap_ids":         gap_ids,
        "invalidating_conditions":  invalidating,
        "current_thesis_confidence": base_confidence,
        "needs_specialist_analysis": True,
        "market_context_summary": _market_context_summary(scope.get("market_context", {})),
        "created_at": datetime.now(_IST).isoformat(),
    }


def _build_thesis_statement(hyp: dict, name: str, scope: dict) -> str:
    opp_title = hyp.get("opportunity_title", "")
    hypothesis = hyp.get("hypothesis", "")
    time_h     = scope.get("time_horizon", "")
    hyp_strength = hyp.get("hypothesis_strength", "")
    confidence   = hyp.get("confidence", 0)

    # Build a concise thesis
    stmt = f"{name} is a {time_h} research target linked to: {opp_title}."
    if hypothesis:
        # Truncate long hypothesis text
        snippet = hypothesis[:300] + "..." if len(hypothesis) > 300 else hypothesis
        stmt += f" Hypothesis ({hyp_strength}, confidence {confidence:.0%}): {snippet}"
    return stmt


def _compute_confidence(scope: dict, cards: list[dict], gaps: list[dict]) -> float:
    base = scope.get("confidence", 0.5)

    non_gap_cards = [c for c in cards if c.get("evidence_type") != "missing_data_gap"]
    strong_cards  = [c for c in non_gap_cards if c.get("strength_label") in ("strong",)]
    moderate_cards = [c for c in non_gap_cards if c.get("strength_label") == "moderate"]

    high_gaps  = sum(1 for g in gaps if g.get("severity") == "high")
    med_gaps   = sum(1 for g in gaps if g.get("severity") == "medium")

    # Boost for strong evidence
    boost = len(strong_cards) * 0.02 + len(moderate_cards) * 0.01
    # Penalize for gaps
    penalty = high_gaps * 0.05 + med_gaps * 0.02

    result = base + boost - penalty
    return round(max(0.1, min(0.95, result)), 3)


def _market_context_summary(ctx: dict) -> dict:
    return {
        "regime":            ctx.get("regime", "unknown"),
        "risk_level":        ctx.get("risk_level", "unknown"),
        "recommended_posture": ctx.get("recommended_posture", "unknown"),
        "vix_india":         ctx.get("vix_india"),
        "fii_net_cr":        ctx.get("fii_net_cr"),
        "usd_inr":           ctx.get("usd_inr"),
        "nifty_pe":          ctx.get("nifty_pe"),
    }
