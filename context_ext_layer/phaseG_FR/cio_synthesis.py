"""
context_ext_layer/phaseG_FR/cio_synthesis.py  —  CIO Synthesis (between Phase F and G)

Single LLM call that reads all Phase F analyst views together and produces a
holistic portfolio-level synthesis: ranked top picks, sector warnings, macro
coherence check, and a daily narrative.

Phase F analysts each see ONE stock. This layer sees ALL of them.

Input  : output/{date}/phaseF/analyst_views/*.json
Output : output/{date}/phaseG/cio_synthesis_{date}.json
Log    : output/{date}/phaseG/cio_log_{date}.jsonl

Standalone test:
  python context_ext_layer/phaseG_FR/cio_synthesis.py [--provider openai]
"""

import json
import threading
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    ANALYST_OUTPUT_DIR, MARKET_REGIME_OUTPUT_DIR, PHASE_G_DIR, PORTFOLIO_FILE,
)
from context_ext_layer.utils.portfolio import load_portfolio

_IST      = timezone(timedelta(hours=5, minutes=30))
_log_lock = threading.Lock()
_log_file: Path | None = None


# ── Pydantic schema ───────────────────────────────────────────────────────────

class TopPick(BaseModel):
    ticker:         str
    rank:           int
    recommendation: Literal["invest", "watch"]
    why_selected:   str   # must cite something specific — number, claim, sector alignment


class CIOSynthesis(BaseModel):
    top_picks:            list[TopPick]   # 3-5; watches allowed if near-term catalyst
    daily_narrative:      str             # 3-4 sentences: regime + themes + what to do
    sector_warnings:      list[str]       # specific alerts, not generic "diversify" advice
    portfolio_actions:    list[str]       # hold/exit/add for held tickers; [] if no portfolio
    macro_coherence_note: str             # does regime posture support the analyst consensus?


# ── LLM prompt ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a Chief Investment Officer reviewing today's Indian equity research.
Your analysts have already evaluated each stock individually. Your job is synthesis — not re-analysis.

Answer: given ALL of this together, what should an investor actually DO today?

Rules:
- top_picks: 3-5 names. May include a high-conviction "watch" if a near-term catalyst makes it
  immediately actionable (e.g. earnings in 3 days, SEBI ruling imminent). Do NOT simply sort by
  conviction score. Consider:
    * Regime alignment — favored-sector stocks rank higher
    * Theme de-duplication — two stocks for the same theme → pick the stronger proxy, flag the other
    * Sector concentration — if >40% of picks share a sector, that is a warning
    * Portfolio overlap — skip a buy if the user already holds a stock with the identical thesis
- why_selected: must cite something specific (a metric, a claim, a sector alignment). "Good
  fundamentals" or "strong conviction" alone is not acceptable.
- daily_narrative: 3-4 sentences. Connect regime posture → active themes → concrete action.
- sector_warnings: specific, not generic. Write "5 of 10 invests are Industrials (50%)" not "diversify".
- macro_coherence_note: if regime is cautious but majority of calls are bullish, call that out explicitly.
- portfolio_actions: only if portfolio holdings are present. Be direct — hold/exit/add with one-line reason."""

_HUMAN_PROMPT = """MARKET REGIME: {regime_posture}
Favored sectors : {favored}
Avoid sectors   : {avoid}
Macro snapshot  : FII net ₹{fii_net} cr  |  VIX {vix}  |  USD/INR {usd_inr}

PORTFOLIO: {portfolio_summary}

ANALYST VIEWS ({n_views} tickers):
{views_table}

INVEST-CALL SECTOR DISTRIBUTION:
{sector_dist}

