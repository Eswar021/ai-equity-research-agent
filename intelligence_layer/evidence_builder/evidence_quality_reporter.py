"""
intelligence_layer/evidence_builder/evidence_quality_reporter.py — Layer 8

Builds the evidence quality report summarizing what L8 produced.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build_report(
    research_run_id: str,
    scopes:          list[dict],
    all_evidence:    dict[str, list[dict]],
    all_gaps:        dict[str, list[dict]],
    all_packs:       list[dict],
    all_packets:     list[dict],
    date_str:        str,
) -> dict:
    total_targets   = len(scopes)
    total_cards     = sum(len(v) for v in all_evidence.values())
    total_gaps      = sum(len(v) for v in all_gaps.values())
    total_packs     = len(all_packs)
    total_packets   = len(all_packets)

    # Strength distribution across all cards
    strength_counts: dict[str, int] = {}
    for cards in all_evidence.values():
        for c in cards:
            lbl = c.get("strength_label", "unknown")
            strength_counts[lbl] = strength_counts.get(lbl, 0) + 1

    avg_strength: float | None = None
    all_scores = [c.get("evidence_strength_score", 0) for cards in all_evidence.values()
                  for c in cards if c.get("evidence_type") != "missing_data_gap"]
    if all_scores:
        avg_strength = round(sum(all_scores) / len(all_scores), 3)

    # Per-target summary
    per_target = []
    for scope in scopes:
        tid = scope["target_id"]
        cards = all_evidence.get(tid, [])
        gaps  = all_gaps.get(tid, [])
        pack  = next((p for p in all_packs if p["target_id"] == tid), {})
        non_gap = [c for c in cards if c.get("evidence_type") != "missing_data_gap"]
        per_target.append({
            "target_id":         tid,
            "target_name":       scope.get("target_name", ""),
            "ticker":            scope.get("ticker", ""),
            "evidence_cards":    len(non_gap),
            "gap_cards":         len(gaps),
            "coverage_status":   pack.get("coverage_status", "unknown"),
            "coverage_pct":      pack.get("coverage_pct", 0),
            "avg_strength_score": pack.get("evidence_summary", {}).get("avg_strength_score"),
            "ready_for_agents":  pack.get("ready_for_agents", False),
        })

    targets_ready  = sum(1 for t in per_target if t["ready_for_agents"])
    critical_gaps  = sum(1 for gaps in all_gaps.values()
                         for g in gaps if g.get("severity") == "high")

    return {
        "research_run_id":         research_run_id,
        "layer":                   "L8_evidence_builder",
        "generated_at":            datetime.now(_IST).isoformat(),
        "targets_processed":       total_targets,
        "targets_ready_for_agents": targets_ready,
        "targets_with_critical_gaps": sum(1 for gaps in all_gaps.values()
                                          if any(g.get("severity") == "high" for g in gaps)),
        "evidence_cards_created":  total_cards,
        "evidence_strength_distribution": strength_counts,
        "average_evidence_strength": avg_strength,
        "evidence_gaps_count":     total_gaps,
        "critical_gaps_count":     critical_gaps,
        "target_evidence_packs":   total_packs,
        "agent_context_packets":   total_packets,
        "per_target":              per_target,
    }
