"""
intelligence_layer/evidence_builder/evidence_gap_mapper.py — Layer 8

Converts L7 coverage + missing data into explicit evidence gap objects.
Also flags module-level gaps for questions that cannot be answered.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_GAP_COUNTER = [0]


def _next_gap_id(date_str: str) -> str:
    _GAP_COUNTER[0] += 1
    return f"EGAP_{date_str}_{_GAP_COUNTER[0]:04d}"


# Maps module → affected analysis domains
_MODULE_IMPACT = {
    "filing_docs":       ["management_commentary", "strategy_analysis"],
    "targeted_news":     ["sentiment_analysis", "event_analysis"],
    "stock_fno_data":    ["derivatives_analysis"],
    "sec_filings":       ["regulatory_analysis"],
    "exchange_filings":  ["event_analysis", "risk_analysis"],
    "screener_in":       ["fundamental_analysis", "valuation_analysis"],
    "analyst_estimates": ["valuation_analysis", "analyst_consensus"],
    "peer_comparison":   ["valuation_analysis", "peer_analysis"],
    "market_data":       ["price_analysis"],
    "price_history":     ["price_analysis", "momentum_analysis"],
}


def map_gaps(scope: dict, date_str: str) -> list[dict]:
    """Returns list of evidence gap dicts for a target."""
    tid  = scope["target_id"]
    name = scope["target_name"]
    gaps: list[dict] = []

    # ── Gaps from L7 missing_data_report ─────────────────────────────────────
    for miss in scope.get("missing_data", []):
        module = miss.get("module", "unknown")
        reason = miss.get("reason") or miss.get("error") or "Collection failed"
        affected = _MODULE_IMPACT.get(module, ["general_analysis"])
        severity = "high" if module in ("screener_in", "price_history", "market_data") else "medium"
        gaps.append({
            "gap_id":                   _next_gap_id(date_str),
            "target_id":                tid,
            "target_name":              name,
            "gap_type":                 f"missing_{module}",
            "description":              f"No {module} data for {name}: {reason[:120]}",
            "module":                   module,
            "affected_analyses":        affected,
            "severity":                 severity,
            "recommended_agent_handling": "lower_confidence",
            "created_at":               datetime.now(_IST).isoformat(),
        })

    # ── Coverage gaps from L7 coverage_report ─────────────────────────────────
    coverage = scope.get("coverage", {})
    question_coverage = coverage.get("question_coverage", [])
    for qc in question_coverage:
        if qc.get("coverage_status") in ("missing", "partial"):
            gaps.append({
                "gap_id":                   _next_gap_id(date_str),
                "target_id":                tid,
                "target_name":              name,
                "gap_type":                 "question_not_answerable",
                "description":              f"Question may not be answerable: {qc.get('question', '')[:150]}",
                "module":                   None,
                "affected_analyses":        ["general_analysis"],
                "severity":                 "medium" if qc.get("coverage_status") == "partial" else "high",
                "recommended_agent_handling": "acknowledge_uncertainty",
                "question":                 qc.get("question", ""),
                "missing_modules":          qc.get("missing_modules", []),
                "created_at":               datetime.now(_IST).isoformat(),
            })

    # ── Opportunity-level data gaps from L5 (what L5 flagged as missing) ─────
    for gap_desc in scope.get("opportunity_data_gaps", []):
        gaps.append({
            "gap_id":                   _next_gap_id(date_str),
            "target_id":                tid,
            "target_name":              name,
            "gap_type":                 "opportunity_data_gap",
            "description":              f"L5 flagged: {gap_desc[:200]}",
            "module":                   None,
            "affected_analyses":        ["thesis_analysis"],
            "severity":                 "low",
            "recommended_agent_handling": "note_in_thesis",
            "created_at":               datetime.now(_IST).isoformat(),
        })

    return gaps
