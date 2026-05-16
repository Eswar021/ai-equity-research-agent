"""
intelligence_layer/research_target_planner/deep_dive_depth_controller.py — Layer 6

Decides research depth for each selected target.

Depth levels:
  light    — market_data + price_history only
  standard — + screener, peers, analyst_estimates, filings
  deep     — + filing_docs (transcripts, presentations)

Design doc: docs/system_design_docs/layer_6.md §16 deep_dive_depth_controller.py
"""

from __future__ import annotations


def decide_depth(target: dict) -> str:
    """Return 'light' | 'standard' | 'deep' for a single target."""
    score = target.get("priority_score", 0)
    ttype = target.get("target_type", "unknown")

    # Non-listed types don't get listed-company modules regardless of score
    if ttype not in ("listed_company", "private_unlisted_company"):
        return "light"

    if score >= 80:
        return "deep"
    if score >= 65:
        return "standard"
    return "light"


def assign_depth_all(selected_targets: list[dict]) -> list[dict]:
    """Assign deep_dive_depth to all selected targets in-place."""
    for t in selected_targets:
        depth = decide_depth(t)
        t["deep_dive_depth"] = depth
        t["depth_reason"] = _depth_reason(t, depth)
    return selected_targets


def _depth_reason(t: dict, depth: str) -> list[str]:
    reasons = [f"Score {t.get('priority_score', 0)} → {depth} depth"]
    if t.get("data_gaps"):
        reasons.append(f"{len(t['data_gaps'])} data gaps flagged")
    if depth == "deep":
        reasons.append("High priority — full filing docs and transcripts included")
    return reasons
