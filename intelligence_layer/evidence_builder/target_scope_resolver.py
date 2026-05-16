"""
intelligence_layer/evidence_builder/target_scope_resolver.py — Layer 8

For each selected target, builds its full evidence scope:
  - which L5 opportunity hypotheses apply (via source_opportunity_ids)
  - which questions must be answered (merged from target + hypotheses)
  - which L7 data files are present
  - coverage + missing data from L7 reports

ADR-L8-001: L7 files are the primary data source (no L2/L3 canonical IDs).
"""

from __future__ import annotations
from pathlib import Path


def resolve_all_scopes(
    selected_targets: list[dict],
    hyp_by_id:        dict[str, dict],
    coverage_by_target: dict[str, dict],
    missing_by_target:  dict[str, list],
    target_files:     dict[str, dict],
    market_view:      dict,
) -> list[dict]:
    """Build a scope dict per selected target."""
    scopes = []
    for target in selected_targets:
        scope = _build_scope(
            target, hyp_by_id, coverage_by_target, missing_by_target,
            target_files, market_view
        )
        scopes.append(scope)
    return scopes


def _build_scope(
    target: dict,
    hyp_by_id: dict[str, dict],
    coverage_by_target: dict[str, dict],
    missing_by_target: dict[str, list],
    target_files: dict[str, dict],
    market_view: dict,
) -> dict:
    tid  = target["target_id"]
    name = target.get("target_name", "")
    ticker = target.get("ticker", "")

    # Linked opportunity hypotheses
    opp_ids = target.get("source_opportunity_ids", [])
    linked_hyps = [hyp_by_id[oid] for oid in opp_ids if oid in hyp_by_id]

    # Merge questions: from target + from linked hypotheses (deduped)
    questions: list[str] = list(target.get("questions_to_answer", []))
    for hyp in linked_hyps:
        for q in hyp.get("required_deep_dive_questions", []):
            if q not in questions:
                questions.append(q)

    # Why selected (thesis hints from L6)
    why_selected = target.get("why_selected", [])

    # Data availability from L7
    files = target_files.get(tid, {})
    available_modules = [
        m for m in ("market_data", "price_history", "screener_in",
                     "peer_comparison", "analyst_estimates", "exchange_filings")
        if files.get(m) is not None
    ]

    coverage = coverage_by_target.get(tid, {})
    missing  = missing_by_target.get(tid, [])

    # Market context from L5 market_view
    market_context = {
        "regime":           market_view.get("regime", "unknown"),
        "risk_level":       market_view.get("risk_level", "unknown"),
        "recommended_posture": market_view.get("recommended_posture", "unknown"),
        "fii_net_cr":       market_view.get("raw_data", {}).get("fii_net_cr"),
        "dii_net_cr":       market_view.get("raw_data", {}).get("dii_net_cr"),
        "vix_india":        market_view.get("raw_data", {}).get("vix_india"),
        "usd_inr":          market_view.get("raw_data", {}).get("usd_inr"),
        "nifty_50":         market_view.get("raw_data", {}).get("nifty_50"),
        "nifty_pe":         market_view.get("raw_data", {}).get("nifty_pe"),
        "favored_sectors":  market_view.get("favored_sectors", []),
        "avoid_sectors":    market_view.get("avoid_sectors", []),
    }

    # Invalidating conditions from hypotheses (passed to thesis card)
    invalidating_conditions: list[str] = []
    for hyp in linked_hyps:
        invalidating_conditions.extend(hyp.get("invalidating_conditions", []))

    # Opportunity data gaps (what L5 flagged as missing)
    opportunity_data_gaps: list[str] = list(target.get("data_gaps", []))

    return {
        "target_id":              tid,
        "target_name":            name,
        "target_type":            target.get("target_type", "listed_company"),
        "ticker":                 ticker,
        "exchange":               target.get("exchange", "NSE"),
        "time_horizon":           target.get("time_horizon", "unknown"),
        "confidence":             target.get("confidence", 0.0),
        "priority_score":         target.get("priority_score", 0),
        "opportunity_ids":        opp_ids,
        "linked_hypotheses":      linked_hyps,
        "questions_to_answer":    questions,
        "why_selected":           why_selected,
        "invalidating_conditions": invalidating_conditions,
        "opportunity_data_gaps":  opportunity_data_gaps,
        "available_modules":      available_modules,
        "coverage":               coverage,
        "missing_data":           missing,
        "market_context":         market_context,
        "target_dir":             files.get("target_dir"),
        "files":                  files,
    }
