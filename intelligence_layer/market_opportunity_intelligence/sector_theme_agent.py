"""
intelligence_layer/market_opportunity_intelligence/sector_theme_agent.py — Layer 5

Rule-based sector/theme intelligence: for each signal group, computes
current_signal_strength, recurrence_level, structural_relevance,
investment_relevance, and possible_opportunity_types.

No LLM. All derivable from signal group metadata + theme_type rules.

Design doc: docs/system_design_docs/layer_5.md §5 sector_theme_intelligence_agent.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_STRUCTURAL_THEME_TYPES = {
    "macro_theme", "policy_theme", "technology_theme", "cross_domain_theme",
}
_SECTOR_THEME_TYPES = {
    "sector_theme", "regional_theme", "commodity_theme",
}

_OPPORTUNITY_TYPE_MAP: dict[str, list[str]] = {
    "macro_theme":        ["sector_theme", "macro_theme", "fund_etf"],
    "policy_theme":       ["listed_stock", "sector_theme", "cross_domain"],
    "technology_theme":   ["listed_stock", "sector_theme", "private_company_proxy"],
    "cross_domain_theme": ["cross_domain", "real_estate_theme", "listed_stock"],
    "sector_theme":       ["listed_stock", "sector_theme", "fund_etf"],
    "regional_theme":     ["listed_stock", "real_estate_theme", "cross_domain"],
    "commodity_theme":    ["commodity", "listed_stock"],
    "other":              ["listed_stock", "sector_theme"],
}


def analyze_all(signal_groups: list[dict], entities: list[dict],
                market_view: dict) -> list[dict]:
    """
    Analyze all signal groups and return a sector_theme_view per group.
    `entities` is the entity_registry list for listing status lookup.
    """
    listed_entity_names = {
        e["entity_name"].lower()
        for e in entities
        if e.get("market_status") in ("listed", "resolved")
    }
    return [
        _analyze_group(grp, listed_entity_names, market_view)
        for grp in signal_groups
    ]


def _analyze_group(grp: dict, listed_entity_names: set[str],
                   market_view: dict) -> dict:
    _CTR[0] += 1
    today    = datetime.now(_IST).strftime("%Y%m%d")
    view_id  = f"THEME_VIEW_{today}_{_CTR[0]:04d}"

    theme_type   = grp.get("theme_type", "other") or "other"
    entities     = grp.get("entities") or []
    event_ids    = grp.get("event_ids") or []
    source_div   = grp.get("source_diversity_count", 0)
    mem_refs     = grp.get("memory_refs") or []
    rec_level    = grp.get("recurrence_level", "new")
    mention_cnt  = grp.get("mention_count", 1)
    conf         = grp.get("confidence", 0.5)

    signal_strength    = _signal_strength(source_div, len(event_ids), mention_cnt)
    structural_rel     = _structural_relevance(theme_type)
    invest_rel         = _investment_relevance(entities, listed_entity_names, grp)
    opp_types          = _OPPORTUNITY_TYPE_MAP.get(theme_type, ["listed_stock", "sector_theme"])
    reasoning          = _build_reasoning(signal_strength, rec_level, structural_rel, invest_rel, theme_type)
    data_gaps          = _data_gaps(invest_rel, theme_type)

    # Market-aware adjustment
    favored_sectors = (market_view.get("sectors") or {}).get("favored") or []
    aligned_with_regime = any(
        s.lower() in grp.get("theme", "").lower() for s in favored_sectors
    )

    return {
        "theme_view_id":            view_id,
        "signal_group_id":          grp.get("signal_group_id", ""),
        "theme_name":               grp.get("theme", ""),
        "theme_type":               theme_type,
        "market":                   "india",
        "related_sectors":          _related_sectors(theme_type, grp.get("theme", "")),
        "related_entities":         entities[:10],
        "current_signal_strength":  signal_strength,
        "recurrence_level":         _normalize_recurrence(rec_level),
        "structural_relevance":     structural_rel,
        "investment_relevance":     invest_rel,
        "possible_opportunity_types": opp_types,
        "aligned_with_regime":      aligned_with_regime,
        "reasoning_summary":        reasoning,
        "supporting_refs":          grp.get("source_refs") or [],
        "data_gaps":                data_gaps,
        "confidence":               round(min(conf + (0.05 if mem_refs else 0), 0.95), 3),
        "source_diversity_count":   source_div,
        "event_count":              len(event_ids),
        "memory_refs":              mem_refs,
    }


def _signal_strength(source_div: int, event_count: int, mention_count: int) -> str:
    score = source_div * 2 + event_count + (1 if mention_count >= 3 else 0)
    if score >= 6:  return "high"
    if score >= 3:  return "medium"
    return "low"


def _structural_relevance(theme_type: str) -> str:
    if theme_type in _STRUCTURAL_THEME_TYPES:  return "high"
    if theme_type in _SECTOR_THEME_TYPES:      return "medium"
    return "low"


def _investment_relevance(entities: list[str], listed_names: set[str],
                          grp: dict) -> str:
    entity_lower = {e.lower() for e in entities}
    if entity_lower & listed_names:
        return "high"
    if grp.get("event_ids"):
        return "medium"
    if entities:
        return "medium"
    return "low"


def _normalize_recurrence(rec_level: str) -> str:
    return {
        "new":              "new",
        "new_with_memory":  "new",
        "recurring":        "recurring",
        "high_recurring":   "high_recurring",
    }.get(rec_level, "new")


def _related_sectors(theme_type: str, theme_name: str) -> list[str]:
    name_lower = theme_name.lower()
    sectors: list[str] = []
    sector_keywords = {
        "banking": "banking", "bank": "banking", "nbfc": "banking",
        "it": "information_technology", "software": "information_technology",
        "tech": "technology", "ai": "technology",
        "power": "power", "energy": "energy", "electricity": "power",
        "infra": "infrastructure", "corridor": "infrastructure",
        "real estate": "real_estate", "realty": "real_estate",
        "pharma": "pharmaceuticals", "drug": "pharmaceuticals",
        "auto": "automobiles", "ev": "automobiles",
        "metal": "metals", "steel": "metals", "commodity": "commodities",
        "fmcg": "fmcg", "consumer": "consumer",
    }
    for kw, sector in sector_keywords.items():
        if kw in name_lower and sector not in sectors:
            sectors.append(sector)
    if not sectors:
        sectors = {
            "macro_theme":    ["broad_market"],
            "policy_theme":   ["policy_driven"],
            "sector_theme":   ["sector_specific"],
            "technology_theme": ["technology"],
        }.get(theme_type, ["general"])
    return sectors


def _build_reasoning(strength: str, rec_level: str, structural: str,
                     invest_rel: str, theme_type: str) -> list[str]:
    r: list[str] = []
    r.append(f"Signal strength: {strength} — based on source diversity and event count.")
    if structural == "high":
        r.append(f"Theme type '{theme_type}' suggests structural, long-term relevance.")
    if rec_level in ("recurring", "high_recurring"):
        r.append("This theme has appeared in prior memory — strengthening conviction.")
    if invest_rel == "high":
        r.append("Listed Indian companies are involved — direct investment relevance.")
    elif invest_rel == "medium":
        r.append("Indirect investment angle — proxy mapping may be needed.")
    return r


def _data_gaps(invest_rel: str, theme_type: str) -> list[str]:
    gaps: list[str] = []
    if invest_rel in ("low", "medium"):
        gaps.append("Need to map theme to listed Indian company proxies.")
    if theme_type in ("policy_theme", "macro_theme"):
        gaps.append("Need official policy document or notification.")
    if theme_type == "cross_domain_theme":
        gaps.append("Need to identify specific asset class targets beyond listed stocks.")
    return gaps
