"""
intelligence_layer/evidence_builder/price_feature_engineer.py — Layer 8

Computes price/trend features from price_history.json + market_data.json.
All calculations are deterministic — no LLM.
"""

from __future__ import annotations
import statistics
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def compute(scope: dict) -> dict:
    """
    Returns a feature_group dict:
    {
        feature_group_id, target_id, feature_group, features,
        source_record_refs, data_quality, calculated_at
    }
    """
    tid    = scope["target_id"]
    files  = scope["files"]
    md     = files.get("market_data") or {}
    ph     = files.get("price_history") or {}
    history = ph.get("history", [])

    feats: dict[str, float | None] = {}
    warnings: list[str] = []

    # ── From market_data (pre-computed by yfinance) ───────────────────────────
    feats["current_price"]          = _num(md.get("price"))
    feats["day_change_pct"]         = _num(md.get("day_change_pct"))
    feats["52w_high"]               = _num(md.get("52w_high"))
    feats["52w_low"]                = _num(md.get("52w_low"))
    feats["return_1m_pct"]          = _num(md.get("return_1m"))
    feats["return_3m_pct"]          = _num(md.get("return_3m"))
    feats["return_1y_pct"]          = _num(md.get("return_1y"))
    feats["volume_latest"]          = _num(md.get("volume"))
    feats["market_cap"]             = _num(md.get("market_cap"))

    price = feats["current_price"]
    high52 = feats["52w_high"]
    low52  = feats["52w_low"]

    if price is not None and high52 and high52 > 0:
        feats["distance_from_52w_high_pct"] = round((price - high52) / high52 * 100, 2)
    else:
        feats["distance_from_52w_high_pct"] = None

    if price is not None and low52 and low52 > 0:
        feats["distance_from_52w_low_pct"] = round((price - low52) / low52 * 100, 2)
    else:
        feats["distance_from_52w_low_pct"] = None

    # ── From price_history (249 daily bars) ───────────────────────────────────
    closes = [h["close"] for h in history if h.get("close") is not None]
    volumes = [h.get("volume", 0) for h in history]

    if len(closes) >= 2:
        feats["return_5d_pct"]  = _pct_return(closes, 5)
        feats["return_6m_pct"]  = _pct_return(closes, 126)
    else:
        feats["return_5d_pct"]  = None
        feats["return_6m_pct"]  = None

    feats["sma_20"]   = _sma(closes, 20)
    feats["sma_50"]   = _sma(closes, 50)
    feats["sma_200"]  = _sma(closes, 200)

    if price is not None and feats["sma_200"] is not None and feats["sma_200"] > 0:
        feats["price_vs_sma_200_pct"] = round((price - feats["sma_200"]) / feats["sma_200"] * 100, 2)
    else:
        feats["price_vs_sma_200_pct"] = None

    feats["volatility_30d"]     = _volatility(closes, 30)
    feats["max_drawdown_1y_pct"]= _max_drawdown(closes)

    avg_vol = _avg(volumes, 30) if volumes else None
    latest_vol = volumes[-1] if volumes else None
    if avg_vol and avg_vol > 0 and latest_vol:
        feats["volume_spike_ratio"] = round(latest_vol / avg_vol, 2)
    else:
        feats["volume_spike_ratio"] = None

    completeness = sum(1 for v in feats.values() if v is not None) / len(feats)
    if not history:
        warnings.append("price_history empty — computed features from market_data only")

    source_refs = []
    if md:
        source_refs.append(f"market_data:{scope.get('target_dir','')}/market_data.json")
    if ph:
        source_refs.append(f"price_history:{scope.get('target_dir','')}/price_history.json")

    return {
        "feature_group_id":  f"FEAT_PRICE_{tid}",
        "target_id":         tid,
        "feature_group":     "price_features",
        "features":          feats,
        "source_record_refs": source_refs,
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


def _pct_return(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    start = closes[-(n + 1)]
    end   = closes[-1]
    if start == 0:
        return None
    return round((end - start) / start * 100, 2)


def _sma(closes: list[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 2)


def _volatility(closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    subset = closes[-n:]
    returns = [(subset[i] - subset[i-1]) / subset[i-1] for i in range(1, len(subset)) if subset[i-1] != 0]
    if len(returns) < 2:
        return None
    return round(statistics.stdev(returns), 4)


def _max_drawdown(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _avg(values: list, n: int) -> float | None:
    subset = [v for v in values[-n:] if v is not None]
    return sum(subset) / len(subset) if subset else None
