"""
run_phase_c.py — Phase C: Company Deep Dive

For each candidate from Phase B, runs all per-ticker data fetchers:
  C1. market_data        — current price + sector (always first)
  C2. price_history      — 1-year OHLCV
  C3. screener_in        — 10-year fundamentals (scraped)
  C4. peer_comparison    — sector peers
  C5. analyst_estimates  — consensus estimates & price targets
  C6. exchange_filings   — NSE corporate announcements (material only)
  C7. filing_docs        — earnings call transcripts + presentations
  C8. corporate_actions  — dividends, splits, buybacks

After all tickers: applies sector bonus from regime (B1) and re-ranks.
Saves candidates_{date}_final.json with sector-adjusted scores.

Usage:
  python run_phase_c.py                      # full run, all candidates
  python run_phase_c.py --skip-screener      # skip screener.in (slow scrape)
  python run_phase_c.py --ticker BHEL.NS     # single ticker test
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from config.paths import CANDIDATES_OUTPUT_DIR, MARKET_REGIME_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

# yfinance sector labels → regime sector keys (from B1 market_regime)
_SECTOR_ALIASES: dict[str, list[str]] = {
    "it":      ["technology", "information technology", "software", "it services"],
    "banking": ["financial services", "banking", "bank", "nbfc"],
    "pharma":  ["healthcare", "pharma", "pharmaceutical", "biotechnology"],
    "fmcg":    ["consumer defensive", "consumer staples", "fmcg"],
    "auto":    ["consumer cyclical", "auto", "automobile"],
    "metal":   ["basic materials", "metal", "mining", "steel"],
    "realty":  ["real estate", "realty"],
    "infra":   ["industrials", "infrastructure", "construction", "capital goods"],
    "oil_gas": ["energy", "oil", "gas", "petroleum"],
}

_SECTOR_BONUS   =  4.0
_SECTOR_PENALTY = -3.0
_MODULE_DELAY   =  1.5   # seconds between module calls for one ticker
_TICKER_DELAY   =  2.0   # extra pause between tickers


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(label: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        name   = Path(result).name if isinstance(result, str) else "ok"
        print(f"    ✓  {label}: {name}")
        return result
    except Exception as e:
        print(f"    ✗  {label}: {e}")
        return None


def _screener_url(ticker: str) -> str:
    symbol = ticker.split(".")[0]
    return f"https://www.screener.in/company/{symbol}/consolidated/"


def _latest_file(dir_path: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(dir_path.glob(pattern))
    return files[-1] if files else None


def _load_json(path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _map_sector(yf_sector: str | None) -> str | None:
    if not yf_sector:
        return None
    sl = yf_sector.lower()
    for key, aliases in _SECTOR_ALIASES.items():
        if any(alias in sl or sl in alias for alias in aliases):
            return key
    return None


# ── Sector re-scoring ─────────────────────────────────────────────────────────

def _apply_sector_scores(
    candidates: list[dict],
    regime:     dict,
    sector_map: dict[str, str],
) -> list[dict]:
    favored = set(regime.get("sectors", {}).get("favored", []))
    avoid   = set(regime.get("sectors", {}).get("avoid",   []))

    for c in candidates:
        ticker     = c["ticker"]
        yf_sector  = sector_map.get(ticker, "")
        sector_key = _map_sector(yf_sector)

        adj = 0.0
        if sector_key in favored:
            adj = _SECTOR_BONUS
        elif sector_key in avoid:
            adj = _SECTOR_PENALTY

        c["sector"]      = yf_sector or "unknown"
        c["sector_key"]  = sector_key
        c["sector_adj"]  = adj
        c["final_score"] = round(c.get("score", c.get("final_score", 0)) + adj, 2)

    candidates.sort(key=lambda c: abs(c["final_score"]), reverse=True)
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    return candidates


# ── Main ──────────────────────────────────────────────────────────────────────

def run(tickers: list[str] | None = None, skip_screener: bool = False) -> dict:
    start = datetime.now(_IST)
    print(f"\n{'═'*60}")
    print(f"  Phase C — Company Deep Dive")
    print(f"  {start.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"{'═'*60}")

    # ── Load Phase B outputs ──────────────────────────────────────────────────
    cand_file = _latest_file(CANDIDATES_OUTPUT_DIR)
    if not cand_file:
        print("  ✗  No candidates file found — run Phase B first")
        return {}

    cand_data  = _load_json(cand_file)
    candidates = cand_data.get("candidates", [])

    regime_file = _latest_file(MARKET_REGIME_OUTPUT_DIR)
    regime      = _load_json(regime_file) if regime_file else {}

    run_tickers = tickers or [c["ticker"] for c in candidates]

    print(f"\n  Candidates file  : {cand_file.name}")
    print(f"  Market posture   : {regime.get('market_posture', '?').upper()}")
    print(f"  Tickers to run   : {len(run_tickers)}")
    print(f"  Favoured sectors : {regime.get('sectors', {}).get('favored', [])}")
    print(f"  Avoid sectors    : {regime.get('sectors', {}).get('avoid', [])}")
    if skip_screener:
        print(f"  Screener.in      : SKIPPED")

    # ── Lazy module imports ───────────────────────────────────────────────────
    from context_ext_layer.phaseC_CDD.market_data       import save_stock
    from context_ext_layer.phaseC_CDD.price_history     import save_history
    from context_ext_layer.phaseC_CDD.screener_in       import save_company
    from context_ext_layer.phaseC_CDD.peer_comparison   import save_peer_comparison
    from context_ext_layer.phaseC_CDD.analyst_estimates import save_analyst_estimates
    from context_ext_layer.phaseC_CDD.exchange_filings  import save_announcements
    from context_ext_layer.phaseC_CDD.filing_docs       import save_filing_docs
    from context_ext_layer.phaseC_CDD.corporate_actions import save_corporate_actions

    # ── Per-ticker loop ───────────────────────────────────────────────────────
    sector_map:     dict[str, str]  = {}
    ticker_results: dict[str, dict] = {}

    for i, ticker in enumerate(run_tickers, 1):
        pad = "─" * max(0, 44 - len(ticker))
        print(f"\n── {i}/{len(run_tickers)}  {ticker}  {pad}")

        res = {}

        # C1: market data — run first so we get the sector
        res["market_data"] = _run("Market data", save_stock, ticker)
        if res["market_data"]:
            md = _load_json(res["market_data"])
            sector_map[ticker] = md.get("sector", "")
            print(f"       sector: {sector_map[ticker] or '—'}"
                  f"  price: {md.get('price', '?')}"
                  f"  mktcap: {md.get('market_cap', '?')}")
        time.sleep(_MODULE_DELAY)

        # C2: price history (1 year)
        res["price_history"] = _run("Price history (1y)", save_history, ticker, "1y")
        time.sleep(_MODULE_DELAY)

        # C3: screener.in (optional — slowest, scrapes website)
        if not skip_screener:
            res["screener_in"] = _run("Screener.in", save_company, _screener_url(ticker))
            time.sleep(_MODULE_DELAY)

        # C4: peer comparison
        res["peer_comparison"] = _run("Peer comparison", save_peer_comparison, ticker)
        time.sleep(_MODULE_DELAY)

        # C5: analyst estimates
        res["analyst_estimates"] = _run("Analyst estimates", save_analyst_estimates, ticker)
        time.sleep(_MODULE_DELAY)

        # C6: NSE announcements (material events only)
        res["exchange_filings"] = _run("Exchange filings", save_announcements, ticker, 50, True)
        time.sleep(_MODULE_DELAY)

        # C7: concall transcripts + investor presentations
        res["filing_docs"] = _run("Filing docs", save_filing_docs, ticker, 4, 2)
        time.sleep(_MODULE_DELAY)

        # C8: corporate actions (dividends, splits, buybacks)
        res["corporate_actions"] = _run("Corporate actions", save_corporate_actions, ticker)

        ticker_results[ticker] = res
        succeeded = sum(1 for v in res.values() if v is not None)
        print(f"    → {succeeded}/{len(res)} modules OK")
        time.sleep(_TICKER_DELAY)

    # ── Sector re-scoring ─────────────────────────────────────────────────────
    print(f"\n── Sector re-scoring ────────────────────────────────────")
    print(f"  {'Rank':4}  {'Ticker':20}  {'Score':7}  {'Adj':5}  {'Final':7}  Sector")
    print(f"  {'─'*65}")

    candidates = _apply_sector_scores(candidates, regime, sector_map)

    for c in candidates:
        adj_s   = f"{c['sector_adj']:+.0f}" if c["sector_adj"] != 0 else "  — "
        print(f"  {c['rank']:4}  {c['ticker']:20}  {c.get('score',0):+7.1f}  "
              f"{adj_s:5}  {c['final_score']:+7.1f}  {c.get('sector','?')}")

    # ── Save final candidates ─────────────────────────────────────────────────
    CANDIDATES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today      = datetime.now(_IST).strftime("%Y-%m-%d")
    final_file = CANDIDATES_OUTPUT_DIR / f"candidates_{today}_final.json"

    final_output = {
        **cand_data,
        "phase_c_run_at":   datetime.now(_IST).isoformat(),
        "sector_map":       sector_map,
        "candidates":       candidates,
        "total_candidates": len(candidates),
    }
    final_file.write_text(json.dumps(final_output, ensure_ascii=False, indent=2))

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now(_IST) - start).seconds
    print(f"\n{'═'*60}")
    print(f"  Phase C complete — {elapsed}s")
    print(f"  Tickers processed : {len(run_tickers)}")
    print(f"  Final candidates  → {final_file.name}")
    print(f"{'═'*60}\n")

    return {
        "candidates_final_file": str(final_file),
        "sector_map":            sector_map,
        "ticker_results":        ticker_results,
    }


if __name__ == "__main__":
    skip_screener = "--skip-screener" in sys.argv

    single = None
    for arg in sys.argv[1:]:
        if arg.startswith("--ticker="):
            single = [arg.split("=", 1)[1]]
        elif arg == "--ticker" and sys.argv.index(arg) + 1 < len(sys.argv):
            single = [sys.argv[sys.argv.index(arg) + 1]]

    run(tickers=single, skip_screener=skip_screener)
