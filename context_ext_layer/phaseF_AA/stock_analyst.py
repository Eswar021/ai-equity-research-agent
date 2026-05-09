"""
context_ext_layer/phaseF_AA/stock_analyst.py  —  Phase F, Layer 6 (Analysis Agent)

For each evidence card produced by Phase E, an LLM call returns a structured
buy / watch / avoid recommendation with thesis, drivers, risks, conviction,
and cited source URLs.

Single-agent design for v1 — one LLM per ticker. Multi-agent ensemble (regime
+ fundamental + valuation + risk specialists) is the v2 evolution.

Inputs : output/{date}/phaseE/evidence_cards/*.json
Output : output/{date}/phaseF/analyst_views/{TICKER}.json
LLM log: output/{date}/phaseF/llm_analyst_logs/analyst_{date}.jsonl

Standalone test:
  python context_ext_layer/phaseF_AA/stock_analyst.py [--ticker BHEL.NS] [--provider openai]
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    EVIDENCE_CARDS_DIR, ANALYST_OUTPUT_DIR, ANALYST_LLM_LOGS_DIR,
)

_IST = timezone(timedelta(hours=5, minutes=30))

_log_lock = threading.Lock()   # guards JSONL log under concurrent writes


# ── Pydantic output schema ────────────────────────────────────────────────────

class StockAnalystView(BaseModel):
    recommendation: Literal["invest", "watch", "avoid"]
    conviction:     Literal["high", "medium", "low"]
    thesis:         str                                    # 2-3 sentences
    key_drivers:    list[str]                              # 3-5 bullets, must reference evidence-card data
    key_risks:      list[str]                              # 2-3 bullets
    time_horizon:   Literal["short", "medium", "long"]
    price_action:   Literal["buy_now", "wait_for_dip", "hold", "exit", "n/a"]
    sources_cited:  list[str]                              # URLs from evidence_card.signals.key_claims[*].url


# ── LLM prompt ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a disciplined Indian-equity research analyst. You
produce recommendations grounded ONLY in the evidence card provided — do not
invent facts, prices, or sources.

Decision rules:
- recommendation = "invest": requires positive sentiment_score AND decent
  fundamentals (revenue_cagr_5y_pct > 8 OR profit_cagr_5y_pct > 10) AND at
  least 2 distinct sources in signals.sources.
- recommendation = "avoid": sharply negative sentiment_score OR fundamental
  red flags (negative profit growth, very high P/E with declining ROE,
  regulatory action signals).
- recommendation = "watch": signal is real but conviction insufficient for a
  full invest call (low source count, mixed sentiment, or data gaps).

Conviction:
- conviction = "high": >=3 distinct sources AND alignment with regime
  favored_sectors AND no material data_gaps.
- conviction = "medium": some signal triangulation but missing one of: source
  diversity / regime alignment / fundamentals support.
- conviction = "low": single source, conflicting signals, or major data_gaps.
- If evidence_card.data_gaps is non-empty, lower conviction by one notch.

Time horizon:
- "short" = <3 months (event-driven: earnings beat/miss, M&A, regulatory)
- "medium" = 3-12 months (sector rotation, regime shift, multi-quarter trend)
- "long" = >12 months (structural growth, capex cycle, secular theme)

Price action:
- portfolio_flag = "held": choose "hold" or "exit" only.
- portfolio_flag in ("none", "watchlisted", "avoided"): choose "buy_now",
  "wait_for_dip", or "n/a" (avoid case).

Sources_cited:
- Include 1-3 actual URLs from evidence_card.signals.key_claims[*].url.
- Do NOT invent URLs. If no URLs are present, return an empty list.

Key drivers / risks:
- Must reference concrete data from the evidence card (a number, a claim, a
  filing, a peer comparison). Generic statements like "good company" are not
  acceptable.
"""

