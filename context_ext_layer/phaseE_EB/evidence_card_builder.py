"""
context_ext_layer/phaseE_EB/evidence_card_builder.py  —  Phase E, Layer 5

Per ticker, aggregates ALL upstream data into one structured "evidence card":
  - Market regime context (Phase B output)
  - Per-ticker signals + key claims with source URLs (Phase B candidates)
  - Phase C deep dive: price/sector, 1y return/drawdown/52w-high%, fundamentals,
    peer comparison, analyst consensus, recent material filings, corporate actions
  - Portfolio flag (held / watchlisted / avoided / none)
  - Computed features: price_vs_52w_high_pct, sentiment_score, signal_density

Pure Python — no LLM. Deterministic. Output is the input to the analyst (Phase F).

Inputs : output/{date}/phaseB/market_regime/, candidates/, phaseC/*/
Output : output/{date}/phaseE/evidence_cards/{TICKER}.json

Standalone test:
  python context_ext_layer/phaseE_EB/evidence_card_builder.py [--ticker BHEL.NS]
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    MARKET_REGIME_OUTPUT_DIR, CANDIDATES_OUTPUT_DIR,
    MARKET_DATA_OUTPUT_DIR, SCREENER_IN_OUTPUT_DIR,
    PEER_COMPARISON_OUTPUT_DIR, ANALYST_ESTIMATES_OUTPUT_DIR,
    EXCHANGE_FILINGS_OUTPUT_DIR, CORPORATE_ACTIONS_OUTPUT_DIR,
    EVIDENCE_CARDS_DIR,
)
from context_ext_layer.utils.portfolio import portfolio_flag, holding_details

_IST = timezone(timedelta(hours=5, minutes=30))

# Sentiment/severity weights — used to compute a single sentiment_score per ticker
_SEV_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}
_SEN_SIGN   = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}

_RECENT_FILINGS_LIMIT     = 5
_RECENT_CORP_ACTIONS_LIMIT = 5
_KEY_CLAIMS_LIMIT          = 5


# ── File-locator helpers ──────────────────────────────────────────────────────

def _ticker_root(ticker: str) -> str:
    """BHEL.NS → BHEL ; HDFCBANK.NS → HDFCBANK"""
    return ticker.replace(".NS", "").replace(".BO", "")


def _ns_root(ticker: str) -> str:
    """BHEL.NS → BHEL_NS (filename pattern used by market_data + price_history)"""
    return _ticker_root(ticker) + "_NS"


def _latest_match(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def _load_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _slugify_company(name: str) -> str:
    """Match the slug used by save_company in screener_in.py."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


# ── Per-module loaders ────────────────────────────────────────────────────────

def _load_market_data(ticker: str) -> dict:
    return _load_json(_latest_match(MARKET_DATA_OUTPUT_DIR,
                                     f"{_ns_root(ticker)}_2*.json"))


def _load_price_history(ticker: str) -> dict:
    return _load_json(_latest_match(MARKET_DATA_OUTPUT_DIR,
                                     f"{_ns_root(ticker)}_history_*.json"))


def _load_peer_comparison(ticker: str) -> dict:
    return _load_json(_latest_match(PEER_COMPARISON_OUTPUT_DIR,
                                     f"{_ticker_root(ticker)}_peers_*.json"))


def _load_analyst_estimates(ticker: str) -> dict:
    return _load_json(_latest_match(ANALYST_ESTIMATES_OUTPUT_DIR,
                                     f"{_ticker_root(ticker)}_analyst_estimates_*.json"))


def _load_exchange_filings(ticker: str) -> dict:
    return _load_json(_latest_match(EXCHANGE_FILINGS_OUTPUT_DIR,
                                     f"{_ticker_root(ticker)}_announcements_*.json"))


def _load_corporate_actions(ticker: str) -> dict:
    return _load_json(_latest_match(CORPORATE_ACTIONS_OUTPUT_DIR,
                                     f"{_ticker_root(ticker)}_corporate_actions_*.json"))


_screener_index_cache: dict[str, Path] | None = None

