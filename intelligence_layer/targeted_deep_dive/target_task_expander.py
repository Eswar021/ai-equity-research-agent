"""
intelligence_layer/targeted_deep_dive/target_task_expander.py — Layer 7

Expands a target execution context into a flat list of executable task specs.
Each task has: task_id, module, fetch_fn, kwargs, output_path.

Tasks for modules not in the registry are skipped (recorded with reason).

Design doc: docs/system_design_docs/layer_7.md §10.4 target_task_expander.py
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intelligence_layer.targeted_deep_dive import collector_registry_adapter


def expand(ctx: dict) -> tuple[list[dict], list[dict]]:
    """
    Returns (tasks, skipped).

    tasks:   list of executable task specs
    skipped: list of {module, reason} for modules that couldn't be expanded
    """
    tasks:   list[dict] = []
    skipped: list[dict] = []

    target_id  = ctx["target_id"]
    output_dir = Path(ctx["output_dir"])

    for spec in ctx["module_specs"]:
        module = spec.get("module", "")
        params = spec.get("params", {})

        entry = collector_registry_adapter.get(module)
        if entry is None:
            skipped.append({"module": module, "reason": "not_in_registry"})
            continue

        # Build the kwargs the fetch function will receive
        kwargs = entry["build_kwargs"](params, ctx)

        task_id     = spec.get("task_id") or f"DD_{ctx['slug']}_{module.upper()}"
        output_path = output_dir / f"{module}.json"

        tasks.append({
            "task_id":     task_id,
            "target_id":   target_id,
            "module":      module,
            "source_type": entry["source_type"],
            "fetch_fn":    entry["fn"],
            "kwargs":      kwargs,
            "output_path": output_path,
        })

    return tasks, skipped


if __name__ == "__main__":
    import sys, json
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from intelligence_layer.targeted_deep_dive.deep_dive_plan_loader import load
    from intelligence_layer.targeted_deep_dive.target_execution_context_builder import build_all_contexts

    result = load(Path("output/2026-05-10/layer6/deep_dive_plan.json"))
    ctxs   = build_all_contexts(result["plan"], Path("output/2026-05-10/layer7"))

    for ctx in ctxs[:2]:
        tasks, skipped = expand(ctx)
        print(f"\n{ctx['target_name']} ({ctx['ticker']}): {len(tasks)} tasks, {len(skipped)} skipped")
        for t in tasks:
            print(f"  {t['task_id']:40} → {t['output_path'].name}")
