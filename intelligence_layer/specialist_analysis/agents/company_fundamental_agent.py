"""
intelligence_layer/specialist_analysis/agents/company_fundamental_agent.py — Layer 9

Specialist agent: assesses business quality, growth, margins, balance sheet,
and management confidence signals using only the evidence provided in the packet.

Uses LLM with Pydantic structured output.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator

_SYSTEM_PROMPT = """\
You are a specialist investment analysis agent focused on company fundamentals.

Your role: Assess whether the company is fundamentally sound based ONLY on the \
evidence and numeric features provided. Do not invent facts or use general knowledge \
about the company. Every key finding must cite evidence IDs from the packet.

Rules:
- Do NOT recommend buying, selling, or any portfolio action.
- Do not say "buy", "sell", "invest", "allocate", "entry price", "stop loss".
- If data is missing, say so and lower confidence.
- Claims and analyst opinions must stay labeled as such — not presented as facts.
- Return JSON only, matching the schema exactly.

Dimension scores (0-100, where 0=very weak, 50=neutral, 100=very strong):
  growth_score: revenue and profit growth quality
  profitability_score: margins, ROE, ROCE quality
  balance_sheet_score: debt, coverage, capital structure
  promoter_confidence_score: promoter holding trend
  overall_fundamental_score: weighted composite

Assessment labels:
  fundamentally_strong | sound_with_concerns | mixed_fundamentals | fundamental_weaknesses | insufficient_data

confidence: your confidence in this assessment as a decimal 0.0 to 1.0 (e.g. 0.75, not 75)
"""


class KeyFinding(BaseModel):
    finding: str
    evidence_refs: list[str]


class FundamentalAssessment(BaseModel):
    assessment_label: str
    summary: str
    growth_score: int
    profitability_score: int
    balance_sheet_score: int
    promoter_confidence_score: int
    overall_fundamental_score: int
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
    """Run fundamental agent. Returns assessment dict."""
    target_summary = packet.get("target_summary", {})
    name   = target_summary.get("target_name", "Unknown")
    ticker = target_summary.get("ticker", "")

    features_text = _format_features(packet.get("inline_features", {}), groups={"fundamental", "price"})
    evidence_text = _format_evidence(packet.get("evidence_cards", []),
                                     categories={"fundamentals", "price"})
    gaps_text     = _format_gaps(packet.get("evidence_gaps", []))

    user_prompt = f"""\
TARGET: {name} ({ticker})
TIME HORIZON: {target_summary.get('time_horizon', 'unknown')}

WHY SELECTED:
{_bullet(target_summary.get('why_selected', [])[:4])}

QUESTIONS TO ANSWER:
{_bullet(packet.get('questions_for_agent', []))}

MARKET CONTEXT:
{_format_market(packet.get('market_context', {}))}

NUMERIC FEATURES (fundamental & price):
{features_text}

EVIDENCE CARDS (fundamental & price):
{evidence_text}

DATA GAPS:
{gaps_text}

Assess the company's fundamental quality using only the above data.
Return JSON matching the FundamentalAssessment schema.
"""

    structured_llm = llm.with_structured_output(FundamentalAssessment, method="function_calling")
    result: FundamentalAssessment = structured_llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])

    return {
        "assessment_id":      f"ASSESS_{packet['packet_id']}",
        "agent_type":         "fundamental_agent",
        "target_id":          packet.get("target_id", ""),
        "target_name":        name,
        "ticker":             ticker,
        "assessment_label":   result.assessment_label,
        "summary":            result.summary,
        "dimension_scores":   {
            "growth_score":              result.growth_score,
            "profitability_score":       result.profitability_score,
            "balance_sheet_score":       result.balance_sheet_score,
            "promoter_confidence_score": result.promoter_confidence_score,
            "overall_fundamental_score": result.overall_fundamental_score,
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
        if any(cat.startswith(g) for g in categories):
            lines.append(f"  [{c['evidence_id']}] [{c.get('strength_label','?')}] {c['statement']}")
    return "\n".join(lines) if lines else "  (no evidence in these categories)"


def _format_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return "  (none)"
    return "\n".join(f"  [{g.get('severity','?')}] {g['description'][:120]}" for g in gaps[:5])


def _format_market(ctx: dict) -> str:
    parts = []
    if ctx.get("regime"):       parts.append(f"regime={ctx['regime']}")
    if ctx.get("risk_level"):   parts.append(f"risk={ctx['risk_level']}")
    if ctx.get("vix_india"):    parts.append(f"VIX={ctx['vix_india']}")
    if ctx.get("fii_net_cr"):   parts.append(f"FII_net=₹{ctx['fii_net_cr']}Cr")
    if ctx.get("usd_inr"):      parts.append(f"USD/INR={ctx['usd_inr']}")
    return "  " + ", ".join(parts) if parts else "  (unavailable)"


def _bullet(items: list) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  (none)"