def _build_screener_index() -> dict[str, Path]:
    """Map slugified company name → screener.in JSON file."""
    global _screener_index_cache
    if _screener_index_cache is not None:
        return _screener_index_cache
    index: dict[str, Path] = {}
    if SCREENER_IN_OUTPUT_DIR.exists():
        for f in SCREENER_IN_OUTPUT_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                name = data.get("company_name", "")
                if name:
                    index[_slugify_company(name)] = f
            except Exception:
                continue
    _screener_index_cache = index
    return index


def _load_screener(company_name: str) -> dict:
    if not company_name:
        return {}
    idx = _build_screener_index()
    slug = _slugify_company(company_name)
    # exact slug match first
    if slug in idx:
        return _load_json(idx[slug])
    # fallback: any indexed slug that starts with the first 6 chars of the company slug
    if len(slug) >= 6:
        for k, path in idx.items():
            if k.startswith(slug[:6]) or slug.startswith(k[:6]):
                return _load_json(path)
    return {}


# ── Feature engineering helpers ───────────────────────────────────────────────

def _pct(numerator, denominator, ndigits: int = 2) -> float | None:
    try:
        if denominator in (0, None):
            return None
        return round(100.0 * (numerator / denominator), ndigits)
    except Exception:
        return None


def _max_drawdown_pct(history: list[dict]) -> float | None:
    if not history:
        return None
    peak = 0.0
    max_dd = 0.0
    for row in history:
        c = row.get("close")
        if c is None:
            continue
        if c > peak:
            peak = c
        if peak > 0:
            dd = (c - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return round(100.0 * max_dd, 2) if peak > 0 else None


def _strip_pct(s) -> float | None:
    if s in (None, "", "—"):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).replace("%", "").strip())
    except Exception:
        return None


def _strip_money(s) -> float | None:
    if s in (None, "", "—"):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        cleaned = str(s).replace("₹", "").replace(",", "").replace(" Cr.", "").replace("Cr", "").strip()
        return float(cleaned)
    except Exception:
        return None


def _peer_metrics(peer_data: dict) -> dict:
    """Compute peer-relative position: median P/E, ROE, growth across peers."""
    peers = peer_data.get("peers", []) or []
    if not peers:
        return {}

    def _med(key):
        vals = [p.get(key) for p in peers if isinstance(p.get(key), (int, float))]
        if not vals:
            return None
        vals.sort()
        n = len(vals)
        return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 2)

    return {
        "peer_count":        len(peers),
        "peer_median_pe":    _med("trailingPE"),
        "peer_median_roe":   _med("returnOnEquity"),
        "peer_median_growth": _med("revenueGrowth"),
    }


def _analyst_consensus(estimates: dict) -> dict:
    """Boil recommendations[period=0m] down to a single rating + n_analysts."""
    pt = estimates.get("price_targets", {}) or {}
    recs = estimates.get("recommendations", []) or []
    current = next((r for r in recs if r.get("period") == "0m"), {})

    sb = current.get("strong_buy", 0) or 0
    b  = current.get("buy", 0) or 0
    h  = current.get("hold", 0) or 0
    s  = current.get("sell", 0) or 0
    ss = current.get("strong_sell", 0) or 0
    n_analysts = sb + b + h + s + ss

    if n_analysts == 0:
        rating = None
    else:
        score = (sb * 2 + b * 1 + s * -1 + ss * -2) / n_analysts
        if score >= 1.0:   rating = "STRONG_BUY"
        elif score >= 0.3: rating = "BUY"
        elif score > -0.3: rating = "HOLD"
        elif score > -1.0: rating = "SELL"
        else:              rating = "STRONG_SELL"

    return {
        "rating":              rating,
        "n_analysts":          n_analysts,
        "target_mean":         pt.get("target_mean"),
        "target_upside_pct":   pt.get("upside_to_mean_pct"),
        "current_price":       pt.get("current_price"),
        "buy_count":           sb + b,
        "hold_count":          h,
        "sell_count":          s + ss,
    }


