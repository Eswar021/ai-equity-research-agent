"""
intelligence_layer/targeted_deep_dive/target_task_scheduler.py — Layer 7

Executes a list of tasks for ONE target using ThreadPoolExecutor.
Targets are run sequentially by the runner; tasks within a target run in parallel.

ADR-L7-005: Sequential targets, parallel tasks within target (max_workers=4).

Design doc: docs/system_design_docs/layer_7.md §10.7 target_task_scheduler.py
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from concurrent.futures import ThreadPoolExecutor, as_completed
from intelligence_layer.targeted_deep_dive import target_output_writer


def run_tasks(tasks: list[dict], max_workers: int = 4) -> list[dict]:
    """
    Execute all tasks for one target in a thread pool.
    Returns list of result dicts (one per task).
    """
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_task = {
            pool.submit(target_output_writer.execute_task, task): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            results.append(future.result())

    # Sort by original task order for deterministic output
    task_order = {t["task_id"]: i for i, t in enumerate(tasks)}
    results.sort(key=lambda r: task_order.get(r["task_id"], 999))

    return results


if __name__ == "__main__":
    # Quick smoke test: run market_data for TCS only
    import json
    from intelligence_layer.targeted_deep_dive.deep_dive_plan_loader import load
    from intelligence_layer.targeted_deep_dive.target_execution_context_builder import build_all_contexts
    from intelligence_layer.targeted_deep_dive.target_task_expander import expand

    result = load(Path("output/2026-05-10/layer6/deep_dive_plan.json"))
    ctxs   = build_all_contexts(result["plan"], Path("output/2026-05-10/layer7"))

    # Just market_data for TCS
    tasks, _ = expand(ctxs[0])
    tasks = [t for t in tasks if t["module"] == "market_data"]

    print(f"Running {len(tasks)} task(s) for {ctxs[0]['target_name']}...")
    results = run_tasks(tasks)
    for r in results:
        print(f"  {r['module']:20} status={r['status']:8} records={r['record_count']} error={r['error']}")
