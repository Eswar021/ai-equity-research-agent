"""
L7 Targeted Deep Dive — collects market data, fundamentals, ownership, and filings for
each deep-dive target from L6. Resolves commodity/sector targets to NSE tickers first.

Reads:
    output/{date}/run_manifest.json              → layer_7 config
    output/{date}/L6/selected_targets.json       → deep_dive bucket targets
    output/{date}/L1/raw_records.json            → most recent india_macro + fii_dii

Writes:
    output/{date}/L7/target_evidence_bundles.json → one bundle per target (consumed by L8)
    output/{date}/L7/summary.json                 → collection stats

LLM: no

Module execution order:
    1. Load manifest → layer_7 config
    2. Load L6/selected_targets.json → filter to bucket="deep_dive"
    3. Load L1/raw_records.json → extract macro_context
    4. Load NSE symbols (db/nse_equity_cache.json, auto-refresh every 7d)
    5. Create NSE session for corporate API calls
    6. For each target:
       a. RESOLVE: commodity/sector keyword → tickers; company → fuzzy lookup
       b. COLLECT per ticker (yfinance parallel, screener serial, NSE parallel):
          market_data.fetch → price, RSI, DMAs, volume, analyst consensus
          screener_scraper.fetch → fundamentals, quarterly_trend, ownership, peers
          nse_collector.fetch → corporate_actions, recent_filings
       c. ASSEMBLE: determine collection_status per ticker, build ticker_data
    7. Write L7/target_evidence_bundles.json
    8. Write L7/summary.json

Usage:
    python -m src.pipeline.L7_deep_dive.runner              # today
    python -m src.pipeline.L7_deep_dive.runner --date 2026-05-17
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, load_manifest, output_dir, today

from . import market_data as md
from . import nse_collector as nse
from . import screener_scraper as screener
from .nse_symbols import load_nse_symbols
from .target_resolver import resolve


# ---------------------------------------------------------------------------
# Macro context
# ---------------------------------------------------------------------------

def _extract_macro(records: list[dict]) -> dict:
    """Pull most recent india_macro + fii_dii snapshot for bundle context."""
    india = next((r for r in reversed(records) if r.get("source") == "india_macro"), None)
    fii   = next((r for r in reversed(records) if r.get("source") == "fii_dii"), None)

    ctx: dict = {}

    if fii:
        content = fii.get("content", "")
        m = re.search(r"FII net=(-?[\d.]+)\s*cr", content)
        if m:
            ctx["fii_net_cr"] = float(m.group(1))
        m = re.search(r"DII net=(-?[\d.]+)\s*cr", content)
        if m:
            ctx["dii_net_cr"] = float(m.group(1))

    if india:
        content = india.get("content", "")
        m = re.search(r"Change=(-?[\d.]+)%", content)
        if m:
            ctx["nifty_change_pct"] = float(m.group(1))
        m = re.search(r"Breadth:\s*(\w+)", content)
        if m:
            ctx["market_breadth"] = m.group(1)

    return ctx


# ---------------------------------------------------------------------------
# Per-ticker collection
# ---------------------------------------------------------------------------

def _collect_ticker(
    ticker: str,
    nse_session,
    cfg: dict,
) -> dict:
    """Collect all data for one NSE ticker. Never raises — marks status on failure."""
    delay   = cfg.get("screener_request_delay_s", 1.5)
    peers_n = cfg.get("max_peers", 4)
    history = cfg.get("price_history_days", 200)
    max_act = cfg.get("max_corporate_actions", 3)
    max_fil = cfg.get("max_recent_filings", 2)

    price_data = md.fetch(ticker, history_days=history)
    scrape     = screener.fetch(ticker, request_delay_s=delay, max_peers=peers_n)
    nse_data   = nse.fetch(ticker, nse_session, max_actions=max_act, max_filings=max_fil)

    has_price   = price_data is not None
    has_scrape  = scrape is not None

    if has_price and has_scrape:
        status = "complete"
    elif has_price or has_scrape:
        status = "partial"
    else:
        status = "failed"

    result: dict = {"collection_status": status}

    if has_price:
        result["price"]             = price_data["price"]
        result["analyst_consensus"] = price_data.get("analyst_consensus")
    if has_scrape:
        result["fundamentals"]    = scrape["fundamentals"]
        result["quarterly_trend"] = scrape["quarterly_trend"]
        result["ownership"]       = scrape["ownership"]
        result["peers"]           = scrape["peers"]

    result["corporate_actions"] = nse_data["corporate_actions"]
    result["recent_filings"]    = nse_data["recent_filings"]

    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l7_cfg   = manifest.get("layer_7")
    if not l7_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_7' key — re-run L0 first")

    out_dir  = output_dir(date) / "L7"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load L6 targets — deep_dive bucket only
    l6_path = output_dir(date) / "L6" / "selected_targets.json"
    if not l6_path.exists():
        raise FileNotFoundError(f"L6 output not found: {l6_path} — run L6 first")

    l6_data  = json.loads(l6_path.read_text())
    targets  = [t for t in l6_data.get("targets", []) if t.get("bucket") == "deep_dive"]
    print(f"  L7: {len(targets)} deep-dive targets in")

    # Macro context from L1
    l1_path = output_dir(date) / "L1" / "raw_records.json"
    macro_context: dict = {}
    if l1_path.exists():
        l1_data   = json.loads(l1_path.read_text())
        l1_records = l1_data.get("records", l1_data) if isinstance(l1_data, dict) else l1_data
        macro_context = _extract_macro(l1_records)
        macro_context["regime"] = l6_data.get("market_regime", "uncertain")

    # NSE symbols for fuzzy ticker lookup
    refresh_days = l7_cfg.get("nse_symbols_refresh_days", 7)
    symbols      = load_nse_symbols(refresh_days=refresh_days)
    print(f"  NSE symbols loaded: {len(symbols)} stocks")

    # Config-driven alias and material-type tables (no code change needed to extend)
    aliases        = l7_cfg.get("company_aliases", {})
    material_types = set(l7_cfg.get("material_announcement_types", []))

    # One shared NSE session for all API calls
    nse_session = nse.make_session()

    # Resolve + collect
    run_start = time.time()
    stats = {"total_tickers": 0, "yfinance_success": 0, "screener_success": 0, "nse_success": 0}

    bundles: list[dict] = []
    max_workers = l7_cfg.get("max_workers", 4)

    for target in targets:
        rtype, tickers, note = resolve(target, symbols, l7_cfg, aliases)

        if rtype == "unresolved":
            print(f"  [UNRESOLVED] {target['target_entity']:35s}  — {note}")
            bundles.append({
                **_target_meta(target),
                "resolution_type":    "unresolved",
                "resolved_tickers":   [],
                "resolution_note":    note,
                "macro_context":      macro_context,
                "ticker_data":        {},
            })
            continue

        print(f"  [{rtype:9s}] {target['target_entity']:35s} → {tickers}")

        # Collect yfinance + NSE data in parallel; screener must be serial (rate-limited)
        ticker_data: dict[str, dict] = {}

        # Phase A: yfinance + NSE in parallel
        def _collect_yf_nse(t: str) -> tuple[str, dict, dict]:
            price = md.fetch(t, history_days=l7_cfg.get("price_history_days", 200))
            ndata = nse.fetch(t, nse_session,
                              max_actions=l7_cfg.get("max_corporate_actions", 3),
                              max_filings=l7_cfg.get("max_recent_filings", 2),
                              material_types=material_types)
            return t, price, ndata

        yf_results: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_collect_yf_nse, t): t for t in tickers}
            for fut in as_completed(futures):
                t, price, ndata = fut.result()
                yf_results[t]   = (price, ndata)

        # Phase B: screener serial (rate-limited)
        scrape_results: dict[str, dict | None] = {}
        for t in tickers:
            scrape_results[t] = screener.fetch(
                t,
                request_delay_s=l7_cfg.get("screener_request_delay_s", 1.5),
                max_peers=l7_cfg.get("max_peers", 4),
            )

        # Assemble per-ticker
        for t in tickers:
            price, ndata   = yf_results.get(t, (None, {"corporate_actions": [], "recent_filings": []}))
            scrape         = scrape_results.get(t)
            has_price      = price is not None
            has_scrape     = scrape is not None

            if has_price and has_scrape:
                status = "complete"
            elif has_price or has_scrape:
                status = "partial"
            else:
                status = "failed"

            entry: dict = {"collection_status": status}
            if has_price:
                entry["price"]             = price["price"]
                entry["analyst_consensus"] = price.get("analyst_consensus")
                stats["yfinance_success"] += 1
            if has_scrape:
                entry["fundamentals"]    = scrape["fundamentals"]
                entry["quarterly_trend"] = scrape["quarterly_trend"]
                entry["ownership"]       = scrape["ownership"]
                entry["peers"]           = scrape["peers"]
                stats["screener_success"] += 1
            entry["corporate_actions"] = ndata.get("corporate_actions", [])
            entry["recent_filings"]    = ndata.get("recent_filings", [])
            if ndata.get("corporate_actions") is not None:
                stats["nse_success"] += 1

            ticker_data[t] = entry
            stats["total_tickers"] += 1

        bundles.append({
            **_target_meta(target),
            "resolution_type":  rtype,
            "resolved_tickers": tickers,
            "resolution_note":  note,
            "macro_context":    macro_context,
            "ticker_data":      ticker_data,
        })

    # Write outputs
    out_path = out_dir / "target_evidence_bundles.json"
    out_path.write_text(json.dumps({
        "run_date":        date,
        "run_id":          l6_data.get("run_id", ""),
        "market_regime":   l6_data.get("market_regime", "uncertain"),
        "total_targets":   len(bundles),
        "collection_stats": stats,
        "bundles":         bundles,
    }, indent=2, ensure_ascii=False))

    elapsed = round(time.time() - run_start, 1)
    complete = sum(1 for b in bundles if any(v.get("collection_status") == "complete" for v in b.get("ticker_data", {}).values()))
    partial  = sum(1 for b in bundles if any(v.get("collection_status") == "partial"  for v in b.get("ticker_data", {}).values()))
    failed   = sum(1 for b in bundles if all(v.get("collection_status") == "failed"   for v in b.get("ticker_data", {}).values()) and b.get("ticker_data"))
    unres    = sum(1 for b in bundles if b.get("resolution_type") == "unresolved")

    (out_dir / "summary.json").write_text(json.dumps({
        "date":                   date,
        "market_regime":          l6_data.get("market_regime", "uncertain"),
        "total_targets":          len(bundles),
        "complete":               complete,
        "partial":                partial,
        "failed":                 failed,
        "unresolved":             unres,
        "total_tickers":          stats["total_tickers"],
        "yfinance_success":       stats["yfinance_success"],
        "screener_success":       stats["screener_success"],
        "nse_success":            stats["nse_success"],
        "nse_symbols_count":      len(symbols),
        "elapsed_s":              elapsed,
    }, indent=2))

    print(f"\n  L7 done in {elapsed}s: {len(bundles)} bundles, "
          f"{stats['total_tickers']} tickers collected "
          f"(screener: {stats['screener_success']}, yfinance: {stats['yfinance_success']})")
    print(f"  → {out_path}")
    return out_path


def _target_meta(t: dict) -> dict:
    return {
        "target_id":               t.get("target_id", ""),
        "target_entity":           t.get("target_entity", ""),
        "bucket":                  t.get("bucket", ""),
        "score":                   t.get("score", 0),
        "hypothesis":              t.get("hypothesis", ""),
        "time_horizon":            t.get("time_horizon", ""),
        "strength":                t.get("strength", ""),
        "deep_dive_questions":     t.get("deep_dive_questions", []),
        "invalidating_conditions": t.get("invalidating_conditions", []),
        "beneficiaries":           t.get("beneficiaries", []),
        "group_type":              t.get("group_type", ""),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
