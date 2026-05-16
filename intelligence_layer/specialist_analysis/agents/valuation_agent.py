"""
intelligence_layer/specialist_analysis/agents/valuation_agent.py — Layer 9

Specialist agent: assesses valuation attractiveness using PE/PB ratios,
peer comparison, analyst price targets, and earnings yield.

Uses LLM with Pydantic structured output.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator

_SYSTEM_PROMPT = """\
You are a specialist investment analysis agent focused on equity valuation.

Your role: Assess whether the stock's current valuation is attractive, fair, expensive, \
or unclear based ONLY on the numeric features and evidence provided. \
Do not invent facts or use general knowledge about the company.

Rules:
- Do NOT recommend buying, selling, or any portfolio action.
- Do not say "buy", "sell", "invest", "allocate", "entry price", "stop loss".
- If valuation data is incomplete, say so and lower confidence.
- PE/PB numbers are facts; your interpretation of them is analysis.
- Return JSON only, matching the ValuationAssessment schema.

Dimension scores (0-100, where 0=very expensive/no margin of safety, 100=very cheap/high margin of safety):
  absolute_valuation_score: PE, PB, earnings yield vs general market norms
  relative_valuation_score: how cheap/expensive vs peers (percentile)
  analyst_upside_score: analyst target price upside as a valuation signal
  margin_of_safety_score: distance from 52w high + downside cushion
  overall_valuation_score: weighted composite

Assessment labels:
  deeply_discounted | attractively_valued | fairly_valued | moderately_expensive | overvalued | insufficient_data
"""


class KeyFinding(BaseModel):
    finding: str
    evidence_refs: list[str]


class ValuationAssessment(BaseModel):
    assessment_label: str
    summary: str
    absolute_valuation_score: int
    relative_valuation_score: int
    analyst_upside_score: int
    margin_of_safety_score: int
    overall_valuation_score: int
    key_findings: list[KeyFinding]
    supportive_factors: list[str]
    negative_factors: list[str]
    data_gaps: list[str]
    confidence: float

    @field_validator("supportive_factors", "negative_factors", "data_gaps", mode="before")
    @classmethod
    def coerce_str_to_list(cls, v):
        if isinstance(v, str):
            return [v] if v.strip() and v.strip().lower() not in ("none", "none.", "n/a") else []
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


def run(packet: dict, context: dict, llm) -> dict:
    target_summary = packet.get("target_summary", {})
    name   = target_summary.get("target_name", "Unknown")
    ticker = target_summary.get("ticker", "")

    features_text = _format_features(packet.get("inline_features", {}),
                                     groups={"valuation", "peer", "analyst", "price"})
    evidence_text = _format_evidence(packet.get("evidence_cards", []),
                                     categories={"valuation", "analyst_consensus",
                                                  "peer_comparison", "earnings_revision"})
    gaps_text = _format_gaps(packet.get("evidence_gaps", []))

    user_prompt = f"""\
TARGET: {name} ({ticker})
TIME HORIZON: {target_summary.get('time_horizon', 'unknown')}

QUESTIONS TO ANSWER:
{_bullet(packet.get('questions_for_agent', []))}

MARKET CONTEXT:
{_format_market(packet.get('market_context', {}))}

NUMERIC FEATURES (valuation, peer, analyst):
{features_text}

EVIDENCE CARDS (valuation & analyst):
{evidence_text}

DATA GAPS:
{gaps_text}

Assess valuation attractiveness using only the above data.
Return JSON matching the ValuationAssessment schema.
"""

    structured_llm = llm.with_structured_output(ValuationAssessment, method="function_calling")
    result: ValuationAssessment = structured_llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])

    return {
        "assessment_id":      f"ASSESS_{packet['packet_id']}",
        "agent_type":         "valuation_agent",
        "target_id":          packet.get("target_id", ""),
        "target_name":        name,
        "ticker":             ticker,
        "assessment_label":   result.assessment_label,
        "summary":            result.summary,
        "dimension_scores":   {
            "absolute_valuation_score":  result.absolute_valuation_score,
            "relative_valuation_score":  result.relative_valuation_score,
            "analyst_upside_score":      result.analyst_upside_score,
            "margin_of_safety_score":    result.margin_of_safety_score,
            "overall_valuation_score":   result.overall_valuation_score,
        },
        "key_findings":       [kf.model_dump() for kf in result.key_findings],
        "supportive_factors": result.supportive_factors,
        "negative_factors":   result.negative_factors,
        "data_gaps":          result.data_gaps,
        "risk_flags":         [],
        "confidence":         result.confidence,
    }


def _format_features(inline: dict, groups: set[str]) -> str:
    lines = []
    for k, v in inline.items():
        prefix = k.split(".")[0] if "." in k else ""
        if any(g in prefix for g in groups):
            lines.append(f"  {k}: {v}")
    return "\n".join(lines) if lines else "  (none)"


def _format_evidence(cards: list[dict], categories: set[str]) -> str:
    lines = []
    for c in cards:
        cat = c.get("evidence_category", "")
        if any(cat.startswith(g) or g in cat for g in categories):
            lines.append(f"  [{c['evidence_id']}] [{c.get('strength_label','?')}] {c['statement']}")
    return "\n".join(lines) if lines else "  (no evidence in these categories)"


def _format_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return "  (none)"
    return "\n".join(f"  [{g.get('severity','?')}] {g['description'][:120]}" for g in gaps[:5])


def _format_market(ctx: dict) -> str:
    parts = []
    if ctx.get("regime"):    parts.append(f"regime={ctx['regime']}")
    if ctx.get("nifty_pe"):  parts.append(f"Nifty_PE={ctx['nifty_pe']}")
    if ctx.get("vix_india"): parts.append(f"VIX={ctx['vix_india']}")
    return "  " + ", ".join(parts) if parts else "  (unavailable)"


def _bullet(items: list) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  (none)"
