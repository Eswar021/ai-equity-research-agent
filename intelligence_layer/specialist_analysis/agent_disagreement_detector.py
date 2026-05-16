"""
intelligence_layer/specialist_analysis/agent_disagreement_detector.py — Layer 9

Detects meaningful conflicts between specialist agent assessments.
Disagreements are not failures — they surface genuine analytical tension for Layer 10.

Checks:
  - Fundamental positive but risk high
  - Valuation expensive but thesis still supported
  - Fundamental strong but thesis weakened
  - Risk high but valuation attractive (value trap risk)
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def detect_all(task_results: list[dict], date_str: str) -> list[dict]:
    """Return list of disagreement dicts across all targets."""
    # Group results by target_id
    by_target: dict[str, dict[str, dict]] = {}
    for r in task_results:
        if r["status"] == "failed":
            continue
        a = r.get("assessment", {})
        tid = a.get("target_id", "")
        by_target.setdefault(tid, {})[r["agent_type"]] = a

    disagreements: list[dict] = []
    for tid, agents in by_target.items():
        disagreements.extend(_check_target(tid, agents, date_str))
    return disagreements


def _check_target(tid: str, agents: dict[str, dict], date_str: str) -> list[dict]:
    results: list[dict] = []

    fund  = agents.get("fundamental_agent", {})
    val   = agents.get("valuation_agent", {})
    risk  = agents.get("risk_agent", {})
    thesis = agents.get("thesis_agent", {})

    fund_score  = fund.get("dimension_scores", {}).get("overall_fundamental_score", 50)
    val_score   = val.get("dimension_scores", {}).get("overall_valuation_score", 50)
    risk_score  = risk.get("dimension_scores", {}).get("risk_score", 50)
    thesis_score = thesis.get("dimension_scores", {}).get("thesis_support_score", 50)

    name   = fund.get("target_name") or val.get("target_name") or ""
    ticker = fund.get("ticker") or val.get("ticker") or ""

    # ── Check 1: Strong fundamentals + high risk ──────────────────────────────
    if fund_score and risk_score and fund_score >= 65 and risk_score >= 65:
        results.append(_disagree(tid, name, ticker, date_str,
            dtype="strong_fundamentals_vs_high_risk",
            desc=f"Fundamental quality is strong (score={fund_score}) but risk assessment is elevated (risk={risk_score}). "
                 f"This tension should be resolved before a final decision.",
            agents=["fundamental_agent", "risk_agent"],
            related=[f"ASSESS_{fund.get('source_packet_id','')}",
                     f"ASSESS_{risk.get('source_packet_id','')}"],
            severity="medium"))

    # ── Check 2: Cheap valuation + high risk (value trap signal) ─────────────
    if val_score and risk_score and val_score >= 65 and risk_score >= 65:
        results.append(_disagree(tid, name, ticker, date_str,
            dtype="cheap_valuation_vs_high_risk",
            desc=f"Valuation appears attractive (score={val_score}) but risk is elevated (risk={risk_score}). "
                 f"This may signal a value trap — lower risk first, then reassess valuation.",
            agents=["valuation_agent", "risk_agent"],
            related=[],
            severity="high"))

    # ── Check 3: Thesis weakened but fundamental positive ────────────────────
    thesis_status = thesis.get("thesis_status", "")
    if thesis_status in ("thesis_weakened", "thesis_invalidated") and fund_score and fund_score >= 65:
        results.append(_disagree(tid, name, ticker, date_str,
            dtype="positive_fundamentals_vs_weak_thesis",
            desc=f"Company fundamentals appear positive (score={fund_score}) but thesis validation "
                 f"is '{thesis_status}'. The thesis may not be aligned with current opportunity drivers.",
            agents=["fundamental_agent", "thesis_agent"],
            related=[],
            severity="medium"))

    # ── Check 4: Thesis well supported but risk elevated ─────────────────────
    if thesis_status in ("well_supported", "partially_supported") and risk_score and risk_score >= 70:
        results.append(_disagree(tid, name, ticker, date_str,
            dtype="supported_thesis_vs_elevated_risk",
            desc=f"Thesis is '{thesis_status}' but risk score is {risk_score}. "
                 f"Layer 10 should weight risk flags carefully before acting on the thesis.",
            agents=["thesis_agent", "risk_agent"],
            related=[],
            severity="medium"))

    return results


def _disagree(tid, name, ticker, date_str, dtype, desc, agents, related, severity) -> dict:
    _CTR[0] += 1
    return {
        "disagreement_id":        f"DISAGREE_{date_str}_{tid}_{_CTR[0]:03d}",
        "target_id":              tid,
        "target_name":            name,
        "ticker":                 ticker,
        "disagreement_type":      dtype,
        "description":            desc,
        "source_agents":          agents,
        "related_assessment_ids": related,
        "severity":               severity,
        "layer10_handling_hint":  "Final synthesis must explicitly address this tension.",
        "created_at":             datetime.now(_IST).isoformat(),
    }
