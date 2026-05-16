"""
intelligence_layer/final_synthesis_layer/opportunity_ranker.py — Layer 10

Computes a final_opportunity_score per target using L9 dimension scores
and market alignment, then ranks all targets.

Scoring formula (all inputs 0-100 scale):
  raw_score =
      0.25 * fundamental_score
    + 0.20 * valuation_score       (high = cheap/attractive)
    + 0.20 * thesis_support_score
    + 0.20 * (100 - risk_score)    (invert: high risk = low score)
    + 0.15 * market_alignment_score

  penalties:
    - 5 per critical data gap (cap 20)
    - 5 per agent disagreement (cap 10)

  final_opportunity_score = max(0, min(100, raw_score - penalties))
"""

from __future__ import annotations

_POSTURE_ALIGNMENT = {
    "selective_buy":      70,
    "selective_research": 50,
    "defensive":          30,
}

_WEIGHT_F  = 0.25
_WEIGHT_V  = 0.20
_WEIGHT_T  = 0.20
_WEIGHT_R  = 0.20   # applied to (100 - risk_score)
_WEIGHT_MA = 0.15


def rank_all(
    target_syntheses: list[dict],
    target_contexts: list[dict],
    market_posture: dict,
) -> list[dict]:
    ctx_by_tid = {c["target_id"]: c for c in target_contexts}
    posture_key = market_posture.get("final_market_posture", "selective_research")
    base_market_align = _POSTURE_ALIGNMENT.get(posture_key, 50)
    favored  = [s.lower() for s in market_posture.get("favored_sectors", [])]
    avoid_s  = [s.lower() for s in market_posture.get("avoid_sectors",   [])]

    ranked = []
    for syn in target_syntheses:
        tid  = syn["target_id"]
        ctx  = ctx_by_tid.get(tid, {})
        dims = syn.get("dimension_scores", {})

        f_score = dims.get("fundamental_score",    50)
        v_score = dims.get("valuation_score",       50)
        t_score = dims.get("thesis_support_score",  50)
        r_score = dims.get("risk_score",            50)

        # ── Market alignment ──────────────────────────────────────────────────
        market_align = base_market_align
        # Check if target sector aligns with market posture
        # (we don't have explicit sector here, but ticker suffix gives a hint)
        # Use linked_opportunity hypothesis_strength as a proxy
        linked_opps = ctx.get("linked_opportunities", [])
        if linked_opps:
            avg_strength = _avg_hypothesis_strength(linked_opps)
            market_align = min(100, market_align + avg_strength * 0.3)

        # ── Raw score ─────────────────────────────────────────────────────────
        raw = (
            _WEIGHT_F  * f_score
          + _WEIGHT_V  * v_score
          + _WEIGHT_T  * t_score
          + _WEIGHT_R  * (100 - r_score)
          + _WEIGHT_MA * market_align
        )

        # ── Penalties ─────────────────────────────────────────────────────────
        gaps        = ctx.get("critical_data_gaps", [])
        disagreements = ctx.get("disagreements", [])
        gap_penalty   = min(len(gaps)        * 5, 20)
        disag_penalty = min(len(disagreements) * 5, 10)

        final_score = max(0.0, min(100.0, raw - gap_penalty - disag_penalty))

        # ── Opportunity category ──────────────────────────────────────────────
        target_type  = syn.get("target_type", "listed_company")
        opp_category = _categorize(target_type, final_score)

        ranked.append({
            **syn,
            "final_opportunity_score":  round(final_score, 1),
            "raw_score":                round(raw, 1),
            "market_alignment_score":   round(market_align, 1),
            "gap_penalty":              gap_penalty,
            "disagreement_penalty":     disag_penalty,
            "opportunity_category":     opp_category,
            "score_breakdown": {
                "fundamental":    round(_WEIGHT_F * f_score, 1),
                "valuation":      round(_WEIGHT_V * v_score, 1),
                "thesis":         round(_WEIGHT_T * t_score, 1),
                "risk_adjusted":  round(_WEIGHT_R * (100 - r_score), 1),
                "market_align":   round(_WEIGHT_MA * market_align, 1),
            },
        })

    # Sort by final_opportunity_score descending
    ranked.sort(key=lambda x: x["final_opportunity_score"], reverse=True)
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    return ranked


def _avg_hypothesis_strength(linked_opps: list[dict]) -> float:
    _STRENGTH_VAL = {"high": 80, "medium": 50, "low": 25, "very_high": 90}
    vals = [
        _STRENGTH_VAL.get(op.get("hypothesis_strength", "medium"), 50)
        for op in linked_opps
        if isinstance(op, dict)
    ]
    return sum(vals) / len(vals) if vals else 50.0


def _categorize(target_type: str, score: float) -> str:
    if target_type == "listed_company":
        if score >= 65:
            return "stock_research_candidate"
        elif score >= 45:
            return "stock_watchlist"
        else:
            return "stock_monitor_or_avoid"
    return "other_opportunity"
