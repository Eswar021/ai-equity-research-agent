"""
intelligence_layer/targeted_deep_dive/target_source_record_builder.py — Layer 7

Builds a source record for each successfully collected module output.
Source records give Layer 2 the lineage it needs for canonicalization.

Design doc: docs/system_design_docs/layer_7.md §10.9 target_source_record_builder.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def build_source_records(
    ctx: dict,
    task_results: list[dict],
    plan_id: str,
    research_run_id: str,
) -> list[dict]:
    """Build one source record per successful task for a target."""
    records = []
    today   = datetime.now(_IST).strftime("%Y%m%d")

    for r in task_results:
        if r["status"] != "success":
            continue

        _CTR[0] += 1
        slug   = ctx["slug"]
        module = r["module"]

        records.append({
            "target_source_record_id": f"TSRCREC_{today}_{slug}_{module.upper()}_{_CTR[0]:04d}",
            "research_run_id":         research_run_id,
            "layer":                   "L7",
            "target_id":               ctx["target_id"],
            "target_type":             ctx["target_type"],
            "target_name":             ctx["target_name"],
            "ticker":                  ctx.get("ticker"),
            "module":                  module,
            "source_type":             r.get("source_type", module),
            "raw_output_path":         r["output_path"],
            "record_count":            r["record_count"],
            "collected_at":            r["collected_at"],
            "status":                  "success",
            "content_type":            "structured_json",
            "lineage": {
                "deep_dive_plan_id":      plan_id,
                "source_opportunity_ids": ctx.get("source_opportunity_ids", []),
            },
        })

    return records


def build_all_source_records(
    contexts: list[dict],
    all_task_results: dict[str, list[dict]],
    plan_id: str,
    research_run_id: str,
) -> list[dict]:
    all_records = []
    for ctx in contexts:
        tid     = ctx["target_id"]
        results = all_task_results.get(tid, [])
        all_records.extend(build_source_records(ctx, results, plan_id, research_run_id))
    return all_records