def _signal_summary(candidate: dict) -> dict:
    """Compute sentiment_score, signal_density, key claims with URLs from a candidate entry."""
    key_signals = candidate.get("key_signals", []) or []
    sentiment_score = 0.0
    for s in key_signals:
        sev  = _SEV_WEIGHT.get(s.get("severity", "low"), 1.0)
        sgn  = _SEN_SIGN.get(s.get("sentiment", "neutral"), 0.0)
        sentiment_score += sev * sgn

    source_count = candidate.get("source_count", 0) or 0
    signal_count = candidate.get("signal_count", 0) or 0
    density = round(signal_count / source_count, 2) if source_count else 0.0

    claims = [{
        "key_claim":  s.get("key_claim", ""),
        "source":     s.get("source", ""),
        "url":        s.get("item_url", ""),
        "severity":   s.get("severity", ""),
        "sentiment":  s.get("sentiment", ""),
        "event_type": s.get("event_type", ""),
    } for s in key_signals[:_KEY_CLAIMS_LIMIT]]

    return {
        "score":           candidate.get("score", 0),
        "final_score":     candidate.get("final_score", 0),
        "signal_count":    signal_count,
        "source_count":    source_count,
        "sources":         candidate.get("sources", []),
        "event_types":     candidate.get("event_types", []),
        "sentiment_score": round(sentiment_score, 2),
        "signal_density":  density,
        "key_claims":      claims,
        "proxy_links":     candidate.get("proxy_links", []),
        "bulk_deal":       candidate.get("bulk_deal"),
    }


# ── Main: build one evidence card ─────────────────────────────────────────────

def build_evidence_card(candidate: dict, regime: dict) -> dict:
    """Aggregate all upstream data for one ticker into a single evidence card dict."""
    ticker  = candidate["ticker"]
    company = candidate.get("company") or _ticker_root(ticker)

    md  = _load_market_data(ticker)
    ph  = _load_price_history(ticker)
    pc  = _load_peer_comparison(ticker)
    ae  = _load_analyst_estimates(ticker)
    ef  = _load_exchange_filings(ticker)
    ca  = _load_corporate_actions(ticker)
    sc  = _load_screener(company)

    data_gaps = []
    for label, val in [("market_data", md), ("price_history", ph),
                       ("peer_comparison", pc), ("analyst_estimates", ae),
                       ("exchange_filings", ef), ("corporate_actions", ca),
                       ("screener_in", sc)]:
        if not val:
            data_gaps.append(label)

    # Price & technical features
    price        = md.get("price")
    high_52w     = md.get("52w_high")
    low_52w      = md.get("52w_low")
    history_rows = ph.get("history", []) or []

    fundamentals = {
        "price":                  price,
        "sector":                 md.get("sector"),
        "industry":               md.get("industry"),
        "market_cap":             md.get("market_cap"),
        "52w_high":               high_52w,
        "52w_low":                low_52w,
        "price_vs_52w_high_pct":  _pct((price - high_52w), high_52w) if (price and high_52w) else None,
        "1y_return_pct":          md.get("return_1y"),
        "1m_return_pct":          md.get("return_1m"),
        "max_drawdown_1y_pct":    _max_drawdown_pct(history_rows),
        # From screener.in
        "stock_pe":               _strip_pct(sc.get("key_ratios", {}).get("Stock P/E")),
        "roe_pct":                _strip_pct(sc.get("key_ratios", {}).get("ROE")),
        "roce_pct":               _strip_pct(sc.get("key_ratios", {}).get("ROCE")),
        "dividend_yield_pct":     _strip_pct(sc.get("key_ratios", {}).get("Dividend Yield")),
        "revenue_cagr_5y_pct":    _strip_pct(sc.get("growth_metrics", {}).get("Compounded Sales Growth", {}).get("5 Years:")),
        "profit_cagr_5y_pct":     _strip_pct(sc.get("growth_metrics", {}).get("Compounded Profit Growth", {}).get("5 Years:")),
        "stock_price_cagr_5y_pct": _strip_pct(sc.get("growth_metrics", {}).get("Stock Price CAGR", {}).get("5 Years:")),
        "screener_pros":          sc.get("pros", []),
        "screener_cons":          sc.get("cons", []),
    }

    # Recent filings: top N most recent material announcements
    announcements = ef.get("announcements", []) or []
    recent_filings = [{
        "date":     a.get("date", ""),
        "type":     a.get("type", ""),
        "subject":  (a.get("subject", "") or "")[:240],
        "url":      a.get("attachment_url", ""),
    } for a in announcements[:_RECENT_FILINGS_LIMIT]]

    # Recent corporate actions: top N from NSE list
    nse_actions = ca.get("nse_actions", []) or []
    recent_actions = [{
        "purpose":     a.get("purpose", ""),
        "ex_date":     a.get("ex_date", ""),
        "record_date": a.get("record_date", ""),
    } for a in nse_actions[:_RECENT_CORP_ACTIONS_LIMIT]]

    flag = portfolio_flag(ticker)
    holding = holding_details(ticker) if flag == "held" else None

    return {
        "ticker":           ticker,
        "company":          company,
        "generated_at":     datetime.now(_IST).isoformat(),
        "rank":             candidate.get("rank"),
        "portfolio_flag":   flag,
        "holding":          holding,

        "regime": {
            "posture":         regime.get("market_posture", "unknown"),
            "favored_sectors": regime.get("sectors", {}).get("favored", []),
            "avoid_sectors":   regime.get("sectors", {}).get("avoid", []),
            "signals":         regime.get("signals", {}),
        },

        "signals":          _signal_summary(candidate),
        "fundamentals":     fundamentals,
        "peer_metrics":     _peer_metrics(pc),
        "analyst_consensus": _analyst_consensus(ae),
        "recent_filings":   recent_filings,
        "recent_corporate_actions": recent_actions,
        "data_gaps":        data_gaps,
    }


