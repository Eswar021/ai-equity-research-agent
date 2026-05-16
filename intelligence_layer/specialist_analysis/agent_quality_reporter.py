"""
intelligence_layer/specialist_analysis/agent_quality_reporter.py — Layer 9

Summarises agent task execution quality:
  - success/failure counts per agent type
  - average confidence per agent type
  - targets ready vs. not ready for Layer 10
  - disagreement and risk flag statistics
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build_report(
    research_run_id: str,
    task_results:    list[dict],
    risk_flags:      list[dict],
    disagreements:   list[dict],
    scorecards:      list[dict],
    date_str:        str,
) -> dict:
    # Per-agent-type stats
    by_type: dict[str, dict] = {}
    for r in task_results:
        atype = r["agent_type"]
        entry = by_type.setdefault(atype, {"success": 0, "failed": 0, "confidences": []})
        if r["status"] == "success":
            entry["success"] += 1
            conf = r.get("assessment", {}).get("confidence")
            if conf:
                entry["confidences"].append(conf)
        else:
            entry["failed"] += 1

    agent_stats = {}
    for atype, e in by_type.items():
        confs = e["confidences"]
        agent_stats[atype] = {
            "success":          e["success"],
            "failed":           e["failed"],
            "avg_confidence":   round(sum(confs) / len(confs), 3) if confs else None,
            "min_confidence":   round(min(confs), 3) if confs else None,
            "max_confidence":   round(max(confs), 3) if confs else None,
        }

    # Scorecard readiness
    ready     = [s for s in scorecards if s.get("ready_for_layer10")]
    not_ready = [s for s in scorecards if not s.get("ready_for_layer10")]

    # Risk flag severity breakdown
    flag_severity: dict[str, int] = {}
    for rf in risk_flags:
        sev = rf.get("severity", "unknown")
        flag_severity[sev] = flag_severity.get(sev, 0) + 1

    # Disagreement type breakdown
    disagree_types: dict[str, int] = {}
    for d in disagreements:
        dtype = d.get("disagreement_type", "unknown")
        disagree_types[dtype] = disagree_types.get(dtype, 0) + 1

    # Per-scorecard summary
    scorecard_summaries = []
    for sc in scorecards:
        scorecard_summaries.append({
            "target_id":     sc["target_id"],
            "target_name":   sc.get("target_name", ""),
            "ticker":        sc.get("ticker", ""),
            "ready":         sc.get("ready_for_layer10", False),
            "confidence":    sc.get("overall_specialist_confidence"),
            "thesis_status": sc.get("thesis_status", ""),
            "dim_scores":    sc.get("dimension_scores", {}),
            "disagreements": sc.get("agent_disagreement_count", 0),
            "risk_flags":    len(sc.get("risk_flag_ids", [])),
        })

    total_tasks = len(task_results)
    succeeded   = sum(1 for r in task_results if r["status"] == "success")

    return {
        "research_run_id":           research_run_id,
        "layer":                     "L9_specialist_analysis",
        "date_str":                  date_str,
        "created_at":                datetime.now(_IST).isoformat(),
        "tasks_total":               total_tasks,
        "tasks_succeeded":           succeeded,
        "tasks_failed":              total_tasks - succeeded,
        "success_rate_pct":          round(succeeded / total_tasks * 100, 1) if total_tasks else 0,
        "agent_stats":               agent_stats,
        "targets_processed":         len(scorecards),
        "targets_ready_for_layer10": len(ready),
        "targets_not_ready":         len(not_ready),
        "not_ready_target_ids":      [s["target_id"] for s in not_ready],
        "risk_flags_total":          len(risk_flags),
        "risk_flag_severity_dist":   flag_severity,
        "disagreements_total":       len(disagreements),
        "disagreement_type_dist":    disagree_types,
        "scorecard_summaries":       scorecard_summaries,
    }
