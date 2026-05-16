"""
intelligence_layer/research_target_planner/deep_dive_plan_builder.py — Layer 6

Assembles the official deep_dive_plan.json consumed by Layer 7.
Combines selected targets + their module task specs into a single executable plan.

Design doc: docs/system_design_docs/layer_6.md §18 deep_dive_plan_builder.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def build_plan(selected_targets: list[dict], module_task_map: dict[str, list[dict]],
               run_id: str) -> dict:
    """
    Build the deep_dive_plan dict.

    Args:
        selected_targets:  list of selected target dicts (with priority_score, depth, etc.)
        module_task_map:   target_id → list of task specs (from deep_dive_module_mapper)
        run_id:            research run ID from L5

    Returns the plan dict.
    """
    now = datetime.now(_IST).isoformat()

    plan_id = f"DDPLAN_{datetime.now(_IST).strftime('%Y%m%d_%H%M')}"
    total_tasks = sum(len(tasks) for tasks in module_task_map.values())

    plan_targets = []
    for t in selected_targets:
        t_id  = t.get("target_id", "")
        tasks = module_task_map.get(t_id, [])
        plan_targets.append({
            "target_id":             t_id,
            "target_name":           t.get("target_name", ""),
            "target_type":           t.get("target_type", ""),
            "ticker":                t.get("ticker"),
            "exchange":              t.get("exchange"),
            "market":                t.get("market", "india"),
            "priority_score":        t.get("priority_score", 0),
            "priority_label":        t.get("priority_label", ""),
            "deep_dive_depth":       t.get("deep_dive_depth", "standard"),
            "time_horizon":          t.get("time_horizon", "medium_term"),
            "source_opportunity_ids": t.get("source_opportunity_ids", []),
            "why_selected":          t.get("why_selected", []),
            "questions_to_answer":   t.get("questions_to_answer", []),
            "data_gaps":             t.get("data_gaps", []),
            "modules_to_run":        tasks,
        })

    return {
        "deep_dive_plan_id":  plan_id,
        "research_run_id":    run_id,
        "created_at":         now,
        "created_by":         "Layer_6_Research_Target_Planner",
        "total_targets":      len(plan_targets),
        "total_tasks":        total_tasks,
        "targets":            plan_targets,
    }
