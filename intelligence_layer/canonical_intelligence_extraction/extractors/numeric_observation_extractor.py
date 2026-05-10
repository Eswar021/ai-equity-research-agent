"""
intelligence_layer/canonical_intelligence_extraction/extractors/numeric_observation_extractor.py — Layer 3

Rule-based extractor: reads market snapshot and price history records and
creates simple numeric observation fact cards.

Allowed in Layer 3 (design doc §13 boundaries):
  current_price, 52w_high, 52w_low, volume, market_cap, pe_ratio, pcr,
  target_price, revenue_value, opening/closing price.

NOT Layer 3: CAGR, drawdown, valuation attractiveness, buy/sell decisions.

Design doc: docs/system_design_docs/layer_3.md §13 numeric_observation_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_fact_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"NOBS_{today}_{_COUNTER[0]:04d}"


def _obs(record: dict, fact_type: str, entity: str, ticker: str,
         metric: str, value, unit: str | None, conf: float = 0.95) -> dict:
    rec_id    = record.get("record_id", "")
    source_id = (record.get("lineage") or {}).get("source_module", "")
    col_date  = record.get("collected_at", "")[:10]
    text      = f"{entity or ticker} {metric}: {value} {unit or ''}".strip()
    return {
        "fact_id":   _next_fact_id(),
        "fact_type": fact_type,
        "fact_text": text,
        "entities":  [entity or ticker] if (entity or ticker) else [],
        "metrics": [{
            "metric_name":  metric,
            "metric_value": str(value),
            "unit":         unit,
        }],
        "source_refs": [{
            "record_id":         rec_id,
            "source_id":         source_id,
            "supporting_text":   text,
            "data_date":         col_date,
            "source_reliability": record.get("source_reliability", "high"),
        }],
        "published_at": col_date,
        "confidence":   conf,
    }


def extract(record: dict) -> list[dict]:
    """Extract numeric observation facts from market_snapshot or price_history records."""
    rec_type = (record.get("record_type") or "").lower()
    data     = record.get("data") or {}
    ctx      = record.get("target_context") or {}
    ticker   = ctx.get("ticker") or data.get("ticker", "")
    entity   = ctx.get("entity_name") or data.get("company_name") or ticker

    if rec_type == "market_snapshot":
        return _extract_market_snapshot(record, data, ticker, entity)
    elif rec_type == "price_history":
        return _extract_price_history(record, data, ticker, entity)
    return []


def _extract_market_snapshot(record, data, ticker, entity) -> list[dict]:
    facts = []
    fields = [
        ("price",               "current_price",          "INR",    "market_snapshot_fact"),
        ("day_change_pct",      "day_change_pct",         "%",      "market_snapshot_fact"),
        ("volume",              "volume",                 "shares", "market_snapshot_fact"),
        ("market_cap",          "market_cap",             "INR",    "market_snapshot_fact"),
        ("fifty_two_week_high", "52w_high",               "INR",    "market_snapshot_fact"),
        ("fifty_two_week_low",  "52w_low",                "INR",    "market_snapshot_fact"),
        ("pe_ratio",            "pe_ratio",               "x",      "analyst_fact"),
        ("pb_ratio",            "pb_ratio",               "x",      "analyst_fact"),
    ]
    for field, metric, unit, ftype in fields:
        val = data.get(field)
        if val is not None:
            facts.append(_obs(record, ftype, entity, ticker, metric, val, unit))
    return facts


def _extract_price_history(record, data, ticker, entity) -> list[dict]:
    """Extract summary stats from price history (first, last, high, low over period)."""
    facts   = []
    history = data.get("history") or []
    if not history:
        return facts

    # Only extract simple start/end observations — no CAGR or drawdown in Layer 3
    try:
        first  = history[0]
        last   = history[-1]
        period = data.get("period", "1y")

        if first.get("close") is not None:
            facts.append(_obs(record, "market_snapshot_fact", entity, ticker,
                f"price_start_{period}", first["close"], "INR"))
        if last.get("close") is not None:
            facts.append(_obs(record, "market_snapshot_fact", entity, ticker,
                f"price_end_{period}", last["close"], "INR"))

        all_highs = [row["high"] for row in history if row.get("high") is not None]
        all_lows  = [row["low"]  for row in history if row.get("low")  is not None]
        if all_highs:
            facts.append(_obs(record, "market_snapshot_fact", entity, ticker,
                f"52w_high_period", max(all_highs), "INR"))
        if all_lows:
            facts.append(_obs(record, "market_snapshot_fact", entity, ticker,
                f"52w_low_period", min(all_lows), "INR"))
    except (IndexError, TypeError, KeyError):
        pass

    return facts
