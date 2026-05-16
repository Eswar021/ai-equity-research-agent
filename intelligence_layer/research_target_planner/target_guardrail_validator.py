"""
intelligence_layer/research_target_planner/target_guardrail_validator.py — Layer 6

Validates selected targets and downgrades those that don't meet evidence standards.

Rules:
  1. No supporting_refs AND merged_count=1 → downgrade to watch
  2. ticker_resolution_status=not_found AND target_type=listed_company → downgrade
  3. private_unlisted_company with no proxy mapping found → watch_only
  4. Single weak source (merged_count=1 + confidence < 0.45) → downgrade

Design doc: docs/system_design_docs/layer_6.md §19 target_guardrail_validator.py
"""

from __future__ import annotations


def check_all(selected_targets: list[dict], proxy_mappings: list[dict]) -> list[dict]:
    """
    Run guardrail checks on selected targets.
    Returns list of guardrail_result dicts.
    """
    proxy_source_ids = {p["source_target_id"] for p in proxy_mappings}
    results: list[dict] = []

    for t in selected_targets:
        issues  = []
        status  = "pass"

        refs         = t.get("supporting_refs") or []
        merged_count = t.get("merged_count", 1)
        ticker_status = t.get("ticker_resolution_status", "")
        ttype        = t.get("target_type", "")
        confidence   = t.get("confidence", 0.5)
        unres_id     = t.get("unresolved_target_id", "")

        # Rule 1: no evidence trail and single source
        if not refs and merged_count == 1:
            issues.append("No supporting_refs and single source hypothesis")
            status = "downgraded"

        # Rule 2: listed_company but ticker not found
        if ttype == "listed_company" and ticker_status == "not_found":
            issues.append("Ticker not found — cannot run listed-company modules")
            status = "downgraded"

        # Rule 3: private_unlisted with no proxy mapping
        if ttype == "private_unlisted_company" and unres_id and unres_id not in proxy_source_ids:
            issues.append("No proxy mapping found for private company")
            status = "watch_only"

        # Rule 4: single weak source
        if merged_count == 1 and confidence < 0.45:
            issues.append(f"Single source with low confidence ({confidence:.2f})")
            status = "downgraded"

        results.append({
            "target_id":      t.get("target_id", ""),
            "target_name":    t.get("target_name", ""),
            "status":         status,
            "issues":         issues,
            "guardrail_action": _action(status),
        })

    return results


def apply_guardrail_decisions(selected_targets: list[dict],
                               guardrail_results: list[dict]) -> list[dict]:
    """
    Attach guardrail status to targets in-place.
    Returns the updated selected_targets list (pass targets only — others moved out).
    """
    gr_map = {r["target_id"]: r for r in guardrail_results}
    for t in selected_targets:
        gr = gr_map.get(t["target_id"], {})
        t["guardrail_status"]  = gr.get("status", "pass")
        t["guardrail_action"]  = gr.get("guardrail_action", "proceed")
        t["guardrail_issues"]  = gr.get("issues", [])
    return selected_targets


def _action(status: str) -> str:
    if status == "pass":       return "proceed_with_deep_dive"
    if status == "downgraded": return "downgrade_to_light_research"
    if status == "watch_only": return "add_to_watch_memory_only"
    return "proceed_with_deep_dive"
