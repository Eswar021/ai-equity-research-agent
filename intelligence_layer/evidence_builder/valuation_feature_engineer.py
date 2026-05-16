"""
intelligence_layer/evidence_builder/valuation_feature_engineer.py — Layer 8

Computes valuation features from market_data + screener_in + peer_comparison
+ analyst_estimates. Layer 9 valuation agent interprets; this module only computes.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def compute(scope: dict, price_feats: dict, fund_feats: dict, peer_feats: dict) -> dict:
    tid   = scope["target_id"]
    files = scope["files"]
    md    = files.get("market_data")    or {}
    sc    = files.get("screener_in")    or {}
    ae    = files.get("analyst_estimates") or {}
    pc    = files.get("peer_comparison") or {}

    feats: dict[str, float | str | None] = {}
    warnings: list[str] = []

    pf = price_feats.get("features", {})
    ff = fund_feats.get("features", {})
    peer_f = peer_feats.get("features", {})

    key_ratios = sc.get("key_ratios", {})

    # ── Valuation multiples ────────────────────────────────────────────────────
    # PE from screener (more reliable than yfinance trailing PE for Indian stocks)
    feats["pe_ratio"]    = ff.get("pe_ratio")
    feats["pb_ratio"]    = _from_screener_pb(key_ratios, pf)
    feats["earnings_yield_pct"] = _earnings_yield(feats["pe_ratio"])
    feats["dividend_yield_pct"] = ff.get("dividend_yield_pct")

    # Market cap in Cr
    mc = pf.get("market_cap")
    feats["market_cap_cr"] = round(mc / 1e7, 0) if mc else None

    # ── Relative to peers ─────────────────────────────────────────────────────
    feats["pe_vs_peer_median_pct"] = peer_f.get("pe_vs_peer_median_pct")
    feats["pb_vs_peer_median_pct"] = peer_f.get("pb_vs_peer_median_pct")

    # ── Analyst consensus price target upside ─────────────────────────────────
    pt = ae.get("price_targets", {})
    current_price = pf.get("current_price")
    target_mean   = _num(pt.get("mean"))
    if current_price and target_mean and current_price > 0:
        feats["analyst_target_upside_pct"] = round((target_mean - current_price) / current_price * 100, 2)
        feats["analyst_target_price_mean"] = target_mean
        feats["analyst_target_price_high"] = _num(pt.get("high"))
        feats["analyst_target_price_low"]  = _num(pt.get("low"))
    else:
        feats["analyst_target_upside_pct"]  = None
        feats["analyst_target_price_mean"]  = target_mean
        feats["analyst_target_price_high"]  = _num(pt.get("high"))
        feats["analyst_target_price_low"]   = _num(pt.get("low"))
        if not target_mean:
            warnings.append("No analyst price target available")

    # ── Price vs fundamentals signal ──────────────────────────────────────────
    # If stock is below 52-week high significantly, may be at discount
    feats["distance_from_52w_high_pct"]  = pf.get("distance_from_52w_high_pct")
    feats["return_1y_pct"]               = pf.get("return_1y_pct")

    # ── Completeness ──────────────────────────────────────────────────────────
    present = sum(1 for v in feats.values() if v is not None)
    completeness = round(present / max(len(feats), 1), 2)
    feats["valuation_data_completeness"] = completeness

    source_refs = [
        f"market_data:{scope.get('target_dir','')}/market_data.json",
        f"screener_in:{scope.get('target_dir','')}/screener_in.json",
        f"peer_comparison:{scope.get('target_dir','')}/peer_comparison.json",
        f"analyst_estimates:{scope.get('target_dir','')}/analyst_estimates.json",
    ]

    return {
        "feature_group_id":  f"FEAT_VAL_{tid}",
        "target_id":         tid,
        "feature_group":     "valuation_features",
        "features":          feats,
        "source_record_refs": source_refs,
        "data_quality": {
            "completeness_score": completeness,
            "warnings":           warnings,
        },
        "calculated_at": datetime.now(_IST).isoformat(),
    }


def _from_screener_pb(key_ratios: dict, price_feats: dict) -> float | None:
    """Compute P/B from current_price / book_value from screener."""
    import re
    bv_str = key_ratios.get("Book Value", "")
    price  = price_feats.get("current_price")
    if not bv_str or price is None:
        return None
    s = re.sub(r'[₹,\s]', '', str(bv_str)).replace("Cr.", "")
    try:
        bv = float(s)
        if bv > 0:
            return round(price / bv, 2)
    except (ValueError, TypeError):
        pass
    return None


def _earnings_yield(pe: float | None) -> float | None:
    if pe and pe > 0:
        return round(100 / pe, 2)
    return None


def _num(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
