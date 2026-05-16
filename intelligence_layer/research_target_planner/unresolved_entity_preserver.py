"""
intelligence_layer/research_target_planner/unresolved_entity_preserver.py — Layer 6

For candidates without a resolved ticker, assigns next_action so they stay
in the research plan rather than being silently dropped.

This keeps Layer 6 opportunity-first: no ticker != no research path.

Design doc: docs/system_design_docs/layer_6.md §8 unresolved_entity_preserver.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST   = timezone(timedelta(hours=5, minutes=30))
_CTR   = [0]

_NEXT_ACTIONS = {
    "private_unlisted_company": "proxy_mapping",
    "sector_theme":             "sector_theme_mapping",
    "macro_theme":              "macro_mapping",
    "fund_etf":                 "fund_vehicle_mapping",
    "commodity":                "commodity_research",
    "real_estate_regional_theme": "real_estate_mapping",
    "unknown":                  "watch_only",
}


def preserve_unresolved(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split candidates into resolved (ticker present) and unresolved.
    Unresolved entries get an unresolved_target_id and next_action.
    Returns (resolved, unresolved).
    """
    today    = datetime.now(_IST).strftime("%Y%m%d")
    resolved: list[dict]   = []
    unresolved: list[dict] = []

    for c in candidates:
        if c.get("ticker"):
            c["preserve_for_planning"] = False
            resolved.append(c)
        else:
            _CTR[0] += 1
            c["unresolved_target_id"]  = f"UNRES_{today}_{_CTR[0]:04d}"
            c["preserve_for_planning"] = True
            c["next_action"]           = _NEXT_ACTIONS.get(c.get("target_type", "unknown"), "watch_only")
            unresolved.append(c)

    return resolved, unresolved
