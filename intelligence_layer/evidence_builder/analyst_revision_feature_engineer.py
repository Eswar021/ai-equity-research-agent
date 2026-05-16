"""
intelligence_layer/evidence_builder/analyst_revision_feature_engineer.py — Layer 8

Computes analyst expectation/revision features from analyst_estimates.json.

analyst_estimates format:
  recommendations: [{period, strong_buy, buy, hold, sell, strong_sell}]  (4 periods: 0m, -1m, -2m, -3m)
  price_targets:   {mean, high, low, numberOfAnalysts}
  earnings_estimates: {0q, +1q, 0y, +1y} each with avg, growth, etc.
  eps_trend: {0q, +1q, 0y, +1y} each with current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo
  eps_revisions: {0q, +1q, 0y, +1y} each with upLast7days, upLast30days, downLast30days, downLast90days
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def compute(scope: dict) -> dict:
    tid  = scope["target_id"]
    ae   = scope["files"].get("analyst_estimates") or {}

    feats: dict[str, float | str | int | None] = {}
    warnings: list[str] = []

    recs  = ae.get("recommendations", [])
    pt    = ae.get("price_targets", {})
    ee    = ae.get("earnings_estimates", {})
    eps_t = ae.get("eps_trend", {})
    eps_r = ae.get("eps_revisions", {})

    # ── Current period recommendation distribution ─────────────────────────────
    current_rec = _get_period(recs, "0m") or {}
    sb  = _num(current_rec.get("strong_buy",  0))
    b   = _num(current_rec.get("buy",         0))
    h   = _num(current_rec.get("hold",        0))
    s   = _num(current_rec.get("sell",        0))
    ss  = _num(current_rec.get("strong_sell", 0))
    total = (sb or 0) + (b or 0) + (h or 0) + (s or 0) + (ss or 0)

    feats["coverage_count"] = int(total) if total else None
    if total and total > 0:
        feats["buy_rating_ratio"]       = round(((sb or 0) + (b or 0)) / total, 3)
        feats["hold_rating_ratio"]      = round((h or 0) / total, 3)
        feats["sell_rating_ratio"]      = round(((s or 0) + (ss or 0)) / total, 3)
        feats["strong_buy_count"]       = int(sb or 0)
        feats["strong_sell_count"]      = int(ss or 0)
    else:
        feats["buy_rating_ratio"]       = None
        feats["hold_rating_ratio"]      = None
        feats["sell_rating_ratio"]      = None
        feats["strong_buy_count"]       = None
        feats["strong_sell_count"]      = None
        warnings.append("No analyst recommendations available")

    # ── Price target ──────────────────────────────────────────────────────────
    feats["price_target_analysts"] = _num(pt.get("numberOfAnalysts"))

    # ── EPS trend direction (are estimates rising or falling?) ────────────────
    # Compare current estimate vs 30 days ago for near-term quarter
    q0 = eps_t.get("0q", {})
    cur_q0 = _num(q0.get("current"))
    ago30_q0 = _num(q0.get("30daysAgo"))
    if cur_q0 is not None and ago30_q0 is not None and ago30_q0 != 0:
        eps_chg = (cur_q0 - ago30_q0) / abs(ago30_q0) * 100
        feats["eps_revision_pct_30d_nq"]  = round(eps_chg, 2)
        feats["eps_revision_direction"]   = "positive" if eps_chg > 0.5 else ("negative" if eps_chg < -0.5 else "stable")
    else:
        feats["eps_revision_pct_30d_nq"]  = None
        feats["eps_revision_direction"]   = "unknown"

    # ── Upgrade/downgrade count (last 30 days) ────────────────────────────────
    rev_0q = eps_r.get("0q", {})
    ups   = _num(rev_0q.get("upLast30days", 0)) or 0
    downs = _num(rev_0q.get("downLast30days", 0)) or 0
    feats["upgrades_last_30d"]  = int(ups)
    feats["downgrades_last_30d"]= int(downs)
    feats["revision_balance"]   = int(ups - downs)

    # ── Forward earnings growth expectation ───────────────────────────────────
    y1 = ee.get("+1y", {})
    feats["forward_earnings_growth_est_pct"] = _pct(y1.get("growth"))

    # ── Estimate dispersion (from price targets) ──────────────────────────────
    pt_mean = _num(pt.get("mean"))
    pt_high = _num(pt.get("high"))
    pt_low  = _num(pt.get("low"))
    if pt_mean and pt_mean > 0 and pt_high and pt_low:
        dispersion_pct = (pt_high - pt_low) / pt_mean * 100
        feats["estimate_dispersion_pct"] = round(dispersion_pct, 1)
        if dispersion_pct > 30:
            feats["estimate_dispersion"] = "high"
        elif dispersion_pct > 15:
            feats["estimate_dispersion"] = "medium"
        else:
            feats["estimate_dispersion"] = "low"
    else:
        feats["estimate_dispersion_pct"] = None
        feats["estimate_dispersion"]     = "unknown"

    if not ae:
        warnings.append("analyst_estimates missing")

    completeness = sum(1 for v in feats.values() if v is not None) / max(len(feats), 1)

    return {
        "feature_group_id":  f"FEAT_ANALYST_{tid}",
        "target_id":         tid,
        "feature_group":     "analyst_revision_features",
        "features":          feats,
        "source_record_refs": [f"analyst_estimates:{scope.get('target_dir','')}/analyst_estimates.json"],
        "data_quality": {
            "completeness_score": round(completeness, 2),
            "warnings":           warnings,
        },
        "calculated_at": datetime.now(_IST).isoformat(),
    }


def _get_period(recs: list[dict], period: str) -> dict | None:
    for r in recs:
        if r.get("period") == period:
            return r
    return None


def _num(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _pct(val) -> float | None:
    """Convert 0.082 → 8.2%"""
    n = _num(val)
    if n is None:
        return None
    if abs(n) <= 1.0:
        return round(n * 100, 2)
    return round(n, 2)
