"""
intelligence_layer/canonical_intelligence_extraction/extractors/structured_fact_extractor.py — Layer 3

Rule-based extractor: converts canonical structured records into fact cards.
No LLM — deterministic field reading only.

Covered record types (design doc §12):
  institutional_flow, macro_snapshot, analyst_estimates/consensus,
  indian_company_fundamentals, peer_comparison, corporate_actions, sec_company_facts,
  bulk_block_deals, regulatory_filing

Design doc: docs/system_design_docs/layer_3.md §12 structured_fact_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_fact_id(prefix: str = "SFACT") -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"{prefix}_{today}_{_COUNTER[0]:04d}"

def _fact(record: dict, fact_type: str, text: str, metric: str | None,
          value, unit: str | None, entities: list[str], conf: float = 0.95) -> dict:
    rec_id    = record.get("record_id", "")
    source_id = (record.get("lineage") or {}).get("source_module", "")
    data_date = record.get("data_date") or record.get("collected_at", "")[:10]
    return {
        "fact_id":   _next_fact_id(),
        "fact_type": fact_type,
        "fact_text": text,
        "entities":  entities,
        "metrics":   [{"metric_name": metric, "metric_value": str(value), "unit": unit}] if metric else [],
        "source_refs": [{
            "record_id":         rec_id,
            "source_id":         source_id,
            "supporting_text":   text,
            "data_date":         data_date,
            "source_reliability": record.get("source_reliability", "high"),
        }],
        "published_at": data_date,
        "confidence":   conf,
    }


def extract(record: dict) -> list[dict]:
    """
    Extract fact cards from a canonical structured record.
    Dispatches by record_type.
    """
    rec_type = (record.get("record_type") or "").lower()
    data     = record.get("data") or {}
    ticker   = (record.get("target_context") or {}).get("ticker") or data.get("ticker", "")
    entity   = (record.get("target_context") or {}).get("entity_name") or ticker or ""

    if rec_type == "institutional_flow":
        return _extract_institutional_flow(record, data)
    elif rec_type == "macro_snapshot":
        return _extract_macro(record, data)
    elif rec_type in ("analyst_estimates", "analyst_consensus"):
        return _extract_analyst(record, data, ticker, entity)
    elif rec_type in ("indian_company_fundamentals", "fundamental_data"):
        return _extract_fundamentals(record, data, entity)
    elif rec_type in ("peer_comparison", "peer_data"):
        return _extract_peers(record, data, ticker, entity)
    elif rec_type in ("corporate_actions", "corporate_action"):
        return _extract_corporate_actions(record, data, ticker, entity)
    elif rec_type == "sec_company_facts":
        return _extract_sec(record, data, ticker, entity)
    elif rec_type == "bulk_block_deals":
        return _extract_bulk_deals(record, data)
    else:
        return []


# ── Per-type extractors ────────────────────────────────────────────────────────

def _extract_institutional_flow(record, data) -> list[dict]:
    facts = []
    fii   = data.get("fii") or {}
    dii   = data.get("dii") or {}
    date  = record.get("data_date", "")[:10]

    if fii.get("net") is not None:
        v = fii["net"]
        facts.append(_fact(record, "institutional_flow_fact",
            f"FII net flow was ₹{v:,.0f} crore on {date}.",
            "fii_net_flow", v, "INR crore", ["FII"], 0.96))
    if dii.get("net") is not None:
        v = dii["net"]
        facts.append(_fact(record, "institutional_flow_fact",
            f"DII net flow was ₹{v:,.0f} crore on {date}.",
            "dii_net_flow", v, "INR crore", ["DII"], 0.96))
    return facts


def _extract_macro(record, data) -> list[dict]:
    facts = []
    field_map = {
        "repo_rate":       ("macro_policy_fact", "repo_rate",      "%",         "RBI", "Repo rate"),
        "gdp_growth":      ("macro_policy_fact", "gdp_growth",     "%",         "India",   "GDP growth"),
        "cpi_inflation":   ("macro_policy_fact", "cpi_inflation",  "%",         "India",   "CPI inflation"),
        "iip_growth":      ("macro_policy_fact", "iip_growth",     "%",         "India",   "IIP growth"),
        "usd_inr":         ("macro_policy_fact", "usd_inr",        "INR",       "USD/INR", "USD/INR rate"),
        "india_vix":       ("macro_policy_fact", "india_vix",      "points",    "NIFTY",   "India VIX"),
        "nifty_pe":        ("macro_policy_fact", "nifty_pe",       "x",         "NIFTY",   "Nifty P/E"),
        "federal_funds_rate": ("macro_policy_fact", "federal_funds_rate", "%",  "US Fed",  "US Fed funds rate"),
        "us_cpi":          ("macro_policy_fact", "us_cpi",         "%",         "US",      "US CPI"),
    }
    for field, (ftype, metric, unit, ent, label) in field_map.items():
        val = data.get(field)
        if val is not None:
            facts.append(_fact(record, ftype,
                f"{label} is {val} {unit}.", metric, val, unit, [ent], 0.95))
    return facts


def _extract_analyst(record, data, ticker, entity) -> list[dict]:
    facts = []
    pt    = data.get("price_targets") or {}
    ee    = data.get("earnings_estimates") or {}
    recs  = data.get("recommendations") or []
    ents  = [entity or ticker]

    if pt.get("mean"):
        facts.append(_fact(record, "analyst_fact",
            f"Mean analyst price target for {ticker} is ₹{pt['mean']:.0f}.",
            "price_target_mean", pt["mean"], "INR", ents))
    if pt.get("number_of_analysts"):
        facts.append(_fact(record, "analyst_fact",
            f"{pt['number_of_analysts']} analysts cover {ticker}.",
            "analyst_count", pt["number_of_analysts"], None, ents))
    if recs:
        latest = recs[-1] if isinstance(recs, list) else {}
        if latest.get("To Grade"):
            facts.append(_fact(record, "analyst_fact",
                f"Analyst consensus rating for {ticker}: {latest['To Grade']}.",
                "analyst_rating", latest["To Grade"], None, ents))
    return facts


def _extract_fundamentals(record, data, entity) -> list[dict]:
    facts = []
    ratios = data.get("key_ratios") or {}
    ents   = [entity]
    ratio_map = {
        "Market Cap":        ("market_cap",      "INR Cr"),
        "P/E":               ("pe_ratio",        "x"),
        "ROE":               ("roe",             "%"),
        "ROCE":              ("roce",            "%"),
        "Debt to equity":    ("debt_to_equity",  "x"),
        "Sales growth":      ("revenue_cagr",    "%"),
        "Profit growth":     ("profit_cagr",     "%"),
    }
    for label, (metric, unit) in ratio_map.items():
        val = ratios.get(label)
        if val is not None:
            facts.append(_fact(record, "earnings_fact",
                f"{entity} {label}: {val} {unit}.", metric, val, unit, ents))
    return facts


def _extract_peers(record, data, ticker, entity) -> list[dict]:
    facts = []
    target = data.get("target") or {}
    ents   = [entity or ticker]
    if target.get("pe"):
        facts.append(_fact(record, "analyst_fact",
            f"{ticker} P/E ratio: {target['pe']}x.", "pe_ratio", target["pe"], "x", ents))
    peers = data.get("peers") or []
    if peers:
        sector_avg = sum(p.get("pe", 0) or 0 for p in peers) / max(1, len(peers))
        if sector_avg:
            facts.append(_fact(record, "analyst_fact",
                f"Sector peer average P/E: {sector_avg:.1f}x.",
                "sector_avg_pe", round(sector_avg, 1), "x", [entity or ticker]))
    return facts


def _extract_corporate_actions(record, data, ticker, entity) -> list[dict]:
    facts = []
    ents  = [entity or ticker]
    for action in (data.get("nse_actions") or []):
        atype   = action.get("purpose") or action.get("series") or "corporate_action"
        ex_date = action.get("exDate") or action.get("exdate") or ""
        facts.append(_fact(record, "corporate_action_fact",
            f"{ticker}: {atype} on {ex_date}.", "corporate_action_type", atype, None, ents))
    return facts


def _extract_sec(record, data, ticker, entity) -> list[dict]:
    facts = []
    ents  = [entity or ticker]
    kf    = data.get("key_financials") or {}
    for metric, val in kf.items():
        if val is not None:
            facts.append(_fact(record, "earnings_fact",
                f"{entity} SEC reported {metric}: {val}.", metric, val, None, ents, 0.92))
    return facts


def _extract_bulk_deals(record, data) -> list[dict]:
    facts = []
    for deal in (data.get("bulk_deals") or []) + (data.get("block_deals") or []):
        ticker = deal.get("symbol") or deal.get("ticker") or ""
        client = deal.get("clientName") or deal.get("client") or "unknown entity"
        qty    = deal.get("quantity") or deal.get("qty")
        txtype = deal.get("buySell") or deal.get("type") or "transaction"
        if ticker:
            text = f"{client} {txtype} {qty or '?'} shares of {ticker} (bulk/block deal)."
            facts.append(_fact(record, "institutional_flow_fact", text,
                "bulk_deal_quantity", qty, "shares", [ticker, client], 0.95))
    return facts