# ── Top-level run ─────────────────────────────────────────────────────────────

def _latest_candidates_file() -> Path | None:
    files = sorted(CANDIDATES_OUTPUT_DIR.glob("candidates_*.json"))
    return files[-1] if files else None


def _latest_regime_file() -> Path | None:
    files = sorted(MARKET_REGIME_OUTPUT_DIR.glob("market_regime_*.json"))
    return files[-1] if files else None


def save_evidence_card(card: dict) -> str:
    EVIDENCE_CARDS_DIR.mkdir(parents=True, exist_ok=True)
    ticker_root = _ticker_root(card["ticker"])
    out_file = EVIDENCE_CARDS_DIR / f"{ticker_root}.json"
    out_file.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    return str(out_file)


def run(tickers: list[str] | None = None, verbose: bool = True) -> dict:
    """Build evidence cards for all (or specified) tickers in latest candidates file."""
    cand_file = _latest_candidates_file()
    if not cand_file:
        if verbose: print("  ✗  No candidates file found — run Phase B first")
        return {}

    cand_data = _load_json(cand_file)
    listed    = cand_data.get("listed_targets",
                cand_data.get("selected_for_phase_c",
                cand_data.get("candidates", [])))

    regime_file = _latest_regime_file()
    regime      = _load_json(regime_file) if regime_file else {}

    if tickers:
        listed = [c for c in listed if c["ticker"] in set(tickers)]

    if verbose:
        print(f"  Candidates file : {cand_file.name}")
        print(f"  Tickers to card : {len(listed)}")
        if regime_file:
            print(f"  Regime          : {regime.get('market_posture','?').upper()}")

    cards_built = []
    for i, c in enumerate(listed, 1):
        card = build_evidence_card(c, regime)
        path = save_evidence_card(card)
        cards_built.append(path)

        if verbose:
            gaps = card["data_gaps"]
            tag = f"({len(gaps)} gaps)" if gaps else "complete"
            sentiment = card["signals"]["sentiment_score"]
            flag = card["portfolio_flag"]
            print(f"  {i:3}/{len(listed)}  {c['ticker']:20s}  "
                  f"sentiment={sentiment:+.1f}  {flag:11s}  {tag}")

    if verbose:
        print(f"\n  Evidence cards saved → {EVIDENCE_CARDS_DIR}")
    return {
        "cards_count": len(cards_built),
        "cards_dir":   str(EVIDENCE_CARDS_DIR),
        "cards":       cards_built,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    single = None
    for arg in _sys.argv[1:]:
        if arg.startswith("--ticker="):
            single = [arg.split("=", 1)[1]]
        elif arg == "--ticker" and _sys.argv.index(arg) + 1 < len(_sys.argv):
            single = [_sys.argv[_sys.argv.index(arg) + 1]]

    print("=" * 60)
    print("  evidence_card_builder — standalone test")
    print("=" * 60)

    run(tickers=single, verbose=True)
