"""
intelligence_layer/research_target_planner/target_type_classifier.py — Layer 6

Normalizes the messy target_type_hint strings from L5 into canonical types.
L5's LLM used 80+ inconsistent values; this module collapses them.

Canonical types:
  listed_company | private_unlisted_company | sector_theme | macro_theme |
  fund_etf | commodity | real_estate_regional_theme | unknown

Design doc: docs/system_design_docs/layer_6.md §5 target_type_classifier.py
"""

from __future__ import annotations
import re

# Canonical type constants
LISTED_COMPANY          = "listed_company"
PRIVATE_UNLISTED        = "private_unlisted_company"
SECTOR_THEME            = "sector_theme"
MACRO_THEME             = "macro_theme"
FUND_ETF                = "fund_etf"
COMMODITY               = "commodity"
REAL_ESTATE_REGIONAL    = "real_estate_regional_theme"
UNKNOWN                 = "unknown"

# Keyword sets — checked in order (most specific first)
_FUND_KW       = {"fund", "etf", "reit", "invit", "nav", "mutual", "index fund"}
_COMMODITY_KW  = {"commodity", "crude", "gold", "silver", "metal", "agri", "wheat", "oil commodity"}
_REAL_ESTATE_KW = {"real estate", "reit_regional", "corridor", "land", "warehouse", "regional theme"}
_MACRO_KW      = {"macro", "policy", "rate", "currency", "fx", "inflation", "gdp", "macro_theme",
                  "geopolitical", "central bank", "rbi", "fed", "monetary"}
_SECTOR_KW     = {"sector", "theme", "beneficiary", "industry", "space", "sector_theme",
                  "sector beneficiary", "sector_beneficiary", "theme_beneficiary",
                  "infrastructure_capex", "it_export", "pharma_export", "banking_sector",
                  "it_sector", "oil_gas_sector"}
_LISTED_KW     = {"stock", "listed", "company", "bank", "banking", "it services", "pharma",
                  "energy", "oil", "gas", "infrastructure", "large-cap", "largecap",
                  "nse", "bse", "equity", "scrip", "share", "corp", "ltd", "limited",
                  "upstream", "downstream", "refiner", "epc", "integrator", "fintech",
                  "nbfc", "insurance", "private sector bank", "public sector bank",
                  "it_services", "defense", "defence", "cyber", "engineering",
                  "real_estate_stock", "information technology", "acquirer"}

# Opportunity types from L5 that map directly
_OPP_TYPE_MAP = {
    "listed_stock":           LISTED_COMPANY,
    "sector_theme":           SECTOR_THEME,
    "macro_theme":            MACRO_THEME,
    "cross_domain":           SECTOR_THEME,
    "fund_etf":               FUND_ETF,
    "commodity":              COMMODITY,
    "real_estate_theme":      REAL_ESTATE_REGIONAL,
    "private_unlisted_company": PRIVATE_UNLISTED,
}


def classify(candidate: dict) -> dict:
    """
    Classify a single candidate's target_type.
    Returns updated candidate with target_type + classification_confidence + classification_reason.
    """
    hint     = (candidate.get("candidate_type_hint") or "").lower().strip()
    opp_type = (candidate.get("source_opportunity_type") or "").lower().strip()
    ticker   = (candidate.get("ticker_hint") or "").strip()
    name     = (candidate.get("candidate_name") or "").lower().strip()

    target_type, confidence, reason = _resolve_type(hint, opp_type, ticker, name)

    candidate["target_type"]               = target_type
    candidate["classification_confidence"] = confidence
    candidate["classification_reason"]     = reason
    return candidate


def classify_all(candidates: list[dict]) -> list[dict]:
    return [classify(c) for c in candidates]


def _resolve_type(hint: str, opp_type: str, ticker: str, name: str) -> tuple[str, float, str]:
    # 1. Ticker with .NS / .BO suffix → definitely listed
    if re.search(r'\.(NS|BO|BSE)$', ticker, re.IGNORECASE):
        return LISTED_COMPANY, 0.97, "Ticker ends with exchange suffix"

    # 2. Theme-level hint (mapping_status = theme_level means it's the self-candidate)
    if hint in ("sector_theme", "macro_theme", "cross_domain", "real_estate_theme",
                "fund_etf", "commodity", "theme_level"):
        mapped = _OPP_TYPE_MAP.get(hint, SECTOR_THEME)
        return mapped, 0.95, f"Hint maps directly to {mapped}"

    # 3. Opportunity type direct map (for self-candidates where hint = opp_type)
    if opp_type in _OPP_TYPE_MAP:
        return _OPP_TYPE_MAP[opp_type], 0.90, f"Opp type '{opp_type}' → {_OPP_TYPE_MAP[opp_type]}"

    # 4. Keyword scan on hint string
    h = hint.replace("_", " ").replace("-", " ")

    if any(kw in h for kw in _FUND_KW):
        return FUND_ETF, 0.85, f"Fund/ETF keyword in hint: '{hint}'"
    if any(kw in h for kw in _COMMODITY_KW):
        return COMMODITY, 0.85, f"Commodity keyword in hint: '{hint}'"
    if any(kw in h for kw in _REAL_ESTATE_KW):
        return REAL_ESTATE_REGIONAL, 0.82, f"Real estate keyword in hint: '{hint}'"
    if any(kw in h for kw in _MACRO_KW):
        return MACRO_THEME, 0.83, f"Macro keyword in hint: '{hint}'"
    if any(kw in h for kw in _SECTOR_KW):
        return SECTOR_THEME, 0.82, f"Sector/theme keyword in hint: '{hint}'"
    if any(kw in h for kw in _LISTED_KW):
        return LISTED_COMPANY, 0.80, f"Listed company keyword in hint: '{hint}'"

    # 5. Keyword scan on candidate name
    if any(kw in name for kw in _SECTOR_KW):
        return SECTOR_THEME, 0.70, f"Sector keyword in name: '{name[:40]}'"
    if any(kw in name for kw in _MACRO_KW):
        return MACRO_THEME, 0.70, f"Macro keyword in name: '{name[:40]}'"

    # 6. If ticker exists but no exchange suffix → assume listed
    if ticker:
        return LISTED_COMPANY, 0.72, "Ticker present but no exchange suffix — assume listed"

    return UNKNOWN, 0.40, f"Could not classify hint='{hint}' name='{name[:30]}'"


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from collections import Counter
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import (
        planning_input_loader, opportunity_filter, target_candidate_builder)

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / date
    ctx  = planning_input_loader.load(base / "layer3", base / "layer4", base / "layer5")
    filt = opportunity_filter.filter_opportunities(ctx["opportunity_hypotheses"])
    cands = target_candidate_builder.build_candidates(filt["accepted"])

    classified = classify_all(cands)
    counts = Counter(c["target_type"] for c in classified)
    print("Target type distribution:")
    for t, n in counts.most_common():
        print(f"  {t:30s} : {n}")
    unknowns = [c for c in classified if c["target_type"] == "unknown"]
    if unknowns:
        print(f"\nUnknown ({len(unknowns)}):")
        for c in unknowns[:5]:
            print(f"  hint={c['candidate_type_hint']!r} name={c['candidate_name'][:40]!r}")