_HUMAN_PROMPT = """Evidence card for {ticker} ({company}):

PORTFOLIO FLAG: {portfolio_flag}{holding_note}

REGIME: {regime_posture}. Favored sectors: {favored}. Avoid: {avoid}.

SIGNALS:
  score: {score}, signal_count: {signal_count}, source_count: {source_count}
  sentiment_score: {sentiment_score}, signal_density: {signal_density}
  event_types: {event_types}
  sources: {sources}
  Key claims (with sources):
{key_claims_block}
  proxy_links (if any): {proxy_links}
  bulk_deal: {bulk_deal}

FUNDAMENTALS:
  price: {price}, sector: {sector}, market_cap: {market_cap}
  price_vs_52w_high_pct: {price_vs_52w_high_pct}, 1y_return_pct: {return_1y}, max_drawdown_1y_pct: {max_drawdown}
  P/E: {pe}, ROE: {roe}%, ROCE: {roce}%, dividend_yield: {div_yield}%
  revenue_cagr_5y: {rev_cagr}%, profit_cagr_5y: {profit_cagr}%, stock_price_cagr_5y: {price_cagr}%
  screener_pros: {pros}
  screener_cons: {cons}

PEER COMPARISON:
  peer_count: {peer_count}, peer_median_pe: {peer_median_pe}, peer_median_roe: {peer_median_roe}, peer_median_growth: {peer_median_growth}

ANALYST CONSENSUS:
  rating: {rating}, n_analysts: {n_analysts}, target_upside_pct: {target_upside_pct}
  buy: {buy_count}, hold: {hold_count}, sell: {sell_count}

RECENT MATERIAL FILINGS:
{filings_block}

RECENT CORPORATE ACTIONS:
{corp_actions_block}

DATA GAPS: {data_gaps}

Produce a structured StockAnalystView."""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human",  _HUMAN_PROMPT),
])


# ── LLM call logger ───────────────────────────────────────────────────────────

_log_file: Path | None = None

def _init_log() -> Path:
    global _log_file
    ANALYST_LLM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(_IST).strftime("%Y-%m-%d")
    _log_file = ANALYST_LLM_LOGS_DIR / f"analyst_{today}.jsonl"
    return _log_file


def _log_call(ticker: str, view: dict | None, error: str | None = None) -> None:
    if _log_file is None:
        return
    record = {
        "ts":     datetime.now(_IST).isoformat(),
        "ticker": ticker,
        "view":   view,
        "error":  error,
    }
    with _log_lock:
        with _log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Card → prompt-input dict ──────────────────────────────────────────────────

def _format_key_claims(card: dict) -> str:
    claims = card.get("signals", {}).get("key_claims", []) or []
    if not claims:
        return "    (none)"
    lines = []
    for c in claims:
        url = c.get("url", "") or "(no-url)"
        lines.append(
            f"    - [{c.get('source','?')}/{c.get('severity','?')}/"
            f"{c.get('sentiment','?')}] {c.get('key_claim','')[:140]}  ({url})"
        )
    return "\n".join(lines)


def _format_filings(card: dict) -> str:
    rows = card.get("recent_filings", []) or []
    if not rows:
        return "  (none)"
    return "\n".join(
        f"  - {r.get('date','')} [{r.get('type','')}] {r.get('subject','')[:120]} ({r.get('url','')})"
        for r in rows
    )


def _format_corp_actions(card: dict) -> str:
    rows = card.get("recent_corporate_actions", []) or []
    if not rows:
        return "  (none)"
    return "\n".join(
        f"  - {r.get('ex_date','')}: {r.get('purpose','')}"
        for r in rows
    )


def _holding_note(card: dict) -> str:
    h = card.get("holding")
    if not h:
        return ""
    return (f" (holding: qty={h.get('qty')}, avg_price={h.get('avg_price')}, "
            f"type={h.get('type','stock')})")


