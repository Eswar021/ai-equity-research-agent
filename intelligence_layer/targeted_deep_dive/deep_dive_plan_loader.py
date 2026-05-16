"""
intelligence_layer/targeted_deep_dive/deep_dive_plan_loader.py — Layer 7

Loads the deep_dive_plan.json produced by Layer 6 and returns a
validated plan dict plus a load summary.

Design doc: docs/system_design_docs/layer_7.md §10.2 deep_dive_plan_loader.py
"""

from __future__ import annotations
import json
from pathlib import Path


def load(plan_path: Path) -> dict:
    """
    Load and sanity-check deep_dive_plan.json.

    Returns:
        {
            "plan":         <full plan dict>,
            "load_summary": {
                "plan_id":       str,
                "target_count":  int,
                "task_count":    int,
                "warnings":      list[str],   # non-fatal issues
            }
        }
    """
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    warnings: list[str] = []
    targets = plan.get("targets", [])

    for t in targets:
        if not t.get("target_id"):
            warnings.append(f"Target missing target_id: {t.get('target_name')}")
        if not t.get("modules_to_run"):
            warnings.append(f"Target {t.get('target_id')} has no modules_to_run")
        if t.get("target_type") == "listed_company" and not t.get("ticker"):
            warnings.append(f"Listed company {t.get('target_name')} has no ticker")

    return {
        "plan": plan,
        "load_summary": {
            "plan_id":      plan.get("deep_dive_plan_id", ""),
            "target_count": len(targets),
            "task_count":   plan.get("total_tasks", 0),
            "warnings":     warnings,
        },
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from config.paths import LAYER6_DIR

    result = load(LAYER6_DIR / "deep_dive_plan.json")
    print(json.dumps(result["load_summary"], indent=2))
    print(f"\nFirst target: {result['plan']['targets'][0]['target_name']} — {len(result['plan']['targets'][0]['modules_to_run'])} modules")
