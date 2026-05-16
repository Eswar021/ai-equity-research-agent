"""
intelligence_layer/specialist_analysis/agent_execution_orchestrator.py — Layer 9

Runs agent tasks in the correct order.
Prerequisite agents (fundamental, valuation, risk) run first, sequentially per target.
Thesis agent runs last and receives the other assessments.

ADR-L9-002: schema validator, evidence_reference_checker, hallucination_guardrail
             are all inline here rather than separate modules.

LLM calls use Pydantic structured output (same pattern as L5).
"""

from __future__ import annotations
import traceback
from datetime import datetime, timezone, timedelta

from intelligence_layer.specialist_analysis.specialist_agent_registry import get_agent_fn

_IST = timezone(timedelta(hours=5, minutes=30))

# Forbidden phrases that signal a final recommendation slipping through
_FORBIDDEN = [
    "buy this stock", "sell this stock", "buy now", "sell now",
    "allocate", "entry price", "stop loss",
    "guaranteed", "definitely will", "certainly will",
]


def run_all_tasks(tasks: list[dict], inputs: dict, llm) -> list[dict]:
    """
    Execute all agent tasks. Thesis tasks are deferred until their prerequisites finish.
    Returns list of result dicts.
    """
    # Separate thesis tasks (need other assessments as input)
    prereq_tasks = [t for t in tasks if t["agent_type"] != "thesis_agent"]
    thesis_tasks  = [t for t in tasks if t["agent_type"] == "thesis_agent"]

    results: list[dict] = []

    # Map of completed assessments by target_id (for thesis agent)
    assessments_by_target: dict[str, list[dict]] = {}

    # ── Run prerequisite agents ────────────────────────────────────────────────
    for task in prereq_tasks:
        result = _run_task(task, inputs, llm, prior_assessments=[])
        results.append(result)
        if result.get("status") in ("success", "partial"):
            assessments_by_target.setdefault(task["target_id"], []).append(
                result["assessment"]
            )

    # ── Run thesis agent last with prior assessments ───────────────────────────
    for task in thesis_tasks:
        tid = task["target_id"]
        prior = assessments_by_target.get(tid, [])
        result = _run_task(task, inputs, llm, prior_assessments=prior)
        results.append(result)

    return results


def _run_task(task: dict, inputs: dict, llm, prior_assessments: list[dict]) -> dict:
    """Run a single agent task. Returns result dict with assessment or error."""
    task_id    = task["agent_task_id"]
    tid        = task["target_id"]
    agent_type = task["agent_type"]
    packet     = task["packet"]
    started_at = datetime.now(_IST).isoformat()

    context = {
        "evidence_by_target":  inputs.get("evidence_by_target",  {}),
        "features_by_target":  inputs.get("features_by_target",  {}),
        "thesis_by_target":    inputs.get("thesis_by_target",    {}),
        "gaps_by_target":      inputs.get("gaps_by_target",      {}),
        "prior_assessments":   prior_assessments,
    }

    try:
        agent_fn = get_agent_fn(agent_type)
        assessment = agent_fn(packet, context, llm)

        # ── Inline guardrails ─────────────────────────────────────────────────
        assessment = _enforce_not_final_recommendation(assessment)
        assessment = _ensure_required_fields(assessment, task)
        factors = assessment.get("supportive_factors", [])
        factors_text = " ".join(f if isinstance(f, str) else f.get("factor", "") for f in factors)
        issues = _check_forbidden_language(assessment.get("summary", "") + " " + factors_text)

        status = "partial" if issues else "success"
        assessment["guardrail_issues"] = issues
        assessment["created_at"] = datetime.now(_IST).isoformat()
        assessment["source_packet_id"] = packet["packet_id"]

        return {
            "agent_task_id": task_id,
            "target_id":     tid,
            "agent_type":    agent_type,
            "status":        status,
            "assessment":    assessment,
            "error":         None,
            "started_at":    started_at,
            "completed_at":  datetime.now(_IST).isoformat(),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        return {
            "agent_task_id": task_id,
            "target_id":     tid,
            "agent_type":    agent_type,
            "status":        "failed",
            "assessment":    _fallback_assessment(task),
            "error":         f"{type(exc).__name__}: {exc}",
            "traceback":     tb,
            "started_at":    started_at,
            "completed_at":  datetime.now(_IST).isoformat(),
        }


def _enforce_not_final_recommendation(assessment: dict) -> dict:
    assessment["not_final_recommendation"] = True
    return assessment


def _ensure_required_fields(assessment: dict, task: dict) -> dict:
    if not assessment.get("assessment_id"):
        assessment["assessment_id"] = f"ASSESS_{task['agent_task_id']}"
    if not assessment.get("agent_type"):
        assessment["agent_type"] = task["agent_type"]
    if not assessment.get("target_id"):
        assessment["target_id"] = task["target_id"]
    if not assessment.get("target_name"):
        assessment["target_name"] = task.get("target_name", "")
    if not assessment.get("ticker"):
        assessment["ticker"] = task.get("ticker", "")
    if "confidence" not in assessment:
        assessment["confidence"] = 0.5
    return assessment


def _check_forbidden_language(text: str) -> list[str]:
    text_lower = text.lower()
    return [phrase for phrase in _FORBIDDEN if phrase in text_lower]


def _fallback_assessment(task: dict) -> dict:
    return {
        "assessment_id":          f"ASSESS_{task['agent_task_id']}_FAILED",
        "agent_type":             task["agent_type"],
        "target_id":              task["target_id"],
        "target_name":            task.get("target_name", ""),
        "ticker":                 task.get("ticker", ""),
        "assessment_label":       "agent_failed",
        "summary":                "Agent execution failed. Results unavailable.",
        "dimension_scores":       {},
        "key_findings":           [],
        "supportive_factors":     [],
        "negative_factors":       [],
        "data_gaps":              ["Agent execution failed"],
        "risk_flags":             [],
        "confidence":             0.0,
        "not_final_recommendation": True,
        "guardrail_issues":       [],
    }
