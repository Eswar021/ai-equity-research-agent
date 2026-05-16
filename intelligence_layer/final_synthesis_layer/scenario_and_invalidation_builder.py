"""
intelligence_layer/final_synthesis_layer/scenario_and_invalidation_builder.py — Layer 10

LLM agent: builds bull/base/bear scenarios and invalidation conditions per target.
1 LLM call per target.

ADR-L10-003: scenarios are LLM-generated but grounded in specialist assessments.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator


_SYSTEM_PROMPT = """\
You are a senior investment research analyst writing scenario analysis for a target.

You receive:
  - Final target synthesis (supporting/weakening points)
  - Specialist assessments (fundamental, valuation, risk, thesis)
  - Existing invalidating conditions from the thesis

Your job: write concise bull/base/bear scenarios and list invalidation conditions.

Rules:
  - Each scenario case: 1-2 sentences.
  - Bull: what has to go right for the thesis to exceed expectations.
  - Base: the most probable outcome given current evidence.
  - Bear: what could go significantly wrong.
  - invalidation_conditions: specific observable events that would invalidate the thesis.
  - monitoring_triggers: what to watch in the next 30-90 days.
  - Do NOT say "buy", "sell", "invest", "guarantee".
  - Return JSON matching ScenarioAnalysis schema.
"""


class ScenarioAnalysis(BaseModel):
    bull_case: str
    base_case: str
    bear_case: str
    invalidation_conditions: list[str]
    monitoring_triggers: list[str]

    @field_validator("invalidation_conditions", "monitoring_triggers", mode="before")
    @classmethod
    def coerce_str_to_list(cls, v):
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            result = []
            for item in v:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    result.extend(str(val) for val in item.values() if val)
            return result
        return v


def build_all(calibrated_items: list[dict], ctx_by_tid: dict[str, dict], llm) -> list[dict]:
    results = []
    for item in calibrated_items:
        tid = item["target_id"]
        ctx = ctx_by_tid.get(tid, {})
        scenario = _build_one(item, ctx, llm)
        results.append({**item, "scenario_analysis": scenario})
    return results


def _build_one(item: dict, ctx: dict, llm) -> dict:
    name   = item.get("target_name", "")
    ticker = item.get("ticker", "")
    thesis_card = ctx.get("thesis_card", {}) or {}
    existing_invalidations = thesis_card.get("invalidating_conditions", [])
    if isinstance(existing_invalidations, str):
        existing_invalidations = [existing_invalidations]

    supporting = "\n".join(f"  - {p}" for p in item.get("supporting_points", [])[:4])
    weakening  = "\n".join(f"  - {p}" for p in item.get("weakening_points", [])[:4])
    gaps       = "\n".join(f"  - {g}" for g in item.get("critical_gaps_summary", [])[:3])
    inv_conds  = "\n".join(f"  - {c[:100]}" for c in existing_invalidations[:4])
    action     = item.get("action_label", "watchlist")
    thesis_status = item.get("thesis_status", "")

    user_prompt = f"""\
TARGET: {name} ({ticker})
ACTION LABEL: {action}
THESIS STATUS: {thesis_status}
FINAL SUMMARY: {item.get('final_summary', '')[:300]}

SUPPORTING POINTS:
{supporting or '  (none)'}

WEAKENING POINTS:
{weakening or '  (none)'}

CRITICAL GAPS:
{gaps or '  (none)'}

EXISTING INVALIDATING CONDITIONS (from thesis):
{inv_conds or '  (none listed)'}

Write concise bull/base/bear scenarios and invalidation/monitoring items.
Return JSON matching ScenarioAnalysis schema.
"""

    try:
        structured_llm = llm.with_structured_output(ScenarioAnalysis, method="function_calling")
        result: ScenarioAnalysis = structured_llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ])
        return {
            "bull_case":               result.bull_case,
            "base_case":               result.base_case,
            "bear_case":               result.bear_case,
            "invalidation_conditions": result.invalidation_conditions,
            "monitoring_triggers":     result.monitoring_triggers,
        }
    except Exception as e:
        # Fallback: minimal scenario from existing data
        return {
            "bull_case":               "Thesis confirms and valuation rerates positively.",
            "base_case":               "Target tracks in line with market; thesis remains partially supported.",
            "bear_case":               "Key risks materialize and evidence deteriorates.",
            "invalidation_conditions": existing_invalidations[:3] or ["Thesis-breaking evidence emerges"],
            "monitoring_triggers":     ["Next quarterly result", "Management commentary"],
            "error":                   str(e)[:100],
        }
