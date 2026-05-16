"""
intelligence_layer/targeted_deep_dive/target_output_writer.py — Layer 7

Executes a single task: calls the fetch function, writes the result to
the task's output_path as JSON, returns a result dict.

Design doc: docs/system_design_docs/layer_7.md §10.8 target_output_writer.py
"""

from __future__ import annotations
import json
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))

# Keys that hold the primary list payload in each module's response
_LIST_KEYS = ("items", "history", "announcements", "peers", "quarterly_results",
              "recommendations", "holdings", "profile_pages", "transcripts")


def _count_records(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return len(data[key])
        # Single-record dicts (market_data, analyst_estimates summary, etc.) → 1
        non_meta = [k for k in data if not k.startswith("_")]
        return 1 if non_meta else 0
    return 0


def execute_task(task: dict) -> dict:
    """
    Run one collector task. Returns:
    {
        task_id, target_id, module, status, output_path, record_count, error, collected_at
    }
    status: "success" | "failed"
    """
    task_id     = task["task_id"]
    target_id   = task["target_id"]
    module      = task["module"]
    fetch_fn    = task["fetch_fn"]
    kwargs      = task["kwargs"]
    output_path = Path(task["output_path"])
    collected_at = datetime.now(_IST).isoformat()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = fetch_fn(**kwargs)

        # Attach target_id + module for traceability (design doc §22)
        if isinstance(data, dict):
            data["_target_id"] = target_id
            data["_module"]    = module
            data["_collected_at"] = collected_at
        elif isinstance(data, list):
            data = {
                "items":         data,
                "_target_id":    target_id,
                "_module":       module,
                "_collected_at": collected_at,
            }

        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        record_count = _count_records(data)

        return {
            "task_id":      task_id,
            "target_id":    target_id,
            "module":       module,
            "status":       "success",
            "output_path":  str(output_path),
            "record_count": record_count,
            "error":        None,
            "collected_at": collected_at,
        }

    except Exception as exc:
        return {
            "task_id":      task_id,
            "target_id":    target_id,
            "module":       module,
            "status":       "failed",
            "output_path":  None,
            "record_count": 0,
            "error":        f"{type(exc).__name__}: {exc}",
            "collected_at": collected_at,
        }