Produce a CIOSynthesis."""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human",  _HUMAN_PROMPT),
])


# ── Input formatters ──────────────────────────────────────────────────────────

def _compress_views(views: list[dict]) -> str:
    header = (f"{'Ticker':<20} {'Sector':<18} {'Rec':<7} {'Conv':<7} "
              f"{'Action':<14} Thesis")
    sep    = "─" * 110
    lines  = [header, sep]
    for v in sorted(views, key=lambda x: x.get("recommendation", "z")):
        lines.append(
            f"{v.get('ticker',''):20s} {v.get('sector','?')[:17]:<18s} "
            f"{v.get('recommendation','?'):7s} {v.get('conviction','?'):7s} "
            f"{v.get('price_action','?'):14s} {v.get('thesis','')[:80]}"
        )
    return "\n".join(lines)


def _sector_distribution(views: list[dict]) -> str:
    invests = [v for v in views if v.get("recommendation") == "invest"]
    total   = len(invests)
    if not total:
        return "  (no invest calls)"
    counts = Counter(v.get("sector", "unknown") for v in invests)
    lines  = []
    for sector, n in counts.most_common():
        pct = round(n / total * 100)
        bar = "█" * (pct // 10)
        lines.append(f"  {sector[:25]:<25s}  {n:2d} / {total}  ({pct:2d}%)  {bar}")
    return "\n".join(lines)


def _portfolio_summary() -> str:
    if not PORTFOLIO_FILE.exists():
        return "(none — no portfolio.json provided)"
    p         = load_portfolio()
    holdings  = [h["ticker"] for h in p.get("holdings", [])]
    watchlist = p.get("watchlist", [])
    avoid     = p.get("avoid_list", [])
    parts     = []
    if holdings:  parts.append(f"Holds: {', '.join(holdings)}")
    if watchlist: parts.append(f"Watching: {', '.join(watchlist)}")
    if avoid:     parts.append(f"Avoids: {', '.join(avoid)}")
    return " | ".join(parts) if parts else "(empty portfolio)"


# ── Logger ────────────────────────────────────────────────────────────────────

def _init_log() -> Path:
    global _log_file
    PHASE_G_DIR.mkdir(parents=True, exist_ok=True)
    today     = datetime.now(_IST).strftime("%Y-%m-%d")
    _log_file = PHASE_G_DIR / f"cio_log_{today}.jsonl"
    return _log_file


def _log_call(result: dict | None, error: str | None = None) -> None:
    if _log_file is None:
        return
    record = {
        "ts":     datetime.now(_IST).isoformat(),
        "result": result,
        "error":  error,
    }
    with _log_lock:
        with _log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _latest(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


# ── Main run ──────────────────────────────────────────────────────────────────

def run(provider: str = "openai", verbose: bool = True) -> dict:
    """Single LLM call over all Phase F views. Returns path to cio_synthesis_{date}.json."""
    if not ANALYST_OUTPUT_DIR.exists():
        if verbose: print("  ✗  No analyst views dir — run Phase F first")
        return {}

    view_files = sorted(ANALYST_OUTPUT_DIR.glob("*.json"))
    views: list[dict] = []
    for f in view_files:
        v = _load_json(f)
        if v and "recommendation" in v:
            views.append(v)

    if not views:
        if verbose: print("  ✗  No valid analyst views found")
        return {}

    regime_file = _latest(MARKET_REGIME_OUTPUT_DIR, "market_regime_*.json")
    regime      = _load_json(regime_file) if regime_file else {}
    raw         = regime.get("raw_data", {}) or {}
    secs        = regime.get("sectors",  {}) or {}

    log_path = _init_log()
    if verbose:
        print(f"  CIO log  → {log_path}")
        print(f"  Views    : {len(views)} tickers  "
              f"(invest={sum(1 for v in views if v.get('recommendation')=='invest')}  "
              f"watch={sum(1 for v in views if v.get('recommendation')=='watch')}  "
              f"avoid={sum(1 for v in views if v.get('recommendation')=='avoid')})")
        print(f"  Regime   : {regime.get('market_posture', '?').upper()}")

    from llm.llm_client import make_llm
    llm      = make_llm(provider=provider, temperature=0.2)
    pipeline = _prompt | llm.with_structured_output(CIOSynthesis)

    if verbose:
        print(f"  Provider : {llm.__class__.__name__}  "
              f"Model: {getattr(llm, 'model_name', 'N/A')}\n")

    try:
        result = pipeline.invoke({
            "regime_posture":    regime.get("market_posture", "unknown").upper(),
            "favored":           ", ".join(secs.get("favored", [])) or "(none)",
            "avoid":             ", ".join(secs.get("avoid",   [])) or "(none)",
            "fii_net":           raw.get("fii_net_cr", "?"),
            "vix":               raw.get("vix_india",  "?"),
            "usd_inr":           raw.get("usd_inr",    "?"),
            "portfolio_summary": _portfolio_summary(),
            "n_views":           len(views),
            "views_table":       _compress_views(views),
            "sector_dist":       _sector_distribution(views),
        })
    except Exception as e:
        _log_call(None, error=str(e))
        if verbose: print(f"  ✗  CIO LLM call failed: {e}")
        return {"error": str(e)}

    out = result.model_dump()
    _log_call(out)

    if verbose:
        print(f"  Top picks ({len(out['top_picks'])}):")
        for p in out["top_picks"]:
            tag = f"[{p['recommendation']}]"
            print(f"    {p['rank']}. {p['ticker']:20s} {tag:9s}  {p['why_selected'][:75]}")
        if out["sector_warnings"]:
            print(f"\n  Sector warnings:")
            for w in out["sector_warnings"]:
                print(f"    ⚠  {w}")
        if out["portfolio_actions"]:
            print(f"\n  Portfolio actions:")
            for a in out["portfolio_actions"]:
                print(f"    →  {a}")
        print(f"\n  Macro: {out['macro_coherence_note'][:110]}")
        print(f"\n  Narrative: {out['daily_narrative'][:160]}")

    PHASE_G_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    out_file = PHASE_G_DIR / f"cio_synthesis_{today}.json"
    out_file.write_text(json.dumps(
        {"generated_at": datetime.now(_IST).isoformat(), **out},
        ensure_ascii=False, indent=2,
    ))

    if verbose:
        print(f"\n  CIO synthesis → {out_file.name}")

    return {"cio_file": str(out_file), "synthesis": out}


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    provider = "openai"
    for arg in _sys.argv[1:]:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]

    print("=" * 60)
    print("  cio_synthesis — standalone test")
    print(f"  Provider: {provider}")
    print("=" * 60 + "\n")

    result = run(provider=provider, verbose=True)
    if "error" in result:
        print(f"\n  ✗  {result['error']}")
    elif not result:
        print("\n  No output produced.")
