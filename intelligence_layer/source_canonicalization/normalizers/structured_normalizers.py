"""
intelligence_layer/source_canonicalization/normalizers/structured_normalizers.py — Layer 2

Normalizers for all structured/tabular Layer 1 collectors. Each function
takes the raw collector JSON content and returns a list of
canonical_structured_record dicts.

Covered collectors (design doc §10–20):
    normalize_market_data        → market_data (Phase C)
    normalize_price_history      → price_history (Phase C)
    normalize_screener           → screener_in (Phase C)
    normalize_peer_comparison    → peer_comparison (Phase C)
    normalize_analyst_estimates  → analyst_estimates (Phase C)
    normalize_macro_snapshot     → india_macro, us_macro (Phase A)
    normalize_institutional_flow → fii_dii (Phase A)
    normalize_bulk_deals         → bulk_deals (Phase A)
    normalize_derivatives        → fno_data (Phase A + C)
    normalize_corporate_actions  → corporate_actions (Phase C)
    normalize_sec_filings        → sec_filings (Phase C)

Design doc: docs/system_design_docs/layer_2.md  §10–20
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from intelligence_layer.source_canonicalization.content_fingerprint      import fingerprint
from intelligence_layer.source_canonicalization.source_reliability_tagger import tag_reliability


def _base_record(
    module: str,
    source_name: str,
    record_type: str,
    source_type: str,
    market: str = "india",
    target_context: dict | None = None,
) -> dict:
    rel = tag_reliability(module=module, source_type=source_type)
    return {
        "record_type":    record_type,
        "source_type":    source_type,
        "source_name":    source_name,
        "source_reliability": rel["source_reliability"],
        "reliability_reason": rel["reliability_reason"],
        "market":         market,
        "target_context": target_context or {
            "target_id": None, "target_type": None,
            "ticker": None, "entity_name": None,
        },
    }


def _ticker_ctx(ticker: str, entity_name: str = "") -> dict:
    return {
        "target_id":   None,
        "target_type": "listed_company",
        "ticker":      ticker,
        "entity_name": entity_name or None,
    }


# ── 1. Market data snapshot ───────────────────────────────────────────────────

def normalize_market_data(content: dict, module: str = "market_data") -> list[dict]:
    """Design doc §10 (market_data_normalizer)."""
    ticker = content.get("ticker", "")
    fp = fingerprint(title=f"market_data_{ticker}")
    return [{
        **_base_record(module, "NSE/Yahoo Finance", "market_snapshot",
                       "market_snapshot", target_context=_ticker_ctx(ticker)),
        "collected_at": content.get("fetched_at") or content.get("collected_at") or "",
        "data": {
            "ticker":              ticker,
            "company_name":        content.get("company_name") or content.get("name", ""),
            "price":               content.get("price"),
            "day_change_pct":      content.get("day_change_pct"),
            "volume":              content.get("volume"),
            "market_cap":          content.get("market_cap"),
            "fifty_two_week_high": content.get("fifty_two_week_high") or content.get("52w_high"),
            "fifty_two_week_low":  content.get("fifty_two_week_low") or content.get("52w_low"),
            "sector":              content.get("sector"),
            "industry":            content.get("industry"),
            "pe_ratio":            content.get("pe_ratio") or content.get("pe"),
            "pb_ratio":            content.get("pb_ratio") or content.get("pb"),
        },
        "fingerprint": fp,
    }]


# ── 2. Price history ──────────────────────────────────────────────────────────

def normalize_price_history(content: dict, module: str = "price_history") -> list[dict]:
    """Design doc §11 (price_history_normalizer)."""
    ticker  = content.get("ticker", "")
    history = content.get("history") or content.get("ohlcv") or []
    fp = fingerprint(title=f"price_history_{ticker}")
    return [{
        **_base_record(module, "Yahoo Finance", "price_history",
                       "price_history", target_context=_ticker_ctx(ticker)),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "ticker":   ticker,
            "period":   content.get("period", ""),
            "interval": content.get("interval", "1d"),
            "history":  history,
        },
        "fingerprint": fp,
    }]


# ── 3. Screener fundamentals ──────────────────────────────────────────────────

def normalize_screener(content: dict, module: str = "screener_in") -> list[dict]:
    """Design doc §12 (screener_normalizer)."""
    company_name = content.get("company_name") or content.get("name") or ""
    # Ticker is not in screener output directly — left null, runner will enrich
    fp = fingerprint(title=f"screener_{company_name}")
    return [{
        **_base_record(module, "Screener.in", "indian_company_fundamentals",
                       "fundamental_data",
                       target_context={"target_id": None, "target_type": "listed_company",
                                       "ticker": None, "entity_name": company_name}),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "company_name":         company_name,
            "description":          content.get("description", ""),
            "key_ratios":           content.get("key_ratios") or {},
            "pros":                 content.get("pros") or [],
            "cons":                 content.get("cons") or [],
            "quarterly_results":    content.get("quarterly_results") or [],
            "profit_loss":          content.get("profit_loss") or [],
            "balance_sheet":        content.get("balance_sheet") or [],
            "cash_flow":            content.get("cash_flow") or [],
            "ratios":               content.get("ratios") or [],
            "growth_metrics":       content.get("growth_metrics") or {},
            "shareholding_quarterly": content.get("shareholding_quarterly") or [],
            "shareholding_yearly":  content.get("shareholding_yearly") or [],
        },
        "fingerprint": fp,
    }]


# ── 4. Peer comparison ────────────────────────────────────────────────────────

def normalize_peer_comparison(content: dict, module: str = "peer_comparison") -> list[dict]:
    """Design doc §13 (peer_comparison_normalizer)."""
    ticker = content.get("ticker", "")
    fp = fingerprint(title=f"peer_comparison_{ticker}")
    return [{
        **_base_record(module, "Yahoo Finance / NSE",
                       "peer_comparison", "peer_data",
                       target_context=_ticker_ctx(ticker)),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "ticker":       ticker,
            "sector_index": content.get("sector_index", ""),
            "target":       content.get("target") or {},
            "peers":        content.get("peers") or [],
        },
        "fingerprint": fp,
    }]


# ── 5. Analyst estimates ──────────────────────────────────────────────────────

def normalize_analyst_estimates(content: dict, module: str = "analyst_estimates") -> list[dict]:
    """Design doc §14 (analyst_estimates_normalizer)."""
    ticker = content.get("ticker", "")
    fp = fingerprint(title=f"analyst_estimates_{ticker}")
    return [{
        **_base_record(module, "Yahoo Finance",
                       "analyst_estimates", "analyst_consensus",
                       target_context=_ticker_ctx(ticker)),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "ticker":             ticker,
            "price_targets":      content.get("price_targets") or {},
            "earnings_estimates": content.get("earnings_estimates") or {},
            "revenue_estimates":  content.get("revenue_estimates") or {},
            "earnings_history":   content.get("earnings_history") or [],
            "recommendations":    content.get("recommendations") or [],
            "eps_trend":          content.get("eps_trend") or {},
            "eps_revisions":      content.get("eps_revisions") or {},
        },
        "fingerprint": fp,
    }]


# ── 6. Macro snapshots (India + US) ──────────────────────────────────────────

def normalize_macro_snapshot(content: dict, module: str, market: str = "india") -> list[dict]:
    """Design doc §15 (macro_data_normalizer). Handles india_macro + us_macro."""
    fp = fingerprint(title=f"macro_{market}_{content.get('fetched_at','')}")
    return [{
        **_base_record(module, "NSE / FRED" if market == "india" else "FRED",
                       "macro_snapshot", "macro_snapshot", market=market,
                       target_context={"target_id": None,
                                       "target_type": "market",
                                       "ticker": None,
                                       "entity_name": f"{market.title()} macro"}),
        "collected_at": content.get("fetched_at") or "",
        "data": dict(content),   # preserve all raw fields
        "fingerprint": fp,
    }]


# ── 7. FII / DII institutional flows ─────────────────────────────────────────

def normalize_institutional_flow(content: dict, module: str = "fii_dii") -> list[dict]:
    """Design doc §16 (institutional_activity_normalizer)."""
    fp = fingerprint(title=f"fii_dii_{content.get('date','')}")
    return [{
        **_base_record(module, "NSE",
                       "institutional_flow", "institutional_flow",
                       target_context={"target_id": None,
                                       "target_type": "market",
                                       "ticker": None,
                                       "entity_name": "Indian equity market"}),
        "data_date":    content.get("date") or content.get("fetched_at") or "",
        "collected_at": content.get("fetched_at") or "",
        "freshness":    {"freshness_type": "today_only", "requires_history_sync": True},
        "data": {
            "fii": content.get("fii") or {},
            "dii": content.get("dii") or {},
        },
        "fingerprint": fp,
    }]


# ── 8. Bulk / block deals ─────────────────────────────────────────────────────

def normalize_bulk_deals(content: dict, module: str = "bulk_deals") -> list[dict]:
    """Design doc §17 (bulk_deals_normalizer)."""
    fp = fingerprint(title=f"bulk_deals_{content.get('fetched_at','')}")
    return [{
        **_base_record(module, "NSE",
                       "bulk_block_deals", "bulk_block_deals",
                       target_context={"target_id": None,
                                       "target_type": "market",
                                       "ticker": None,
                                       "entity_name": "NSE bulk/block deals"}),
        "collected_at": content.get("fetched_at") or "",
        "freshness":    {"freshness_type": "today_only", "requires_history_sync": True},
        "data": {
            "bulk_deals":  content.get("bulk_deals") or [],
            "block_deals": content.get("block_deals") or [],
        },
        "fingerprint": fp,
    }]


# ── 9. F&O / derivatives snapshots ───────────────────────────────────────────

def normalize_derivatives(content: dict, module: str = "fno_data") -> list[dict]:
    """Design doc §18 (derivatives_data_normalizer). Handles index + per-ticker F&O."""
    ticker = content.get("ticker") or content.get("symbol") or "NIFTY"
    is_index = ticker.upper() in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
    target_type = "index" if is_index else "listed_company"
    fp = fingerprint(title=f"fno_{ticker}_{content.get('timestamp','')}")
    return [{
        **_base_record(module, "NSE Option Chain",
                       "derivatives_snapshot", "derivatives_snapshot",
                       target_context={"target_id": None, "target_type": target_type,
                                       "ticker": ticker, "entity_name": None}),
        "collected_at": content.get("fetched_at") or content.get("timestamp") or "",
        "freshness":    {"freshness_type": "live_snapshot", "requires_history_sync": True},
        "data": {
            "ticker":           ticker,
            "underlying_value": content.get("underlying_value"),
            "timestamp":        content.get("timestamp", ""),
            "expiry_dates":     content.get("expiry_dates") or [],
            "pcr":              content.get("pcr"),
            "max_pain":         content.get("max_pain"),
            "atm_iv":           content.get("atm_iv") or {},
            "top_oi_strikes":   content.get("top_oi_strikes") or {},
            "option_chain":     content.get("option_chain") or [],
        },
        "fingerprint": fp,
    }]


# ── 10. Corporate actions ─────────────────────────────────────────────────────

def normalize_corporate_actions(content: dict, module: str = "corporate_actions") -> list[dict]:
    """Design doc §19 (corporate_action_normalizer)."""
    ticker = content.get("ticker", "")
    fp = fingerprint(title=f"corporate_actions_{ticker}")
    return [{
        **_base_record(module, "NSE / Yahoo Finance",
                       "corporate_actions", "corporate_action",
                       target_context=_ticker_ctx(ticker)),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "ticker":       ticker,
            "nse_actions":  content.get("nse_actions") or [],
            "yf_dividends": content.get("yf_dividends") or [],
            "yf_splits":    content.get("yf_splits") or [],
        },
        "fingerprint": fp,
    }]


# ── 11. SEC filings ───────────────────────────────────────────────────────────

def normalize_sec_filings(content: dict, module: str = "sec_filings") -> list[dict]:
    """Design doc §20 (sec_filing_normalizer)."""
    ticker       = content.get("ticker", "")
    company_name = content.get("company_name", "")
    cik          = content.get("cik", "")
    fp = fingerprint(title=f"sec_{ticker}_{cik}")
    records: list[dict] = []

    # Structured record for XBRL financials + filing metadata
    records.append({
        **_base_record(module, "SEC EDGAR",
                       "sec_company_facts", "regulatory_filing", market="us",
                       target_context={"target_id": None, "target_type": "listed_company",
                                       "ticker": ticker, "entity_name": company_name}),
        "collected_at": content.get("fetched_at") or "",
        "data": {
            "ticker":          ticker,
            "cik":             cik,
            "company_name":    company_name,
            "key_financials":  content.get("key_financials") or {},
            "recent_filings":  content.get("recent_filings") or {},
        },
        "fingerprint": fp,
    })
    return records
