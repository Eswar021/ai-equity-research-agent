"""
intelligence_layer/research_target_planner/sector_constituent_mapper.py — Layer 6

For sector_theme unresolved targets, maps the theme name to known NSE sector
constituents using keyword matching and a hardcoded sector→stocks dict.

Design doc: docs/system_design_docs/layer_6.md §10 sector_constituent_mapper.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

# Major NSE sector → top liquid stocks
_SECTOR_STOCKS: dict[str, list[str]] = {
    "banking":         ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "nbfc":            ["BAJFINANCE.NS", "BAJAJFINSV.NS", "SBICARD.NS", "CHOLAFIN.NS"],
    "it":              ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"],
    "pharma":          ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "AUROPHARMA.NS"],
    "oil_gas":         ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS", "GAIL.NS"],
    "auto":            ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
    "fmcg":            ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS"],
    "infra":           ["LT.NS", "BHEL.NS", "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS"],
    "real_estate":     ["DLF.NS", "LODHA.NS", "PRESTIGE.NS", "OBEROIRLTY.NS", "GODREJPROP.NS"],
    "cement":          ["ULTRACEMCO.NS", "GRASIM.NS", "AMBUJACEM.NS", "ACC.NS", "SHREECEM.NS"],
    "metals":          ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "SAIL.NS"],
    "power":           ["NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "NHPC.NS"],
    "telecom":         ["BHARTIARTL.NS", "JIOFIN.NS", "IDEA.NS"],
    "defense":         ["HAL.NS", "BEL.NS", "BHEL.NS", "MTAR.NS", "PARAS.NS"],
    "chemicals":       ["PIDILITIND.NS", "AAVAS.NS", "DEEPAKNITRITE.NS", "ATUL.NS"],
    "logistics":       ["DELHIVERY.NS", "BLUEDART.NS", "MAHINDRALOG.NS"],
}

# Keywords to map theme name → sector key (check more specific/longer first)
_THEME_TO_SECTOR: list[tuple[list[str], str]] = [
    (["oil price", "crude oil", "opec", "strait of hormuz", "brent",
      "petroleum", "refin", "upstream", "downstream"],                  "oil_gas"),
    (["bank", "banking", "lender", "nim", "margin pressure", "credit"], "banking"),
    (["nbfc", "microfinance", "mfi", "fintech", "lending"],             "nbfc"),
    (["software", "tech", "artificial intel", "digital", "semiconductor",
      "cyber", "it sector", "it services", "information tech"],         "it"),
    (["pharma", "drug", "healthcare", "biotech", "medic"],              "pharma"),
    (["oil", "gas", "energy", "lng", "cng"],                            "oil_gas"),
    (["auto", "vehicle", "car", " ev ", "electric vehicle", "mobility"], "auto"),
    (["fmcg", "consumer", "staple", "beverage", "food"],                "fmcg"),
    (["infra", "infrastructure", "capex", "epc", "engineer"],           "infra"),
    (["real estate", "property", "housing", "reit", "realty"],          "real_estate"),
    (["cement", "construction material"],                                "cement"),
    (["metal", "steel", "alumin", "copper", "zinc", "mining"],          "metals"),
    (["power", "electric", "renewable", "solar", "wind", "ntpc"],       "power"),
    (["telecom", "wireless", "5g", "spectrum", "airtel", "jio"],        "telecom"),
    (["defense", "defence", "military", "missile", "ammunition"],       "defense"),
    (["chemical", "specialty chemical", "agrochemical"],                 "chemicals"),
    (["logistics", "warehouse", "supply chain", "freight"],             "logistics"),
]


def map_sectors(unresolved: list[dict]) -> list[dict]:
    """
    For sector_theme unresolved targets, produce a sector_mapping result
    with possible listed constituents.
    Returns list of sector_mapping dicts.
    """
    today = datetime.now(_IST).strftime("%Y%m%d")
    results: list[dict] = []

    for u in unresolved:
        if u.get("target_type") != "sector_theme":
            continue

        name   = (u.get("candidate_name") or "").lower()
        sector = _match_sector(name)

        _CTR[0] += 1
        results.append({
            "sector_mapping_id":          f"SECMAP_{today}_{_CTR[0]:04d}",
            "source_target_id":           u.get("unresolved_target_id", ""),
            "theme_name":                 u.get("candidate_name", ""),
            "matched_sector":             sector,
            "possible_listed_constituents": [
                {"ticker": t, "reason": f"Top {sector or 'sector'} constituent"}
                for t in _SECTOR_STOCKS.get(sector, [])
            ],
        })

    return results


def _match_sector(name: str) -> str:
    for keywords, sector in _THEME_TO_SECTOR:
        if any(kw in name for kw in keywords):
            return sector
    return ""
