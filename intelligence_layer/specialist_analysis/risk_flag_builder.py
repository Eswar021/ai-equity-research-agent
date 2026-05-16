"""
intelligence_layer/specialist_analysis/risk_flag_builder.py — Layer 9

Consolidates risk flags from the risk_agent across all targets.
Also adds structural risk flags from price features (deep drawdown, EPS cuts).
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def build_all(task_results: list[dict], inputs: dict, date_str: str) -> list[dict]:
    """Collect and return all consolidated risk flags."""
    all_flags: list[dict] = []

    for result in task_results:
        if result.get("agent_type") != "risk_agent" or result["status"] == "failed":
            continue
        assessment = result.get("assessment", {})
        tid = assessment.get("target_id", "")
        flags = assessment.get("risk_flags", [])

        for rf in flags:
            # Ensure IDs and required fields
            if not rf.get("risk_flag_id"):
                _CTR[0] += 1
                rf["risk_flag_id"] = f"RISK_{date_str}_{tid}_{_CTR[0]:03d}"
            rf.setdefault("target_id", tid)
            rf.setdefault("target_name", assessment.get("target_name", ""))
            rf.setdefault("ticker", assessment.get("ticker", ""))
            rf.setdefault("source_agents", ["risk_agent"])
            rf.setdefault("created_at", datetime.now(_IST).isoformat())
            all_flags.append(rf)

    return all_flags
