"""
intelligence_layer/final_synthesis_layer/market_posture_synthesizer.py — Layer 10

Derives the final market posture from the Layer 5 market view.
Pure Python, no LLM.
"""

from __future__ import annotations

_POSTURE_MAP = {
    "bullish":    "selective_buy",
    "risk_on":    "selective_buy",
    "selective":  "selective_research",
    "neutral":    "selective_research",
    "cautious":   "defensive",
    "defensive":  "defensive",
    "risk_off":   "defensive",
    "bearish":    "defensive",
}

_POSTURE_LABELS = {
    "selective_buy":      "Selective buying environment — quality + reasonable valuation preferred",
    "selective_research": "Selective research environment — broad aggressive buying not supported",
    "defensive":          "Defensive environment — capital preservation preferred; high-conviction only",
}


def synthesize(market_view: dict) -> dict:
    regime     = market_view.get("regime", "neutral")
    rec_posture = market_view.get("recommended_posture", "selective")
    risk_level = market_view.get("risk_level", "medium")
    trend      = market_view.get("trend_state", "sideways")
    valuation  = market_view.get("valuation_state", "fair")
    liquidity  = market_view.get("liquidity_flow_state", "neutral")
    volatility = market_view.get("volatility_state", "moderate")
    confidence = market_view.get("confidence", 0.7)

    posture_key = _POSTURE_MAP.get(rec_posture, "selective_research")

    # ── Sectors ───────────────────────────────────────────────────────────────
    sectors_block = market_view.get("sectors", {})
    if isinstance(sectors_block, dict):
        favored  = sectors_block.get("favored", [])
        avoid    = sectors_block.get("avoid",   [])
    else:
        favored, avoid = [], []

    # ── Reasoning ────────────────────────────────────────────────────────────
    reasoning = market_view.get("reasoning_summary", [])
    if isinstance(reasoning, str):
        reasoning = [reasoning]

    # ── Summary sentence ─────────────────────────────────────────────────────
    summary_parts = [
        f"Market regime is {regime} with {risk_level} risk.",
        f"Trend is {trend}, valuation is {valuation}.",
        f"Liquidity flow is {liquidity}; volatility is {volatility}.",
        _POSTURE_LABELS.get(posture_key, ""),
    ]

    # Downgrade buying if liquidity is negative
    if liquidity in ("negative", "outflows") and posture_key == "selective_buy":
        posture_key = "selective_research"

    return {
        "market_summary_card_id": f"MKTSUM_{market_view.get('market_view_id', 'UNKNOWN')}",
        "market":                 market_view.get("market", "india"),
        "regime":                 regime,
        "final_market_posture":   posture_key,
        "risk_level":             risk_level,
        "trend_state":            trend,
        "valuation_state":        valuation,
        "liquidity_flow_state":   liquidity,
        "volatility_state":       volatility,
        "favored_sectors":        favored,
        "avoid_sectors":          avoid,
        "summary":                " ".join(p for p in summary_parts if p),
        "key_points":             reasoning[:4],
        "confidence":             confidence,
        "posture_label":          _POSTURE_LABELS.get(posture_key, posture_key),
    }
