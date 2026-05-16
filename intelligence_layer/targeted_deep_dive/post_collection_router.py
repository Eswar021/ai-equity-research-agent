"""
intelligence_layer/targeted_deep_dive/post_collection_router.py — Layer 7

Writes all remaining Layer 7 artifacts (status, source records, coverage,
missing data, manifest) and returns the Layer 2 handoff dict.

Design doc: docs/system_design_docs/layer_7.md §10.14 post_collection_router.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))


def write_and_route(
    layer7_dir: Path,
    research_run_id: str,
    plan_id: str,
    extraction_statuses: list[dict],
    source_records: list[dict],
    coverage_list: list[dict],
    missing_data: list[dict],
    bundle_summary: dict,
) -> dict:
    """
    Write all output files and return the Layer 2 handoff manifest.
    """
    layer7_dir = Path(layer7_dir)
    layer7_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(_IST).isoformat()

    # Write each artifact file
    _write(layer7_dir / "target_extraction_status.json",  extraction_statuses)
    _write(layer7_dir / "target_source_records.json",     source_records)
    _write(layer7_dir / "coverage_report.json",           _build_coverage_report(
        research_run_id, coverage_list, extraction_statuses, missing_data
    ))
    _write(layer7_dir / "missing_data_report.json",       missing_data)

    # Quality summary
    n_success = sum(1 for s in extraction_statuses if s["target_status"] == "success")
    n_partial  = sum(1 for s in extraction_statuses if s["target_status"] == "partial_success")
    n_failed   = sum(1 for s in extraction_statuses if s["target_status"] == "failed")
    total_tasks_run = sum(s["modules_requested"] for s in extraction_statuses)
    tasks_ok   = sum(s["modules_success"] for s in extraction_statuses)
    tasks_fail = sum(s["modules_failed"] for s in extraction_statuses)
    tasks_skip = sum(s["modules_skipped"] for s in extraction_statuses)

    manifest = {
        "research_run_id":              research_run_id,
        "deep_dive_plan_id":            plan_id,
        "layer":                        "L7_targeted_deep_dive_extraction",
        "created_at":                   now_str,
        "status":                       "success" if n_failed == 0 else "partial",
        "targets_processed":            len(extraction_statuses),
        "targets_success":              n_success,
        "targets_partial":              n_partial,
        "targets_failed":               n_failed,
        "collector_tasks_run":          total_tasks_run,
        "collector_tasks_success":      tasks_ok,
        "collector_tasks_failed":       tasks_fail,
        "collector_tasks_skipped":      tasks_skip,
        "target_raw_bundles_path":      str(layer7_dir / "target_raw_bundles.json"),
        "target_source_records_path":   str(layer7_dir / "target_source_records.json"),
        "target_extraction_status_path": str(layer7_dir / "target_extraction_status.json"),
        "coverage_report_path":         str(layer7_dir / "coverage_report.json"),
        "missing_data_report_path":     str(layer7_dir / "missing_data_report.json"),
        # Layer 2 handoff contract (§25 of design doc)
        "next_layer_input": {
            "send_to_layer2":          True,
            "raw_bundle_path":         str(layer7_dir / "target_raw_bundles.json"),
            "source_records_path":     str(layer7_dir / "target_source_records.json"),
            "collection_status_path":  str(layer7_dir / "target_extraction_status.json"),
            "canonicalization_scope": {
                "include_targeted_context": True,
                "include_broad_context":    False,
            },
        },
    }
    _write(layer7_dir / "layer7_manifest.json", manifest)

    return manifest


def _build_coverage_report(
    research_run_id: str,
    coverage_list: list[dict],
    extraction_statuses: list[dict],
    missing_data: list[dict],
) -> dict:
    from collections import Counter
    failure_counts = Counter(m["module"] for m in missing_data if "skipped" not in m.get("reason", ""))
    common_failures = [
        {"module": mod, "count": cnt}
        for mod, cnt in failure_counts.most_common()
    ]
    total_q  = sum(c.get("total_questions", 0) for c in coverage_list)
    covered_q = sum(c.get("covered_questions", 0) for c in coverage_list)
    completeness = round(covered_q / total_q, 2) if total_q else 1.0

    return {
        "research_run_id":         research_run_id,
        "targets_requested":       len(extraction_statuses),
        "targets_success":         sum(1 for s in extraction_statuses if s["target_status"] == "success"),
        "targets_partial":         sum(1 for s in extraction_statuses if s["target_status"] == "partial_success"),
        "targets_failed":          sum(1 for s in extraction_statuses if s["target_status"] == "failed"),
        "coverage_by_target":      coverage_list,
        "common_failures":         common_failures,
        "data_completeness_score": completeness,
    }


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
