"""
intelligence_layer/canonical_intelligence_extraction/extractors/market_signal_builder.py — Layer 3

Rule-based builder: creates primitive market signal cards from structured records.
These are NOT final interpretations — they are raw observable signals for Layer 5.

"Do not say market is risk-off yet. Do not decide investment posture." — design doc §14

Design doc: docs/system_design_docs/layer_3.md §14 market_signal_builder.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_signal_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"SIG_{today}_{_COUNTER[0]:04d}"

def _signal(record: dict, signal_type: str, name: str, metric: str,
            value, unit: str | None, direction: str, horizon: str = "short_term",
            ticker: str | None = None, conf: float = 0.95) -> dict:
    rec_id    = record.get("record_id", "")
    source_id = (record.get("lineage") or {}).get("source_module", "")
    data_date = record.get("data_date") or record.get("collected_at", "")[:10]
    return {
        "signal_id":          _next_signal_id(),
        "signal_type":        signal_type,
        "signal_name":        name,
        "market":             record.get("market", "india"),
        "data_date":          data_date,
        "metric_name":        metric,
        "metric_value":       value,
        "unit":               unit,
        "direction_hint":     direction,
        "time_horizon_hint":  horizon,
        "ticker":             ticker,
        "source_record_id":   rec_id,
        "source_id":          source_id,
        "source_refs":        [{"record_id": rec_id, "source_id": source_id}] if rec_id else [],
        "source_reliability": record.get("source_reliability", "high"),
        "confidence":         conf,
    }


def build(record: dict) -> list[dict]:
    """Build primitive signal cards from a canonical structured record."""
    rec_type = (record.get("record_type") or "").lower()
    data     = record.get("data") or {}

    if rec_type == "institutional_flow":
        return _build_fii_dii_signals(record, data)
    elif rec_type == "macro_snapshot":
        return _build_macro_signals(record, data)
    elif rec_type == "derivatives_snapshot":
        return _build_derivatives_signals(record, data)
    elif rec_type == "bulk_block_deals":
        return _build_bulk_deal_signals(record, data)
    else:
        return []


# ── Per-type signal builders ──────────────────────────────────────────────────

def _build_fii_dii_signals(record, data) -> list[dict]:
    signals = []
    fii     = data.get("fii") or {}
    dii     = data.get("dii") or {}

    if fii.get("net") is not None:
        v   = fii["net"]
        dir = "positive" if v > 0 else "negative" if v < 0 else "neutral"
        lbl = "FII net buying observed" if v > 0 else "FII net selling observed"
        signals.append(_signal(record, "institutional_flow", lbl,
                               "fii_net_flow", v, "INR crore", dir))

    if dii.get("net") is not None:
        v   = dii["net"]
        dir = "positive" if v > 0 else "negative" if v < 0 else "neutral"
        lbl = "DII net buying observed" if v > 0 else "DII net selling observed"
        signals.append(_signal(record, "institutional_flow", lbl,
                               "dii_net_flow", v, "INR crore", dir))
    return signals


def _build_macro_signals(record, data) -> list[dict]:
    signals = []

    # India VIX
    vix = data.get("india_vix")
    if vix is not None:
        dir = "negative" if float(vix) > 20 else "neutral" if float(vix) > 15 else "positive"
        signals.append(_signal(record, "macro_indicator", "India VIX level observed",
                               "india_vix", vix, "points", dir))

    # USD/INR
    usd_inr = data.get("usd_inr")
    if usd_inr is not None:
        signals.append(_signal(record, "macro_indicator", "USD/INR rate observed",
                               "usd_inr", usd_inr, "INR", "neutral"))

    # US Fed funds rate
    ffr = data.get("federal_funds_rate")
    if ffr is not None:
        dir = "negative" if float(ffr) > 5 else "neutral"
        signals.append(_signal(record, "macro_indicator", "US Fed funds rate observed",
                               "federal_funds_rate", ffr, "%", dir, "medium_term"))

    # Repo rate
    repo = data.get("repo_rate")
    if repo is not None:
        signals.append(_signal(record, "macro_indicator", "RBI repo rate observed",
                               "repo_rate", repo, "%", "neutral", "medium_term"))

    return signals


def _build_derivatives_signals(record, data) -> list[dict]:
    signals = []
    ticker  = data.get("ticker") or ""

    pcr = data.get("pcr")
    if pcr is not None:
        pcr_f = float(pcr)
        if pcr_f > 1.2:
            dir, lbl = "positive", "Put-call ratio elevated (bearish hedging)"
        elif pcr_f < 0.8:
            dir, lbl = "negative", "Put-call ratio low (call-heavy, caution)"
        else:
            dir, lbl = "neutral", "Put-call ratio in normal range"
        signals.append(_signal(record, "derivatives", lbl, "pcr", pcr_f, None, dir, ticker=ticker or None))

    atm_iv = data.get("atm_iv") or {}
    if atm_iv.get("call"):
        signals.append(_signal(record, "derivatives", "ATM IV observed",
                               "atm_iv_call", atm_iv["call"], "%", "neutral", ticker=ticker or None))

    max_pain = data.get("max_pain")
    if max_pain is not None:
        signals.append(_signal(record, "derivatives", f"Max pain level: {max_pain}",
                               "max_pain", max_pain, "INR", "neutral", ticker=ticker or None))

    return signals


def _build_bulk_deal_signals(record, data) -> list[dict]:
    signals = []
    threshold_qty = 100_000  # 1 lakh shares minimum to create a signal

    for deal in (data.get("bulk_deals") or []) + (data.get("block_deals") or []):
        ticker = deal.get("symbol") or deal.get("ticker") or ""
        try:
            qty = int(float(deal.get("quantity") or deal.get("qty") or 0))
        except (TypeError, ValueError):
            qty = 0
        if not ticker or qty < threshold_qty:
            continue
        txtype = (deal.get("buySell") or deal.get("type") or "").upper()
        dir    = "positive" if txtype == "BUY" else "negative" if txtype == "SELL" else "neutral"
        name   = f"Large {'bulk buy' if dir == 'positive' else 'bulk sell'} observed in {ticker}"
        signals.append(_signal(record, "institutional_flow", name,
                               "bulk_deal_quantity", qty, "shares", dir, ticker=ticker))

    return signals
