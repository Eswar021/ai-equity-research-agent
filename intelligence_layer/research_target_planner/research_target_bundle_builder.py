"""
intelligence_layer/research_target_planner/research_target_bundle_builder.py — Layer 6

Writes all Layer 6 artifacts to layer6_dir and returns the manifest.

Output files:
  research_target_candidates.json
  target_resolution_results.json
  selected_research_targets.json
  deferred_targets.json
  rejected_targets.json
  unresolved_entities.json
  proxy_mapping_results.json
  sector_mapping_results.json
  macro_mapping_results.json
  deep_dive_plan.json
  target_selection_audit.json
  layer6_quality_report.json
  layer6_manifest.json

Design doc: docs/system_design_docs/layer_6.md §20 research_target_bundle_builder.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))


def build_and_write(
    layer6_dir: Path,
    run_id: str,
    all_candidates: list[dict],
    selected_targets: list[dict],
    deferred_targets: list[dict],
    watch_targets: list[dict],
    rejected_targets: list[dict],
    unresolved_entities: list[dict],
    proxy_mappings: list[dict],
    sector_mappings: list[dict],
    macro_mappings: list[dict],
    guardrail_results: list[dict],
    deep_dive_plan: dict,
    opportunity_filter_result: dict,
    load_summary: dict,
) -> dict:
    layer6_dir = Path(layer6_dir)
    layer6_dir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(_IST).isoformat()

    _write(layer6_dir / "research_target_candidates.json", all_candidates)
    _write(layer6_dir / "selected_research_targets.json",  selected_targets)
    _write(layer6_dir / "deferred_targets.json",           deferred_targets)
    _write(layer6_dir / "watch_targets.json",              watch_targets)
    _write(layer6_dir / "rejected_targets.json",           rejected_targets)
    _write(layer6_dir / "unresolved_entities.json",        unresolved_entities)
    _write(layer6_dir / "proxy_mapping_results.json",      proxy_mappings)
    _write(layer6_dir / "sector_mapping_results.json",     sector_mappings)
    _write(layer6_dir / "macro_mapping_results.json",      macro_mappings)
    _write(layer6_dir / "guardrail_results.json",          guardrail_results)
    _write(layer6_dir / "deep_dive_plan.json",             deep_dive_plan)

    # Audit: one entry per target candidate with its fate
    audit: list[dict] = []
    for t in selected_targets + deferred_targets + watch_targets + rejected_targets:
        audit.append({
            "target_id":       t.get("target_id", ""),
            "target_name":     t.get("target_name", ""),
            "target_type":     t.get("target_type", ""),
            "ticker":          t.get("ticker"),
            "priority_score":  t.get("priority_score", 0),
            "selection_status": t.get("selection_status", ""),
            "selection_reason": t.get("selection_reason", []),
            "guardrail_status": t.get("guardrail_status", ""),
        })
    _write(layer6_dir / "target_selection_audit.json", audit)

    # Quality report
    gr_pass = sum(1 for r in guardrail_results if r.get("status") == "pass")
    gr_down  = sum(1 for r in guardrail_results if r.get("status") == "downgraded")
    gr_watch = sum(1 for r in guardrail_results if r.get("status") == "watch_only")

    quality_report = {
        "research_run_id":                 run_id,
        "layer":                           "L6_research_target_planner",
        "created_at":                      now_str,
        "input_summary":                   load_summary,
        "hypotheses_accepted_for_planning": len(opportunity_filter_result.get("accepted", [])),
        "hypotheses_deferred":             len(opportunity_filter_result.get("deferred", [])),
        "hypotheses_rejected":             len(opportunity_filter_result.get("rejected", [])),
        "target_candidates_built":         len(all_candidates),
        "unresolved_entities_preserved":   len(unresolved_entities),
        "proxy_mappings_created":          len(proxy_mappings),
        "sector_mappings_created":         len(sector_mappings),
        "macro_mappings_created":          len(macro_mappings),
        "targets_selected":                len(selected_targets),
        "targets_deferred":                len(deferred_targets),
        "targets_watch":                   len(watch_targets),
        "targets_rejected":                len(rejected_targets),
        "guardrail_pass":                  gr_pass,
        "guardrail_downgraded":            gr_down,
        "guardrail_watch_only":            gr_watch,
        "deep_dive_plan_targets":          deep_dive_plan.get("total_targets", 0),
        "deep_dive_plan_tasks":            deep_dive_plan.get("total_tasks", 0),
        "type_breakdown": {
            "listed_company": sum(1 for t in selected_targets if t.get("target_type") == "listed_company"),
            "sector_theme":   sum(1 for t in selected_targets if t.get("target_type") == "sector_theme"),
            "macro_theme":    sum(1 for t in selected_targets if t.get("target_type") == "macro_theme"),
            "other":          sum(1 for t in selected_targets if t.get("target_type") not in ("listed_company","sector_theme","macro_theme")),
        },
    }
    _write(layer6_dir / "layer6_quality_report.json", quality_report)

    manifest = {
        "research_run_id":                 run_id,
        "layer":                           "L6_research_target_planner",
        "created_at":                      now_str,
        "status":                          "success",
        "research_target_candidates_path": str(layer6_dir / "research_target_candidates.json"),
        "selected_research_targets_path":  str(layer6_dir / "selected_research_targets.json"),
        "deferred_targets_path":           str(layer6_dir / "deferred_targets.json"),
        "rejected_targets_path":           str(layer6_dir / "rejected_targets.json"),
        "unresolved_entities_path":        str(layer6_dir / "unresolved_entities.json"),
        "deep_dive_plan_path":             str(layer6_dir / "deep_dive_plan.json"),
        "quality_report_path":             str(layer6_dir / "layer6_quality_report.json"),
        "quality_summary": {
            "targets_selected":   len(selected_targets),
            "targets_deferred":   len(deferred_targets),
            "deep_dive_tasks":    deep_dive_plan.get("total_tasks", 0),
        },
    }
    _write(layer6_dir / "layer6_manifest.json", manifest)

    return manifest


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
