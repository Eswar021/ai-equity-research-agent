"""
intelligence_layer/evidence_builder/peer_feature_engineer.py — Layer 8

Computes peer comparison features from peer_comparison.json.

peer_comparison format:
  target: {symbol, trailingPE, priceToBook, marketCap, revenueGrowth, profitMargins,
            returnOnEquity, debtToEquity, dividendYield, currentRatio, sector}
  peers:  list of same structure
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_METRICS = [
    ("trailingPE",     "pe",             False),  # lower is not better
    ("priceToBook",    "pb",             False),
    ("revenueGrowth",  "revenue_growth", True),   # higher is better
    ("profitMargins",  "profit_margins", True),
    ("returnOnEquity", "roe",            True),
    ("debtToEquity",   "debt_equity",    False),  # lower is better
]


def compute(scope: dict) -> dict:
    tid  = scope["target_id"]
    pc   = scope["files"].get("peer_comparison") or {}

    feats: dict[str, float | str | int | None] = {}
    warnings: list[str] = []

    target = pc.get("target", {})
    peers  = pc.get("peers", [])

    if not target:
        warnings.append("peer_comparison missing target data")

    feats["peer_count"] = len(peers)

    # ── For each metric: compute percentile, peer median, target value ─────────
    for yf_key, label, higher_is_better in _METRICS:
        peer_vals = [_num(p.get(yf_key)) for p in peers]
        peer_vals = [v for v in peer_vals if v is not None]
        target_val = _num(target.get(yf_key))

        feats[f"{label}_target"] = target_val
        feats[f"{label}_peer_median"] = _median(peer_vals) if peer_vals else None

        if target_val is not None and peer_vals:
            vs_median = feats[f"{label}_peer_median"]
            if vs_median and vs_median != 0:
                feats[f"{label}_vs_peer_median_pct"] = round((target_val - vs_median) / abs(vs_median) * 100, 2)
            else:
                feats[f"{label}_vs_peer_median_pct"] = None
            feats[f"{label}_percentile"] = _percentile(target_val, peer_vals, higher_is_better)
        else:
            feats[f"{label}_vs_peer_median_pct"] = None
            feats[f"{label}_percentile"] = None

    # ── Quality and valuation composite hints ─────────────────────────────────
    roe_pctile = feats.get("roe_percentile")
    rev_pctile = feats.get("revenue_growth_percentile")
    margin_pctile = feats.get("profit_margins_percentile")
    pe_pctile  = feats.get("pe_percentile")

    quality_scores = [v for v in [roe_pctile, rev_pctile, margin_pctile] if v is not None]
    feats["quality_vs_peer_hint"] = _quality_hint(quality_scores)

    val_scores = [v for v in [pe_pctile, feats.get("pb_percentile")] if v is not None]
    feats["valuation_vs_peer_hint"] = _valuation_hint(val_scores)

    # For valuation_feature_engineer to use
    feats["pe_vs_peer_median_pct"] = feats.get("pe_vs_peer_median_pct")
    feats["pb_vs_peer_median_pct"] = feats.get("pb_vs_peer_median_pct")

    completeness = sum(1 for v in feats.values() if v is not None) / max(len(feats), 1)

    return {
        "feature_group_id":  f"FEAT_PEER_{tid}",
        "target_id":         tid,
        "feature_group":     "peer_features",
        "features":          feats,
        "source_record_refs": [f"peer_comparison:{scope.get('target_dir','')}/peer_comparison.json"],
        "data_quality": {
            "completeness_score": round(completeness, 2),
            "warnings":           warnings,
        },
        "calculated_at": datetime.now(_IST).isoformat(),
    }


def _num(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return round((s[mid - 1] + s[mid]) / 2, 4)
    return round(s[mid], 4)


def _percentile(target_val: float, peer_vals: list[float], higher_is_better: bool) -> int:
    """What % of peers does target beat (0-100)?"""
    if not peer_vals:
        return 50
    if higher_is_better:
        beaten = sum(1 for v in peer_vals if target_val > v)
    else:
        beaten = sum(1 for v in peer_vals if target_val < v)
    return round(beaten / len(peer_vals) * 100)


def _quality_hint(pctiles: list[float]) -> str:
    if not pctiles:
        return "unknown"
    avg = sum(pctiles) / len(pctiles)
    if avg >= 70:
        return "above_average"
    if avg >= 40:
        return "near_median"
    return "below_average"


def _valuation_hint(pctiles: list[float]) -> str:
    """PE/PB percentile: high percentile = expensive (beats many peers on valuation multiple)."""
    if not pctiles:
        return "unknown"
    avg = sum(pctiles) / len(pctiles)
    if avg >= 70:
        return "expensive_vs_peers"
    if avg >= 40:
        return "near_median"
    return "cheap_vs_peers"
