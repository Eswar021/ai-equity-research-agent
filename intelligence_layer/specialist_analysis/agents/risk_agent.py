"""
intelligence_layer/specialist_analysis/agents/risk_agent.py — Layer 9

Specialist agent: identifies and assesses downside risks, red flags,
critical data gaps, and missing evidence for the target.

Uses LLM with Pydantic structured output.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator

_SYSTEM_PROMPT = """\
You are a specialist investment analysis agent focused on risk assessment.

Your role: Identify and assess the key downside risks for this investment target \
based ONLY on the evidence provided. Pay special attention to:
  - Missing data (gaps = hidden risks)
  - Price drawdown and volatility
  - Debt levels and margin deterioration
  - EPS cuts and negative analyst revisions
  - Exchange filing gaps or anomalies
  - Macro and market pressure signals

Rules:
- Do NOT recommend avoiding or selling as a final recommendation.
- Do not say "buy", "sell", "invest", "allocate".
- Every risk flag must cite evidence_refs.
- If no risks are found, say so — do not manufacture risks.
- Missing data should ALWAYS be flagged as a risk category.
- Return JSON only, matching the RiskAssessment schema.

Risk severity levels:
  high: could materially impair thesis or cause significant loss
  medium: real concern but manageable with monitoring
  low: worth noting but unlikely to be thesis-breaking

Assessment labels:
  low_risk | moderate_risk | elevated_risk | high_risk | risk_data_insufficient
"""


class RiskFlag(BaseModel):
    risk_flag_id: str
    risk_type: str
    severity: str  # high | medium | low
    description: str
    evidence_refs: list[str]


class KeyFinding(BaseModel):
    finding: str
    evidence_refs: list[str]


class RiskAssessment(BaseModel):
    assessment_label: str
    summary: str
    risk_flags: list[RiskFlag]
    key_findings: list[KeyFinding]
    critical_data_gaps: list[str]
    macro_risks: list[str]
    risk_score: int  # 0=no risk, 100=very high risk
    confidence: float

    @field_validator("critical_data_gaps", "macro_risks", mode="before")
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
    tid    = packet.get("target_id", "")

    features_text = _format_risk_features(packet.get("inline_features", {}))
    evidence_text = _format_evidence(packet.get("evidence_cards", []))
    gaps_text     = _format_gaps(packet.get("evidence_gaps", []))

    user_prompt = f"""\
TARGET: {name} ({ticker})
TIME HORIZON: {target_summary.get('time_horizon', 'unknown')}

QUESTIONS TO ANSWER:
{_bullet(packet.get('questions_for_agent', []))}

MARKET CONTEXT:
{_format_market(packet.get('market_context', {}))}

NUMERIC FEATURES (risk-relevant):
{features_text}

EVIDENCE CARDS (all types — look for risk signals):
{evidence_text}

DATA GAPS (each gap = potential hidden risk):
{gaps_text}

Assess all downside risks using only the above data.
Use target_id prefix "{tid}" for risk_flag_id (e.g., "RISK_{tid}_001").
Return JSON matching the RiskAssessment schema.
"""

    structured_llm = llm.with_structured_output(RiskAssessment, method="function_calling")
    result: RiskAssessment = structured_llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])

    return {
        "assessment_id":      f"ASSESS_{packet['packet_id']}",
        "agent_type":         "risk_agent",
        "target_id":          tid,
        "target_name":        name,
        "ticker":             ticker,
        "assessment_label":   result.assessment_label,
        "summary":            result.summary,
        "dimension_scores":   {"risk_score": result.risk_score},
        "key_findings":       [kf.model_dump() for kf in result.key_findings],
        "supportive_factors": [],
        "negative_factors":   [rf.description for rf in result.risk_flags],
        "risk_flags":         [rf.model_dump() for rf in result.risk_flags],
        "critical_data_gaps": result.critical_data_gaps,
        "macro_risks":        result.macro_risks,
        "data_gaps":          result.critical_data_gaps,
        "confidence":         result.confidence,
    }


def _format_risk_features(inline: dict) -> str:
    """Show features most relevant to risk: price drops, debt, drawdown, margins."""
    risk_keys = {
        "return", "drawdown", "volatility", "52w", "sma",
        "debt", "opm", "net_profit", "promoter",
        "eps_revision", "downgrade", "buy_rating", "sell_rating",
    }
    lines = []
    for k, v in inline.items():
        if any(rk in k.lower() for rk in risk_keys):
            lines.append(f"  {k}: {v}")
    return "\n".join(lines) if lines else "  (none)"


def _format_evidence(cards: list[dict]) -> str:
    lines = []
    for c in cards:
        # Show all card types for risk assessment — risk agent needs the full picture
        strength = c.get("strength_label", "?")
        evid_type = c.get("evidence_type", "")
        lines.append(f"  [{c['evidence_id']}] [{evid_type}:{strength}] {c['statement'][:120]}")
    return "\n".join(lines) if lines else "  (no evidence)"


def _format_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return "  (none)"
    return "\n".join(
        f"  [{g.get('severity','?')}] {g['description'][:140]}"
        for g in gaps
    )


def _format_market(ctx: dict) -> str:
    parts = []
    if ctx.get("regime"):       parts.append(f"regime={ctx['regime']}")
    if ctx.get("risk_level"):   parts.append(f"risk={ctx['risk_level']}")
    if ctx.get("fii_net_cr"):   parts.append(f"FII_net=₹{ctx['fii_net_cr']}Cr")
    if ctx.get("vix_india"):    parts.append(f"VIX={ctx['vix_india']}")
    if ctx.get("usd_inr"):      parts.append(f"USD/INR={ctx['usd_inr']}")
    return "  " + ", ".join(parts) if parts else "  (unavailable)"


def _bullet(items: list) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  (none)"
