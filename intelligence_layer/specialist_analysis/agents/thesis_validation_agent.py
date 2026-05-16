"""
intelligence_layer/specialist_analysis/agents/thesis_validation_agent.py — Layer 9

Specialist agent: validates whether available evidence supports, weakens, or
invalidates the investment thesis from Layer 8. Runs LAST — receives prior
assessments from fundamental, valuation, and risk agents.

Uses LLM with Pydantic structured output.
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator

_SYSTEM_PROMPT = """\
You are a specialist investment analysis agent focused on thesis validation.

Your role: Synthesize the specialist assessments to determine whether the evidence \
SUPPORTS, PARTIALLY SUPPORTS, WEAKENS, or INVALIDATES the investment thesis.

You receive:
  - The thesis statement (from Layer 8)
  - Prior specialist assessments (fundamental, valuation, risk)
  - All evidence cards and gaps

Rules:
- Do NOT make a final buy/sell/hold recommendation.
- Do not say "buy", "sell", "invest", "allocate".
- Your job is to assess thesis strength, NOT to make a portfolio decision.
- Cite specific evidence IDs and assessment findings.
- If evidence is contradictory, say so explicitly.
- Return JSON only, matching the ThesisValidationAssessment schema.

Thesis status labels:
  well_supported | partially_supported | mixed_support | weakly_supported | thesis_weakened | thesis_invalidated | insufficient_evidence

Confidence change:
  upgrade | hold | slight_downgrade | downgrade | significant_downgrade
"""


class KeyFinding(BaseModel):
    finding: str
    evidence_refs: list[str]


class ThesisValidationAssessment(BaseModel):
    thesis_status: str
    assessment_label: str
    summary: str  # 3-4 sentences synthesizing all specialist views
    supporting_evidence_summary: str
    weakening_evidence_summary: str
    specialist_alignment: str  # e.g. "fundamental positive, valuation fair, risk moderate"
    key_findings: list[KeyFinding]
    critical_gaps: list[str]
    invalidating_conditions_triggered: list[str]  # which L5 invalidating conditions are now real
    confidence_change: str
    updated_thesis_confidence: float  # 0.0-1.0
    confidence: float  # confidence in THIS assessment

    @field_validator("invalidating_conditions_triggered", "critical_gaps", mode="before")
    @classmethod
    def coerce_str_to_list(cls, v):
        if isinstance(v, str):
            return [v] if v.strip() and v.strip().lower() not in ("none", "none.") else []
        if isinstance(v, list):
            result = []
            for item in v:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    result.extend(str(val) for val in item.values() if val)
            return result
        return v

    @field_validator("confidence", "updated_thesis_confidence", mode="before")
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

    thesis = packet.get("thesis_card", {})
    prior  = context.get("prior_assessments", [])
    all_cards = context.get("evidence_by_target", {}).get(tid, [])
    all_gaps  = context.get("gaps_by_target", {}).get(tid, [])

    user_prompt = f"""\
TARGET: {name} ({ticker})
TIME HORIZON: {target_summary.get('time_horizon', 'unknown')}

THESIS STATEMENT:
{thesis.get('thesis_statement', '(no thesis)')[:500]}

CURRENT THESIS CONFIDENCE: {thesis.get('current_thesis_confidence', 'unknown')}

INVALIDATING CONDITIONS (from L5 hypothesis):
{_bullet(thesis.get('invalidating_conditions', [])[:5])}

SPECIALIST ASSESSMENTS (from prior agents):
{_format_prior(prior)}

ALL EVIDENCE SUMMARY:
{_format_all_evidence(all_cards)}

CRITICAL DATA GAPS:
{_format_gaps(all_gaps)}

TARGET QUESTIONS:
{_bullet(packet.get('questions_for_agent', [])[:6])}

Based on ALL specialist assessments and evidence, validate whether the thesis holds.
Return JSON matching the ThesisValidationAssessment schema.
"""

    structured_llm = llm.with_structured_output(ThesisValidationAssessment, method="function_calling")
    result: ThesisValidationAssessment = structured_llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])

    return {
        "assessment_id":                 f"ASSESS_{packet['packet_id']}",
        "agent_type":                    "thesis_agent",
        "target_id":                     tid,
        "target_name":                   name,
        "ticker":                        ticker,
        "assessment_label":              result.assessment_label,
        "thesis_status":                 result.thesis_status,
        "summary":                       result.summary,
        "supporting_evidence_summary":   result.supporting_evidence_summary,
        "weakening_evidence_summary":    result.weakening_evidence_summary,
        "specialist_alignment":          result.specialist_alignment,
        "dimension_scores":              {"thesis_support_score": _thesis_score(result.thesis_status)},
        "key_findings":                  [kf.model_dump() for kf in result.key_findings],
        "supportive_factors":            [result.supporting_evidence_summary],
        "negative_factors":              [result.weakening_evidence_summary],
        "critical_gaps":                 result.critical_gaps,
        "invalidating_conditions_triggered": result.invalidating_conditions_triggered,
        "confidence_change":             result.confidence_change,
        "updated_thesis_confidence":     result.updated_thesis_confidence,
        "risk_flags":                    [],
        "data_gaps":                     result.critical_gaps,
        "confidence":                    result.confidence,
    }


def _format_prior(assessments: list[dict]) -> str:
    if not assessments:
        return "  (no prior assessments available)"
    lines = []
    for a in assessments:
        agent  = a.get("agent_type", "?")
        label  = a.get("assessment_label", "?")
        summ   = a.get("summary", "")[:300]
        scores = a.get("dimension_scores", {})
        score_str = ", ".join(f"{k}={v}" for k, v in scores.items()) if scores else "N/A"
        lines.append(f"\n  [{agent.upper()}] label={label} | scores: {score_str}\n  summary: {summ}")
    return "\n".join(lines)


def _format_all_evidence(cards: list[dict]) -> str:
    non_gap = [c for c in cards if c.get("evidence_type") != "missing_data_gap"]
    if not non_gap:
        return "  (no evidence)"
    lines = []
    for c in non_gap[:20]:  # cap at 20 for prompt length
        lines.append(f"  [{c['evidence_id']}] [{c.get('strength_label','?')}] {c['statement'][:100]}")
    if len(non_gap) > 20:
        lines.append(f"  ... and {len(non_gap)-20} more evidence cards")
    return "\n".join(lines)


def _format_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return "  (none)"
    high = [g for g in gaps if g.get("severity") == "high"]
    med  = [g for g in gaps if g.get("severity") == "medium"]
    lines = [f"  [high] {g['description'][:120]}" for g in high[:3]]
    lines += [f"  [medium] {g['description'][:120]}" for g in med[:3]]
    return "\n".join(lines) if lines else "  (none)"


def _bullet(items: list) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  (none)"


def _thesis_score(status: str) -> int:
    mapping = {
        "well_supported":         85,
        "partially_supported":    65,
        "mixed_support":          50,
        "weakly_supported":       38,
        "thesis_weakened":        25,
        "thesis_invalidated":     10,
        "insufficient_evidence":  40,
    }
    return mapping.get(status, 50)
