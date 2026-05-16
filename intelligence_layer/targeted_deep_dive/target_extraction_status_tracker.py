"""
intelligence_layer/targeted_deep_dive/target_extraction_status_tracker.py — Layer 7

Rolls up per-task results into a per-target extraction status record.

Design doc: docs/system_design_docs/layer_7.md §10.10 + §19
"""

from __future__ import annotations


def build_status(ctx: dict, task_results: list[dict], skipped: list[dict]) -> dict:
    """
    Build a status record for one target.

    target_status: "success" | "partial_success" | "failed"
    can_continue_to_layer2: True if at least one module succeeded
    """
    success = [r for r in task_results if r["status"] == "success"]
    failed  = [r for r in task_results if r["status"] == "failed"]

    if len(failed) == 0 and len(skipped) == 0:
        target_status = "success"
    elif len(success) == 0:
        target_status = "failed"
    else:
        target_status = "partial_success"

    module_records = [
        {
            "module":       r["module"],
            "task_id":      r["task_id"],
            "status":       r["status"],
            "record_count": r["record_count"],
            "output_path":  r["output_path"],
            "error":        r["error"],
            "collected_at": r["collected_at"],
        }
        for r in task_results
    ] + [
        {
            "module":       s["module"],
            "task_id":      None,
            "status":       "skipped",
            "record_count": 0,
            "output_path":  None,
            "error":        s["reason"],
            "collected_at": None,
        }
        for s in skipped
    ]

    return {
        "target_id":                ctx["target_id"],
        "target_name":              ctx["target_name"],
        "target_type":              ctx["target_type"],
        "ticker":                   ctx.get("ticker"),
        "target_status":            target_status,
        "modules_requested":        len(task_results) + len(skipped),
        "modules_success":          len(success),
        "modules_failed":           len(failed),
        "modules_skipped":          len(skipped),
        "critical_modules_failed":  [],  # no critical/optional distinction at standard depth
        "can_continue_to_layer2":   len(success) > 0,
        "modules":                  module_records,
    }


def build_all_statuses(
    contexts: list[dict],
    all_task_results: dict[str, list[dict]],   # target_id → results
    all_skipped: dict[str, list[dict]],         # target_id → skipped
) -> list[dict]:
    statuses = []
    for ctx in contexts:
        tid     = ctx["target_id"]
        results = all_task_results.get(tid, [])
        skipped = all_skipped.get(tid, [])
        statuses.append(build_status(ctx, results, skipped))
    return statuses
