"""
intelligence_layer/research_target_planner/proxy_mapper.py — Layer 6

Maps private_unlisted_company unresolved targets to listed proxies.
L5 already named beneficiaries with tickers for each hypothesis, so proxies
are extracted from the sibling beneficiaries of the same hypothesis — no LLM needed.

Design doc: docs/system_design_docs/layer_6.md §9 proxy_mapper.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def map_proxies(unresolved: list[dict], all_candidates: list[dict],
                opportunity_hypotheses: list[dict]) -> list[dict]:
    """
    For each private_unlisted_company unresolved target, collect its proxy candidates
    from sibling beneficiaries in the same hypothesis that DO have tickers.

    Returns list of proxy_mapping dicts (one per unresolved private target).
    """
    today = datetime.now(_IST).strftime("%Y%m%d")

    # Index: opportunity_id → hypothesis dict
    hyp_by_id = {h["opportunity_id"]: h for h in opportunity_hypotheses}

    # Index: opportunity_id → all resolved candidates from that hypothesis
    resolved_by_opp: dict[str, list[dict]] = {}
    for c in all_candidates:
        if c.get("ticker"):
            oid = c.get("source_opportunity_id", "")
            resolved_by_opp.setdefault(oid, []).append(c)

    results: list[dict] = []
    for u in unresolved:
        if u.get("target_type") != "private_unlisted_company":
            continue

        _CTR[0] += 1
        oid      = u.get("source_opportunity_id", "")
        hyp      = hyp_by_id.get(oid, {})
        siblings = resolved_by_opp.get(oid, [])

        proxy_candidates = []
        for s in siblings[:6]:
            proxy_candidates.append({
                "proxy_name":         s.get("candidate_name", ""),
                "ticker":             s.get("ticker"),
                "proxy_type":         "listed_company",
                "relationship":       "sector_beneficiary",
                "mapping_confidence": round(s.get("confidence", 0.5) * 0.85, 3),
                "requires_deep_dive": True,
            })

        results.append({
            "proxy_mapping_id":  f"PROXYMAP_{today}_{_CTR[0]:04d}",
            "source_target_id":  u.get("unresolved_target_id", ""),
            "entity_name":       u.get("candidate_name", ""),
            "target_type":       "private_unlisted_company",
            "proxy_candidates":  proxy_candidates,
            "supporting_refs":   u.get("supporting_refs", []),
            "data_gaps":         [f"Need confirmation of direct exposure for {u.get('candidate_name','')}"],
        })

    return results
