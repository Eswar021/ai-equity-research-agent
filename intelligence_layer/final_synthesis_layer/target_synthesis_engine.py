"""
intelligence_layer/final_synthesis_layer/target_synthesis_engine.py — Layer 10

LLM agent: synthesizes specialist assessments into a final target view.
1 LLM call per target. Returns final_view, summary, supporting/weakening points.

ADR-L10-001: LLM only for narrative explanation; scoring/policy is deterministic.
ADR-L10-002: method="function_calling" — same pattern as all L9 agents.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator

_SYSTEM_PROMPT = """\
You are a senior investment research analyst synthesizing specialist assessments into a final target view.

You receive 4 specialist assessments (fundamental, valuation, risk, thesis validation) plus scorecard metrics.

Your job:
  1. Write a coherent 3-4 sentence final summary combining all specialist views.
  2. List 3-5 key supporting points (grounded in specialist findings).
  3. List 2-4 key weakening points or unresolved risks.
  4. Note the most critical data gaps that limit confidence.

Rules:
  - Do NOT say "buy", "sell", "invest", "allocate", "entry price", "stop loss".
  - Do NOT make a final trade recommendation.
  - Every point must reference something from the specialist assessments.
  - If specialist views conflict, acknowledge the conflict.
  - Return JSON matching the TargetSynthesis schema.

final_view_rationale: one sentence explaining WHY this target is interesting (or not),
  synthesizing the core tension across specialist views.
"""


class TargetSynthesis(BaseModel):
    final_view_rationale: str
    final_summary: str
    supporting_points: list[str]
    weakening_points: list[str]
    critical_gaps_summary: list[str]
    specialist_alignment: str  # e.g. "fundamental positive, valuation fair, risk elevated, thesis mixed"
    confidence: float

    @field_validator("supporting_points", "weakening_points", "critical_gaps_summary", mode="before")
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

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if isinstance(v, (int, float)) and v > 1.0:
            return round(v / 100.0, 3)
        return v


def synthesize(ctx: dict, market_posture: dict, llm) -> dict:
    tid    = ctx["target_id"]
    name   = ctx["target_name"]
    ticker = ctx["ticker"]
    sc     = ctx["scorecard"]
    assessments = ctx.get("specialist_assessments", {})

    # ── Format specialist summaries ───────────────────────────────────────────
    def _fmt_assess(atype: str) -> str:
        a = assessments.get(atype, {})
        if not a:
            return f"  {atype}: (not available)"
        label = a.get("assessment_label", "")
        summary = a.get("summary", "")[:300]
        conf = a.get("confidence", "?")
        return f"  {atype}: [{label}] conf={conf}\n    {summary}"

    assess_text = "\n".join(_fmt_assess(t) for t in
                            ["fundamental_agent", "valuation_agent", "risk_agent", "thesis_agent"])

    # ── Format scorecard metrics ──────────────────────────────────────────────
    dim = sc.get("dimension_scores", {})
    dim_text = "\n".join(f"  {k}: {v}" for k, v in dim.items())
    dim_labels = sc.get("dimension_labels", {})
    label_text = "\n".join(f"  {k}: {v}" for k, v in dim_labels.items())

    # ── Top risks ─────────────────────────────────────────────────────────────
    top_risks = sc.get("top_risks", [])
    risks_text = "\n".join(f"  - {r[:120]}" for r in top_risks[:4])

    # ── Data gaps ─────────────────────────────────────────────────────────────
    gaps = ctx.get("critical_data_gaps", [])
    gaps_text = "\n".join(f"  - {g[:100]}" for g in gaps[:5]) if gaps else "  (none)"

    # ── Market posture ────────────────────────────────────────────────────────
    mkt_posture = market_posture.get("final_market_posture", "selective_research")
    mkt_summary = market_posture.get("summary", "")[:200]

    user_prompt = f"""\
TARGET: {name} ({ticker})
TARGET_ID: {tid}
TIME HORIZON: {sc.get('time_horizon', 'unknown')}
THESIS STATUS: {sc.get('thesis_status', 'unknown')}
THESIS: {sc.get('thesis_statement_snippet', '')[:300]}

SPECIALIST ASSESSMENTS:
{assess_text}

DIMENSION SCORES (0-100):
{dim_text}

DIMENSION LABELS:
{label_text}

TOP RISKS:
{risks_text}

CRITICAL DATA GAPS:
{gaps_text}

MARKET CONTEXT:
  posture={mkt_posture}
  {mkt_summary}

Synthesize all specialist views into a coherent final target view.
Return JSON matching the TargetSynthesis schema.
"""

    structured_llm = llm.with_structured_output(TargetSynthesis, method="function_calling")
    result: TargetSynthesis = structured_llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])

    return {
        "target_id":             tid,
        "target_name":           name,
        "ticker":                ticker,
        "target_type":           ctx.get("target_type", "listed_company"),
        "time_horizon":          sc.get("time_horizon", ""),
        "thesis_status":         sc.get("thesis_status", ""),
        "final_view_rationale":  result.final_view_rationale,
        "final_summary":         result.final_summary,
        "supporting_points":     result.supporting_points,
        "weakening_points":      result.weakening_points,
        "critical_gaps_summary": result.critical_gaps_summary,
        "specialist_alignment":  result.specialist_alignment,
        "dimension_scores":      dim,
        "dimension_labels":      dim_labels,
        "overall_specialist_confidence": sc.get("overall_specialist_confidence", 0.5),
        "synthesis_confidence":  result.confidence,
        "not_final_recommendation": True,
    }