def _card_to_prompt_dict(card: dict) -> dict:
    sig  = card.get("signals", {})
    fund = card.get("fundamentals", {})
    peer = card.get("peer_metrics", {})
    cons = card.get("analyst_consensus", {})
    reg  = card.get("regime", {})

    return {
        "ticker":         card.get("ticker", ""),
        "company":        card.get("company", ""),
        "portfolio_flag": card.get("portfolio_flag", "none"),
        "holding_note":   _holding_note(card),

        "regime_posture": reg.get("posture", "unknown"),
        "favored":        reg.get("favored_sectors", []),
        "avoid":          reg.get("avoid_sectors", []),

        "score":            sig.get("score"),
        "signal_count":     sig.get("signal_count"),
        "source_count":     sig.get("source_count"),
        "sentiment_score":  sig.get("sentiment_score"),
        "signal_density":   sig.get("signal_density"),
        "event_types":      sig.get("event_types", []),
        "sources":          sig.get("sources", []),
        "key_claims_block": _format_key_claims(card),
        "proxy_links":      sig.get("proxy_links", []),
        "bulk_deal":        sig.get("bulk_deal"),

        "price":                   fund.get("price"),
        "sector":                  fund.get("sector"),
        "market_cap":              fund.get("market_cap"),
        "price_vs_52w_high_pct":   fund.get("price_vs_52w_high_pct"),
        "return_1y":               fund.get("1y_return_pct"),
        "max_drawdown":            fund.get("max_drawdown_1y_pct"),
        "pe":                      fund.get("stock_pe"),
        "roe":                     fund.get("roe_pct"),
        "roce":                    fund.get("roce_pct"),
        "div_yield":               fund.get("dividend_yield_pct"),
        "rev_cagr":                fund.get("revenue_cagr_5y_pct"),
        "profit_cagr":             fund.get("profit_cagr_5y_pct"),
        "price_cagr":              fund.get("stock_price_cagr_5y_pct"),
        "pros":                    fund.get("screener_pros", []),
        "cons":                    fund.get("screener_cons", []),

        "peer_count":         peer.get("peer_count"),
        "peer_median_pe":     peer.get("peer_median_pe"),
        "peer_median_roe":    peer.get("peer_median_roe"),
        "peer_median_growth": peer.get("peer_median_growth"),

        "rating":            cons.get("rating"),
        "n_analysts":        cons.get("n_analysts"),
        "target_upside_pct": cons.get("target_upside_pct"),
        "buy_count":         cons.get("buy_count"),
        "hold_count":        cons.get("hold_count"),
        "sell_count":        cons.get("sell_count"),

        "filings_block":      _format_filings(card),
        "corp_actions_block": _format_corp_actions(card),
        "data_gaps":          card.get("data_gaps", []),
    }


# ── Per-card LLM call ─────────────────────────────────────────────────────────

def analyze_card(card: dict, pipeline) -> dict:
    """One LLM call per evidence card. Returns analyst view dict (with provenance)."""
    ticker = card.get("ticker", "?")
    try:
        view = pipeline.invoke(_card_to_prompt_dict(card))
    except Exception as e:
        _log_call(ticker, None, error=str(e))
        return {"_error": str(e), "ticker": ticker}

    out = view.model_dump()
    _log_call(ticker, out)

    # Attach upstream context for traceability in the report layer
    out["ticker"]          = ticker
    out["company"]         = card.get("company", "")
    out["portfolio_flag"]  = card.get("portfolio_flag", "none")
    out["sector"]          = card.get("fundamentals", {}).get("sector", "")
    out["price"]           = card.get("fundamentals", {}).get("price")
    out["sentiment_score"] = card.get("signals", {}).get("sentiment_score", 0)
    out["signal_score"]    = card.get("signals", {}).get("final_score", 0)
    out["data_gaps"]       = card.get("data_gaps", [])
    out["generated_at"]    = datetime.now(_IST).isoformat()
    return out


def save_view(view: dict) -> str:
    ANALYST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ticker_root = view.get("ticker", "?").replace(".NS", "").replace(".BO", "")
    out_file = ANALYST_OUTPUT_DIR / f"{ticker_root}.json"
    out_file.write_text(json.dumps(view, ensure_ascii=False, indent=2))
    return str(out_file)


