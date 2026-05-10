"""
intelligence_layer/market_opportunity_intelligence/hypothesis_strength_scorer.py — Layer 5

8-dimension rule-based scorer that gates Layer 6 forwarding.
Not a final recommendation scorer — scores whether the hypothesis
is strong enough to merit deeper research.

Scoring dimensions (max 95 before penalties):
  event_materiality_score        0-15
  source_reliability_score       0-15
  source_diversity_score         0-10
  memory_recurrence_score        0-10
  structural_relevance_score     0-15
  investment_actionability_score 0-15
  target_mappability_score       0-10
  time_horizon_clarity_score     0-5
  data_gap_penalty              -0 to -15
  speculation_penalty           -0 to -20

send_to_layer6 = score >= 45

Design doc: docs/system_design_docs/layer_5.md §11 hypothesis_strength_scorer.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_HIGH_IMPACT_EVENTS = {
    "policy_change", "industrial_corridor", "guidance_cut", "guidance_raise",
    "earnings_miss", "earnings_beat", "merger_acquisition", "capex_announcement",
    "fraud_or_accounting_concern", "regulatory_action", "large_order_win",
}


def score_all(hypotheses: list[dict], signal_groups: list[dict],
              sector_theme_views: list[dict], event_impact_views: list[dict],
              market_view: dict) -> list[dict]:
    grp_by_id: dict[str, dict] = {g["signal_group_id"]: g for g in signal_groups}
    tv_by_grp:  dict[str, dict] = {v["signal_group_id"]: v for v in sector_theme_views}
    impact_by_evt: dict[str, dict] = {v["event_id"]: v for v in event_impact_views}

    return [_score(hyp, grp_by_id, tv_by_grp, impact_by_evt, market_view)
            for hyp in hypotheses]


def _score(hyp: dict, grp_by_id: dict, tv_by_grp: dict,
           impact_by_evt: dict, market_view: dict) -> dict:
    _CTR[0] += 1
    today  = datetime.now(_IST).strftime("%Y%m%d")
    sc_id  = f"HSS_{today}_{_CTR[0]:04d}"

    origin = hyp.get("origin") or {}
    grp_id = origin.get("signal_group_id", "")
    grp    = grp_by_id.get(grp_id, {})
    tv     = tv_by_grp.get(grp_id, {})

    events_detail  = grp.get("events_detail") or []
    source_div     = grp.get("source_diversity_count", 0)
    rec_level      = grp.get("recurrence_level", "new")
    memory_refs    = grp.get("memory_refs") or []
    supporting_refs = hyp.get("supporting_refs") or []
    data_gaps      = hyp.get("data_gaps") or []
    beneficiaries  = hyp.get("likely_beneficiaries_or_targets") or []
    hyp_strength   = hyp.get("hypothesis_strength", "medium")
    time_horizon   = hyp.get("time_horizon", "")

    # 1. event_materiality_score (0-15)
    high_impact_count = sum(
        1 for e in events_detail
        if e.get("event_type") in _HIGH_IMPACT_EVENTS
    )
    evt_sev_high = sum(
        1 for e in events_detail
        if impact_by_evt.get(e.get("event_id", ""), {}).get("impact_strength") == "high"
    )
    event_materiality = min(high_impact_count * 4 + evt_sev_high * 3, 15)

    # 2. source_reliability_score (0-15): source diversity as proxy for reliability
    source_reliability = min(source_div * 4, 15)

    # 3. source_diversity_score (0-10)
    source_diversity = min(source_div * 3, 10)

    # 4. memory_recurrence_score (0-10)
    recurrence_pts = {"high_recurring": 10, "recurring": 7, "new_with_memory": 4, "new": 0}
    memory_recurrence = recurrence_pts.get(rec_level, 0)
    if memory_refs:
        memory_recurrence = min(memory_recurrence + 3, 10)

    # 5. structural_relevance_score (0-15)
    struct_rel = tv.get("structural_relevance", "low")
    struct_pts = {"high": 15, "medium": 8, "low": 3}
    structural_relevance = struct_pts.get(struct_rel, 3)

    # 6. investment_actionability_score (0-15)
    invest_rel = tv.get("investment_relevance", "low")
    invest_pts = {"high": 12, "medium": 7, "low": 2}
    actionability = invest_pts.get(invest_rel, 2)
    if len(beneficiaries) >= 2:
        actionability = min(actionability + 3, 15)

    # 7. target_mappability_score (0-10)
    listed = sum(1 for t in beneficiaries if t.get("target_type") == "listed_company")
    target_mappability = min(listed * 3 + len(beneficiaries), 10)

    # 8. time_horizon_clarity_score (0-5)
    time_horizon_clarity = 5 if time_horizon in ("short_term", "medium_term", "long_term", "structural") else 1

    # 9. data_gap_penalty (0 to -15)
    data_gap_penalty = -min(len(data_gaps) * 3, 15)

    # 10. speculation_penalty (0 to -20)
    speculation_penalty = 0
    if hyp_strength == "low":
        speculation_penalty -= 10
    if not supporting_refs:
        speculation_penalty -= 10

    breakdown = {
        "event_materiality_score":        event_materiality,
        "source_reliability_score":       source_reliability,
        "source_diversity_score":         source_diversity,
        "memory_recurrence_score":        memory_recurrence,
        "structural_relevance_score":     structural_relevance,
        "investment_actionability_score": actionability,
        "target_mappability_score":       target_mappability,
        "time_horizon_clarity_score":     time_horizon_clarity,
        "data_gap_penalty":               data_gap_penalty,
        "speculation_penalty":            speculation_penalty,
    }

    total = sum(breakdown.values())
    total = max(0, total)

    if total >= 70:
        label = "strong_research_worthy"
    elif total >= 45:
        label = "research_worthy"
    else:
        label = "weak_speculative"

    send_to_l6 = total >= 45

    reasoning = _build_reasoning(breakdown, total, label, rec_level)

    return {
        "strength_score_id":         sc_id,
        "opportunity_id":            hyp.get("opportunity_id", ""),
        "hypothesis_strength_score": total,
        "strength_label":            label,
        "score_breakdown":           breakdown,
        "send_to_layer6":            send_to_l6,
        "reasoning_summary":         reasoning,
        "confidence":                round(hyp.get("confidence", 0.5), 3),
    }


def _build_reasoning(bd: dict, total: int, label: str, rec_level: str) -> list[str]:
    r: list[str] = [f"Total score: {total} → {label}."]
    if bd["memory_recurrence_score"] >= 7:
        r.append(f"Recurring signal ({rec_level}) elevates conviction.")
    if bd["event_materiality_score"] >= 10:
        r.append("High-materiality events detected — research warranted.")
    if bd["speculation_penalty"] < -5:
        r.append("Speculation penalty applied: weak sources or low hypothesis strength.")
    if bd["data_gap_penalty"] < -6:
        r.append("Multiple data gaps reduce score — deep dive required.")
    return r
