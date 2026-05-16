"""
intelligence_layer/targeted_deep_dive/target_execution_context_builder.py — Layer 7

Builds a per-target execution context from a plan target dict.
The context carries metadata + resolved output_dir used by all downstream modules.

Design doc: docs/system_design_docs/layer_7.md §10.3 target_execution_context_builder.py
"""

from __future__ import annotations
import re
from pathlib import Path


def build_context(plan_target: dict, layer7_dir: Path) -> dict:
    """
    Build execution context for one target.

    Returns a flat dict with everything downstream modules need per target.
    """
    target_id   = plan_target["target_id"]
    target_name = plan_target.get("target_name", "")
    ticker      = plan_target.get("ticker", "")
    target_type = plan_target.get("target_type", "")

    slug = _make_slug(ticker, target_name)
    output_dir = Path(layer7_dir) / "targets" / f"{target_id}_{slug}"

    return {
        "target_id":             target_id,
        "target_name":           target_name,
        "target_type":           target_type,
        "ticker":                ticker,
        "market":                "india",
        "deep_dive_depth":       plan_target.get("deep_dive_depth", "standard"),
        "priority_score":        plan_target.get("priority_score", 0),
        "source_opportunity_ids": plan_target.get("source_opportunity_ids", []),
        "questions_to_answer":   plan_target.get("questions_to_answer", []),
        "why_selected":          plan_target.get("why_selected", []),
        "modules_to_run":        [m["module"] for m in plan_target.get("modules_to_run", [])],
        "module_specs":          plan_target.get("modules_to_run", []),  # full specs with params
        "output_dir":            output_dir,
        "slug":                  slug,
    }


def build_all_contexts(plan: dict, layer7_dir: Path) -> list[dict]:
    return [build_context(t, layer7_dir) for t in plan.get("targets", [])]


def _make_slug(ticker: str, name: str) -> str:
    if ticker:
        # TCS.NS → TCS, HCLTECH.NS → HCLTECH
        return re.sub(r"\.(NS|BO)$", "", ticker.upper())
    # Fall back to first two words of name, stripped to alphanum
    words = re.sub(r"[^A-Za-z0-9 ]", "", name).split()
    return "_".join(w.upper() for w in words[:2]) if words else "UNKNOWN"


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from intelligence_layer.targeted_deep_dive.deep_dive_plan_loader import load

    result = load(Path("output/2026-05-10/layer6/deep_dive_plan.json"))
    ctxs = build_all_contexts(result["plan"], Path("output/2026-05-10/layer7"))
    for c in ctxs:
        print(f"{c['target_id']} | {c['target_name'][:30]:30} | {c['ticker']:12} | dir: .../{c['output_dir'].name}")
