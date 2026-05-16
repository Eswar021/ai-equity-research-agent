"""
intelligence_layer/final_synthesis_layer/final_context_assembler.py — Layer 10

Builds one final synthesis context per target, combining:
  - L9 specialist scorecard
  - L9 specialist assessments (fundamental, valuation, risk, thesis)
  - L9 risk flags
  - L9 agent disagreements
  - L8 thesis card
  - Top evidence cards
  - Linked opportunity hypotheses
"""

from __future__ import annotations


_TOP_EVIDENCE_PER_TARGET = 6
_TOP_HYPOTHESES_PER_TARGET = 4


def build_all(inputs: dict) -> list[dict]:
    scorecards       = inputs.get("target_scorecards", [])
    assessments_by   = inputs.get("assessments_by_target", {})
    risk_flags_by    = inputs.get("risk_flags_by_target", {})
    disagreements_by = inputs.get("disagreements_by_target", {})
    evidence_by      = inputs.get("evidence_by_target", {})
    thesis_by        = inputs.get("thesis_by_target", {})
    opps_by_id       = inputs.get("opportunities_by_id", {})

    contexts = []
    for sc in scorecards:
        if not isinstance(sc, dict):
            continue
        tid = sc.get("target_id", "")
        ctx = _build_one(
            scorecard        = sc,
            assessments      = assessments_by.get(tid, []),
            risk_flags       = risk_flags_by.get(tid, []),
            disagreements    = disagreements_by.get(tid, []),
            evidence_cards   = evidence_by.get(tid, []),
            thesis_card      = thesis_by.get(tid, {}),
            opps_by_id       = opps_by_id,
        )
        contexts.append(ctx)
    return contexts


def _build_one(
    scorecard: dict,
    assessments: list[dict],
    risk_flags: list[dict],
    disagreements: list[dict],
    evidence_cards: list[dict],
    thesis_card: dict,
    opps_by_id: dict,
) -> dict:
    tid = scorecard.get("target_id", "")

    # ── Parse assessments by agent type ──────────────────────────────────────
    parsed_assessments: dict[str, dict] = {}
    for entry in assessments:
        atype = entry.get("agent_type", "")
        assess = entry.get("assessment")
        if assess and entry.get("status") in ("success", "partial"):
            parsed_assessments[atype] = assess

    # ── Top evidence cards (by strength score desc, then first N) ────────────
    _STRENGTH_ORDER = {"strong": 0, "moderate": 1, "weak": 2, "unknown": 3}
    sorted_ev = sorted(
        evidence_cards,
        key=lambda e: _STRENGTH_ORDER.get(e.get("strength_label", "unknown"), 3)
    )
    top_evidence = sorted_ev[:_TOP_EVIDENCE_PER_TARGET]

    # ── Linked opportunity hypotheses ─────────────────────────────────────────
    opp_ids = scorecard.get("opportunity_ids", [])
    linked_opps = [
        opps_by_id[oid]
        for oid in opp_ids[:_TOP_HYPOTHESES_PER_TARGET]
        if oid in opps_by_id
    ]

    # ── Critical data gaps (union across scorecard + thesis card) ────────────
    sc_gaps = scorecard.get("critical_data_gaps", [])
    tc_gaps = thesis_card.get("data_gaps", []) if thesis_card else []  # type: ignore[union-attr]
    all_gaps: list[str] = list(dict.fromkeys(sc_gaps + tc_gaps))  # dedup preserving order

    return {
        "target_id":          tid,
        "target_name":        scorecard.get("target_name", ""),
        "target_type":        scorecard.get("target_type", "listed_company"),
        "ticker":             scorecard.get("ticker", ""),
        "time_horizon":       scorecard.get("time_horizon", ""),
        "scorecard":          scorecard,
        "specialist_assessments": parsed_assessments,
        "risk_flags":         risk_flags,
        "disagreements":      disagreements,
        "top_evidence_cards": top_evidence,
        "thesis_card":        thesis_card,
        "linked_opportunities": linked_opps,
        "critical_data_gaps": all_gaps,
        "dimension_scores":   scorecard.get("dimension_scores", {}),
        "overall_specialist_confidence": scorecard.get("overall_specialist_confidence", 0.5),
    }
