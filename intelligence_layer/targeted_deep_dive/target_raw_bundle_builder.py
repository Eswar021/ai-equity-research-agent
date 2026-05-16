"""
intelligence_layer/targeted_deep_dive/target_raw_bundle_builder.py — Layer 7

Assembles:
  - A per-target bundle dict (also written as target_bundle.json in each target dir)
  - The full target_raw_bundles.json for the whole Layer 7 run

Design doc: docs/system_design_docs/layer_7.md §10.13 + §18 target raw bundle schema
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))


def build_target_bundle(
    ctx: dict,
    task_results: list[dict],
    skipped: list[dict],
    coverage: dict,
    missing_data: list[dict],
) -> dict:
    """Build the raw bundle for one target."""
    raw_outputs = []
    for r in task_results:
        raw_outputs.append({
            "module":          r["module"],
            "status":          r["status"],
            "raw_output_path": r["output_path"],
            "record_count":    r["record_count"],
            "error":           r["error"],
        })
    for s in skipped:
        raw_outputs.append({
            "module":          s["module"],
            "status":          "skipped",
            "raw_output_path": None,
            "record_count":    0,
            "error":           s["reason"],
        })

    return {
        "target_id":             ctx["target_id"],
        "target_name":           ctx["target_name"],
        "target_type":           ctx["target_type"],
        "ticker":                ctx.get("ticker"),
        "market":                ctx.get("market", "india"),
        "deep_dive_depth":       ctx.get("deep_dive_depth", "standard"),
        "source_opportunity_ids": ctx.get("source_opportunity_ids", []),
        "why_selected":          ctx.get("why_selected", []),
        "questions_to_answer":   ctx.get("questions_to_answer", []),
        "raw_outputs":           raw_outputs,
        "coverage_status":       coverage.get("coverage_status", "unknown"),
        "covered_questions":     coverage.get("covered_questions", 0),
        "total_questions":       coverage.get("total_questions", 0),
        "missing_data":          missing_data,
        "created_at":            datetime.now(_IST).isoformat(),
    }


def build_and_write(
    layer7_dir: Path,
    research_run_id: str,
    contexts: list[dict],
    all_task_results: dict[str, list[dict]],
    all_skipped: dict[str, list[dict]],
    coverage_by_target: dict[str, dict],
    missing_by_target: dict[str, list[dict]],
) -> dict:
    """
    Write per-target bundle.json files + top-level target_raw_bundles.json.
    Returns the top-level bundles dict.
    """
    layer7_dir = Path(layer7_dir)
    bundles    = []

    for ctx in contexts:
        tid     = ctx["target_id"]
        results = all_task_results.get(tid, [])
        skipped = all_skipped.get(tid, [])
        cov     = coverage_by_target.get(tid, {})
        missing = missing_by_target.get(tid, [])

        bundle = build_target_bundle(ctx, results, skipped, cov, missing)
        bundles.append(bundle)

        # Write per-target bundle.json
        target_dir = Path(ctx["output_dir"])
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "target_bundle.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    full_bundle = {
        "research_run_id": research_run_id,
        "layer":           "L7_targeted_deep_dive_extraction",
        "created_at":      datetime.now(_IST).isoformat(),
        "total_targets":   len(contexts),
        "target_raw_bundles": bundles,
    }

    (layer7_dir / "target_raw_bundles.json").write_text(
        json.dumps(full_bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return full_bundle
