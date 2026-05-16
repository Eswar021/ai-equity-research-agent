"""
intelligence_layer/specialist_analysis/target_specialist_scorecard_builder.py — Layer 9

Builds one specialist scorecard per target. This is the primary output Layer 10 consumes.
Compactly summarizes all agent assessments, risk flags, and disagreements per target.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build_all(
    task_results:   list[dict],
    risk_flags:     list[dict],
    disagreements:  list[dict],
    inputs:         dict,
    date_str:       str,
) -> list[dict]:
    """Build one scorecard per target. Returns list of scorecard dicts."""
    # Group by target_id
    by_target: dict[str, dict[str, dict]] = {}
    for r in task_results:
        a = r.get("assessment", {})
        tid = a.get("target_id", "")
        if tid:
            by_target.setdefault(tid, {})[r["agent_type"]] = {
                "assessment": a,
                "status":     r["status"],
            }

    flags_by_target: dict[str, list[dict]] = {}
    for rf in risk_flags:
        flags_by_target.setdefault(rf.get("target_id",""), []).append(rf)

    disagree_by_target: dict[str, list[dict]] = {}
    for d in disagreements:
        disagree_by_target.setdefault(d.get("target_id",""), []).append(d)

    packs_by_target = inputs.get("packs_by_target", {})

    scorecards: list[dict] = []
    for tid, agents in by_target.items():
        pack = packs_by_target.get(tid, {})
        sc = _build_scorecard(tid, agents, pack,
                              flags_by_target.get(tid, []),
                              disagree_by_target.get(tid, []),
                              date_str)
        scorecards.append(sc)
    return scorecards


def _build_scorecard(
    tid:          str,
    agents:       dict[str, dict],
    pack:         dict,
    flags:        list[dict],
    disagreements: list[dict],
    date_str:     str,
) -> dict:
    fund_entry   = agents.get("fundamental_agent", {})
    val_entry    = agents.get("valuation_agent", {})
    risk_entry   = agents.get("risk_agent", {})
    thesis_entry = agents.get("thesis_agent", {})

    fund   = fund_entry.get("assessment", {})
    val    = val_entry.get("assessment", {})
    risk   = risk_entry.get("assessment", {})
    thesis = thesis_entry.get("assessment", {})

    name   = fund.get("target_name") or val.get("target_name") or pack.get("target_name", "")
    ticker = fund.get("ticker") or val.get("ticker") or pack.get("ticker", "")

    # Dimension scores (default 50 if agent didn't run)
    fund_scores = fund.get("dimension_scores", {})
    val_scores  = val.get("dimension_scores", {})
    risk_scores = risk.get("dimension_scores", {})
    thesis_scores = thesis.get("dimension_scores", {})

    dim_scores = {
        "fundamental_score":  fund_scores.get("overall_fundamental_score", 50) if fund else None,
        "valuation_score":    val_scores.get("overall_valuation_score", 50) if val else None,
        "risk_score":         risk_scores.get("risk_score", 50) if risk else None,
        "thesis_support_score": thesis_scores.get("thesis_support_score", 50) if thesis else None,
    }
    dim_scores = {k: v for k, v in dim_scores.items() if v is not None}

    dim_labels = {
        "fundamentals": fund.get("assessment_label", "not_assessed"),
        "valuation":    val.get("assessment_label", "not_assessed"),
        "risk":         risk.get("assessment_label", "not_assessed"),
        "thesis":       thesis.get("assessment_label", "not_assessed"),
    }

    # Top supportive points from each agent
    supportive: list[str] = []
    for a in [fund, val]:
        for f in a.get("supportive_factors", [])[:2]:
            if f and f not in supportive:
                supportive.append(f)

    # Top risks
    top_risks: list[str] = []
    for rf in flags[:3]:
        top_risks.append(f"[{rf.get('severity','?')}] {rf.get('description','')[:120]}")
    for f in risk.get("negative_factors", [])[:2]:
        if f and f not in top_risks:
            top_risks.append(f[:120])

    # Critical data gaps
    critical_gaps: list[str] = []
    critical_gaps.extend(thesis.get("critical_gaps", [])[:3])
    critical_gaps.extend(risk.get("critical_data_gaps", [])[:2])

    # Overall confidence = weighted avg of agent confidences
    conf_values = [
        a.get("confidence", 0) for a in [fund, val, risk, thesis] if a.get("confidence")
    ]
    overall_conf = round(sum(conf_values) / len(conf_values), 3) if conf_values else 0.5

    # Updated thesis confidence (from thesis agent if available)
    updated_thesis_conf = thesis.get("updated_thesis_confidence", None)

    # Assessment IDs
    assess_ids = [a.get("assessment_id", "") for a in [fund, val, risk, thesis] if a.get("assessment_id")]
    flag_ids   = [rf.get("risk_flag_id", "") for rf in flags]
    disagree_ids = [d.get("disagreement_id", "") for d in disagreements]

    ready = bool(dim_scores) and overall_conf > 0.2

    return {
        "target_scorecard_id":           f"SCORECARD_{date_str}_{tid}",
        "target_id":                     tid,
        "target_name":                   name,
        "target_type":                   pack.get("target_type", "listed_company"),
        "ticker":                        ticker,
        "time_horizon":                  pack.get("time_horizon", "unknown"),
        "opportunity_ids":               pack.get("opportunity_ids", []),

        "dimension_scores":              dim_scores,
        "dimension_labels":              dim_labels,

        "thesis_status":                 thesis.get("thesis_status", "not_assessed"),
        "thesis_statement_snippet":      thesis.get("summary", "")[:300],
        "updated_thesis_confidence":     updated_thesis_conf,

        "top_supportive_points":         supportive,
        "top_risks":                     top_risks,
        "critical_data_gaps":            critical_gaps,

        "specialist_assessment_ids":     assess_ids,
        "risk_flag_ids":                 flag_ids,
        "agent_disagreement_ids":        disagree_ids,
        "agent_disagreement_count":      len(disagreements),

        "overall_specialist_confidence": overall_conf,
        "ready_for_layer10":             ready,
        "not_final_recommendation":      True,
        "created_at":                    datetime.now(_IST).isoformat(),
    }
