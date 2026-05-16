"""
intelligence_layer/research_target_planner/macro_target_mapper.py — Layer 6

Converts macro_theme unresolved targets into affected sectors for research routing.
Rule-based keyword matching — no LLM.

Design doc: docs/system_design_docs/layer_6.md §12 macro_target_mapper.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

# macro keywords → affected sectors
_MACRO_SECTOR_MAP: list[tuple[list[str], list[str]]] = [
    (["rate cut", "rbi cut", "easing", "dovish"],         ["banking", "nbfc", "real_estate", "auto"]),
    (["rate hike", "tightening", "hawkish"],              ["banking", "nbfc"]),
    (["fx", "dollar", "usd", "rupee", "currency"],        ["it", "pharma", "oil_gas"]),
    (["oil price", "crude", "opec", "brent"],             ["oil_gas", "aviation", "paint"]),
    (["inflation", "cpi", "wpi"],                         ["fmcg", "auto", "real_estate"]),
    (["geopolit", "war", "conflict", "sanction"],         ["defense", "oil_gas", "metals"]),
    (["trade deal", "fta", "export", "tariff"],           ["it", "pharma", "auto"]),
    (["election", "political", "governance", "policy"],   ["infra", "banking", "fmcg"]),
    (["semiconductor", "chip", "ai", "data center"],      ["it", "power", "infra"]),
    (["hydropower", "water", "treaty"],                   ["power", "infra"]),
    (["real estate", "housing", "reit"],                  ["real_estate", "cement", "infra"]),
    (["broad market", "nifty", "index", "accumulation"],  ["banking", "it", "pharma", "oil_gas"]),
]


def map_macro_targets(unresolved: list[dict]) -> list[dict]:
    """
    For macro_theme unresolved targets, produce macro_target mapping dicts
    with affected sectors to route to sector-level research.
    """
    today = datetime.now(_IST).strftime("%Y%m%d")
    results: list[dict] = []

    for u in unresolved:
        if u.get("target_type") not in ("macro_theme", "cross_domain"):
            continue

        name     = (u.get("candidate_name") or "").lower()
        sectors  = _match_sectors(name)

        _CTR[0] += 1
        results.append({
            "macro_target_mapping_id": f"MACROMAP_{today}_{_CTR[0]:04d}",
            "source_target_id":        u.get("unresolved_target_id", ""),
            "macro_theme_name":        u.get("candidate_name", ""),
            "affected_sectors":        sectors,
            "macro_targets": [
                {
                    "target_type":         "macro_theme",
                    "target_name":         u.get("candidate_name", ""),
                    "requires_deep_dive":  True,
                },
            ] + [
                {
                    "target_type":        "sector_theme",
                    "target_name":        f"{s} sector (macro-linked)",
                    "related_sector":     s,
                    "requires_deep_dive": True,
                }
                for s in sectors
            ],
        })

    return results


def _match_sectors(name: str) -> list[str]:
    for keywords, sectors in _MACRO_SECTOR_MAP:
        if any(kw in name for kw in keywords):
            return sectors
    return []