# ── Top-level run ─────────────────────────────────────────────────────────────

def run(
    tickers:     list[str] | None = None,
    provider:    str  = "openai",
    verbose:     bool = True,
    max_workers: int  = 10,
) -> dict:
    """Analyze every evidence card (or a filtered subset) and save the views."""
    if not EVIDENCE_CARDS_DIR.exists():
        if verbose: print(f"  ✗  No evidence cards dir at {EVIDENCE_CARDS_DIR} — run Phase E first")
        return {}

    card_files = sorted(EVIDENCE_CARDS_DIR.glob("*.json"))
    if not card_files:
        if verbose: print("  ✗  Evidence cards dir empty")
        return {}

    if tickers:
        wanted = {t.replace(".NS", "").replace(".BO", "") for t in tickers}
        card_files = [f for f in card_files if f.stem in wanted]

    log_path = _init_log()
    if verbose:
        print(f"  Analyst LLM log → {log_path}")
        print(f"  Cards to analyze: {len(card_files)}")

    from llm.llm_client import make_llm
    llm = make_llm(provider=provider, temperature=0.1)
    pipeline = _prompt | llm.with_structured_output(StockAnalystView)
    if verbose:
        print(f"  Provider: {llm.__class__.__name__}  Model: {getattr(llm,'model_name','N/A')}")
        print(f"  Running {max_workers} concurrent workers …\n")

    total = len(card_files)
    results_by_idx: list[dict | None] = [None] * total
    completed = 0

    def _worker(card_file: Path) -> dict:
        try:
            card = json.loads(card_file.read_text())
        except Exception as e:
            return {"_error": str(e), "ticker": card_file.stem}
        return analyze_card(card, pipeline)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_worker, cf): i
            for i, cf in enumerate(card_files)
        }
        for future in as_completed(future_to_idx):
            i    = future_to_idx[future]
            try:
                view = future.result()
            except Exception as e:
                view = {"_error": str(e), "ticker": card_files[i].stem}
            results_by_idx[i] = view
            completed += 1
            if verbose:
                if "_error" in view:
                    print(f"  {completed:3}/{total}  {view.get('ticker','?'):20s}  ✗  {view['_error']}")
                else:
                    print(f"  {completed:3}/{total}  {view['ticker']:20s}  "
                          f"{view['recommendation']:6s}  {view['conviction']:6s}  "
                          f"price_action={view['price_action']:13s}  "
                          f"thesis={view['thesis'][:50]}")

    # Save in original order; count results
    views: list[dict] = []
    failed = 0
    rec_counts = {"invest": 0, "watch": 0, "avoid": 0}

    for view in results_by_idx:
        if view is None:
            continue
        if "_error" in view:
            failed += 1
            continue
        save_view(view)
        rec_counts[view["recommendation"]] = rec_counts.get(view["recommendation"], 0) + 1
        views.append(view)

    if verbose:
        print(f"\n  Analyst views saved → {ANALYST_OUTPUT_DIR}")
        print(f"  Recommendations: invest={rec_counts['invest']}  "
              f"watch={rec_counts['watch']}  avoid={rec_counts['avoid']}  failed={failed}")

    return {
        "views_count":    len(views),
        "views_dir":      str(ANALYST_OUTPUT_DIR),
        "rec_counts":     rec_counts,
        "failed":         failed,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    provider = "openai"
    single   = None
    for arg in _sys.argv[1:]:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
        elif arg == "--provider" and _sys.argv.index(arg) + 1 < len(_sys.argv):
            provider = _sys.argv[_sys.argv.index(arg) + 1]
        elif arg.startswith("--ticker="):
            single = [arg.split("=", 1)[1]]
        elif arg == "--ticker" and _sys.argv.index(arg) + 1 < len(_sys.argv):
            single = [_sys.argv[_sys.argv.index(arg) + 1]]

    print("=" * 60)
    print("  stock_analyst — standalone test")
    print(f"  Provider: {provider}")
    print("=" * 60)

    run(tickers=single, provider=provider, verbose=True)
